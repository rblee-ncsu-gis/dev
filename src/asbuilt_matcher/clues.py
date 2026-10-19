"""Manual geographic evidence with explicit review and retained correction history."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import uuid

from .pdf_extract import write_json
from .raster import validate_bbox

CLUE_KINDS = {"street_name", "subdivision_name", "project_name", "parcel_number",
              "lot_number", "survey_coordinate", "landmark", "sheet_number", "station_range",
              "address", "municipal_name", "township_name", "postal_zone"}
STATUSES = {"unverified", "verified", "rejected", "unreadable"}


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_coordinates(coordinates):
    if not isinstance(coordinates, dict) or not all(k in coordinates for k in ("x", "y", "crs", "units")):
        raise ValueError("Survey coordinate requires x, y, crs and units; use null for unknown CRS/units")
    if not all(type(coordinates[k]) in (int, float) and math.isfinite(coordinates[k]) for k in ("x", "y")):
        raise ValueError("Survey coordinate x/y must be finite numbers")
    if not all(coordinates[k] is None or isinstance(coordinates[k], str) for k in ("crs", "units")):
        raise ValueError("CRS and units must be strings or null")


def init_clues(manifest_path, registry_path):
    registry_path = Path(registry_path)
    if registry_path.exists():
        raise FileExistsError(registry_path)
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    data = {"schema_version": 1, "source": manifest["source"],
            "raster_manifest": str(manifest_path), "raster_run_id": manifest["run_id"],
            "coordinates": manifest["coordinates"],
            "pages": [{"page_number": p["page_number"], "bounds": p["bounds"]}
                      for p in manifest["pages"] if "bounds" in p],
            "created_at": now(), "clues": []}
    write_json(registry_path, data)
    return data


def add_clue(registry_path, *, kind, text, page_number, bbox, author,
             coordinates=None, notes=""):
    path = Path(registry_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if kind not in CLUE_KINDS or not text.strip() or not author.strip():
        raise ValueError("Valid kind, nonblank text and author are required")
    page = next((p for p in data["pages"] if p["page_number"] == page_number), None)
    if page is None:
        raise ValueError("Unknown page number")
    validate_bbox(bbox, page["bounds"])
    if kind == "survey_coordinate":
        validate_coordinates(coordinates)
    elif coordinates is not None:
        raise ValueError("Coordinate values only apply to survey_coordinate clues")
    clue = {"id": str(uuid.uuid4()), "document_sha256": data["source"]["sha256"],
            "page_number": page_number, "bbox": list(bbox), "kind": kind,
            "original_text": text, "text": text, "extraction_method": "manual",
            "verification_status": "unverified", "coordinates": coordinates,
            "author": author, "created_at": now(), "notes": notes,
            "history": [], "verification": None}
    data["clues"].append(clue)
    write_json(path, data)
    return clue


def review_clue(registry_path, clue_id, *, author, reason, text=None, status=None,
                bbox=None, coordinates=None, reviewer_type="unspecified", independent=False):
    path = Path(registry_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    clue = review_entry(data, clue_id, author=author, reason=reason, text=text,
                        status=status, bbox=bbox, coordinates=coordinates, reviewer_type=reviewer_type,
                        independent=independent)
    write_json(path, data)
    return clue


def review_entry(data, clue_id, *, author, reason, text=None, status=None,
                 bbox=None, coordinates=None, reviewer_type="unspecified", independent=False):
    """Shared in-memory review operation; callers persist only after validation."""
    clue = next((c for c in data["clues"] if c["id"] == clue_id), None)
    if clue is None:
        raise ValueError("Unknown clue ID")
    if not author.strip() or not reason.strip() or (status is not None and status not in STATUSES):
        raise ValueError("Author, reason and valid status are required")
    if reviewer_type not in {"human", "ai", "unspecified"}:
        raise ValueError("reviewer_type must be human, ai or unspecified")
    if type(independent) is not bool:
        raise ValueError("independent must be a boolean")
    if independent and (reviewer_type != "human" or author.strip().casefold() == clue["author"].strip().casefold()):
        raise ValueError("Independent acceptance requires a human reviewer distinct from the extraction author")
    if text is None and status is None and bbox is None and coordinates is None:
        raise ValueError("A correction or review status is required")
    before = {key: clue[key] for key in ("text", "bbox", "coordinates", "verification_status", "verification")}
    if text is not None:
        if not text.strip():
            raise ValueError("Corrected text cannot be blank")
        clue["text"] = text
    if bbox is not None:
        page = next(p for p in data["pages"] if p["page_number"] == clue["page_number"])
        clue["bbox"] = validate_bbox(bbox, page["bounds"])
    if coordinates is not None:
        if clue["kind"] != "survey_coordinate":
            raise ValueError("Coordinate correction requires a survey_coordinate clue")
        validate_coordinates(coordinates)
        clue["coordinates"] = coordinates
    # A correction invalidates prior verification unless explicitly reviewed again.
    clue["verification_status"] = status or "unverified"
    clue["verification"] = {"reviewer": author, "reviewer_type": reviewer_type, "scope": "transcription",
                            "independent": bool(independent),
                            "reason": reason, "timestamp": now()} if status else None
    clue["history"].append({"timestamp": now(), "author": author, "reason": reason, "before": before,
                            "action": "corrected" if text is not None or bbox is not None or coordinates is not None else status,
                            "after": {key: clue[key] for key in before}})
    return clue
