from copy import deepcopy
import csv
import json
from pathlib import Path

import pytest

from asbuilt_matcher.cli import main
from asbuilt_matcher.geo_eval import evaluate_localization
from asbuilt_matcher.geo_reference import import_references, load_references, read_json
from asbuilt_matcher.geo_report import localize
from asbuilt_matcher.geolocate import locate_documents

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/phase2b"


@pytest.fixture
def catalog():
    return load_references(EXAMPLE / "reference-config.json")


@pytest.fixture
def clues():
    return read_json(EXAMPLE / "accepted-clues.json")


def row(clues, kind, text, clue_id):
    result = deepcopy(clues["clues"][0])
    result.update(clue_id=clue_id, kind=kind, text=text, original_text=text)
    return result


def test_two_roads_and_subdivision_prioritize_known_synthetic_area(clues, catalog):
    run = locate_documents(clues, catalog)
    drawing = run["drawings"][0]
    assert drawing["status"] == "proposed_area"
    best = drawing["candidates"][0]
    assert best["match_type"] == "intersection_neighborhood"
    assert {f["native_id"] for f in best["supporting_features"]} == {"A-PINE", "A-OAK", "AREA-A"}
    assert best["intersection"]["reference_point"] == pytest.approx([-78.2,34.05])
    assert best["analyst_review_status"] == "pending"
    assert best["evidence"][0]["points"] > 0
    assert locate_documents(clues,catalog) == run
    reverse = deepcopy(catalog)
    reverse["features"].reverse()
    assert locate_documents(clues,reverse) == run


def test_equal_crossings_remain_ambiguous_and_single_street_insufficient(clues,catalog):
    clues["clues"] = clues["clues"][:2]
    clues["clues"][0]["text"] = "SYNTHETIC PINE ROAD"
    run = locate_documents(clues,catalog)
    assert run["drawings"][0]["status"] == "ambiguous"
    top = run["drawings"][0]["candidates"][:2]
    assert top[0]["score"] == top[1]["score"]
    clues["clues"] = clues["clues"][:1]
    assert locate_documents(clues,catalog)["drawings"][0]["status"] == "insufficient_evidence"


def test_unsupported_context_is_not_turned_into_roads_and_missing_names_abstain(clues,catalog):
    clues["clues"] = [row(clues,"landmark","SYNTHETIC PINE ROAD","landmark"),row(clues,"project_name","SYNTHETIC ALPHA ESTATES","project")]
    d = locate_documents(clues,catalog)["drawings"][0]
    assert not d["candidates"] and len(d["context_clues"]) == 2
    clues["clues"] = [row(clues,"street_name","UNKNOWN UNRELATED BOULEVARD","missing")]
    d = locate_documents(clues,catalog)["drawings"][0]
    assert d["status"] == "insufficient_evidence" and not d["candidates"]


def test_ai_not_reapproved_and_existing_acceptance_not_mutated(clues,catalog):
    before = deepcopy(clues)
    clues["clues"][0]["reviewer_type"] = "ai"
    expected = deepcopy(clues)
    run = locate_documents(clues,catalog)
    assert run["excluded_clues"] == [{"clue_id":"synthetic-road-1","reason":"not_independently_accepted"}]
    assert clues == expected
    assert before["clues"][1] == run["drawings"][0]["accepted_clues"][0]


def test_repeated_clue_and_reference_alias_dont_inflate_support(clues,catalog):
    one = [clues["clues"][0]]
    original = locate_documents({"clues":one},catalog)["drawings"][0]
    duplicate = deepcopy(one[0]); duplicate["clue_id"] = "repeat"
    repeated = locate_documents({"clues":one+[duplicate]},catalog)["drawings"][0]
    assert [c["score"] for c in original["candidates"]] == [c["score"] for c in repeated["candidates"]]
    aliases = deepcopy(catalog)
    for f in aliases["features"]:
        if f["kind"] == "roads" and "PINE" in str(f["native_id"]):
            f["aliases"].append("SYNTHETIC NC 211")
    second = row(clues,"street_name","SYNTHETIC NC 211","route-alias")
    d = locate_documents({"clues":one+[second]},aliases)["drawings"][0]
    assert d["status"] == "insufficient_evidence"
    assert all(not c["intersection"] for c in d["candidates"])


def test_fuzzy_match_preserves_original_and_conflicts(clues,catalog):
    clues["clues"][0]["text"] = "SYNTHETIC PINF ROAD"
    d = locate_documents(clues,catalog)["drawings"][0]
    e = next(e for e in d["candidates"][0]["evidence"] if e["kind"] == "street_name" and "PINF" in e["text"])
    assert e["best_match_type"] == "approximate"
    assert e["text"] == "SYNTHETIC PINF ROAD"
    other = next(c for c in d["candidates"] if "B-PINE" in [f["native_id"] for f in c["supporting_features"]])
    assert any(c["kind"] == "subdivision_name" for c in other["conflicts"])


def test_parcel_lot_same_feature_and_numeric_ids_not_fuzzy(clues,catalog):
    parcel = row(clues,"parcel_number","PX-001","parcel")
    lot = row(clues,"lot_number","Lot 012","lot")
    d = locate_documents({"clues":[parcel,lot]},catalog)["drawings"][0]
    assert d["status"] == "proposed_area"
    assert {f["native_id"] for f in d["candidates"][0]["supporting_features"]} == {"PARCEL-A"}
    lot["text"] = "013"
    d = locate_documents({"clues":[parcel,lot]},catalog)["drawings"][0]
    # A nearby but different parcel's lot cannot corroborate PX-001.
    best = d["candidates"][0]
    assert not any(e["kind"] == "lot_number" for e in best["evidence"])
    assert best["conflicts"]
    assert d["status"] == "ambiguous"
    parcel["text"] = "PX001"
    d = locate_documents({"clues":[parcel]},catalog)["drawings"][0]
    assert not d["candidates"]


def test_different_exported_levels_do_not_generate_intersection_bonus(clues,catalog):
    for feature in catalog["features"]:
        if feature["kind"] == "roads" and "OAK" in feature["native_id"]:
            feature["values"]["level"] = 1
    d = locate_documents(clues,catalog)["drawings"][0]
    assert all(c["intersection"] is None for c in d["candidates"])


def test_caps_and_partial_references_prevent_definitive_result(clues,catalog):
    d = locate_documents(clues,catalog,settings={"max_candidates":1})["drawings"][0]
    assert d["status"] == "ambiguous" and d["diagnostics"]["search_truncated"]
    d = locate_documents(clues,catalog,settings={"max_matches_per_clue":1})["drawings"][0]
    assert d["diagnostics"]["broad_clues"]
    assert d["status"] in {"ambiguous","insufficient_evidence"}
    catalog["status"] = "partial"
    assert locate_documents(clues,catalog)["drawings"][0]["status"] == "ambiguous"


def test_cross_sheet_uses_actual_labels_not_sequence_and_does_not_pool(clues):
    second = deepcopy(clues["clues"][0])
    second.update(clue_id="other",source_pdf="unrelated-name.pdf",document_sha256="b"*64)
    clues["clues"].append(second)
    run = locate_documents(clues)
    assert len(run["drawings"]) == 2
    assert all(d["status"] == "awaiting_reference_data" for d in run["drawings"])
    assert run["cross_sheet"][0]["shared_clues"][0]["kind"] == "street_name"
    second["text"] = "DIFFERENT ROAD"
    assert not locate_documents(clues)["cross_sheet"][0]["shared_clues"]


@pytest.mark.parametrize("settings", [{"typo":1},{"fuzzy_threshold":1.1},{"spatial_tolerance_m":float('nan')},{"max_candidates":1.5}])
def test_invalid_settings_rejected(clues,catalog,settings):
    with pytest.raises(ValueError):
        locate_documents(clues,catalog,settings=settings)


def test_cli_reports_snapshots_and_evaluation_workflow(tmp_path):
    imported = tmp_path / "reference"
    output = tmp_path / "run"
    assert main(["geo-import",str(EXAMPLE/"reference-config.json"),"--output",str(imported)]) == 0
    assert main(["localize",str(EXAMPLE/"accepted-clues.json"),"--references",str(imported/"references.json"),"--output",str(output)]) == 0
    assert (output/"clues-input.json").read_bytes() == (EXAMPLE/"accepted-clues.json").read_bytes()
    html = (output/"REVIEW.html").read_text(encoding="utf-8")
    assert "<svg" in html and "probabilities" in html and "https://" not in html
    run = read_json(output/"localization.json")
    with (output/"candidates.csv").open(encoding="utf-8-sig",newline="") as f:
        assert len(list(csv.DictReader(f))) == len(run["drawings"][0]["candidates"])
    review = read_json(output/"evaluation-template.json")
    review_path = tmp_path/"review.json"
    review_path.write_text(json.dumps(review),encoding="utf-8")
    pending = evaluate_localization(output/"localization.json",review_path,tmp_path/"pending")
    assert pending["summary"]["reviewed_drawings"] == 0
    assert pending["summary"]["candidate_recall"] is None
    r = review["reviews"][0]
    r.update(reviewer="Synthetic independent evaluator",reviewer_type="human",independent_review=True,
             reviewed_at="2026-10-16T00:00:00Z",reason="Fabricated ground truth area Alpha",truth_status="localizable",
             correct_areas=[{"bbox":[-78.206,34.044,-78.194,34.056],"crs":"EPSG:4326","source":"Independent synthetic area A fixture"}],complete_candidate_review=True)
    for decision,candidate in zip(r["candidate_decisions"],run["drawings"][0]["candidates"]):
        decision["decision"] = "correct" if "AREA-A" in [f["native_id"] for f in candidate["supporting_features"]] else "false_match"
    review_path.write_text(json.dumps(review),encoding="utf-8")
    assert main(["localization-evaluate",str(output/"localization.json"),str(review_path),"--output",str(tmp_path/"evaluated")]) == 0
    summary = read_json(tmp_path/"evaluated/evaluation.json")["summary"]
    assert summary["top_k_recall"]["1"] == 1 and summary["false_geographic_matches"] >= 1
    assert main(["localize",str(EXAMPLE/"accepted-clues.json"),"--output",str(output)]) == 1
    review["localization_sha256"] = "wrong"
    review_path.write_text(json.dumps(review),encoding="utf-8")
    with pytest.raises(ValueError,match="hash"):
        evaluate_localization(output/"localization.json",review_path,tmp_path/"bad")


def test_evaluation_counts_ambiguity_insufficiency_false_areas_and_misses(tmp_path,clues):
    accepted = []
    for index, rows in enumerate([clues["clues"][:3], clues["clues"][:2], clues["clues"][:1], clues["clues"][:1]]):
        for source in rows:
            c = deepcopy(source)
            c.update(clue_id=f"{index}-{source['clue_id']}",document_sha256=str(index+1)*64,source_pdf=f"SYNTHETIC-{index}.pdf")
            if index in {1,2} and c["kind"] == "street_name" and "Pine" in c["text"]:
                c["text"] = "SYNTHETIC PINE ROAD"
            if index == 3:
                c["text"] = "UNKNOWN DIFFERENT STREET"
            accepted.append(c)
    export = tmp_path/"accepted.json"
    export.write_text(json.dumps({"clues":accepted}),encoding="utf-8")
    import_references(EXAMPLE/"reference-config.json",tmp_path/"references")
    run = localize(export,tmp_path/"run",references_path=tmp_path/"references/references.json")
    review = read_json(tmp_path/"run/evaluation-template.json")
    for r,d in zip(review["reviews"],run["drawings"]):
        r.update(reviewer="Synthetic test reviewer",reviewer_type="human",independent_review=True,
                 reviewed_at="2026-10-16T00:00:00Z",reason="Fictional known area A, not a real human decision",
                 truth_status="insufficient_reference" if d["source_pdf"] == "SYNTHETIC-2.pdf" else "localizable",
                 correct_areas=[{"bbox":[-78.206,34.044,-78.194,34.056],"crs":"EPSG:4326","source":"Synthetic fixed ground truth A"}],
                 complete_candidate_review=True)
        for decision,c in zip(r["candidate_decisions"],d["candidates"]):
            # Test oracle is the independently specified synthetic coordinate
            # area; no scores or predicted rank determine correctness.
            is_a = -78.21 < (c["bbox"][0]+c["bbox"][2])/2 < -78.19
            decision["decision"] = "ambiguous" if r["truth_status"] == "insufficient_reference" else "correct" if is_a else "false_match"
    path = tmp_path/"review.json"
    path.write_text(json.dumps(review),encoding="utf-8")
    result = evaluate_localization(tmp_path/"run/localization.json",path,tmp_path/"evaluation")
    assert result["summary"]["reviewed_drawings"] == 4
    assert result["summary"]["candidate_recall"] == pytest.approx(2/3)
    assert result["summary"]["ambiguous_results"] == 1
    assert result["summary"]["insufficient_evidence_results"] == 2
    assert result["summary"]["false_geographic_matches"] >= 2
    assert result["summary"]["ambiguous_candidates"] == 2
