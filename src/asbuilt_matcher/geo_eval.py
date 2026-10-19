"""Evaluate frozen localization runs using separate independent area decisions."""

from datetime import datetime
from collections import Counter
from pathlib import Path
import math

from .geo_reference import read_json
from .pdf_extract import file_sha256, write_json
from .geo_report import _csv
from .geo_geometry import validate_geometry


def validate_location_reference(location):
    if not isinstance(location,dict):
        raise ValueError('Independent reference must be an object')
    kind=location.get('kind')
    if location.get('crs')!='EPSG:4326' or not location.get('source') or location.get('independently_determined') is not True:
        raise ValueError('Independent geographic references need source, EPSG:4326 and an explicit independence declaration')
    allowed={'area':{'Polygon','MultiPolygon'},'footprint':{'Polygon','MultiPolygon'},
             'intersection':{'Point'},'control_point':{'Point'}}
    if kind not in allowed:
        raise ValueError('Reference kind must be area, footprint, intersection or control_point')
    validate_geometry(location.get('geometry'),allowed[kind])
    if kind in {'intersection','control_point'}:
        tolerance=location.get('accuracy_m')
        if isinstance(tolerance,bool) or not isinstance(tolerance,(int,float)) or not math.isfinite(tolerance) or tolerance<=0:
            raise ValueError('Point references require positive finite accuracy_m')


def evaluate_localization(run_path, review_path, output):
    run, review = read_json(run_path), read_json(review_path)
    if review.get("localization_sha256") != file_sha256(run_path):
        raise ValueError("Evaluation review does not match the frozen localization run hash")
    drawings = {d["drawing_id"]: d for d in run["drawings"]}
    reviews = review.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("reviews must be an array")
    rows, seen, pending = [], set(), []
    for entry in reviews:
        key = entry.get("drawing_id")
        if key not in drawings or key in seen:
            raise ValueError("Review drawing IDs must be unique and present in the run")
        seen.add(key)
        d = drawings[key]
        if (entry.get("reviewer_type") != "human" or entry.get("independent_review") is not True
                or any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in ["reviewer", "reviewed_at", "reason"])
                or entry.get("truth_status") not in {"localizable", "insufficient_reference", "ambiguous_truth"}):
            pending.append({"drawing_id": key, "reason": "independent_area_review_incomplete"})
            continue
        timestamp = datetime.fromisoformat(entry["reviewed_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Evaluation timestamps require a timezone")
        if run.get("reference_status") in {"not_provided", "empty"}:
            pending.append({"drawing_id": key, "reason": "no_reference_data_in_run"})
            continue
        areas = entry.get("correct_areas", [])
        locations=entry.get('correct_locations',[])
        scope=entry.get('evaluation_scope') or 'geographic_localization'
        if scope not in {'geographic_localization','corridor_recovery'}:
            raise ValueError('Unknown geographic evaluation scope')
        if entry["truth_status"] == "localizable":
            if not areas and not locations:
                raise ValueError("Localizable truth needs independent correct_areas with bbox/crs/source")
            for location in locations:
                validate_location_reference(location)
                if location.get('model_input_landmark_id') or any(location['geometry'] == p['geometry'] for p in run.get('model_input_reference_locations', [])):
                    raise ValueError('Landmark model input cannot serve as independent drawing ground truth')
            for area in areas:
                bbox = area.get("bbox", [])
                if (area.get("crs") != "EPSG:4326" or not area.get("source") or len(bbox) != 4
                        or not -180 <= bbox[0] < bbox[2] <= 180 or not -80 <= bbox[1] < bbox[3] <= 80):
                    raise ValueError("Correct areas require a valid EPSG:4326 bbox and independent source")
        candidates = {c["candidate_id"]: c for c in [*d["candidates"], *d.get('narrowed_candidates', [])]}
        decisions = entry.get("candidate_decisions", [])
        decision_map = {}
        for decision in decisions:
            candidate_id = decision.get("candidate_id")
            if candidate_id not in candidates or candidate_id in decision_map:
                raise ValueError("Candidate decisions must be unique and belong to the drawing")
            if decision.get("decision") not in {None, "correct", "false_match", "ambiguous"}:
                raise ValueError("Candidate decision must be correct, false_match, ambiguous, or null")
            decision_map[candidate_id] = decision.get("decision")
        if (entry.get("complete_candidate_review") is not True or set(decision_map) != set(candidates)
                or any(value is None for value in decision_map.values())):
            pending.append({"drawing_id": key, "reason": "candidate_review_incomplete"})
            continue
        ranks = [candidates[k]["rank"] for k, decision in decision_map.items() if decision == "correct"]
        if scope=='geographic_localization' and any(decision=='correct' and candidates[k].get('localization_level') in {'road_corridor', 'landmark_review_locality'} for k,decision in decision_map.items()):
            raise ValueError('A corridor hit cannot be scored as geographic localization; use corridor_recovery review scope')
        if ranks and entry["truth_status"] != "localizable":
            raise ValueError("Correct candidate decisions require independently localizable truth")
        rows.append({"drawing_id": key, "source_pdf": d["source_pdf"], "truth_status": entry["truth_status"],
                     'evaluation_scope':scope,'independent_references':locations or areas,
                     "localization_status": d["status"], "correct_area_in_candidates": bool(ranks),
                     "best_correct_rank": min(ranks) if ranks else None,
                     "false_geographic_matches": sum(v == "false_match" for v in decision_map.values()),
                     "ambiguous_candidates": sum(v == "ambiguous" for v in decision_map.values()),
                     "candidate_count": len(candidates), "reviewer": entry["reviewer"], "reason": entry["reason"]})
    pending += [{"drawing_id": key, "reason": "no_independent_area_review"} for key in drawings.keys() - seen]
    geographic_rows=[r for r in rows if r['evaluation_scope']=='geographic_localization']
    corridor_rows=[r for r in rows if r['evaluation_scope']=='corridor_recovery']
    localizable = [r for r in geographic_rows if r["truth_status"] == "localizable"]
    denominator = len(localizable)
    summary = {"reviewed_drawings": len(rows), "pending_drawings": len(pending), "localizable_drawings": denominator,
               "correct_area_in_candidates": sum(r["correct_area_in_candidates"] for r in localizable),
               "candidate_recall": sum(r["correct_area_in_candidates"] for r in localizable) / denominator if denominator else None,
               "top_k_recall": {str(k): sum(r["best_correct_rank"] is not None and r["best_correct_rank"] <= k for r in localizable) / denominator if denominator else None for k in [1, 3, 5]},
               "false_geographic_matches": sum(r["false_geographic_matches"] for r in geographic_rows),
               "ambiguous_candidates": sum(r["ambiguous_candidates"] for r in rows),
               "ambiguous_results": sum(r["localization_status"] == "ambiguous" for r in rows),
               "insufficient_evidence_results": sum(r["localization_status"] == "insufficient_evidence" for r in rows)}
    result = {"schema_version": 1, "inputs": {"localization_sha256": file_sha256(run_path), "review_sha256": file_sha256(review_path)},
              "scope": "Independent geographic-area review; not OCR accuracy, asset matching or calibrated probabilities.",
              "metric_status":"pending_independent_review" if not rows else "partially_reviewed" if pending else "reviewed",
              "generated_results":{"drawing_count":len(drawings),"candidate_count":sum(len(d['candidates']) + len(d.get('narrowed_candidates', [])) for d in drawings.values()),
                                   "status_counts":dict(Counter(d['status'] for d in drawings.values()))},
              "reference_metadata": run.get("reference_datasets", []), "summary": summary, "drawings": rows, "pending": pending}
    result['corridor_recovery']={'reviewed_drawings':len(corridor_rows),
                                  'correct_corridor_in_candidates':sum(r['correct_area_in_candidates'] for r in corridor_rows),
                                  'best_correct_ranks':{r['drawing_id']:r['best_correct_rank'] for r in corridor_rows},
                                  'scope':'Corridor evidence only; excluded from geographic localization Top-1/Top-3 denominators.'}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "evaluation.json", result)
    _csv(output / "evaluation.csv", ["drawing_id", "source_pdf", "truth_status", 'evaluation_scope','independent_references', "localization_status", "correct_area_in_candidates", "best_correct_rank", "false_geographic_matches", "ambiguous_candidates", "candidate_count", "reviewer", "reason"], rows)
    return result
