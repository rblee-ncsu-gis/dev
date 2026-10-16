"""Native image evidence and page composites. No OCR or GIS dependency."""

from datetime import datetime, timezone
import hashlib
import logging
import math
from pathlib import Path
import re
import uuid

from .pdf_extract import file_sha256, load_pdf_backend, write_json

REGION_KINDS = {"title_block", "location_map", "plan_view_labels", "coordinate_annotations"}
LOGGER = logging.getLogger(__name__)


def validate_bbox(bbox, bounds):
    if len(bbox) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bbox):
        raise ValueError("bbox must contain four finite page-point numbers")
    x0, y0, x1, y1 = bbox
    if not (bounds[0] <= x0 < x1 <= bounds[2] and bounds[1] <= y0 < y1 <= bounds[3]):
        raise ValueError("bbox must have positive area and lie within the unrotated page")
    return list(bbox)


def validate_regions(regions):
    seen = set()
    for region in regions:
        if not isinstance(region.get("page_number"), int) or region["page_number"] < 1:
            raise ValueError("Region page_number must be a positive integer")
        if region.get("kind") not in REGION_KINDS:
            raise ValueError("Unsupported region kind")
        name = region.get("id", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", name) or (region["page_number"], name) in seen:
            raise ValueError("Region IDs must be safe filenames and unique within a page")
        seen.add((region["page_number"], name))


def render_region(pdf, page, destination, bbox, dpi, max_pixels):
    """Render normalized unrotated page coordinates with an explicit pixel mapping."""
    rect = pdf.Rect(bbox)
    scale = min(dpi / 72, math.sqrt(max_pixels / (rect.width * rect.height)))
    # Nonzero clip origins can expand both integer edges by one pixel.
    while (math.ceil(rect.x1 * scale) - math.floor(rect.x0 * scale)) * (
        math.ceil(rect.y1 * scale) - math.floor(rect.y0 * scale)
    ) > max_pixels:
        scale *= 0.99
    pix = page.get_pixmap(matrix=pdf.Matrix(scale, scale), clip=rect,
                          colorspace=pdf.csRGB, alpha=False, annots=True)
    pix.save(str(destination))
    return {"file": destination.name, "width": pix.width, "height": pix.height,
            "bbox": list(bbox), "requested_dpi": dpi, "effective_dpi": scale * 72,
            "resolution_capped": scale < dpi / 72, "scale": scale,
            "pixel_origin": [pix.x, pix.y],
            "page_to_pixel": [scale, 0, 0, scale, -pix.x, -pix.y]}


def extract_native(document, xref, output):
    image = document.extract_image(xref)
    if not image:
        raise ValueError(f"No extractable image for xref {xref}")
    # Keep PyMuPDF's extracted format and bytes, never resize or recompress.
    extension = image["ext"]
    if not re.fullmatch(r"[a-zA-Z0-9]+", extension):
        raise ValueError("Unexpected extracted image extension")
    filename = f"image-xref-{xref}.{extension}"
    (output / filename).write_bytes(image["image"])
    return {"xref": xref, "file": filename, "width": image["width"],
            "height": image["height"], "format": extension,
            "sha256": hashlib.sha256(image["image"]).hexdigest(),
            "pdf_filter": document.xref_get_key(xref, "Filter")[1],
            "pdf_mask": document.xref_get_key(xref, "Mask")[1],
            "pdf_image_mask": document.xref_get_key(xref, "ImageMask")[1],
            "pdf_decode": document.xref_get_key(xref, "Decode")[1],
            "bits_per_component": document.xref_get_key(xref, "BitsPerComponent")[1],
            "soft_mask_xref": image.get("smask", 0)}


def prepare_rasters(source, output, *, regions=None, dpi=200, max_pixels=40_000_000):
    """Preserve image resources and always render a complete page composite.

    The composite handles tiles, masks, overlays, inline images and clipping via
    MuPDF instead of assuming that individual image resources reproduce the page.
    Regions are explicit analyst-selected areas, never automatically detected.
    """
    source, output = Path(source).resolve(), Path(output).resolve()
    regions = list(regions or [])
    validate_regions(regions)
    if not math.isfinite(dpi) or dpi <= 0 or max_pixels < 16:
        raise ValueError("dpi must be positive and finite; max_pixels must be at least 16")
    source_hash = file_sha256(source)
    pdf = load_pdf_backend()
    if output.exists():
        raise FileExistsError(output)
    # Invalid configs are rejected before artifacts are created.
    with pdf.open(source) as doc:
        if not doc.is_pdf or doc.needs_pass:
            raise ValueError("An unencrypted PDF is required")
        for region in regions:
            if region["page_number"] > len(doc):
                raise ValueError("Region refers to a nonexistent page")
            page = doc[region["page_number"] - 1]
            page.set_rotation(0)  # In-memory normalization only; source never saved.
            validate_bbox(region["bbox"], list(page.rect))
    output.mkdir(parents=True)
    manifest = {"schema_version": 1, "run_id": str(uuid.uuid4()),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "source": {"path": str(source), "filename": source.name, "sha256": source_hash},
                "pymupdf_version": str(pdf.VersionBind),
                "coordinates": "Unrotated visible page points, top-left origin, 72 points/inch",
                "settings": {"dpi": dpi, "max_pixels": max_pixels},
                "pages": [], "errors": [], "status": "running"}
    handler = logging.FileHandler(output / "raster.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    previous_level = LOGGER.level
    LOGGER.setLevel(logging.INFO)
    try:
        with pdf.open(source) as doc:
            manifest["page_count"] = len(doc)
            for index in range(len(doc)):
                record = {"page_number": index + 1, "status": "running", "images": [],
                          "resources": [], "crops": [], "errors": []}
                manifest["pages"].append(record)
                try:
                    page = doc[index]
                    record["original_rotation"] = page.rotation
                    record["original_rotation_matrix"] = list(page.rotation_matrix)
                    record["cropbox"] = list(page.cropbox)
                    page.set_rotation(0)
                    record["bounds"] = list(page.rect)
                    page_dir = output / f"page-{index + 1:04d}"
                    page_dir.mkdir()
                    record["directory"] = page_dir.name
                    # Inventory displayed occurrences separately from resource xrefs.
                    try:
                        infos = page.get_image_info(xrefs=True)
                    except Exception as exc:
                        infos = []
                        record["errors"].append(f"Image occurrence inventory: {exc}")
                        LOGGER.exception("Image occurrence inventory failed")
                    try:
                        resource_xrefs = {item[0] for item in page.get_images(full=True)}
                    except Exception as exc:
                        resource_xrefs = set()
                        record["errors"].append(f"Image resource inventory: {exc}")
                        LOGGER.exception("Image resource inventory failed")
                    resource_xrefs.update(i["xref"] for i in infos if i["xref"])
                    exported = {}
                    pending = list(sorted(resource_xrefs))
                    while pending:
                        xref = pending.pop(0)
                        if xref in exported:
                            continue
                        try:
                            resource = extract_native(doc, xref, page_dir)
                            exported[xref] = resource
                            record["resources"].append(resource)
                            smask = resource["soft_mask_xref"]
                            # Explicit /Mask image references can also be separate images.
                            mask = re.fullmatch(r"(\d+) 0 R", resource["pdf_mask"])
                            for extra in [smask, int(mask[1]) if mask else 0]:
                                if extra and extra not in exported:
                                    pending.append(extra)
                        except Exception as exc:
                            exported[xref] = {"error": str(exc)}
                            record["errors"].append(f"xref {xref}: {exc}")
                            LOGGER.exception("Native image extraction failed on page %d", index + 1)
                    for info in infos:
                        a, b, c, d, e, f = info["transform"]
                        x_inches, y_inches = math.hypot(a, b) / 72, math.hypot(c, d) / 72
                        record["images"].append({
                            "xref": info["xref"], "width": info["width"], "height": info["height"],
                            "bbox": list(info["bbox"]), "transform": list(info["transform"]),
                            "effective_dpi_x": info["width"] / x_inches if x_inches else None,
                            "effective_dpi_y": info["height"] / y_inches if y_inches else None,
                            "resource_file": exported.get(info["xref"], {}).get("file"),
                            "native_status": "extracted" if exported.get(info["xref"], {}).get("file")
                                             else "inline_or_unavailable",
                        })
                    # Always authoritative for displayed composition, even with one image.
                    try:
                        record["full_page"] = render_region(pdf, page, page_dir / "full-page.png",
                                                             list(page.rect), dpi, max_pixels)
                    except Exception as exc:
                        record["errors"].append(f"Full-page render: {exc}")
                        LOGGER.exception("Full-page render failed")
                    record["composition_policy"] = "Full-page render includes masks, tiles, clipping, text and annotations"
                    record["unselected_region_kinds"] = sorted(REGION_KINDS - {
                        r["kind"] for r in regions if r["page_number"] == index + 1})
                    for region in regions:
                        if region["page_number"] != index + 1:
                            continue
                        try:
                            crop = render_region(pdf, page, page_dir / f"crop-{region['id']}.png",
                                                 region["bbox"], dpi, max_pixels)
                            crop.update(id=region["id"], kind=region["kind"],
                                        selection_method="manual", notes=region.get("notes", ""))
                            record["crops"].append(crop)
                        except Exception as exc:
                            record["errors"].append(f"region {region['id']}: {exc}")
                            LOGGER.exception("Crop failed")
                    record["status"] = "partial" if record["errors"] else "complete"
                    LOGGER.info("Page %d: %d instances, %d resources, %d crops", index + 1,
                                len(record["images"]), len(record["resources"]), len(record["crops"]))
                except Exception as exc:
                    record["status"] = "failed"
                    record["errors"].append(f"{type(exc).__name__}: {exc}")
                    LOGGER.exception("Page %d failed", index + 1)
                if record["errors"]:
                    manifest["errors"].append({"page_number": index + 1, "errors": record["errors"]})
            if file_sha256(source) != source_hash:
                raise RuntimeError("Source changed during processing; discard this run")
            manifest["status"] = "partial" if manifest["errors"] else "complete"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["errors"].append({"error": str(exc)})
        LOGGER.exception("Raster preparation failed")
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            write_json(output / "raster-manifest.json", manifest)
            write_assessment(output / "RASTER_ASSESSMENT.md", manifest)
        finally:
            LOGGER.removeHandler(handler)
            LOGGER.setLevel(previous_level)
            handler.close()
    return manifest


def write_assessment(path, manifest):
    lines = ["# Raster preparation assessment", "",
             f"Source: {manifest['source']['filename']}",
             f"SHA-256: `{manifest['source']['sha256']}`", f"Status: {manifest['status']}", "",
             "Full-page PNGs preserve visible composition; native resources retain source pixel dimensions.",
             "Extracted format is the format returned by PyMuPDF, which may differ from PDF stream compression.",
             "Raw stencil images, masks and color-key images can have different polarity or appearance from the drawing; use the composite for OCR.",
             "Readability is unreviewed until a person inspects the images. No OCR or accuracy measurement ran.", ""]
    for page in manifest["pages"]:
        lines.extend([f"## Page {page['page_number']}", "", f"Status: {page['status']}", ""])
        for image in page["images"]:
            resolution = (f"{image['effective_dpi_x']:.1f} × {image['effective_dpi_y']:.1f} DPI"
                          if image['effective_dpi_x'] and image['effective_dpi_y'] else "unknown DPI")
            lines.append(f"- Image xref {image['xref']}: {image['width']} × {image['height']}, {resolution}; {image['native_status']}.")
        for resource in page["resources"]:
            lines.append(f"- Resource {resource['xref']}: format {resource['format']}, PDF filter `{resource['pdf_filter']}`, stencil `{resource['pdf_image_mask']}`, soft mask xref {resource['soft_mask_xref']}.")
        full = page.get("full_page")
        if full:
            lines.append(f"- Composite: {full['width']} × {full['height']}, {full['effective_dpi']:.1f} DPI; capped: {full['resolution_capped']}.")
        lines.append(f"- Crops: {len(page['crops'])}. Unselected categories: {', '.join(page.get('unselected_region_kinds', [])) or 'none'}.")
        lines.extend(["", "OCR readiness: raster evidence is available when rendering succeeds; review faint text,",
                      "skew, rotated labels and crop coverage before selecting OCR settings.", ""])
        lines.extend(f"Error: {error}" for error in page["errors"])
    lines.extend(["", f"Run errors: {manifest['errors']}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
