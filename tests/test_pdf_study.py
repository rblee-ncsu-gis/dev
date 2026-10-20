"""Study regressions: real samples when present; synthetic PDFs only for missing cases.

Synthetic cases are test fixtures, never included in Phase 3A observation totals.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from asbuilt_matcher.cli import main
from asbuilt_matcher.pdf_classify import classify_evidence, criteria_with_defaults, rectangle_union_area, text_candidates
from asbuilt_matcher.pdf_extract import file_sha256
from asbuilt_matcher.pdf_inspect import geospatial_evidence, inspect_page
from asbuilt_matcher.pdf_study import apply_study_review, run_study


@pytest.fixture
def pdf():
    return pytest.importorskip("pymupdf")


def evidence(**changes):
    return {"raster_coverage": 0, "non_border_vector_paths": 0, "native_nonspace_characters": 0,
            "suspect_character_fraction": 0, "annotation_count": 0, "geospatial_candidates": 0} | changes


@pytest.mark.parametrize("values,primary", [
    ({"raster_coverage": 1}, "predominantly_raster"),
    ({"raster_coverage": 1, "native_nonspace_characters": 800}, "predominantly_raster"),
    ({"raster_coverage": 1, "non_border_vector_paths": 1}, "predominantly_raster"),
    ({"raster_coverage": .01, "non_border_vector_paths": 100}, "predominantly_vector"),
    ({"raster_coverage": .3, "non_border_vector_paths": 100}, "hybrid_raster_vector"),
    ({"native_nonspace_characters": 800}, "text_rich_digital"),
    ({}, "indeterminate"),
    ({"raster_coverage": .01}, "indeterminate"),
])
def test_missing_content_combinations(values, primary):
    result = classify_evidence(evidence(**values))
    assert result["primary_class"] == primary
    if primary == "predominantly_raster":
        assert "text_rich_digital" not in result["labels"]


def test_classification_overlaps_and_configurable_boundary():
    row = evidence(raster_coverage=.2, non_border_vector_paths=21, native_nonspace_characters=400,
                   annotation_count=1, geospatial_candidates=1)
    result = classify_evidence(row)
    assert set(result["labels"]) == {"hybrid_raster_vector", "separate_annotations", "possible_geospatial"}
    assert classify_evidence(row, {"hybrid_raster_coverage": .25})["primary_class"] == "predominantly_vector"
    assert "text_rich_digital" in classify_evidence(row, {"hybrid_raster_coverage": .25})["labels"]


@pytest.mark.parametrize("setting", [{"unknown": 1}, {"raster_dominance": float("nan")},
                                     {"incidental_image_coverage": .2}, {"substantial_vector_paths": 0},
                                     {"raster_dominance": 2}, {"text_rich_characters": True}])
def test_invalid_criteria(setting):
    with pytest.raises(ValueError):
        criteria_with_defaults(setting)


def test_overlapping_tiled_and_offpage_boxes_are_not_double_counted():
    assert rectangle_union_area([[0, 0, 70, 100], [30, 0, 120, 100], [10, 10, 20, 20]], [0, 0, 100, 100]) == 10000
    assert rectangle_union_area([[0, 0, 40, 100], [60, 0, 100, 100]], [0, 0, 100, 100]) == 8000


def test_multiple_wrapped_scale_statements_do_not_calibrate_page():
    lines = [{"text": 'HORIZ 1" = 40\'', "bbox": [10, 10, 100, 20]},
             {"text": 'VERT 1 INCH =', "bbox": [10, 30, 100, 40]},
             {"text": '4 FEET', "bbox": [10, 40, 100, 50]},
             {"text": 'LOCATION MAP NOT TO SCALE', "bbox": [10, 60, 100, 70]},
             {"text": 'DETAIL 1:500 STATION 78+75', "bbox": [10, 80, 150, 90]}]
    result = text_candidates(lines, [0, 0, 300, 200])
    assert len(result["scale_statements"]) == 4
    assert result["scale_statements"][1]["bbox"] == [10, 30, 100, 50]
    assert all(not s["effective_page_scale_verified"] for s in result["scale_statements"])
    assert result["effective_page_scale"] is None and result["multiple_statements"]
    assert any(e["kind"] == "station" for e in result["entities"])


def _fixture(tmp_path, pdf):
    """Missing from actual study: searchable scan, true hybrid, text-only, empty page."""
    source = tmp_path / "inputs"
    source.mkdir()
    image = pdf.Pixmap(pdf.csRGB, pdf.IRect(0, 0, 40, 40), False)
    image.clear_with(170)
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_image(page.rect, pixmap=image)
        page.insert_text((10, 20), "SYNTHETIC searchable scan road text", render_mode=3)
        page.set_rotation(90)
        page = doc.new_page(width=300, height=200)
        page.insert_image(pdf.Rect(0, 0, 120, 200), pixmap=image)
        for y in range(10, 100, 2):
            page.draw_line((130, y), (280, y), color=(1, 0, 0))
        page.insert_text((130, 120), '1" = 40\'')
        page = doc.new_page(width=300, height=200)
        for y in range(20, 181, 20):
            page.insert_text((10, y), "SYNTHETIC NATIVE CONSTRUCTION NOTES")
        doc.new_page(width=300, height=200)
        doc.set_metadata({"producer": "AutoCAD - deliberately misleading for the scanned page"})
        doc.save(source / "synthetic.pdf")
    (source / "corrupt.pdf").write_bytes(b"not a PDF")
    (source / "drawing.dwg").write_bytes(b"unsupported synthetic CAD")
    config = tmp_path / "sample.json"
    config.write_text(json.dumps({"input_directory": "inputs", "prior_pilot_files": ["synthetic.pdf"], "max_preview_pixels": 10000}), encoding="utf-8")
    return source, config


def test_missing_cases_batch_reports_errors_provenance_and_preserves_sources(tmp_path, pdf):
    source, config = _fixture(tmp_path, pdf)
    before = {p.name: file_sha256(p) for p in source.iterdir()}
    output = tmp_path / "study"
    result = run_study(config, output)
    assert result["status"] == "partial"
    assert len(result["documents"]) == 2 and result["summary"]["pages"] == 4
    assert result["classification_accuracy"] is None
    assert result["cohorts"]["prior_pilot_comparison"]["pages"] == 4
    assert result["non_pdf_inputs"][0]["status"] == "not_inspected_non_pdf"
    assert result["errors"] and result["documents"][0]["page_count"] is None
    pages = result["documents"][1]["pages"]
    assert [p["classification"]["primary_class"] for p in pages] == ["predominantly_raster", "hybrid_raster_vector", "text_rich_digital", "indeterminate"]
    assert pages[0]["rotation"] == 90 and pages[0]["dimensions"]["width_points"] == 300
    assert pages[0]["text"]["render_character_counts"]["invisible"] > 0
    assert pages[1]["vectors"]["red_color_path_indices"]
    assert pages[1]["candidates"]["effective_page_scale"] is None
    for p in pages:
        assert p["preview"]["width"] * p["preview"]["height"] <= 10000
        assert p["preview"]["includes_annotations"]
        assert p["source_sha256"] == result["documents"][1]["sha256"]
        assert json.loads((output / p["directory"] / "page.json").read_text())["page_id"] == p["page_id"]
    assert before == {p.name: file_sha256(p) for p in source.iterdir()}
    assert json.loads((output / "inspection.json").read_text()) == result
    for artifact in ["documents.csv", "pages.csv", "native-text.csv", "vectors.csv", "scales.csv", "annotations.csv", "raster-hybrid.csv", "registration-readiness.csv", "REVIEW.html", "ASSESSMENT.md", "classification-review.csv"]:
        assert (output / artifact).stat().st_size > 0
    assert (output / "REVIEW.html").read_text().count('<article data-page=') == 4
    with pytest.raises(FileExistsError):
        run_study(config, output)


@pytest.mark.parametrize("variant", ["empty", "encrypted", "disguised"])
def test_empty_encrypted_and_nonpdf_extension(tmp_path, pdf, variant):
    source = tmp_path / "inputs"
    source.mkdir()
    if variant == "encrypted":
        with pdf.open() as doc:
            doc.new_page()
            doc.save(source / "encrypted.pdf", encryption=pdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="synthetic")
    elif variant == "disguised":
        (source / "not-really.pdf").write_text("<html>unsupported non-PDF</html>")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"input_directory": "inputs"}))
    result = run_study(config, tmp_path / "out")
    assert result["status"] == ("empty" if variant == "empty" else "partial")
    if variant == "encrypted":
        assert result["documents"][0]["needs_password"]
        assert result["documents"][0]["source_unchanged"]


def test_failed_extraction_is_indeterminate_not_silently_vector_free(tmp_path, pdf):
    with pdf.open() as doc:
        doc.new_page()
        with patch("asbuilt_matcher.pdf_inspect.native_text", side_effect=RuntimeError("synthetic failure")):
            result = inspect_page(doc, 0, tmp_path, {"preview_dpi": 72, "max_preview_pixels": 10000}, None)
    assert result["status"] == "partial"
    assert result["classification"]["primary_class"] == "indeterminate"
    assert result["errors"][0]["stage"] == "native_text"


def test_synthetic_geospatial_measure_and_nongeographic_viewport(tmp_path, pdf):
    # No actual representative file has this missing positive geospatial structure.
    with pdf.open() as doc:
        page = doc.new_page()
        viewport = doc.get_new_xref()
        doc.update_object(viewport, '<</Type /Viewport /BBox [0 0 100 100]>>')
        doc.xref_set_key(page.xref, "VP", f"[{viewport} 0 R]")
        assert not geospatial_evidence(doc, page)["candidates"]
        measure = doc.get_new_xref()
        doc.update_object(measure, '<</Type /Measure /Subtype /GEO /GPTS [0 0 0 1 1 1 1 0] /LPTS [0 0 0 1 1 1 1 0] /GCS << /Type /GEOGCS /EPSG 4326 >> >>')
        doc.xref_set_key(viewport, "Measure", f"{measure} 0 R")
        result = geospatial_evidence(doc, page)
        assert result["candidates"] and not result["confirmed"]
        assert not result["candidates"][0]["declared_crs_verified"]


@pytest.mark.parametrize("name,index,paths,chars,annotations", [
    ("Calabash Lakes Redev Plans Sheet 8.pdf", 0, 0, 0, 9),
    ("Calabash Lakes_Asbuilt_Randy Ward PLS_08192016.pdf", 0, 4963, 0, 6),
    ("31725.500 2026-08-19 BC W&S closeout.pdf", 22, 18798, 500, 0),
])
def test_actual_representative_annotation_and_native_content(tmp_path, pdf, name, index, paths, chars, annotations):
    source = Path(__file__).resolve().parents[1] / "src/pdf" / name
    if not source.is_file():
        pytest.skip("Analyst-supplied real PDF unavailable; not replaced with a synthetic observation")
    before = file_sha256(source)
    with pdf.open(source) as doc:
        row = inspect_page(doc, index, tmp_path, {"preview_dpi": 40, "max_preview_pixels": 40000}, None)
    assert row["status"] == "ok"
    assert row["vectors"]["path_count"] == paths
    assert row["text"]["characters"] == chars
    assert len(row["annotations"]) == annotations
    assert row["preview"]["includes_annotations"]
    if annotations:
        assert row["annotation_separation"]["composite_vector_paths"] > paths
        if paths:
            # The small bitmap belongs to the stamp appearance, not the base plan.
            assert row["composite_images"]["occurrence_count"] == 1
            assert row["images"]["occurrence_count"] == 0
    if chars:
        assert row["candidates"]["multiple_statements"]
        assert any(s["text"] == "1 INCH = 60 FEET" for s in row["candidates"]["scale_statements"])
    assert file_sha256(source) == before


def _review_setup(tmp_path, pdf):
    _, config = _fixture(tmp_path, pdf)
    out = tmp_path / "study"
    run_study(config, out)
    decision = json.loads((out / "classification-decisions.template.json").read_text())
    decision.update(reviewer="Analyst", reviewer_type="human", independent=True)
    decision["decisions"][0].update(action="confirm", reason="Independent inspection of original source")
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(decision))
    return out / "inspection.json", path, decision


def test_independent_review_new_snapshot_and_complete_correction_history(tmp_path, pdf):
    inspection, path, decision = _review_setup(tmp_path, pdf)
    before = file_sha256(inspection)
    first = tmp_path / "review1"
    result = apply_study_review(inspection, path, first)
    assert result["independently_accepted_pages"] == 1
    pid = decision["decisions"][0]["page_id"]
    decision["parent_snapshot_sha256"] = file_sha256(first / "classification-review.json")
    decision["decisions"][0].update(action="reject", reason="Conflicting source evidence; revisit")
    path.write_text(json.dumps(decision))
    second = apply_study_review(first / "classification-review.json", path, tmp_path / "review2")
    assert second["independently_accepted_pages"] == 0
    assert len(second["reviews"][pid]["history"]) == 2
    assert second["reviews"][pid]["history"][0]["action"] == "confirm"
    assert file_sha256(inspection) == before
    assert second["classification_accuracy"] is None


@pytest.mark.parametrize("change", ["ai", "hash", "duplicate", "label", "confirm_changed", "missing_reason", "self_acceptance"])
def test_review_rejects_invalid_or_nonindependent_acceptance(tmp_path, pdf, change):
    inspection, path, decision = _review_setup(tmp_path, pdf)
    entry = decision["decisions"][0]
    if change == "ai":
        decision.update(reviewer_type="ai", independent=False)
    elif change == "hash":
        decision["inspection_sha256"] = "0" * 64
    elif change == "duplicate":
        decision["decisions"].append(dict(entry))
    elif change == "label":
        entry["labels"] = ["invented"]
    elif change == "confirm_changed":
        entry.update(primary_class="indeterminate", labels=["indeterminate"])
    elif change == "missing_reason":
        entry["reason"] = ""
    elif change == "self_acceptance":
        decision["reviewer"] = "pdf-study-heuristic-v1"
    path.write_text(json.dumps(decision))
    if change == "ai":
        result = apply_study_review(inspection, path, tmp_path / "review")
        assert result["independently_accepted_pages"] == 0
        assert result["reviews"][entry["page_id"]]["history"]
    else:
        with pytest.raises(ValueError):
            apply_study_review(inspection, path, tmp_path / "review")
        assert not (tmp_path / "review").exists()


def test_cli_and_configuration_preflight(tmp_path, pdf, capsys):
    _, config = _fixture(tmp_path, pdf)
    assert main(["pdf-study", str(config), "--output", str(tmp_path / "out")]) == 1
    assert json.loads(capsys.readouterr().out)["documents"] == 2
    data = json.loads(config.read_text())
    data["input_directory"] = "missing"
    config.write_text(json.dumps(data))
    with pytest.raises(NotADirectoryError, match="input_directory"):
        run_study(config, tmp_path / "missing-out")
    assert not (tmp_path / "missing-out").exists()


@pytest.mark.parametrize("target", ["pdf", "preview", "native_text"])
def test_review_checks_original_source_and_displayed_evidence(tmp_path, pdf, target):
    inspection, path, decision = _review_setup(tmp_path, pdf)
    base = json.loads(inspection.read_text())
    page = base["documents"][1]["pages"][0]
    if target == "pdf":
        evidence_path = Path(base["input_directory"]) / "synthetic.pdf"
    else:
        evidence_path = inspection.parent / page["directory"] / ("composite.png" if target == "preview" else "native-text.txt")
    evidence_path.write_bytes(evidence_path.read_bytes() + b"synthetic tamper")
    with pytest.raises(ValueError, match="evidence changed"):
        apply_study_review(inspection, path, tmp_path / "review")
    assert not (tmp_path / "review").exists()


def test_page_failure_and_document_failure_leave_inventory_records(tmp_path, pdf):
    _, config = _fixture(tmp_path, pdf)
    with patch("asbuilt_matcher.pdf_inspect.inspect_page", side_effect=RuntimeError("synthetic page failure")):
        result = run_study(config, tmp_path / "pages-fail")
    assert result["status"] == "partial" and len(result["documents"][1]["pages"]) == 4
    assert result["summary"]["overlapping_categories"]["indeterminate"]["pages"] == 4
    with patch("asbuilt_matcher.pdf_study.inspect_document", side_effect=OSError("synthetic document failure")):
        result = run_study(config, tmp_path / "docs-fail")
    assert len(result["documents"]) == 2 and result["summary"]["pages"] == 0
    assert len(result["errors"]) == 2


def test_review_cli_and_overwrite_refusal(tmp_path, pdf, capsys):
    inspection, path, _ = _review_setup(tmp_path, pdf)
    assert main(["pdf-study-review", str(inspection), str(path), "--output", str(tmp_path / "review")]) == 0
    assert json.loads(capsys.readouterr().out)["independently_accepted_pages"] == 1
    assert main(["pdf-study-review", str(inspection), str(path), "--output", str(tmp_path / "review")]) == 1
