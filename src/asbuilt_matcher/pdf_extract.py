"""Extract local PDF evidence into a new run directory, never edit the source."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
import logging
import math
from pathlib import Path
import uuid

LOGGER = logging.getLogger(__name__)


def load_pdf_backend():
    try:
        return importlib.import_module("pymupdf")
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is unavailable. Run scripts/check_environment.py in the selected "
            "clone; obtain approval before installing PyMuPDF."
        ) from exc


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def extract_pdf(source, output, *, dpi=100, max_pixels=16_000_000):
    """Return manifest. Page errors are retained and processing continues.

    Output must not exist. Coordinates are page points, never geographic coordinates.
    Preview resolution is capped to avoid rendering full engineering sheets at huge sizes.
    """
    if not math.isfinite(dpi) or dpi <= 0 or max_pixels < 4:
        raise ValueError("dpi must be positive and finite; max_pixels must be at least 4")
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    backend = load_pdf_backend()
    source_hash = file_sha256(source)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1, "run_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
        "source": {"path": str(source), "filename": source.name,
                   "sha256": source_hash, "size_bytes": source.stat().st_size},
        "document_id": source_hash, "extractor_version": "0.1.0",
        "pymupdf_version": str(getattr(backend, "VersionBind", "unknown")),
        "settings": {"requested_dpi": dpi, "max_preview_pixels": max_pixels},
        "coordinate_system": {
            "units": "PDF points (1/72 inch)", "origin": "MuPDF top-left",
            "extraction": "unrotated page", "preview": "rotated page",
            "gis_transform": None,
        },
        "pages": [], "errors": [],
    }
    handler = logging.FileHandler(output / "extraction.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    try:
        with backend.open(str(source)) as document:
            if not document.is_pdf:
                raise ValueError("Input is not a PDF")
            if document.needs_pass:
                raise ValueError("Encrypted PDF requires a password; password input is not supported")
            manifest.update(page_count=len(document), pdf_metadata=document.metadata)
            for index in range(len(document)):
                record = {"page_index": index, "page_number": index + 1,
                          "sheet_id": f"{source_hash}:{index}", "status": "error"}
                manifest["pages"].append(record)
                try:
                    page = document[index]
                    stem = f"page-{index + 1:04d}"
                    text = page.get_text("text", sort=True)
                    drawings = page.get_drawings()
                    images = page.get_image_info()
                    operations = Counter(item[0] for drawing in drawings for item in drawing["items"])
                    (output / f"{stem}.txt").write_text(text, encoding="utf-8")
                    width, height = page.rect.width, page.rect.height
                    record.update(
                        text_file=f"{stem}.txt", text_characters=len(text),
                        has_embedded_text=bool(text.strip()),
                        image_instances=len(images), vector_paths=len(drawings),
                        width_points=width, height_points=height,
                        width_inches=width / 72, height_inches=height / 72,
                        orientation="landscape" if width > height else "portrait" if height > width else "square",
                        rotation=page.rotation,
                    )
                    scale = min(dpi / 72, math.sqrt(max_pixels / (page.rect.width * page.rect.height)))
                    # Allow for integer rounding of both raster dimensions.
                    while math.ceil(page.rect.width * scale) * math.ceil(page.rect.height * scale) > max_pixels:
                        scale *= 0.99
                    pixmap = page.get_pixmap(matrix=backend.Matrix(scale, scale),
                                             colorspace=backend.csRGB, alpha=False)
                    pixmap.save(str(output / f"{stem}.png"))
                    record.update(
                        status="ok", text_file=f"{stem}.txt", preview_file=f"{stem}.png",
                        text_characters=len(text), has_embedded_text=bool(text.strip()),
                        image_instances=len(images), vector_paths=len(drawings),
                        vector_operations=dict(operations), rotation=page.rotation,
                        page_rect=list(page.rect), cropbox=list(page.cropbox), mediabox=list(page.mediabox),
                        rotation_matrix=list(page.rotation_matrix),
                        preview={"width": pixmap.width, "height": pixmap.height,
                                 "effective_dpi": scale * 72, "scale": scale,
                                 "pixel_origin": [pixmap.x, pixmap.y]},
                        content_hint=("mixed" if images and drawings else "raster" if images
                                      else "vector" if drawings else "text_only" if text.strip() else "empty"),
                        ocr_recommended=bool(images) and not text.strip(),
                    )
                    write_json(output / f"{stem}.json", record)
                except Exception as exc:
                    record["status"] = "error"
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    manifest["errors"].append({"page_index": index, "error": record["error"]})
                    LOGGER.exception("Extraction failed for page %s", index + 1)
            if file_sha256(source) != source_hash:
                raise RuntimeError("Source changed during extraction; discard this run")
            manifest["status"] = "partial" if manifest["errors"] else "complete"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["errors"].append({"error": f"{type(exc).__name__}: {exc}"})
        LOGGER.exception("Document extraction failed")
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            write_json(output / "manifest.json", manifest)
        finally:
            LOGGER.removeHandler(handler)
            handler.close()
    return manifest
