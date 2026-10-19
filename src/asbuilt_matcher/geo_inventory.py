"""County export validation, provenance history and unapproved mapping proposals."""

from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .geo_geometry import validate_geometry, vertices
from .geo_reference import CRS, GEOMETRIES, read_json, required_mapping, validate_mapping
from .geo_stream import collection_events
from .pdf_extract import file_sha256, write_json

SOURCE_FIELDS = ["source_feature_class", "source_crs", "database_version", "exported_at", "data_owner"]
HINTS = {
    "id": ["globalid", "roadguid", "subkey", "parcelguid", "addressid", "siteaddressid", "uniqueid", "objectid", "fid"],
    "name": ["fullname", "fullstreetname", "streetname", "roadname", "subdivisionname", "subname", "name", "townname", "township", "zip", "zipcode"],
    "prefix_direction": ["predir", "prefixdirection", "stpredir", "prefixdir"],
    "street_prefix": ["pretype", "streetprefix", "stpretype"],
    "street_name": ["streetname", "stname", "roadname", "street", "basename"],
    "street_suffix": ["suffix", "streettype", "sttype", "streetsuffix", "rdtype"],
    "suffix_direction": ["postdir", "suffixdir", "stsufdir"],
    "aliases": ["alias", "aliases", "altname", "alternatename", "route", "routename", "routenumber"],
    "parcel_id": ["pin", "parcelid", "parcelnumber", "parcelno", "taxparcelid"],
    "lot": ["lot", "lotnum", "lotnumber", "lotno"],
    "phase": ["phase", "phasenum", "phasenumber"],
    "address": ["fulladdress", "siteaddress", "address", "addressfull", "situsaddress", "staddr"],
    "address_number": ["addrnum", "addressnumber", "housenumber", "addnumber", "stnum", "stnumb"],
    "municipal_name": ["municipality", "municipalname", "townname", "city", "town"],
    "township_name": ["township", "townshipname", "townshipnm"],
    "postal_zone": ["zip", "zipcode", "postalcode", "postalzone", "zip5"],
    "level": ["level", "zlevel", "elevationlevel"]}
NAME_HINTS = {"roads": ["fullname", "fullstreetname", "streetname", "roadname"],
              "subdivisions": ["subdivision", "subdivisionname", "subname", "name"],
              "town_limits": ["municipality", "townname", "town", "city", "name"],
              "townships": ["township", "townshipname", "townshipnm", "townname", "name"],
              "postal_zones": ["zip", "zipcode", "postalcode", "postalzone", "name"]}
ID_HINTS=set(HINTS['id']+HINTS['parcel_id'])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def write_field_inventory(manifest,output):
    """Tabular actual schema/quality for analysts; never sample address values."""
    fields=['dataset','field','types','present_count','null_count','missing_count','blank_count','unique_nonblank_count','duplicate_nonblank_count','confirmed_roles']
    with (Path(output)/'fields.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fields,extrasaction='ignore');writer.writeheader()
        for dataset in manifest['datasets']:
            mapping=dataset['mapping_review'].get('fields',{}) if dataset['mapping_review']['status']=='confirmed' else {}
            for field,profile in dataset['field_profiles'].items():
                roles=[role for role,value in mapping.items() if field in (value if isinstance(value,list) else [value])]
                writer.writerow({**profile,'dataset':dataset['dataset'],'field':field,'types':json.dumps(profile['types']),
                                 'confirmed_roles':','.join(roles)})


def propose_mapping(kind, profiles):
    """Name hints are review suggestions, never approved mappings."""
    roles = {"id", "name", "aliases"}
    if kind in {"roads", "addresses"}:
        roles |= {"prefix_direction", "street_prefix", "street_name", "street_suffix", "suffix_direction"}
    roles |= {"roads": {"level"}, "subdivisions": {"phase"}, "parcels": {"parcel_id", "lot", "address"},
              "addresses": {"address", "address_number", "municipal_name", "township_name", "postal_zone"}}.get(kind, set())
    suggestions, fields = {}, {}
    for role in sorted(roles):
        hints = NAME_HINTS.get(kind, HINTS["name"]) if role == "name" else HINTS[role]
        candidates = []
        for field, profile in profiles.items():
            normalized = _key(field)
            if normalized in hints:
                candidates.append({"field": field, "basis": "field-name hint only; semantics require analyst confirmation",
                                   "missing_count": profile["missing_count"], "null_count": profile["null_count"],
                                   "blank_count": profile["blank_count"], "priority": hints.index(normalized)})
        candidates.sort(key=lambda c: (c["priority"], c["field"]))
        suggestions[role] = {"candidates": candidates, "status": "ambiguous" if len(candidates) > 1 else "suggested" if candidates else "unresolved"}
        if candidates:
            # Prefer the strongest field-name hint in the editable proposal,
            # while retaining all alternatives and mandatory analyst signoff.
            fields[role] = [candidates[0]["field"]] if role == "aliases" else candidates[0]["field"]
    if kind == "addresses":
        fields.pop("name", None)
    return {"status": "proposed_only", "roles": suggestions, "suggested_fields": fields,
            "required_mapping_resolved": required_mapping(kind, fields)}


def _declared_crs(header):
    declaration = header.get("crs")
    if declaration is None:
        return None
    if not isinstance(declaration, dict):
        return "unrecognized"
    name = declaration.get("properties", {}).get("name", "")
    if name in {"EPSG:4326", "urn:ogc:def:crs:EPSG::4326", "urn:ogc:def:crs:OGC:1.3:CRS84"}:
        return CRS
    return name or "unrecognized"


def inspect_dataset(path, kind, *, analyst_metadata=None, decision=None):
    path = Path(path).resolve()
    before = file_sha256(path)
    result = {"dataset": kind, "filename": path.name, "path": str(path), "size_bytes": path.stat().st_size,
              "sha256": before, "feature_count": 0, "geometry_types": {}, "available_fields": [],
              "field_profiles": {}, "extent": None, "warnings": [], "errors": [], "error_count": 0,
              "source_metadata": {key: (analyst_metadata or {}).get(key) for key in SOURCE_FIELDS}}
    header, profiles, geometry_types, extent = {}, {}, Counter(), None
    unique_ids = {}
    geometry_errors, range_errors = 0, 0
    def error(index, message):
        result["error_count"] += 1
        if len(result["errors"]) < 50:
            result["errors"].append({"feature_index": index, "error": message})
    try:
        for event, value in collection_events(path):
            if event == "header":
                header[value[0]] = value[1]
                continue
            index = result["feature_count"]
            result["feature_count"] += 1
            if not isinstance(value, dict) or value.get("type") != "Feature":
                error(index, "Expected Feature object")
                continue
            props = value.get("properties")
            if not isinstance(props, dict):
                error(index, "Missing or invalid properties object")
            else:
                for field, item in props.items():
                    p = profiles.setdefault(field, {"present_count": 0, "null_count": 0, "blank_count": 0, "types": Counter()})
                    p["present_count"] += 1
                    p["null_count"] += item is None
                    p["blank_count"] += isinstance(item, str) and not item.strip()
                    p["types"][type(item).__name__] += 1
                    if _key(field) in ID_HINTS and isinstance(item,(str,int)) and not isinstance(item,bool) and str(item).strip():
                        unique_ids.setdefault(field,set()).add((type(item).__name__,str(item)))
            geometry = value.get("geometry")
            geo_type = geometry.get("type", "missing") if isinstance(geometry, dict) else "null"
            geometry_types[geo_type] += 1
            try:
                bbox = validate_geometry(geometry, GEOMETRIES[kind])
                extent = bbox if extent is None else [min(extent[0],bbox[0]),min(extent[1],bbox[1]),max(extent[2],bbox[2]),max(extent[3],bbox[3])]
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                geometry_errors += 1
                if "WGS84" in str(exc):
                    range_errors += 1
                error(index, str(exc))
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        error(None, str(exc))
    if file_sha256(path) != before:
        error(None, "File changed during validation; rerun before importing")
    total = result["feature_count"]
    for field, p in profiles.items():
        p["missing_count"] = total - p["present_count"]
        p["types"] = dict(p["types"])
        if field in unique_ids:
            p['unique_nonblank_count']=len(unique_ids[field])
            p['duplicate_nonblank_count']=p['present_count']-p['null_count']-p['blank_count']-len(unique_ids[field])
    result.update(field_profiles=dict(sorted(profiles.items())), available_fields=sorted(profiles),
                  geometry_types=dict(geometry_types), extent=extent,
                  schema={field:sorted(p['types']) for field,p in sorted(profiles.items())},
                  invalid_geometry_count=geometry_errors, out_of_range_geometry_count=range_errors,
                  declared_geojson_name=header.get("name"))
    decision = decision or {}
    if decision and decision.get("dataset_sha256") != before:
        result["warnings"].append("Mapping/CRS decision is stale or not bound to current dataset hash")
        decision = {}
    declared = _declared_crs(header)
    supplied_crs = decision.get("output_crs") if decision.get("crs_confirmed") is True else None
    evidence_crs = supplied_crs or declared
    if declared is not None and declared != CRS or supplied_crs is not None and supplied_crs != CRS:
        error(None, "Declared/analyst-supplied output CRS is not EPSG:4326; no automatic reprojection")
    if declared and supplied_crs and declared != supplied_crs:
        error(None, "Conflicting CRS declarations")
    # CRS provenance and geometry validity are separate facts. Empty rings do
    # not erase an analyst's CRS attestation; they still prevent a clean import.
    confirmed = evidence_crs == CRS and range_errors == 0 and not (declared and declared != CRS)
    result["coordinate_system"] = {"intended_output_crs": CRS, "file_declaration": header.get("crs"),
                                    "declared_crs": declared, "coordinate_ranges_compatible": range_errors == 0 and total > 0,
                                    "confirmed_output_crs": CRS if confirmed else None,
                                    "confirmation_basis": "analyst_attestation" if supplied_crs == CRS else "explicit_file_declaration" if declared == CRS else None,
                                    "analyst_confirmed": supplied_crs == CRS,
                                    "note": "Ranges alone cannot confirm CRS, source CRS, datum transformation or geographic correctness."}
    if evidence_crs is None:
        result["warnings"].append("No explicit output CRS evidence; hash-bound analyst CRS confirmation needed")
    missing_source = [k for k,v in result["source_metadata"].items() if v is None]
    if missing_source:
        result["warnings"].append("Source metadata not supplied: " + ", ".join(missing_source))
    proposal = propose_mapping(kind, result["field_profiles"])
    result["mapping_proposal"] = proposal
    confirmed_fields = decision.get("fields", {})
    review_ok = (decision.get("status") == "confirmed" and decision.get("reviewer_type") == "human"
                 and all(isinstance(decision.get(k),str) and decision[k].strip() for k in ["reviewer","reviewed_at","reason"]))
    if review_ok:
        try:
            validate_mapping(kind,confirmed_fields)
            mapped = [f for item in confirmed_fields.values() for f in (item if isinstance(item,list) else [item])]
            if any(f not in profiles for f in mapped):
                raise ValueError("Mapped field absent from schema")
        except ValueError:
            error(None, "Confirmed mapping contains absent fields or missing required canonical roles")
            review_ok = False
        if review_ok and profiles[confirmed_fields['id']].get('duplicate_nonblank_count',0):
            error(None,"Confirmed unique-ID mapping contains duplicate values")
            review_ok=False
    result["mapping_review"] = {**decision, "status": "confirmed" if review_ok else "pending"}
    important = set(f for item in (confirmed_fields if review_ok else proposal["suggested_fields"]).values()
                    for f in (item if isinstance(item,list) else [item]))
    result["important_field_quality"] = {f:profiles[f] for f in sorted(important) if f in profiles}
    for field,profile in result['important_field_quality'].items():
        if profile['null_count'] or profile['blank_count'] or profile['missing_count']:
            result['warnings'].append(f"Mapped/proposed field {field} has null, blank or missing values; see field_profiles")
    result["ready_for_import"] = confirmed and review_ok and result["error_count"] == 0
    result["status"] = "invalid" if result["error_count"] else "ready" if result["ready_for_import"] else "needs_review"
    return result


def validate_county(directory, output, *, source_directory=None, decisions_path=None):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    previous_path = directory / "export_metadata.json"
    previous = read_json(previous_path) if previous_path.exists() else {}
    old = {d["dataset"]:d for d in previous.get("datasets",[])}
    decisions = read_json(decisions_path) if decisions_path else {"datasets":{}}
    if not isinstance(decisions.get("datasets"),dict):
        raise ValueError("Mapping decisions require a datasets object keyed by dataset kind")
    manifest = {"schema_version": 1, "generated_at": _now(), "expected_directory":str(directory),
                "source_directory":str(Path(source_directory).resolve()) if source_directory else None,
                "datasets":[], "missing_datasets":[], "changes":[], "status":"pending", "real_world_accuracy_measured":False}
    for kind in GEOMETRIES:
        path = directory / f"{kind}.geojson"
        if not path.exists() and source_directory:
            path = Path(source_directory).resolve() / path.name
        if not path.is_file():
            manifest["missing_datasets"].append(kind)
            if kind in old:
                manifest["changes"].append({"dataset":kind,"changes":["dataset_removed"]})
            continue
        print(f"Validating {kind}: {path.stat().st_size:,} bytes", flush=True)
        decision = decisions["datasets"].get(kind,{})
        supplied = {**old.get(kind,{}).get("source_metadata",{}),**decision.get("source_metadata",{})}
        result = inspect_dataset(path,kind,analyst_metadata=supplied,decision=decision)
        manifest["datasets"].append(result)
        changes = [key for key in ["sha256","feature_count","available_fields","schema","geometry_types"]
                   if kind in old and key in old[kind] and old[kind][key]!=result[key]]
        if kind not in old:
            changes=["new_dataset"]
        if changes:
            manifest["changes"].append({"dataset":kind,"changes":changes})
        print(f"  {result['feature_count']:,} features; {result['status']}; {result['error_count']} error(s)",flush=True)
    invalid = [d["dataset"] for d in manifest["datasets"] if d["error_count"]]
    ready = [d for d in manifest["datasets"] if d["ready_for_import"]]
    manifest.update(status="invalid" if invalid else "ready" if ready else "needs_review" if manifest["datasets"] else "awaiting_reference_data",
                    invalid_datasets=invalid, ready_datasets=[d["dataset"] for d in ready])
    output.mkdir(parents=True,exist_ok=False)
    directory.mkdir(parents=True,exist_ok=True)
    if previous_path.exists():
        history = directory/"metadata_history"
        history.mkdir(exist_ok=True)
        archived = history/f"export_metadata-{file_sha256(previous_path)}.json"
        if not archived.exists():
            archived.write_bytes(previous_path.read_bytes())
        manifest["previous_manifest"]={"path":str(archived),"sha256":file_sha256(archived)}
    write_json(previous_path,manifest)
    (output/"export_metadata.json").write_bytes(previous_path.read_bytes())
    write_field_inventory(manifest,output)
    template={"schema_version":1,"instructions":"Review actual fields and source export provenance. Proposed fields are NOT approved. Confirm roles explicitly, provide reviewer/reason/time, retain dataset hash; do not change clue approvals.","datasets":{}}
    config={"crs":CRS,"require_confirmed_mappings":True,"datasets":[]}
    for d in manifest["datasets"]:
        kind=d["dataset"]
        template["datasets"][kind]={"dataset_sha256":d["sha256"],"status":None,"reviewer":None,"reviewer_type":None,
                                     "reviewed_at":None,"reason":None,"fields":d["mapping_proposal"]["suggested_fields"],
                                     "crs_confirmed":False,"output_crs":None,"source_metadata":d["source_metadata"]}
        if d["ready_for_import"]:
            source=d["source_metadata"]
            config["datasets"].append({"id":kind,"kind":kind,"path":d["path"],"fields":d["mapping_review"]["fields"],
                "mapping_review":d["mapping_review"],"metadata":{**source,"authority":source.get("data_owner") or "User-provided Brunswick County reference export",
                "source_layer":source.get("source_feature_class") or d["filename"],"output_crs":CRS,"synthetic":False,
                "export_sha256":d["sha256"],"validation_manifest_sha256":file_sha256(previous_path)}})
    write_json(output/"mapping-decisions.template.json",template)
    write_json(output/"reference-config.confirmed.json",config)
    write_json(output/"mapping-proposals.json",{d["dataset"]:d["mapping_proposal"] for d in manifest["datasets"]})
    lines=["# County reference readiness", "",f"Status: {manifest['status']}. Missing datasets: {', '.join(manifest['missing_datasets']) or 'none'}.",
           "", "Mappings are proposals until independently confirmed. Existing clue approvals are unchanged.", ""]
    for d in manifest["datasets"]:
        lines += [f"## {d['dataset']}","",f"{d['feature_count']:,} features; {d['status']}; SHA-256 `{d['sha256']}`.",
                  f"Geometry: {json.dumps(d['geometry_types'])}. Extent: {d['extent']}.",
                  f"Output CRS evidence: {json.dumps(d['coordinate_system'])}.","", "Fields: " + ", ".join(d["available_fields"]),"",
                  "```json",json.dumps(d["mapping_proposal"],indent=2),"```","",
                  "Warnings: " + "; ".join(d["warnings"]),f"Errors: {d['error_count']} (up to 50 examples in JSON).",""]
    (output/"READINESS.md").write_text("\n".join(lines),encoding="utf-8")
    (output/"validation.log").write_text("\n".join(f"{d['dataset']}: {d['status']}; {d['feature_count']} features; {d['error_count']} errors" for d in manifest["datasets"])+"\n",encoding="utf-8")
    return manifest
