"""Read-only technical PDF evidence for the representative study.

Annotation appearances participate in MuPDF text/path/image extraction. Render the
intact composite first, then remove annotations in memory only to inspect base content.
The document is never saved. Counts alone cannot distinguish engineering semantics.
"""

from collections import Counter
import json
import math
from pathlib import Path
import re
import unicodedata

from .pdf_extract import file_sha256, load_pdf_backend, write_json
from .raster import render_region
from .pdf_classify import classify_evidence, rectangle_union_area, text_candidates


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return [plain(v) for v in value]


def _extent(boxes):
    boxes = [b for b in boxes if len(b) == 4 and all(math.isfinite(x) for x in b)]
    return ([min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None)


def native_text(page, bounds):
    # Keep stream transcription: sort=True can synthesize large runs of layout spaces.
    # Positioned words/lines below support reading order without inflating counts.
    text = page.get_text("text", sort=False)
    words = page.get_text("words", sort=True)
    blocks = page.get_text("dict", flags=0)["blocks"]  # Do not load raster payloads.
    lines = [{"text": "".join(s["text"] for s in line["spans"]),
              "bbox": list(line["bbox"]), "direction": list(line["dir"]),
              "spans": plain(line["spans"])}
             for b in blocks if b["type"] == 0 for line in b["lines"]]
    traces = page.get_texttrace()
    trace_counts = Counter()
    for t in traces:
        key = "invisible" if t.get("type") == 3 or t.get("opacity", 1) == 0 else "visible_render_instruction"
        trace_counts[key] += len(t["chars"])
    nonspace = [ch for ch in text if not ch.isspace()]
    suspect = sum(ch == "\ufffd" or unicodedata.category(ch) in {"Co", "Cc"} for ch in nonspace)
    cells = set()
    for line in lines:
        x, y = (line["bbox"][0] + line["bbox"][2]) / 2, (line["bbox"][1] + line["bbox"][3]) / 2
        cells.add((min(3, max(0, int(4 * x / bounds[2]))), min(3, max(0, int(4 * y / bounds[3])))))
    return {"text": text, "characters": len(text), "nonspace_characters": len(nonspace),
            "words": [dict(bbox=list(w[:4]), text=w[4], block=w[5], line=w[6], word=w[7]) for w in words],
            "lines": lines, "line_count": len(lines), "word_count": len(words),
            "suspect_characters": suspect, "suspect_character_fraction": suspect / max(1, len(nonspace)),
            "occupied_4x4_cells": plain(sorted(cells)), "occupied_cell_count": len(cells),
            "render_character_counts": dict(trace_counts),
            "quality_limitations": "Visibility from rendering instructions only; occlusion, incorrect mappings and outlined glyphs require visual review. Searchable text does not prove digital plot origin."}


def vector_evidence(paths, bounds):
    operations = Counter(item[0] for p in paths for item in p["items"])
    path_types = Counter(p["type"] for p in paths)
    styles = Counter()
    border, red, fractional, coordinate_values = [], [], 0, 0
    boundaries, horizontal = [], []
    area = bounds[2] * bounds[3]
    for index, path in enumerate(paths):
        box = path.get("rect", (0, 0, 0, 0))
        box_area = max(0, box[2] - box[0]) * max(0, box[3] - box[1])
        if box_area >= .9 * area and len(path["items"]) <= 5:
            border.append(index)
        style = {k: plain(path[k]) for k in ("color", "fill", "width", "dashes", "stroke_opacity", "fill_opacity", "layer") if k in path}
        styles[json.dumps(style, sort_keys=True)] += 1
        for color in (path.get("color"), path.get("fill")):
            if color and len(color) == 3 and color[0] > .6 and color[1] < .4 and color[2] < .4:
                red.append(index)
                break
        for item in path["items"]:
            if item[0] == "re":
                r = item[1]
                if .05 * area <= max(0, r[2] - r[0]) * max(0, r[3] - r[1]) <= .95 * area:
                    boundaries.append({"path_index": index, "bbox": list(r), "status": "unverified_view_or_table_boundary_candidate"})
            if item[0] == "l":
                p0, p1 = item[1:3]
                if abs(p0[1] - p1[1]) <= .5 and 5 <= abs(p0[0] - p1[0]) <= bounds[2] * .5:
                    horizontal.append({"path_index": index, "endpoints": [list(p0), list(p1)]})
            for value in item[1:]:
                if isinstance(value, (tuple, list)):
                    for coord in value:
                        if isinstance(coord, (float, int)):
                            coordinate_values += 1
                            fractional += int(abs(coord - round(coord)) > 1e-5)
    return {"path_count": len(paths), "path_types": dict(path_types), "operations": dict(operations),
            "bbox": _extent([p["rect"] for p in paths]), "non_border_path_count": len(paths) - len(border),
            "border_or_background_candidates": border,
            "styles": [{"style": json.loads(k), "path_count": v} for k, v in styles.most_common()],
            "red_color_path_indices": red, "view_boundary_candidates": boundaries,
            "horizontal_segment_candidates": horizontal,
            "fractional_coordinate_values": fractional, "coordinate_values": coordinate_values,
            "engineering_linework_status": "unverified_candidate" if paths else "none_detected",
            "limitations": "Paths may be outlined lettering, hatching, symbols or borders. Coordinates retain sub-point values but are not CAD objects, topology, ground coordinates or positional accuracy. Ordinary extraction does not resolve clipping/occlusion or original-versus-modified authority."}


def image_evidence(document, page, bounds):
    images = []
    for image in page.get_image_info(hashes=True, xrefs=True):
        row = plain(image)
        a, b, c, d, _, _ = image["transform"]
        x_length, y_length = math.hypot(a, b), math.hypot(c, d)
        row["effective_dpi_x"] = image["width"] * 72 / x_length if x_length else None
        row["effective_dpi_y"] = image["height"] * 72 / y_length if y_length else None
        row["pdf_filter"] = document.xref_get_key(image["xref"], "Filter")[1] if image["xref"] else "inline_or_unresolved"
        images.append(row)
    coverage = rectangle_union_area([im["bbox"] for im in images], bounds) / (bounds[2] * bounds[3])
    resources = [{"xref": r[0], "soft_mask_xref": r[1], "width": r[2], "height": r[3],
                  "bpc": r[4], "colorspace": r[5], "name": r[7], "filter": r[8],
                  "referencer": r[9] if len(r) > 9 else None} for r in page.get_images(full=True)]
    return {"occurrences": images, "occurrence_count": len(images), "resources": resources,
            "coverage_bbox_union": coverage,
            "coverage_method": "Union of visible-page-clipped image bounding boxes; upper bound for skewed images, masks, clipping and occlusion. Resource lists may contain unused objects."}


def geospatial_evidence(document, page):
    """Inspect page/catalog geospatial keys and referenced viewport/measure objects.

    A viewport alone is not geospatial. Structural hints never verify a geographic
    transform. No stream-wide keyword search or coordinate conversion is attempted.
    """
    candidates, examined = [], []
    for xref, role in ((page.xref, "page"), (document.pdf_catalog(), "catalog")):
        for key in ("LGIDict", "VP"):
            kind, value = document.xref_get_key(xref, key)
            if kind == "null":
                continue
            objects = [{"xref": xref, "key": key, "value": value}]
            pending = [int(n) for n in re.findall(r"(\d+)\s+\d+\s+R\b", value)]
            seen = set()
            geo_measure = bool(re.search(r"/Subtype\s*/GEO\b", value))
            while pending and len(seen) < 100:
                ref = pending.pop()
                if ref in seen:
                    continue
                seen.add(ref)
                raw = document.xref_object(ref)
                objects.append({"xref": ref, "object": raw[:20000]})
                geo_measure |= bool(re.search(r"/Subtype\s*/GEO\b", raw))
                # Follow only the relevant geospatial dictionary chain, not all resources.
                for child_key in ("Measure", "GCS", "DCS", "LGIDict"):
                    child_kind, child_value = document.xref_get_key(ref, child_key)
                    if child_kind != "null":
                        objects.append({"xref": ref, "key": child_key, "value": child_value[:20000]})
                        geo_measure |= bool(re.search(r"/Subtype\s*/GEO\b", child_value))
                        pending.extend(int(n) for n in re.findall(r"(\d+)\s+\d+\s+R\b", child_value))
            examined.append({"role": role, "key": key, "objects": objects, "traversal_truncated": bool(pending)})
            if key == "LGIDict" or geo_measure:
                candidates.append({"role": role, "key": key, "objects": objects,
                                   "status": "possible_unverified", "declared_crs_verified": False})
    return {"candidates": candidates, "examined": examined, "confirmed": False,
            "scope": "Page/catalog LGIDict and VP/Measure GEO. XMP, unusual nested forms or proprietary structures may escape this diagnostic. Absence is not certification of no georeferencing."}


def inspect_page(document, index, output, settings, criteria):
    page = document[index]
    row = {"page_number": index + 1, "status": "ok", "errors": [], "warnings": [],
           "rotation": page.rotation, "displayed_rect": list(page.rect),
           "rotation_matrix": list(page.rotation_matrix), "derotation_matrix": list(page.derotation_matrix),
           "boxes": {name: list(getattr(page, name)) for name in ("mediabox", "cropbox", "trimbox", "bleedbox", "artbox")}}
    page.set_rotation(0)  # Memory only, source is never saved.
    bounds = list(page.rect)
    row["bounds"] = bounds
    row["dimensions"] = {"width_points": bounds[2], "height_points": bounds[3],
                         "width_inches": bounds[2] / 72, "height_inches": bounds[3] / 72,
                         "width_mm": bounds[2] * 25.4 / 72, "height_mm": bounds[3] * 25.4 / 72,
                         "orientation_unrotated": "landscape" if bounds[2] > bounds[3] else "portrait" if bounds[2] < bounds[3] else "square"}
    directory = output / f"page-{index + 1:04d}"
    directory.mkdir()

    def collect(name, operation, default=None):
        try:
            return operation()
        except Exception as exc:
            row["errors"].append({"stage": name, "error": f"{type(exc).__name__}: {exc}"})
            return default

    row["preview"] = collect("composite_render", lambda: render_region(load_pdf_backend(), page, directory / "composite.png", bounds,
                                                                        settings["preview_dpi"], settings["max_preview_pixels"]))
    if row["preview"]:
        row["preview"].update(sha256=file_sha256(directory / "composite.png"), includes_annotations=True,
                              coordinate_system="Unrotated visible page points, MuPDF top-left; original PDF rotation separately recorded")
    annotations = list(page.annots() or [])
    row["annotations"] = [plain({"xref": a.xref, "type": a.type, "bbox": a.rect, "info": a.info,
                                  "colors": a.colors, "opacity": a.opacity, "flags": a.flags,
                                  "vertices": a.vertices,
                                  "appearance": document.xref_get_key(a.xref, "AP")[1]}) for a in annotations]
    row["widgets"] = [{"xref": w.xref, "field_name": w.field_name, "field_type": w.field_type_string,
                       "bbox": list(w.rect)} for w in (page.widgets() or [])]
    row["links"] = plain(page.get_links())
    # Composite extraction includes appearance streams, not just base page contents.
    composite_text = collect("composite_text", lambda: page.get_text("text", sort=False), "")
    composite_paths = collect("composite_vectors", lambda: len(page.get_cdrawings()))
    row["composite_images"] = collect("composite_images", lambda: image_evidence(document, page, bounds))
    row["geospatial"] = collect("geospatial", lambda: geospatial_evidence(document, page))
    for annotation in annotations:
        page.delete_annot(annotation)  # Only in-memory, after intact rendering/evidence.
    if annotations:
        # get_image_info caches occurrences on Page: deleting an annotation does not
        # invalidate that cache. Reload so stamp bitmaps do not leak into base counts.
        page = document.reload_page(page)
    text = collect("native_text", lambda: native_text(page, bounds))
    paths = collect("native_vectors", lambda: page.get_cdrawings())
    row["images"] = collect("native_images", lambda: image_evidence(document, page, bounds))
    row["fonts"] = plain(page.get_fonts(full=True))
    row["annotation_separation"] = {"method": "Intact composite rendered first; annotation objects removed and page reloaded only in memory for base-content extraction; source document never saved",
                                    "composite_text_characters": len(composite_text), "composite_vector_paths": composite_paths,
                                    "annotation_appearance_path_difference": composite_paths - len(paths) if composite_paths is not None and paths is not None else None}
    (directory / "composite-text.txt").write_text(composite_text, encoding="utf-8")
    row["text_file"] = "native-text.txt"
    if text is not None:
        (directory / row["text_file"]).write_text(text["text"], encoding="utf-8")
        write_json(directory / "native-text.json", text)
        row["text"] = {k: v for k, v in text.items() if k not in {"text", "lines", "words"}}
        row["text"]["detail_file"] = "native-text.json"
        row["candidates"] = text_candidates(text["lines"], bounds)
        if text["suspect_characters"]:
            row["warnings"].append("Native text contains replacement, private-use or control characters")
    if paths is not None:
        # Compact complete path evidence; retain styling and every drawing operation.
        (directory / "native-vectors.json").write_text(json.dumps(plain(paths), ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        row["vectors"] = vector_evidence(paths, bounds)
        row["vectors"]["detail_file"] = "native-vectors.json"
        if not text or text["nonspace_characters"] < 30:
            if paths:
                row["warnings"].append("Native paths with little/no extractable base text: outlined lettering or nontext graphics may require OCR")
        # A graphical bar candidate requires nearby horizontal linework and a scale statement.
        scale_boxes = [s["bbox"] for s in row.get("candidates", {}).get("scale_statements", []) if s["kind"] != "not_to_scale"]
        row["graphical_scale_candidates"] = [s for s in row["vectors"]["horizontal_segment_candidates"]
                                              if any(min(b[0], b[2]) - 150 <= s["endpoints"][0][0] <= max(b[0], b[2]) + 150
                                                     and b[1] - 100 <= s["endpoints"][0][1] <= b[3] + 100 for b in scale_boxes)]
        row["vectors"]["horizontal_segment_count"] = len(row["vectors"].pop("horizontal_segment_candidates"))
    if row["images"] and row["images"]["coverage_bbox_union"]:
        row["warnings"].append("Raster/flattened colored edits cannot be isolated from originals without independent evidence")
    if row["annotations"]:
        row["warnings"].append("Separate annotation objects detected; authorship/date and red/orange colors do not establish construction authority")
    if row["errors"]:
        row["status"] = "partial"
    required = (text, paths, row["images"], row["geospatial"])
    if all(item is not None for item in required):
        evidence = {"raster_coverage": row["images"]["coverage_bbox_union"],
                    "non_border_vector_paths": row["vectors"]["non_border_path_count"],
                    "native_nonspace_characters": text["nonspace_characters"],
                    "suspect_character_fraction": text["suspect_character_fraction"],
                    "annotation_count": len(annotations), "geospatial_candidates": len(row["geospatial"]["candidates"])}
        row["classification"] = classify_evidence(evidence, criteria)
        row["classification"]["evidence"] = evidence
    else:
        row["classification"] = {"primary_class": "indeterminate", "labels": ["indeterminate"],
                                 "processing_paths": ["manual_content_review"], "reasons": ["Extraction incomplete"],
                                 "verification_status": "unreviewed", "author": "pdf-study-heuristic-v1"}
    row["registration_readiness"] = {"status": "not_registered", "effective_scale_verified": False,
                                    "approved_controls_in_this_study": 0, "independent_checkpoints_in_this_study": 0,
                                    "next_evidence": ["Identify engineering view and distinguish design versus modifications", "Verify scale for each view", "Collect independent geographic controls and separate checkpoints using Phase 2B.3"],
                                    "initial_placement": "Only a future analyst-review hint from scale/locality; no authoritative placement computed"}
    row["artifacts"] = [{"file": p.name, "sha256": file_sha256(p)} for p in sorted(directory.iterdir()) if p.is_file()]
    write_json(directory / "page.json", row)
    row["directory"] = directory.name
    return row


def inspect_document(source, output, settings, criteria):
    pdf = load_pdf_backend()
    record = {"sha256": file_sha256(source), "size_bytes": source.stat().st_size,
              "page_count": None, "pages": [], "status": "failed", "errors": [], "warnings": []}
    output.mkdir(parents=True)
    with source.open("rb") as stream:
        header = stream.read(1024)
    version = re.search(rb"%PDF-(\d+\.\d+)", header)
    record["header_pdf_version"] = version.group(1).decode("ascii") if version else None
    try:
        with pdf.open(source) as document:
            if not document.is_pdf:
                raise ValueError("Unsupported: file is not a PDF, regardless of extension")
            record.update(needs_password=bool(document.needs_pass), is_encrypted=bool(document.is_encrypted),
                          permissions=document.permissions, metadata=plain(document.metadata), is_repaired=bool(document.is_repaired))
            if document.needs_pass:
                raise ValueError("Encrypted PDF requires a password; password entry is not implemented")
            record["page_count"] = len(document)
            record["restrictions"] = {name: not bool(document.permissions & getattr(pdf, flag))
                                      for name, flag in (("copy", "PDF_PERM_COPY"), ("print", "PDF_PERM_PRINT"),
                                                         ("modify", "PDF_PERM_MODIFY"), ("annotate", "PDF_PERM_ANNOTATE"))}
            if any(record["restrictions"].values()):
                record["warnings"].append("PDF permission restrictions recorded; no password/security changes are attempted")
            if record["is_repaired"]:
                record["warnings"].append("MuPDF repaired the document in memory; inspect for content differences")
            record["optional_content_groups"] = plain(document.get_ocgs())
            record["xml_metadata_present"] = bool(document.get_xml_metadata())
            for index in range(len(document)):
                try:
                    row = inspect_page(document, index, output, settings, criteria)
                except Exception as exc:
                    row = {"page_number": index + 1, "status": "failed", "errors": [{"stage": "page", "error": f"{type(exc).__name__}: {exc}"}],
                           "classification": {"primary_class": "indeterminate", "labels": ["indeterminate"], "processing_paths": ["manual_content_review"],
                                              "verification_status": "unreviewed", "author": "pdf-study-heuristic-v1"}}
                record["pages"].append(row)
                record["errors"].extend(dict(e, page_number=index + 1) for e in row["errors"])
            record["status"] = "partial" if record["errors"] else "complete"
    except Exception as exc:
        record["errors"].append({"stage": "document", "error": f"{type(exc).__name__}: {exc}"})
    record["source_unchanged"] = file_sha256(source) == record["sha256"]
    if not record["source_unchanged"]:
        record["status"] = "failed"
        record["errors"].append({"stage": "preservation", "error": "Source changed during inspection; discard derived artifacts"})
    write_json(output / "document.json", record)
    return record
