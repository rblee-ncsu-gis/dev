"""Review bundles and verified exports, using the existing clue correction logic."""

from collections import Counter
import csv
import json
import os
from pathlib import Path

from .clues import now, review_entry
from .pdf_extract import file_sha256, write_json
from .raster import validate_bbox, render_region
from .pdf_extract import load_pdf_backend

FIELDS = ["registry", "clue_id", "source_pdf", "document_sha256", "page_number", "kind",
          "original_text", "text", "verification_status", "bbox", "image_reference",
          "image_sha256", "extraction_method", "reviewer", "reviewer_type", "review_reason", "review_timestamp",
          "coordinates", "history", "evidence_issue", "target_image_reference", "target_image_sha256"]
FIELDS += ["extraction_author", "independent_review", "ground_truth_eligible"]


def analyst_accepted(row):
    """Explicit local attestation, not identity authentication; AI reviews never qualify."""
    return (row.get("verification_status") == "verified" and row.get("reviewer_type") == "human"
            and row.get("independent_review") is True
            and all(isinstance(row.get(k), str) and row[k].strip()
                    for k in ("reviewer", "review_reason", "review_timestamp", "extraction_author"))
            and row["reviewer"].strip().casefold() != row["extraction_author"].strip().casefold())


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evidence_for(registry, clue):
    """Resolve the smallest containing composition-correct crop, else full page."""
    manifest_path = Path(registry["raster_manifest"])
    manifest = read_json(manifest_path)
    if manifest["source"]["sha256"] != registry["source"]["sha256"] or manifest["run_id"] != registry["raster_run_id"]:
        raise ValueError("Raster manifest provenance does not match registry")
    if clue["document_sha256"] != registry["source"]["sha256"]:
        raise ValueError("Clue document hash does not match registry")
    page = next(p for p in manifest["pages"] if p["page_number"] == clue["page_number"])
    bbox = validate_bbox(clue["bbox"], page["bounds"])
    candidates = [r for r in page.get("crops", []) if r["bbox"][0] <= bbox[0] and r["bbox"][1] <= bbox[1]
                  and r["bbox"][2] >= bbox[2] and r["bbox"][3] >= bbox[3]]
    if not candidates:
        candidates = [page["full_page"]]
    image = min(candidates, key=lambda r: (r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1]))
    image_path = (manifest_path.parent / page["directory"] / image["file"]).resolve()
    if manifest_path.parent.resolve() not in image_path.parents:
        raise ValueError("Image path escapes raster evidence directory")
    return {"path": str(image_path), "sha256": file_sha256(image_path),
            "bbox": image["bbox"], "width": image["width"], "height": image["height"],
            "effective_dpi": image["effective_dpi"], "page_to_pixel": image["page_to_pixel"]}


def collect_rows(registries, *, verified_only=False):
    rows = []
    seen = set()
    for registry_path in registries:
        registry_path = Path(registry_path).resolve()
        data = read_json(registry_path)
        source = Path(data["source"]["path"])
        source_issue = ""
        try:
            if file_sha256(source) != data["source"]["sha256"]:
                source_issue = "Source PDF hash differs from registry"
        except OSError as exc:
            source_issue = f"Source PDF unavailable: {exc}"
        for clue in data["clues"]:
            if clue["id"] in seen:
                raise ValueError("Duplicate clue ID across input registries")
            seen.add(clue["id"])
            if verified_only and clue["verification_status"] != "verified":
                continue
            issue, image = source_issue, None
            try:
                image = evidence_for(data, clue)
            except (OSError, ValueError, KeyError, StopIteration) as exc:
                issue = "; ".join(filter(None, [issue, f"Evidence unavailable: {exc}"]))
            verification = clue.get("verification") or {}
            if verified_only and (issue or not all(verification.get(k) for k in ("reviewer", "reason", "timestamp"))):
                raise ValueError(f"Verified clue {clue['id']} lacks valid evidence or review: {issue}")
            rows.append({"registry": str(registry_path), "clue_id": clue["id"],
                         "source_pdf": data["source"]["filename"], "document_sha256": clue["document_sha256"],
                         "page_number": clue["page_number"], "kind": clue["kind"],
                         "original_text": clue["original_text"], "text": clue["text"],
                         "verification_status": clue["verification_status"], "bbox": clue["bbox"],
                         "image_reference": image["path"] if image else None,
                         "image_sha256": image["sha256"] if image else None,
                         "image": image, "extraction_method": clue["extraction_method"],
                         "reviewer": verification.get("reviewer"), "review_reason": verification.get("reason"),
                         "reviewer_type": verification.get("reviewer_type", "unspecified"),
                         "review_timestamp": verification.get("timestamp"), "coordinates": clue["coordinates"],
                         "history": clue["history"], "evidence_issue": issue})
            rows[-1].update(extraction_author=clue["author"], independent_review=verification.get("independent", False))
            rows[-1]["ground_truth_eligible"] = analyst_accepted(rows[-1])
    return rows


def csv_rows(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                             for key, value in row.items() if key in FIELDS})


def markdown_cell(value):
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def write_review_bundle(registries, output):
    registries = [Path(p).resolve() for p in registries]
    if not registries:
        raise ValueError("At least one registry is required")
    rows = collect_rows(registries)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "review.json", {"schema_version": 1, "created_at": now(), "clues": rows})
    csv_rows(output / "review.csv", rows)
    lines = ["# Geographic clue review manifest", "",
             f"Clues: {len(rows)}. Status counts: {dict(Counter(r['verification_status'] for r in rows))}", "",
             f"Independently analyst-accepted references: {sum(analyst_accepted(r) for r in rows)}. AI review alone is not ground truth.", "",
             "Bounding boxes are unrotated visible-page points. Verification concerns transcription, not GIS location.",
             "Corrected is an action; it resets verification unless explicitly verified in the same review.",
             "Keep unreadable/rejected evidence for audit; neither is included in verified exports.", "",
             "| Source / page | Clue ID / type | Current transcription | Original transcription | Status / reviewer | Box | Evidence |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        image = row["image_reference"]
        href = Path(os.path.relpath(image, output)).as_posix() if image else ""
        evidence = f"[image](<{href}>)" if href else markdown_cell(row["evidence_issue"])
        if row["evidence_issue"] and href:
            evidence += " " + markdown_cell(row["evidence_issue"])
        lines.append("| " + " | ".join([
            markdown_cell(f"{row['source_pdf']} / {row['page_number']}"),
            markdown_cell(f"{row['clue_id']} / {row['kind']}"), markdown_cell(row["text"]),
            markdown_cell(row["original_text"]), markdown_cell(f"{row['verification_status']} / {row['reviewer'] or 'pending'}"),
            str(row["bbox"]), evidence]) + " |")
    (output / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for index, registry in enumerate(registries, 1):
        data = read_json(registry)
        template = {"registry_sha256": file_sha256(registry), "registry": str(registry),
                    "decisions": [{"clue_id": c["id"], "text_for_reference": c["text"],
                                   "action": None, "author": "", "reviewer_type": "unspecified",
                                   "independent": False,
                                   "reason": ""} for c in data["clues"]]}
        write_json(output / f"decisions-{index:02d}.json", template)
    return {"clues": len(rows), "statuses": dict(Counter(r["verification_status"] for r in rows))}


def apply_decisions(registry_path, decisions_path):
    """Validate all decisions in memory; replace the registry once, only if all pass."""
    registry_path = Path(registry_path).resolve()
    decisions = read_json(decisions_path)
    if file_sha256(registry_path) != decisions["registry_sha256"]:
        raise ValueError("Stale decisions: registry changed; regenerate the review bundle")
    if Path(decisions["registry"]).resolve() != registry_path:
        raise ValueError("Decisions belong to another registry")
    data = read_json(registry_path)
    count, seen = 0, set()
    for decision in decisions["decisions"]:
        action = decision.get("action")
        if action is None:
            continue
        if action not in {"verified", "corrected", "rejected", "unreadable"}:
            raise ValueError("Action must be verified, corrected, rejected or unreadable")
        clue_id = decision["clue_id"]
        if clue_id in seen:
            raise ValueError("Repeated decision for clue")
        seen.add(clue_id)
        edits = {key: decision[key] for key in ("text", "bbox", "coordinates") if key in decision}
        if action == "corrected" and not any(v is not None for v in edits.values()):
            raise ValueError("A corrected action requires text, bbox or coordinates")
        review_entry(data, clue_id, author=decision["author"], reason=decision["reason"],
                     status=None if action == "corrected" else action,
                     reviewer_type=decision.get("reviewer_type", "unspecified"),
                     independent=decision.get("independent", False), **edits)
        count += 1
    if count:
        # Optimistic check: do not overwrite edits made while validating the batch.
        if file_sha256(registry_path) != decisions["registry_sha256"]:
            raise ValueError("Registry changed while reviewing; no decisions saved")
        write_json(registry_path, data)
    return {"applied": count}


def export_verified(registries, output, *, render_targets=False, analyst_only=False):
    registries = [Path(p).resolve() for p in registries]
    if not registries:
        raise ValueError("At least one registry is required")
    rows = collect_rows(registries, verified_only=True)
    if analyst_only:
        rows = [r for r in rows if analyst_accepted(r)]
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if render_targets:
        pdf = load_pdf_backend()
        for index, row in enumerate(rows, 1):
            source = read_json(row["registry"])["source"]["path"]
            with pdf.open(source) as doc:
                page = doc[row["page_number"] - 1]
                page.set_rotation(0)
                target = output / f"target-{index:04d}.png"
                row["target_image"] = render_region(pdf, page, target, row["bbox"], 200, 40_000_000)
                row["target_image_reference"] = str(target)
                row["target_image_sha256"] = file_sha256(target)
            if file_sha256(source) != row["document_sha256"]:
                raise ValueError("Source changed while rendering targets; discard export")
    write_json(output / "verified-clues.json", {
        "schema_version": 1, "created_at": now(), "verification_scope": "transcription only; not geographic truth",
        "analyst_only": analyst_only,
        "registries": [{"path": str(p), "sha256": file_sha256(p)} for p in registries],
        "clues": rows})
    csv_rows(output / "verified-clues.csv", rows)
    return {"verified_clues": len(rows)}
