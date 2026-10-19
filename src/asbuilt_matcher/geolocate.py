"""Deterministic, read-only candidate areas from accepted clue exports.

Scores are ranking points, not probabilities. Unaccepted input stays excluded;
this module never edits or re-verifies a clue. Unsupported kinds stay context.
"""

from collections import defaultdict
import hashlib
import itertools
import json
import math
import re

from .clue_review import analyst_accepted
from .geo_geometry import (extent_diagonal, geometry_distance, neighborhood,
                           point_distance, road_intersections)
from .geo_names import match_name, normalize_identifier, normalize_name
from .geo_aliases import compile_aliases, match_alias
from .geo_corridors import corridor_candidates

KIND_DATASETS = {"street_name": "roads", "subdivision_name": "subdivisions",
                 "parcel_number": "parcels", "lot_number": "parcels", "address": "addresses",
                 "municipal_name": "town_limits", "township_name": "townships", "postal_zone": "postal_zones"}
CONTEXT_KINDS = {"municipal_name", "township_name", "postal_zone"}
CONTEXT_DATASETS = {KIND_DATASETS[k] for k in CONTEXT_KINDS}
DEFAULT_SETTINGS = {"fuzzy_threshold": 0.86, "spatial_tolerance_m": 75.0,
                    "ambiguity_margin": 10.0, "max_area_diagonal_m": 5000.0,
                    "max_matches_per_clue": 200, "max_candidates": 2000, "corridor_gap_m":5.0}
WEIGHTS = {"street_name": 30, "subdivision_name": 30, "parcel_number": 40, "lot_number": 18,
           "address":35,"municipal_name":6,"township_name":4,"postal_zone":4}


def settings_for(settings=None):
    settings = settings or {}
    if set(settings) - set(DEFAULT_SETTINGS):
        raise ValueError("Unknown geographic ranking setting")
    result = {**DEFAULT_SETTINGS, **settings}
    for key, value in result.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Invalid setting: {key}")
    if not 0.5 <= result["fuzzy_threshold"] <= 1:
        raise ValueError("fuzzy_threshold must be between 0.5 and 1")
    if (not 1 <= result["spatial_tolerance_m"] <= 1000 or result["ambiguity_margin"] < 0
            or result["max_area_diagonal_m"] <= 0 or not .01 <= result['corridor_gap_m'] <= 100):
        raise ValueError("Invalid geographic distance/margin settings")
    for key in ["max_matches_per_clue", "max_candidates"]:
        if not isinstance(result[key], int) or result[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    return result


def clue_key(clue):
    kind = clue["kind"]
    value = (normalize_identifier(clue["text"], lot=kind == "lot_number") if kind in {"parcel_number", "lot_number", "postal_zone"}
             else normalize_name(clue["text"], street=kind in {"street_name","address"}))
    return kind, value


def feature_match(clue, feature, settings, *, aliases=None):
    kind = clue["kind"]
    if KIND_DATASETS.get(kind) != feature["kind"]:
        return None
    values = feature["values"]
    if kind in {"parcel_number", "lot_number", "postal_zone"}:
        label = values.get({"parcel_number":"parcel_id","lot_number":"lot","postal_zone":"name"}[kind])
        if label is None or not str(label).strip():
            return None
        a, b = normalize_identifier(clue["text"], lot=kind == "lot_number"), normalize_identifier(label, lot=kind == "lot_number")
        if a != b:
            return None
        match = {"match_type": "exact_identifier", "similarity": 1.0, "normalized_query": a, "normalized_reference": b}
    else:
        labels = [values["address"] if kind == "address" else values["name"], *feature["aliases"]]
        if kind == "subdivision_name" and values.get("phase") is not None:
            labels.append(f"{values['name']} PHASE {values['phase']}")
        matches = [(match_name(clue["text"], str(label), street=kind in {"street_name","address"}, threshold=settings["fuzzy_threshold"]), str(label))
                   for label in labels]
        matches = [(m, label) for m, label in matches if m]
        scoped=match_alias(clue['text'],feature,aliases) if kind=='street_name' else None
        if not matches and not scoped:return None
        order = {"exact": 3, "normalized": 2, "approximate": 1}
        if matches:
            match,label=max(matches,key=lambda pair:(order[pair[0]['match_type']],pair[0]['similarity'],pair[1]))
        if scoped and (not matches or match['match_type']=='approximate'):
            match,label=scoped,values['name']
    return {**match, "clue_id": clue["clue_id"], "clue_kind": kind, "reference_label": str(label),
            "feature_key": feature["feature_key"], "dataset_id": feature["dataset_id"], "native_id": feature["native_id"]}


def _stable_id(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:20]


def _seeds(matches, features, origin, tolerance, max_candidates):
    keys = sorted({m["feature_key"] for key,group in matches.items() if key[0] not in CONTEXT_KINDS for m in group})
    seeds = []
    for key in keys:
        f=features[key]
        bbox=neighborhood(f['geometry']['coordinates'],tolerance,origin) if f['geometry']['type']=='Point' else f['bbox']
        seeds.append({"kind":"reference_extent","feature_keys":[key],"bbox":bbox})
    # Use distinct road label groups. Segments of the same named road do not
    # provide two independent clues or an intersection bonus.
    road_groups = [group for key, group in matches.items() if key[0] == "street_name"]
    truncated = len(seeds) > max_candidates
    intersections = []
    for left, right in itertools.combinations(road_groups, 2):
        for a, b in itertools.product(left, right):
            fa, fb = features[a["feature_key"]], features[b["feature_key"]]
            if fa["feature_key"] == fb["feature_key"]:
                continue
            level_a, level_b = fa["values"].get("level"), fb["values"].get("level")
            if level_a is not None and level_b is not None and str(level_a) != str(level_b):
                continue
            for point in road_intersections(fa["geometry"], fb["geometry"], origin):
                intersections.append({"kind": "intersection_neighborhood", "feature_keys": sorted([fa["feature_key"], fb["feature_key"]]),
                                      "point": point, "bbox": neighborhood(point, tolerance, origin),
                                      "grade_status": "equal_exported_levels" if level_a is not None and level_b is not None else "unknown"})
                if len(intersections) >= max_candidates:
                    return intersections[:max_candidates], True
    # Prefer local intersections if the safety cap is reached, but never call a
    # truncated search a definitive proposed location.
    combined = intersections + seeds
    return combined[:max_candidates], truncated or len(combined) > max_candidates


def generate_candidates(clues, catalog, *, settings=None, document_id="", aliases=None):
    settings = settings_for(settings)
    usable = [c for c in clues if c["kind"] in KIND_DATASETS]
    groups = defaultdict(list)
    for c in usable:
        groups[clue_key(c)].append(c)
    features = {f["feature_key"]: f for f in catalog["features"]}
    matches, broad, inventory = {}, [], []
    for key, rows in sorted(groups.items()):
        found = [m for f in features.values() if (m := feature_match(rows[0], f, settings, aliases=aliases))]
        inventory.append({"clue_ids": [c["clue_id"] for c in rows], "kind": key[0], "text": rows[0]["text"],
                          "reference_match_count": len(found), "dataset_kind": KIND_DATASETS[key[0]],
                          "dataset_available": any(d["kind"] == KIND_DATASETS[key[0]] for d in catalog["datasets"])})
        # No arbitrary first N matches: broad labels are withheld as seeds.
        if len(found) > settings["max_matches_per_clue"]:
            broad.append({"kind": key[0], "normalized_text": key[1], "match_count": len(found), "reason": "too_many_reference_matches"})
            matches[key] = []
        else:
            matches[key] = found
    origin = catalog.get("distance_origin")
    if not origin or not any(matches.values()):
        return [], {"broad_clues": broad, "search_truncated": False, "clue_match_inventory": inventory}
    corridors=corridor_candidates(groups,matches,features,origin,settings,document_id) if aliases and aliases['entries'] else []
    primary_groups=[key for key in groups if key[0] not in CONTEXT_KINDS]
    same_road_groups=(primary_groups and all(k[0]=='street_name' for k in primary_groups)
                      and len({tuple(sorted(m['feature_key'] for m in matches[k])) for k in primary_groups})==1)
    if corridors and same_road_groups:
        corridors.sort(key=lambda c:(-c['score'],c['candidate_id']))
        truncated=len(corridors)>settings['max_candidates']
        corridors=corridors[:settings['max_candidates']]
        for rank,c in enumerate(corridors,1):c['rank']=rank
        return corridors,{'broad_clues':broad,'search_truncated':truncated,'clue_match_inventory':inventory}
    seeds, truncated = _seeds(matches, features, origin, settings["spatial_tolerance_m"], settings["max_candidates"])
    candidates = []
    for seed in seeds:
        anchor = features[seed["feature_keys"][0]]["geometry"]
        supporting, missing, conflicts = [], [], []
        score = 0.0
        corroboration_keys = set()
        # Process parcel before lot so a matching lot on a neighboring parcel
        # cannot corroborate an incompatible parcel ID merely by proximity.
        parcel_keys = None
        for key in sorted(groups, key=lambda k: (k[0] == "lot_number", k)):
            nearby = []
            for match in matches[key]:
                f = features[match["feature_key"]]
                distance = (point_distance(seed["point"], f["geometry"], origin) if "point" in seed
                            else geometry_distance(anchor, f["geometry"], origin))
                if distance <= settings["spatial_tolerance_m"]:
                    if key[0] == "lot_number" and parcel_keys is not None and match["feature_key"] not in parcel_keys:
                        continue
                    nearby.append({**match, "distance_to_anchor_m": round(distance, 3)})
            if key[0] == "parcel_number":
                current = {m["feature_key"] for m in nearby}
                parcel_keys = current if parcel_keys is None else parcel_keys & current
            if not nearby:
                reason = "matching_reference_elsewhere_or_incompatible_parcel" if matches[key] else "no_reference_name_match"
                item = {"clue_ids": [c["clue_id"] for c in groups[key]], "kind": key[0], "text": groups[key][0]["text"], "reason": reason}
                (conflicts if matches[key] else missing).append(item)
                score -= 12 if matches[key] else 6
                continue
            best = max(nearby, key=lambda m: (m["match_type"] in {"exact", "exact_identifier"}, m["similarity"], m["match_type"] == "normalized"))
            multiplier = 1 if best["match_type"] in {"exact", "exact_identifier"} else 0.93 if best["match_type"] == "normalized" else .85 if best['match_type']=='scoped_alias' else 0.65 * best["similarity"]
            points = round(WEIGHTS[key[0]] * multiplier, 3)
            corroboration_key = (key[0], tuple(sorted(m["feature_key"] for m in nearby)))
            duplicate_alias = corroboration_key in corroboration_keys
            if duplicate_alias:
                points = 0.0
            if key[0] not in CONTEXT_KINDS:
                corroboration_keys.add(corroboration_key)
            score += points
            supporting.append({"kind": key[0], "text": groups[key][0]["text"],
                               "clue_ids": [c["clue_id"] for c in groups[key]], "points": points,
                               "duplicate_reference_alias": duplicate_alias,
                               "matches": sorted(nearby, key=lambda m: m["feature_key"]), "best_match_type": best["match_type"]})
        bonuses = []
        independent_groups = len(corroboration_keys)
        if independent_groups > 1:
            score += 10
            bonuses.append({"reason": "multiple distinct clue groups meet the same reference area/neighborhood", "points": 10})
        if seed["kind"] == "intersection_neighborhood":
            score += 20
            bonuses.append({"reason": "two named road geometries cross in 2D; at-grade connectivity not established", "points": 20})
        exact_parcel = any(e["kind"] == "parcel_number" and e["best_match_type"] == "exact_identifier" for e in supporting)
        exact_address = any(e["kind"] == "address" and e["best_match_type"] in {"exact","normalized"} for e in supporting)
        size = extent_diagonal(seed["bbox"], origin)
        qualified = (independent_groups >= 2 or exact_parcel or exact_address) and size <= settings["max_area_diagonal_m"]
        feature_keys = sorted({m["feature_key"] for e in supporting for m in e["matches"]} | set(seed["feature_keys"]))
        limitations = ["Reference-derived area only; drawing is not georeferenced.",
                       "Distances use a bounded WGS84 ellipsoidal east/north tangent-plane projection, not survey registration."]
        if seed["kind"] == "reference_extent":
            limitations.append("Extent of an anchor reference feature; nearby supporting features can extend beyond it. No drawing footprint inferred.")
        else:
            limitations.append("Crossing may be grade separated; buffer radius is a search parameter, not a measured positional error.")
        if size > settings["max_area_diagonal_m"]:
            limitations.append("Reference extent exceeds the configured useful-area size; insufficient localization specificity.")
        context = []
        for f in features.values():
            if f['kind'] in CONTEXT_DATASETS and geometry_distance(anchor,f['geometry'],origin)==0:
                context.append({"dataset_id":f['dataset_id'],"native_id":f['native_id'],"kind":f['kind'],
                                "name":f['values']['name'],"basis":"2D overlap with anchor reference geometry", "points":0})
        candidates.append({"candidate_id": _stable_id([document_id, seed]), "score": round(score, 3), "qualified": qualified,
                           "match_type": seed["kind"], "crs": "EPSG:4326", "bbox": seed["bbox"],
                           "area_diagonal_m": round(size, 2), "anchor_feature_keys": seed["feature_keys"],
                           "intersection": {"reference_point": seed["point"], "search_radius_m": settings["spatial_tolerance_m"],
                                            "grade_status": seed["grade_status"]} if "point" in seed else None,
                           "evidence": supporting, "bonuses": bonuses, "conflicts": conflicts, "missing": missing,
                           "spatial_context":sorted(context,key=lambda c:(c['dataset_id'],str(c['native_id']))),
                           "penalties": {"conflicting_group_points": -12, "missing_group_points": -6},
                           "supporting_features": [{"feature_key": k, "dataset_id": features[k]["dataset_id"],
                                                    "native_id": features[k]["native_id"], "kind": features[k]["kind"],
                                                    "bbox": features[k]["bbox"]} for k in feature_keys],
                           "limitations": limitations, "analyst_review_status": "pending"})
    # Remove alternate anchors for exactly the same evidence, keeping the best
    # score and most focused extent. Distinct intersection neighborhoods survive.
    unique = {}
    for candidate in sorted(candidates, key=lambda c: (-c["score"], c["area_diagonal_m"], c["candidate_id"])):
        key = (tuple(f["feature_key"] for f in candidate["supporting_features"]),
               tuple(tuple(e["clue_ids"]) for e in candidate["evidence"]),
               tuple(round(n, 7) for n in candidate["bbox"]) if candidate["intersection"] else None)
        if not candidate["intersection"] and any(existing[:2] == key[:2] for existing in unique):
            # Keep focused crossing neighborhoods over a second, broad anchor
            # for the same evidence. Multiple distinct crossings still survive.
            continue
        if key not in unique:
            unique[key] = candidate
    result = sorted([*unique.values(),*corridors], key=lambda c: (-c["score"], -int(c["qualified"]), c["area_diagonal_m"], c["candidate_id"]))
    if len(result)>settings['max_candidates']:
        result=result[:settings['max_candidates']];truncated=True
    for rank, candidate in enumerate(result, 1):
        candidate["rank"] = rank
    return result, {"broad_clues": broad, "search_truncated": truncated, "clue_match_inventory": inventory}


def locate_documents(export, catalog=None, *, settings=None, alias_registry=None):
    settings = settings_for(settings)
    aliases=compile_aliases(alias_registry,catalog)
    clues = export.get("clues")
    if not isinstance(clues, list):
        raise ValueError("Expected existing clue export with a clues array")
    accepted, excluded, seen = [], [], set()
    for clue in clues:
        if not analyst_accepted(clue):
            excluded.append({"clue_id": clue.get("clue_id"), "reason": "not_independently_accepted"})
            continue
        if (not isinstance(clue.get("document_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", clue["document_sha256"])
                or not isinstance(clue.get("page_number"), int) or isinstance(clue["page_number"], bool) or clue["page_number"] < 1
                or not isinstance(clue.get("text"), str) or not clue["text"].strip() or not clue.get("source_pdf")
                or not clue.get("clue_id") or clue["clue_id"] in seen):
            raise ValueError("Accepted clue export requires unique IDs, document hashes, page numbers and nonempty evidence text")
        seen.add(clue["clue_id"])
        accepted.append(clue)
    groups = defaultdict(list)
    for clue in accepted:
        groups[(clue["document_sha256"], clue["page_number"])].append(clue)
    drawings = []
    available = bool(catalog and catalog["features"])
    for (document_hash, page), rows in sorted(groups.items()):
        candidates, diagnostics = generate_candidates(rows, catalog, settings=settings, document_id=f"{document_hash}:{page}",aliases=aliases) if available else ([], {"broad_clues": [], "search_truncated": False})
        qualified = [c for c in candidates if c["qualified"]]
        corridors=[c for c in candidates if c['match_type']=='road_corridor']
        if not available:
            status = "awaiting_reference_data"
        elif corridors and (not qualified or candidates[0]['match_type']=='road_corridor'):
            status='ambiguous_corridors' if len(corridors)>1 or corridors[0]['conflicts'] or corridors[0]['missing'] or diagnostics['search_truncated'] else 'corridor_identified'
        elif not qualified or not candidates[0]["qualified"]:
            status = "insufficient_evidence"
        elif (diagnostics["search_truncated"] or diagnostics["broad_clues"] or catalog.get("status") == "partial"
              or candidates[0]["conflicts"] or candidates[0]["missing"]
              or len(qualified) > 1 and qualified[0]["score"] - qualified[1]["score"] < settings["ambiguity_margin"]):
            status = "ambiguous"
        else:
            status = "proposed_area"
        drawings.append({"drawing_id": f"{document_hash}:{page}", "source_pdf": rows[0]["source_pdf"],
                         "document_sha256": document_hash, "page_number": page,
                         "sheet_numbers": [c["text"] for c in rows if c["kind"] == "sheet_number"],
                         "status": status, "crs": "EPSG:4326", "analyst_review_status": "pending",
                         "geographic_resolution":{"name_recognized":any(r.get('reference_match_count',0)>0 for r in diagnostics.get('clue_match_inventory',[])),
                                                  'roadway_or_route_matched':bool(corridors) or any(e['kind']=='street_name' for c in candidates for e in c['evidence']),
                                                  'candidate_area_generated':bool(qualified),'drawing_footprint_verified':False},
                         "accepted_clues": rows, "localizing_clue_ids": [c["clue_id"] for c in rows if c["kind"] in KIND_DATASETS],
                         "context_clues": [{"clue_id": c["clue_id"], "kind": c["kind"], "text": c["text"],
                                            "reason": "not a supported reference identifier; retained as context"} for c in rows if c["kind"] not in KIND_DATASETS],
                         "candidates": candidates, "diagnostics": diagnostics,
                         "limitations": ["No asset associations or drawing registration produced.",
                                         "Landmarks/projects remain context without authoritative matching layers; context boundaries do not independently establish a location."]})
    cross_sheet = []
    for left, right in itertools.combinations(drawings, 2):
        left_keys = defaultdict(list)
        right_keys = defaultdict(list)
        kinds = {"street_name", "subdivision_name", "project_name", "landmark", "parcel_number"}
        for clue in left["accepted_clues"]:
            if clue["kind"] in kinds:
                left_keys[clue_key(clue)].append(clue["clue_id"])
        for clue in right["accepted_clues"]:
            if clue["kind"] in kinds:
                right_keys[clue_key(clue)].append(clue["clue_id"])
        shared = [{"kind": key[0], "normalized_text": key[1], "left_clue_ids": left_keys[key], "right_clue_ids": right_keys[key]}
                  for key in sorted(left_keys.keys() & right_keys.keys())]
        cross_sheet.append({"left_drawing_id": left["drawing_id"], "right_drawing_id": right["drawing_id"],
                            'shared_corridor_keys':sorted({c['corridor_key'] for c in left['candidates'] if c.get('corridor_key')} & {c['corridor_key'] for c in right['candidates'] if c.get('corridor_key')}),
                            "shared_clues": shared, "interpretation": "shared_label_evidence" if shared else "no_shared_label_evidence",
                            "limitations": "Shared labels suggest common project/area context only; no location, score or approval transferred. Filenames/sheet sequence not used."})
    return {"schema_version": 1, "crs": "EPSG:4326", "settings": settings, "drawings": drawings,
            "excluded_clues": excluded, "cross_sheet": cross_sheet,
            "status": "awaiting_reference_data" if not available else "complete",
            "algorithm": "bounded-reference-area-ranking-v3",
            'alias_registry':alias_registry,
            "distance_model":{"type":"WGS84 ellipsoid local east/north tangent-plane projection", "units":"metres",
                              "origin":catalog.get('distance_origin') if catalog else None,"maximum_catalog_extent_m":250000},
            "scoring_policy": {"clue_weights": WEIGHTS, "exact_multiplier": 1, "normalized_multiplier": 0.93, 'scoped_alias_multiplier':.85,
                               "approximate_multiplier": "0.65 * SequenceMatcher similarity",
                               "multiple_group_bonus": 10, "road_intersection_bonus": 20,
                               "conflicting_group_penalty": -12, "missing_group_penalty": -6,
                               "duplicate_reference_alias_points": 0},
            "score_semantics": "Deterministic ranking points, not statistical probabilities or analyst approval."}
