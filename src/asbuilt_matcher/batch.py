"""Sequential local PDF inventory, independent of ArcPy and AI services."""

from collections import Counter
import csv
from datetime import datetime, timezone
import logging
import math
from pathlib import Path
import uuid

from .pdf_extract import extract_pdf, file_sha256, load_pdf_backend, write_json

LOGGER = logging.getLogger(__name__)
DOCUMENT_FIELDS = ["filename", "relative_path", "sha256", "page_count", "status",
                   "classification", "text_characters", "vector_paths", "image_instances",
                   "measured_pages", "output_directory", "error"]
PAGE_FIELDS = ["relative_path", "sha256", "page_index", "page_number", "status",
               "width_points", "height_points", "width_inches", "height_inches",
               "orientation", "rotation", "text_characters", "vector_paths",
               "image_instances", "classification", "text_file", "error"]


def classify_page(page):
    """Presence heuristic, not proof of scan origin or useful engineering content."""
    if not all(key in page for key in ("image_instances", "vector_paths", "text_characters")):
        return "unknown"
    raster = page["image_instances"] > 0
    vector = page["vector_paths"] > 0 or page.get("has_embedded_text", False)
    if raster and vector:
        return "mixed"
    if raster:
        return "scanned"
    return "vector" if vector else "empty"


def classify_document(pages):
    classes = {p["classification"] for p in pages} - {"empty", "unknown"}
    if "mixed" in classes or {"scanned", "vector"} <= classes:
        return "mixed"
    return next(iter(classes)) if classes else "unknown"


def write_csv(path, fields, records):
    # UTF-8 BOM allows direct opening in Windows Excel without losing Unicode.
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def inventory_pdfs(directory, output, *, recursive=False, dpi=100, max_pixels=16_000_000):
    """Extract each PDF into its own directory and write inventory.json plus two CSVs.

    A failed document does not stop the batch. Existing output directories are rejected.
    Counts are observed totals; incomplete documents are explicitly marked.
    """
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    if output == directory or output in directory.parents:
        raise ValueError("Output cannot be the input directory or its ancestor")
    if output.exists():
        raise FileExistsError(output)
    if not math.isfinite(dpi) or dpi <= 0 or max_pixels < 4:
        raise ValueError("Invalid preview settings")
    load_pdf_backend()  # Fail once on missing dependency, before creating any output.
    candidates = directory.rglob("*") if recursive else directory.iterdir()
    sources = sorted((p for p in candidates if p.is_file() and p.suffix.lower() == ".pdf"
                      and output not in p.resolve().parents),
                     key=lambda p: p.relative_to(directory).as_posix())
    output.mkdir(parents=True)
    report = {
        "schema_version": 1, "run_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input_directory": str(directory), "recursive": recursive,
        "settings": {"dpi": dpi, "max_pixels": max_pixels},
        "classification_method": "Image presence versus vector paths/embedded nonblank text; heuristic only",
        "dimension_units": "Displayed page points (72 per inch), with page rotation applied",
        "documents": [], "pages": [], "errors": [],
    }
    handler = logging.FileHandler(output / "batch.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    previous_level = LOGGER.level
    LOGGER.setLevel(logging.INFO)
    try:
        LOGGER.info("Starting inventory of %d PDFs", len(sources))
        for number, source in enumerate(sources, 1):
            relative = source.relative_to(directory).as_posix()
            run_dir = f"documents/document-{number:05d}"
            record = {"filename": source.name, "relative_path": relative,
                      "sha256": None, "page_count": None, "status": "failed",
                      "classification": "unknown", "output_directory": run_dir,
                      "text_characters": 0, "vector_paths": 0, "image_instances": 0,
                      "measured_pages": 0, "error": ""}
            report["documents"].append(record)
            LOGGER.info("Processing %s", relative)
            try:
                manifest = extract_pdf(source, output / run_dir, dpi=dpi, max_pixels=max_pixels)
                record.update(sha256=manifest["source"]["sha256"],
                              page_count=manifest.get("page_count"), status=manifest["status"])
                pages = []
                for page in manifest["pages"]:
                    summary = {key: page[key] for key in PAGE_FIELDS if key in page}
                    summary.update(relative_path=relative, sha256=record["sha256"],
                                   classification=classify_page(page))
                    if page.get("text_file"):
                        summary["text_file"] = f"{run_dir}/{page['text_file']}"
                    pages.append(summary)
                report["pages"].extend(pages)
                record["classification"] = classify_document(pages)
                record["measured_pages"] = sum(p["classification"] != "unknown" for p in pages)
                for field in ("text_characters", "vector_paths", "image_instances"):
                    record[field] = sum(p.get(field, 0) for p in pages)
                if manifest["errors"]:
                    record["error"] = "; ".join(e["error"] for e in manifest["errors"])
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
                try:
                    record["sha256"] = file_sha256(source)
                except OSError:
                    pass
                LOGGER.exception("Failed to process %s", relative)
            if record["status"] != "complete":
                report["errors"].append({"relative_path": relative, "error": record["error"]})
                LOGGER.error("%s: %s", relative, record["error"])
        report["status"] = "empty" if not sources else "partial" if report["errors"] else "complete"
        report["totals"] = {"documents": len(sources), "pages": len(report["pages"]),
                            "document_statuses": dict(Counter(d["status"] for d in report["documents"])),
                            "classifications": dict(Counter(d["classification"] for d in report["documents"]))}
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "inventory.json", report)
        write_csv(output / "documents.csv", DOCUMENT_FIELDS, report["documents"])
        write_csv(output / "pages.csv", PAGE_FIELDS, report["pages"])
        LOGGER.info("Finished inventory: %s", report["status"])
    finally:
        LOGGER.removeHandler(handler)
        LOGGER.setLevel(previous_level)
        handler.close()
    return report
