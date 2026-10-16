"""Import local read-only GeoJSON snapshots through explicit field mappings."""

from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path

from .geo_geometry import bounds, extent_diagonal, validate_geometry
from .pdf_extract import file_sha256, write_json

CRS = "EPSG:4326"
GEOMETRIES = {"roads": {"LineString", "MultiLineString"},
              "subdivisions": {"Polygon", "MultiPolygon"},
              "parcels": {"Polygon", "MultiPolygon"}}
FIELDS = {"id", "name", "aliases", "parcel_id", "lot", "address", "level"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def mapped_value(properties, mapping):
    """A string selects a field; a list concatenates address/name components."""
    if isinstance(mapping, list):
        return " ".join(str(properties[f]).strip() for f in mapping if properties.get(f) is not None)
    return properties.get(mapping)


def load_references(config_path):
    config_path = Path(config_path).resolve()
    config = read_json(config_path)
    if config.get("crs") != CRS:
        raise ValueError("Reference config must explicitly declare EPSG:4326; reproject EPSG:2264 outside this tool")
    datasets = config.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("datasets must be an array")
    aoi = config.get("area_of_interest_bbox")
    if aoi is not None and (not isinstance(aoi, list) or len(aoi) != 4
                           or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in aoi)
                           or not -180 <= aoi[0] < aoi[2] <= 180 or not -80 <= aoi[1] < aoi[3] <= 80):
        raise ValueError("area_of_interest_bbox must be a WGS84 [west,south,east,north] extent")
    catalog = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
               "crs": CRS, "config": {"path": str(config_path), "sha256": file_sha256(config_path)},
               "datasets": [], "features": [], "errors": [], "warnings": [], "status": "complete"}
    dataset_ids = set()
    for entry in datasets:
        dataset_id, kind = entry.get("id"), entry.get("kind")
        if not isinstance(dataset_id, str) or not dataset_id.strip() or dataset_id in dataset_ids:
            raise ValueError("Dataset IDs must be nonblank and unique")
        dataset_ids.add(dataset_id)
        if kind not in GEOMETRIES:
            raise ValueError("Dataset kind must be roads, subdivisions or parcels")
        if entry.get("crs", CRS) != CRS:
            raise ValueError("Mixed dataset CRS is not supported; all layers must be EPSG:4326")
        fields = entry.get("fields", {})
        required = {"id", "name"} if kind != "parcels" else {"id"}
        if not required <= set(fields) or set(fields) - FIELDS:
            raise ValueError(f"Invalid field mapping for {dataset_id}; required: {sorted(required)}")
        for key, value in fields.items():
            if not (isinstance(value, str) and value or isinstance(value, list) and value
                    and key in {"name", "address", "aliases"} and all(isinstance(f, str) and f for f in value)):
                raise ValueError(f"Invalid field mapping: {key}")
        metadata = entry.get("metadata", {})
        if not isinstance(metadata, dict) or not metadata.get("authority") or not metadata.get("source_layer"):
            raise ValueError("Each dataset needs metadata.authority and metadata.source_layer (synthetic fixtures must say so)")
        if metadata.get("output_crs", CRS) != CRS:
            raise ValueError("Dataset output_crs metadata conflicts with EPSG:4326")
        raw_path = entry.get("path", "")
        if not raw_path or "://" in raw_path:
            raise ValueError("Only local GeoJSON files are accepted")
        path = (config_path.parent / raw_path).resolve()
        document = read_json(path)
        # RFC 7946: CRS is WGS84 lon/lat. Legacy declarations must agree;
        # numeric range checks alone cannot detect correctly ranged wrong-CRS data.
        legacy = document.get("crs")
        if legacy is not None and legacy not in [
                {"type": "name", "properties": {"name": "EPSG:4326"}},
                {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}]:
            raise ValueError(f"Conflicting or unsupported GeoJSON CRS in {path.name}")
        if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
            raise ValueError("GeoJSON must be a FeatureCollection")
        summary = {"id": dataset_id, "kind": kind, "path": str(path), "sha256": file_sha256(path),
                   "fields": fields, "metadata": metadata, "input_features": len(document["features"]),
                   "accepted_features": 0, "rejected_features": 0}
        catalog["datasets"].append(summary)
        seen = set()
        for index, feature in enumerate(document["features"]):
            try:
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    raise ValueError("Expected GeoJSON Feature")
                props = feature.get("properties")
                if not isinstance(props, dict):
                    raise ValueError("Feature properties must be an object")
                absent = [f for value in fields.values() for f in (value if isinstance(value, list) else [value]) if f not in props]
                if absent:
                    raise ValueError(f"Mapped fields absent: {sorted(set(absent))}")
                native_id = mapped_value(props, fields["id"])
                if isinstance(native_id, bool) or not isinstance(native_id, (str, int)) or not str(native_id).strip():
                    raise ValueError("Stable native ID must be a nonblank string or integer")
                key = str(native_id)
                if key in seen:
                    # A collision cannot be silently converted into two feature identities.
                    raise RuntimeError(f"Duplicate native ID in {dataset_id}: {key}")
                seen.add(key)
                b = validate_geometry(feature.get("geometry"), GEOMETRIES[kind])
                if aoi and not (aoi[0] <= b[0] <= b[2] <= aoi[2] and aoi[1] <= b[1] <= b[3] <= aoi[3]):
                    raise ValueError("Feature outside configured area_of_interest_bbox; do not silently clip")
                values = {k: mapped_value(props, v) for k, v in fields.items() if k != "aliases"}
                if kind != "parcels" and (not isinstance(values.get("name"), str) or not values["name"].strip()):
                    raise ValueError("Road/subdivision name must be nonblank text")
                aliases = []
                alias_fields = fields.get("aliases", [])
                for f in alias_fields if isinstance(alias_fields, list) else [alias_fields]:
                    value = props.get(f)
                    if value is None:
                        continue
                    for label in value if isinstance(value, list) else [value]:
                        if not isinstance(label, str):
                            raise ValueError("Aliases must be strings or arrays of strings")
                        if label.strip():
                            aliases.append(label)
                catalog["features"].append({"feature_key": json.dumps([dataset_id, key], separators=(",", ":")),
                                            "dataset_id": dataset_id, "kind": kind, "native_id": native_id,
                                            "geojson_id": feature.get("id"), "values": values, "aliases": aliases,
                                            "geometry": feature["geometry"], "bbox": b, "properties": props})
                summary["accepted_features"] += 1
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                summary["rejected_features"] += 1
                catalog["errors"].append({"dataset_id": dataset_id, "feature_index": index, "error": str(exc)})
    if catalog["features"]:
        boxes = [f["bbox"] for f in catalog["features"]]
        b = [min(p[0] for p in boxes), min(p[1] for p in boxes), max(p[2] for p in boxes), max(p[3] for p in boxes)]
        origin = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
        if extent_diagonal(b, origin) > 250000:
            raise ValueError("Reference extent exceeds 250 km; county-scale local distance approximation only")
        catalog.update(bbox=b, distance_origin=origin)
    else:
        catalog.update(bbox=None, distance_origin=None)
    catalog["status"] = "partial" if catalog["errors"] else "complete" if catalog["features"] else "empty"
    catalog["warnings"].append("2D geometries only; Z ignored. Validate topology and CRS at export. No reprojection performed.")
    return catalog


def import_references(config_path, output):
    catalog = load_references(config_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "references.json", catalog)
    fields = ["id", "kind", "path", "sha256", "input_features", "accepted_features", "rejected_features"]
    with (output / "datasets.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(catalog["datasets"])
    lines = [f"{d['id']}: {d['accepted_features']} accepted; {d['rejected_features']} rejected" for d in catalog["datasets"]]
    lines += [json.dumps(e, ensure_ascii=False) for e in catalog["errors"]]
    (output / "import.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return catalog


def read_catalog(path):
    catalog = read_json(path)
    if catalog.get("schema_version") != 1 or catalog.get("crs") != CRS:
        raise ValueError("Expected an imported EPSG:4326 reference catalog")
    if not isinstance(catalog.get("features"), list) or not isinstance(catalog.get("datasets"), list):
        raise ValueError("Malformed reference catalog")
    # Reuse the snapshot; the original exports need not remain at their original
    # paths. Catalog bytes are hashed in each localization run.
    return catalog
