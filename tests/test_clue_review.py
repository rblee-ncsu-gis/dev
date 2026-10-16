import csv
import json
from pathlib import Path

import pytest

from asbuilt_matcher.clues import init_clues, add_clue, review_clue
from asbuilt_matcher.clue_review import write_review_bundle, apply_decisions, export_verified, collect_rows
from asbuilt_matcher.pdf_extract import file_sha256, write_json
from asbuilt_matcher.raster import prepare_rasters
from asbuilt_matcher.cli import main


@pytest.fixture
def registry(tmp_path):
    pdf = pytest.importorskip("pymupdf")
    source = tmp_path / "source.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=200, height=100)
        page.insert_text((20, 30), "ROAD NAME")
        doc.save(source)
    out = tmp_path / "raster"
    prepare_rasters(source, out, dpi=72, regions=[
        {"id": "road", "kind": "plan_view_labels", "page_number": 1, "bbox": [10, 10, 150, 50]}])
    registry = tmp_path / "clues.json"
    init_clues(out / "raster-manifest.json", registry)
    for text in ["Road, Name", "Unreadable", "Reject", "Pending"]:
        add_clue(registry, kind="street_name", text=text, page_number=1,
                 bbox=[20, 20, 100, 40], author="synthetic analyst")
    return registry


def decisions_for(registry, tmp_path):
    write_review_bundle([registry], tmp_path / "review")
    path = tmp_path / "review" / "decisions-01.json"
    return path, json.loads(path.read_text())


def test_bundle_includes_all_clues_and_crop_references(registry, tmp_path):
    result = write_review_bundle([registry], tmp_path / "bundle")
    assert result == {"clues": 4, "statuses": {"unverified": 4}}
    rows = json.loads((tmp_path / "bundle" / "review.json").read_text())["clues"]
    assert all(r["image_reference"].endswith("crop-road.png") for r in rows)
    assert all(r["source_pdf"] == "source.pdf" and r["page_number"] == 1 and r["image_sha256"] for r in rows)
    assert "Road, Name" in (tmp_path / "bundle" / "REVIEW.md").read_text()
    template = json.loads((tmp_path / "bundle" / "decisions-01.json").read_text())
    assert all(d["action"] is None for d in template["decisions"])


def test_verified_export_filters_and_preserves_history(registry, tmp_path):
    entries = json.loads(registry.read_text())["clues"]
    review_clue(registry, entries[0]["id"], author="reviewer", reason="checked crop",
                text="ROAD, NAME", status="verified")
    review_clue(registry, entries[1]["id"], author="reviewer", reason="too faint", status="unreadable")
    review_clue(registry, entries[2]["id"], author="reviewer", reason="consultant address", status="rejected")
    assert export_verified([registry], tmp_path / "export") == {"verified_clues": 1}
    data = json.loads((tmp_path / "export" / "verified-clues.json").read_text())
    row = data["clues"][0]
    assert row["original_text"] == "Road, Name" and row["text"] == "ROAD, NAME"
    assert row["history"][0]["before"]["text"] == "Road, Name"
    assert row["reviewer"] == "reviewer"
    with (tmp_path / "export" / "verified-clues.csv").open(encoding="utf-8-sig", newline="") as stream:
        csv_data = list(csv.DictReader(stream))
    assert csv_data[0]["text"] == row["text"]
    assert json.loads(csv_data[0]["history"]) == row["history"]


def test_atomic_apply_and_stale_template_rejected(registry, tmp_path):
    path, template = decisions_for(registry, tmp_path)
    template["decisions"][0].update(action="verified", author="reviewer", reason="read crop")
    template["decisions"][1].update(action="unreadable", author="reviewer", reason="faint")
    write_json(path, template)
    assert apply_decisions(registry, path) == {"applied": 2}
    data = json.loads(registry.read_text())["clues"]
    assert [c["verification_status"] for c in data] == ["verified", "unreadable", "unverified", "unverified"]
    saved = registry.read_bytes()
    with pytest.raises(ValueError, match="Stale"):
        apply_decisions(registry, path)
    assert registry.read_bytes() == saved


def test_invalid_second_decision_saves_nothing(registry, tmp_path):
    path, template = decisions_for(registry, tmp_path)
    template["decisions"][0].update(action="verified", author="reviewer", reason="read")
    template["decisions"][1].update(action="corrected", author="reviewer", reason="fix")
    write_json(path, template)
    saved = registry.read_bytes()
    with pytest.raises(ValueError, match="requires"):
        apply_decisions(registry, path)
    assert registry.read_bytes() == saved


def test_corrected_action_resets_verification(registry, tmp_path):
    clue = json.loads(registry.read_text())["clues"][0]
    review_clue(registry, clue["id"], author="reviewer", reason="read", status="verified")
    path, template = decisions_for(registry, tmp_path)
    template["decisions"][0].update(action="corrected", text="ROAD NAME", author="reviewer", reason="remove comma")
    write_json(path, template)
    apply_decisions(registry, path)
    updated = json.loads(registry.read_text())["clues"][0]
    assert updated["verification_status"] == "unverified"
    assert updated["verification"] is None
    assert updated["original_text"] == "Road, Name"
    assert len(updated["history"]) == 2


def test_export_rejects_tampered_source_and_missing_review(registry, tmp_path):
    data = json.loads(registry.read_text())
    clue = data["clues"][0]
    review_clue(registry, clue["id"], author="reviewer", reason="read", status="verified")
    source = Path(data["source"]["path"])
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="lacks valid evidence"):
        export_verified([registry], tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert "hash differs" in collect_rows([registry])[0]["evidence_issue"]


def test_no_verified_clues_produces_valid_empty_export(registry, tmp_path):
    assert export_verified([registry], tmp_path / "out") == {"verified_clues": 0}
    assert json.loads((tmp_path / "out" / "verified-clues.json").read_text())["clues"] == []


def test_verified_targets_render_with_recorded_hash(registry, tmp_path):
    clue = json.loads(registry.read_text())["clues"][0]
    review_clue(registry, clue["id"], author="reviewer", reason="image checked", status="verified")
    export_verified([registry], tmp_path / "out", render_targets=True)
    row = json.loads((tmp_path / "out" / "verified-clues.json").read_text())["clues"][0]
    assert file_sha256(row["target_image_reference"]) == row["target_image_sha256"]
    assert row["target_image"]["bbox"] == clue["bbox"]


def test_missing_image_and_duplicate_inputs_fail_export(registry, tmp_path):
    row = collect_rows([registry])[0]
    review_clue(registry, row["clue_id"], author="reviewer", reason="read", status="verified")
    Path(row["image_reference"]).unlink()
    with pytest.raises(ValueError):
        export_verified([registry], tmp_path / "out")
    with pytest.raises(ValueError, match="Duplicate"):
        write_review_bundle([registry, registry], tmp_path / "bundle")


def test_cli_review_and_export(registry, tmp_path, capsys):
    bundle = tmp_path / "bundle"
    assert main(["clues-manifest", str(registry), "--output", str(bundle)]) == 0
    assert main(["clues-apply", str(registry), str(bundle / "decisions-01.json")]) == 0
    clue_id = json.loads(registry.read_text())["clues"][0]["id"]
    assert main(["clues-review", str(registry), clue_id, "--status", "unreadable",
                 "--author", "reviewer", "--reason", "faint"]) == 0
    assert main(["clues-export", str(registry), "--output", str(tmp_path / "export")]) == 0


def test_ai_review_attribution_is_structured(registry, tmp_path):
    clue = json.loads(registry.read_text())["clues"][0]
    review_clue(registry, clue["id"], author="Codex", reviewer_type="ai", reason="visual review", status="verified")
    export_verified([registry], tmp_path / "out")
    row = json.loads((tmp_path / "out" / "verified-clues.json").read_text())["clues"][0]
    assert row["reviewer_type"] == "ai"
    assert row["history"][-1]["after"]["verification"]["scope"] == "transcription"


def test_analyst_only_export_requires_explicit_independent_human(registry, tmp_path):
    clue = json.loads(registry.read_text())["clues"][0]
    review_clue(registry, clue["id"], author="Codex", reviewer_type="ai", reason="visual review", status="verified")
    assert export_verified([registry], tmp_path / "ai", analyst_only=True) == {"verified_clues": 0}
    with pytest.raises(ValueError, match="human"):
        review_clue(registry, clue["id"], author="Codex", reviewer_type="ai", reason="not human", status="verified", independent=True)
    review_clue(registry, clue["id"], author="Synthetic independent analyst", reviewer_type="human",
                reason="independent test acceptance", status="verified", independent=True)
    assert export_verified([registry], tmp_path / "human", analyst_only=True) == {"verified_clues": 1}
