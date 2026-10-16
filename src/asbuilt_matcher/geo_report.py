"""Auditable localization snapshots and offline SVG review; no map services."""

import csv
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import uuid

from .geo_geometry import parts, project
from .geo_reference import read_catalog, read_json
from .geolocate import locate_documents
from .pdf_extract import file_sha256, write_json


def _csv(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()}
                         for row in rows)


def _map(candidate, features, origin):
    bbox = candidate["bbox"]
    # Include full supporting reference extents. The candidate area remains
    # visually distinct; a road extent must not appear to be the drawing footprint.
    boxes = [bbox] + [f["bbox"] for f in candidate["supporting_features"]]
    xmin, ymin = min(b[0] for b in boxes), min(b[1] for b in boxes)
    xmax, ymax = max(b[2] for b in boxes), max(b[3] for b in boxes)
    low, high = project([xmin, ymin], origin), project([xmax, ymax], origin)
    width, height = max(high[0] - low[0], 1), max(high[1] - low[1], 1)
    scale = min(620 / width, 340 / height)
    def xy(p):
        x, y = project(p, origin)
        return 20 + (x - low[0]) * scale, 360 - (y - low[1]) * scale
    paths = []
    for entry in candidate["supporting_features"]:
        feature = features[entry["feature_key"]]
        color = {"roads": "#165b9a", "subdivisions": "#7a488b", "parcels": "#3c7b3b"}[feature["kind"]]
        shape = feature["geometry"]
        for part in parts(shape):
            rings = part if "Polygon" in shape["type"] else [part]
            commands = []
            for ring in rings:
                commands.append("M " + " L ".join(f"{xy(p)[0]:.2f},{xy(p)[1]:.2f}" for p in ring)
                                + (" Z" if "Polygon" in shape["type"] else ""))
            paths.append(f'<path d="{" ".join(commands)}" stroke="{color}" stroke-width="2" fill="{color if "Polygon" in shape["type"] else "none"}" fill-opacity=".12" fill-rule="evenodd"><title>{escape(str(feature["native_id"]))}</title></path>')
    x1, y1 = xy(bbox[:2])
    x2, y2 = xy(bbox[2:])
    paths.append(f'<rect x="{min(x1,x2):.2f}" y="{min(y1,y2):.2f}" width="{max(abs(x2-x1),2):.2f}" height="{max(abs(y2-y1),2):.2f}" fill="#e8a021" fill-opacity=".14" stroke="#9b5c00" stroke-dasharray="5 3"/>')
    return '<svg viewBox="0 0 660 380" role="img" aria-label="Candidate area and reference features">' + "".join(paths) + '</svg><p class="note">Schematic local map, north up. Blue: roads; purple: subdivisions; green: parcels; orange dashed: candidate reference/search extent. No basemap or drawing registration.</p>'


def write_html(run, catalog, output):
    features = {f["feature_key"]: f for f in catalog["features"]} if catalog else {}
    origin = catalog.get("distance_origin") if catalog else None
    sections = []
    for drawing in run["drawings"]:
        clues = "".join(f'<li>{escape(c["kind"])}: {escape(c["text"])} <small>({escape(c["clue_id"])})</small></li>' for c in drawing["accepted_clues"])
        cards = []
        for candidate in drawing["candidates"]:
            evidence = "".join(f'<li>{escape(e["kind"])}: {escape(e["text"])} — {escape(e["best_match_type"])}; {e["points"]} points; reference IDs {escape(", ".join(str(m["native_id"]) for m in e["matches"]))}</li>' for e in candidate["evidence"])
            audit = escape(json.dumps({k: candidate[k] for k in ["evidence", "bonuses", "conflicts", "missing", "limitations"]}, indent=2, ensure_ascii=False))
            cards.append(f'<details><summary>Rank {candidate["rank"]} · {candidate["score"]} ranking points · {escape(candidate["match_type"])} · analyst review pending</summary>{_map(candidate,features,origin)}<p>Candidate ID: {candidate["candidate_id"]}; qualified area: {candidate["qualified"]}; CRS: EPSG:4326</p><ul>{evidence}</ul><pre>{audit}</pre></details>')
        sections.append(f'<section><h2>{escape(drawing["source_pdf"])} · {escape(", ".join(drawing["sheet_numbers"]))} · page {drawing["page_number"]}</h2><p>Status: <strong>{escape(drawing["status"])}</strong>. SHA-256: <code>{drawing["document_sha256"]}</code></p><details><summary>Accepted sheet evidence</summary><ul>{clues}</ul></details>{"".join(cards) if cards else "<p>No candidate areas. Authoritative reference data or sufficient matching evidence are still needed.</p>"}</section>')
    shared = escape(json.dumps(run["cross_sheet"], indent=2, ensure_ascii=False))
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Geographic localization review</title><style>body{font:16px system-ui;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#172a36}section{border-top:2px solid #9cb6c6;margin:2rem 0}details{border:1px solid #bccbd3;padding:1rem;margin:1rem 0}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f6;padding:1rem}svg{max-width:800px;width:100%;background:#f7fafb}code,small{overflow-wrap:anywhere}.note{font-size:.9rem}</style>'
            '<h1>Geographic localization review</h1><p>All candidate decisions are pending analyst review. Scores are deterministic ranking points, not probabilities. No asset associations or survey positions are created.</p>'
            f'<p>Run: {escape(run["run_id"])} · {escape(run["status"])} · EPSG:4326 (longitude, latitude). Reference import: {escape(run["reference_status"])}.</p>'
            + "".join(sections) + f'<h2>Cross-sheet evidence</h2><pre>{shared}</pre><p>Review is read-only. Record independently checked outcomes using the evaluation template; this HTML cannot approve a location.</p></html>')
    (Path(output) / "REVIEW.html").write_text(html, encoding="utf-8")


def localize(export_path, output, *, references_path=None, settings=None):
    export_path = Path(export_path).resolve()
    catalog = read_catalog(references_path) if references_path else None
    result = locate_documents(read_json(export_path), catalog, settings=settings)
    result.update(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat(),
                  inputs={"clues": {"path": str(export_path), "sha256": file_sha256(export_path)},
                          "references": {"path": str(Path(references_path).resolve()), "sha256": file_sha256(references_path)} if references_path else None},
                  reference_datasets=catalog["datasets"] if catalog else [],
                  reference_status=catalog["status"] if catalog else "not_provided")
    result["implementation"] = {name: file_sha256(Path(__file__).parent / name) for name in [
        "geo_reference.py", "geo_names.py", "geo_geometry.py", "geolocate.py", "geo_report.py"]}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "clues-input.json").write_bytes(export_path.read_bytes())
    if references_path:
        (output / "references-input.json").write_bytes(Path(references_path).read_bytes())
    write_json(output / "localization.json", result)
    document_rows, candidate_rows = [], []
    for drawing in result["drawings"]:
        common = {k: drawing[k] for k in ["drawing_id", "source_pdf", "document_sha256", "page_number", "sheet_numbers", "status", "crs", "analyst_review_status"]}
        document_rows.append({**common, "accepted_clues": len(drawing["accepted_clues"]), "candidate_count": len(drawing["candidates"])})
        for candidate in drawing["candidates"]:
            candidate_rows.append({**common, **{k: candidate[k] for k in ["candidate_id", "rank", "score", "qualified", "match_type", "bbox", "supporting_features", "evidence", "bonuses", "conflicts", "missing", "limitations"]}})
    common_fields = ["drawing_id", "source_pdf", "document_sha256", "page_number", "sheet_numbers", "status", "crs", "analyst_review_status"]
    _csv(output / "drawings.csv", common_fields + ["accepted_clues", "candidate_count"], document_rows)
    _csv(output / "candidates.csv", common_fields + ["candidate_id", "rank", "score", "qualified", "match_type", "bbox", "supporting_features", "evidence", "bonuses", "conflicts", "missing", "limitations"], candidate_rows)
    write_html(result, catalog, output)
    template = {"schema_version": 1, "localization_sha256": file_sha256(output / "localization.json"),
                "instructions": "Independent analyst evaluation only. Correct areas must be independently established in EPSG:4326, not copied from predictions. Keep unreviewed entries null. complete_candidate_review must be true only after classifying every candidate.",
                "reviews": [{"drawing_id": d["drawing_id"], "reviewer": None, "reviewer_type": None,
                             "independent_review": False, "reviewed_at": None, "reason": None,
                             "truth_status": None, "correct_areas": [], "complete_candidate_review": False,
                             "candidate_decisions": [{"candidate_id": c["candidate_id"], "decision": None} for c in d["candidates"]]}
                            for d in result["drawings"]]}
    write_json(output / "evaluation-template.json", template)
    (output / "localization.log").write_text("\n".join(f'{d["drawing_id"]}: {d["status"]}; {len(d["candidates"])} candidate(s)' for d in result["drawings"]) + "\n", encoding="utf-8")
    return result
