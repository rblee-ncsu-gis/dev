"""Coverage-aware PDF triage. Evidence heuristics, never source authenticity or GIS truth."""

import math
import re

DEFAULT_CRITERIA = {
    "raster_dominance": .65, "hybrid_raster_coverage": .15,
    "incidental_image_coverage": .05, "substantial_vector_paths": 20,
    "text_rich_characters": 200, "minimum_usable_text_characters": 30,
    "maximum_suspect_character_fraction": .05,
}
LABELS = {"predominantly_raster", "predominantly_vector", "hybrid_raster_vector",
          "text_rich_digital", "separate_annotations", "possible_geospatial", "indeterminate"}


def criteria_with_defaults(settings=None):
    values = dict(DEFAULT_CRITERIA)
    if settings:
        if set(settings) - set(values):
            raise ValueError("Unknown classification criteria")
        values.update(settings)
    for key, value in values.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Criteria must be finite numbers")
        if key.endswith(("coverage", "dominance", "fraction")):
            if not 0 <= value <= 1:
                raise ValueError("Coverage criteria must lie in [0, 1]")
        elif type(value) is not int or value < 1:
            raise ValueError("Count criteria must be positive integers")
    if not values["incidental_image_coverage"] < values["hybrid_raster_coverage"] < values["raster_dominance"]:
        raise ValueError("Require incidental < hybrid < raster dominance")
    return values


def rectangle_union_area(rects, bounds):
    """Exact union of clipped axis-aligned boxes, not summed overlapping image areas.

    Boxes overestimate skewed/rotated image quadrilaterals and ignore content clipping,
    masks and later occlusion. Coverage is a diagnostic, not visible ink coverage.
    """
    clipped = []
    for x0, y0, x1, y1 in rects:
        box = max(bounds[0], x0), max(bounds[1], y0), min(bounds[2], x1), min(bounds[3], y1)
        if box[2] > box[0] and box[3] > box[1]:
            clipped.append(box)
    area = 0.
    edges = sorted({b[i] for b in clipped for i in (0, 2)})
    for left, right in zip(edges, edges[1:]):
        intervals = sorted((b[1], b[3]) for b in clipped if b[0] < right and b[2] > left)
        length, end = 0., -math.inf
        for lo, hi in intervals:
            length += max(0., hi - max(lo, end))
            end = max(end, hi)
        area += (right - left) * length
    return area


def classify_evidence(evidence, settings=None):
    c = criteria_with_defaults(settings)
    coverage = evidence["raster_coverage"]
    paths = evidence["non_border_vector_paths"]
    chars = evidence["native_nonspace_characters"]
    usable = chars >= c["minimum_usable_text_characters"] and evidence["suspect_character_fraction"] <= c["maximum_suspect_character_fraction"]
    substantial = paths >= c["substantial_vector_paths"]
    labels, reasons = [], []
    if coverage >= c["hybrid_raster_coverage"] and substantial:
        primary = "hybrid_raster_vector"
        reasons.append("Substantial native paths and substantial image bounding-box coverage")
    elif coverage >= c["raster_dominance"]:
        primary = "predominantly_raster"
        reasons.append("Raster occupies most page area; text or minor overlays do not establish native engineering linework")
    elif paths and coverage < c["hybrid_raster_coverage"]:
        primary = "predominantly_vector"
        reasons.append("Native drawing paths with no substantial raster area")
    elif chars >= c["text_rich_characters"] and coverage < c["hybrid_raster_coverage"]:
        primary = "text_rich_digital"
        reasons.append("Substantial native text without a dominant scan")
    else:
        primary = "indeterminate"
        reasons.append("Insufficient or ambiguous content for a predominant engineering content class")
    labels.append(primary)
    if primary != "text_rich_digital" and chars >= c["text_rich_characters"] and coverage < c["hybrid_raster_coverage"]:
        labels.append("text_rich_digital")
    if evidence["annotation_count"]:
        labels.append("separate_annotations")
    if evidence["geospatial_candidates"]:
        labels.append("possible_geospatial")
    paths_out = []
    if chars:
        paths_out.append("native_text_first" if usable else "native_text_quality_review")
    if paths:
        paths_out.append("native_vector_inspection")
    if primary == "predominantly_raster":
        paths_out.extend(["raster_preparation", "ocr_supplement" if usable else "ocr_primary"])
    elif primary == "hybrid_raster_vector":
        paths_out.extend(["separate_native_and_raster", "selective_ocr"])
    elif primary == "predominantly_vector":
        paths_out.extend(["native_scale_analysis", "selective_ocr_for_outlined_or_missing_text"])
    elif primary == "indeterminate":
        paths_out.append("manual_content_review")
    if evidence["annotation_count"]:
        paths_out.append("annotation_review")
    if evidence["geospatial_candidates"]:
        paths_out.append("verify_embedded_crs_and_viewports")
    paths_out.append("preserve_composite")
    return {"primary_class": primary, "labels": labels, "reasons": reasons,
            "processing_paths": paths_out, "usable_native_text_candidate": usable,
            "incidental_raster_candidate": 0 < coverage <= c["incidental_image_coverage"],
            "verification_status": "unreviewed", "author": "pdf-study-heuristic-v1"}


SCALE_PATTERNS = [
    ("feet_per_inch", re.compile(r'(\d+(?:\.\d+)?)\s*(?:INCH(?:ES)?|["\u2033])\s*=\s*(\d+(?:\.\d+)?)\s*(?:FEET|FOOT|FT\b|[\'\u2032])', re.I)),
    ("ratio", re.compile(r'(?<!\d)1\s*:\s*(\d{2,7})(?!\d)')),
    ("not_to_scale", re.compile(r'\b(?:NOT\s+TO\s+SCALE|N\.?\s*T\.?\s*S\.?)\b', re.I)),
]
ENTITY_PATTERNS = {
    "station": re.compile(r'\b\d{1,4}\+\d{2}(?:\.\d+)?\b'),
    "sheet_identifier": re.compile(r'\b(?:SHEET\s+[\w-]+(?:\s+OF\s+\d+)?|[CWS]-?\d{1,3})\b', re.I),
    "road_name": re.compile(r'\b(?:[\w\'-]+\s+){1,5}(?:ROAD|RD|STREET|ST|DRIVE|DR|LANE|LN|BOULEVARD|BLVD|HIGHWAY|HWY|COURT|CT)\b', re.I),
    "project_or_subdivision": re.compile(r'\b(?:SUBDIVISION|PROJECT|PHASE|CALABASH|LAKES|POINTE)\b', re.I),
    "pipe_or_construction_note": re.compile(r'\b(?:SEWER|WATER|MANHOLE|PIPE|VALVE|HYDRANT|CONSTRUCT|INSTALL|REPLACE)\b|\b\d+\s*(?:INCH|["\u2033])', re.I),
}


def text_candidates(lines, bounds):
    """Unverified lexical candidates with exact source line positions; no clue approval.

    Whole-page text permits wrapped scale recognition. Candidate bounding boxes cover
    every participating line; line-level candidates preserve their own source text.
    """
    scales, entities = [], []
    combined = "\n".join(line["text"] for line in lines)
    offsets, offset = [], 0
    for line in lines:
        offsets.append((offset, offset + len(line["text"]), line))
        offset += len(line["text"]) + 1
        x0, y0, x1, y1 = line["bbox"]
        # Layout hints, not detected title blocks or engineering view boundaries.
        region = "title_block_candidate" if x0 > bounds[2] * .60 and y0 > bounds[3] * .60 else "plan_or_other_text"
        for kind, pattern in ENTITY_PATTERNS.items():
            if pattern.search(line["text"]):
                entities.append({"kind": kind, "text": line["text"], "bbox": line["bbox"],
                                 "layout_hint": region, "method": "native_text_regex",
                                 "verification_status": "unverified"})
    for kind, pattern in SCALE_PATTERNS:
        for match in pattern.finditer(combined):
            matched = [line for lo, hi, line in offsets if lo < match.end() and hi > match.start()]
            box = [min(l["bbox"][0] for l in matched), min(l["bbox"][1] for l in matched),
                   max(l["bbox"][2] for l in matched), max(l["bbox"][3] for l in matched)]
            scales.append({"kind": kind, "text": match.group(), "bbox": box,
                           "method": "native_text_regex", "verification_status": "unverified",
                           "effective_page_scale_verified": False, "view_scope": "unknown",
                           "numeric_groups": list(match.groups())})
    return {"entities": entities, "scale_statements": scales,
            "multiple_statements": len(scales) > 1,
            "effective_page_scale": None, "registration_transform": None}
