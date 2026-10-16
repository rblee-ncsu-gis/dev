"""Local Tesseract baseline with derivative images and reversible page mappings."""

from collections import Counter
import csv
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from .clues import now
from .clue_review import analyst_accepted
from .ocr_eval import score_predictions
from .pdf_extract import file_sha256, load_pdf_backend, write_json


DEFAULT_CONFIG = {
    "language": "eng", "psm": 6, "oem": 1, "timeout_seconds": 60, "max_pixels": 40_000_000,
    "variants": [
        {"id": "baseline"}, {"id": "gray", "grayscale": True},
        {"id": "contrast", "grayscale": True, "contrast": 1.5},
        {"id": "threshold", "grayscale": True, "threshold": 160},
        {"id": "scale2", "grayscale": True, "scale": 2},
        {"id": "scale2_threshold", "grayscale": True, "scale": 2, "threshold": 160},
    ],
}


def probe_tesseract(executable=None, tessdata_dir=None):
    searched = []
    if executable:
        candidate = Path(executable)
        # An absolute override is resolved directly, without consulting PATH.
        resolved = (str(candidate.resolve()) if candidate.is_file() else None) if candidate.is_absolute() else shutil.which(str(executable))
        searched.append(str(executable))
    else:
        resolved = shutil.which("tesseract")
        searched.append("PATH:tesseract")
        for candidate in [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR/tesseract.exe",
                          Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Tesseract-OCR/tesseract.exe",
                          Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs/Tesseract-OCR/tesseract.exe",
                          Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Tesseract-OCR/tesseract.exe"]:
            searched.append(str(candidate))
            if not resolved and candidate.is_file():
                resolved = str(candidate)
    if resolved:
        resolved = str(Path(resolved).resolve())
    report = {"ready": False, "executable": resolved, "searched": searched,
              "tessdata_dir": str(tessdata_dir) if tessdata_dir else None,
              "tessdata_prefix": os.environ.get("TESSDATA_PREFIX"), "languages": [], "english_available": None,
              "adapter_outputs": ["txt", "word-level tsv"], "recognition_smoke_test": "not_run"}
    if not resolved:
        report["error"] = "Tesseract executable not found; English data availability cannot be determined"
        return report
    try:
        version = subprocess.run([resolved, "--version"], capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=15, check=False)
        args = [resolved, "--list-langs"]
        if tessdata_dir:
            args += ["--tessdata-dir", str(tessdata_dir)]
        languages = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=15, check=False)
        report.update(version=(version.stdout or version.stderr).strip(),
                      executable_sha256=file_sha256(resolved), language_probe_stdout=languages.stdout,
                      language_probe_stderr=languages.stderr)
        if version.returncode or languages.returncode:
            raise RuntimeError("Tesseract version/language probe failed")
        report["languages"] = [line.strip() for line in languages.stdout.splitlines()
                               if re.fullmatch(r"[A-Za-z0-9_/.-]+", line.strip())]
        report["english_available"] = "eng" in report["languages"]
        report["ready"] = report["english_available"]
        if not report["ready"]:
            report["error"] = "English traineddata was not listed"
        # Snapshot model bytes when the reported or explicit data directory is discoverable.
        quoted = re.search(r'"([^"]+)"', languages.stdout)
        dirs = [Path(tessdata_dir)] if tessdata_dir else []
        if quoted:
            dirs.append(Path(quoted[1]))
        dirs.append(Path(resolved).parent / "tessdata")
        for directory in dirs:
            model = directory / "eng.traineddata"
            if model.is_file():
                report["english_model"] = {"path": str(model.resolve()), "sha256": file_sha256(model)}
                break
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        report.update(ready=False, error=str(exc))
    return report


def validate_config(config):
    if not re.fullmatch(r"[A-Za-z0-9_+]+", config["language"]):
        raise ValueError("Invalid OCR language")
    if config["psm"] not in range(3, 14) or config["oem"] not in range(4):
        raise ValueError("psm must be 3..13 (no automatic OSD); oem must be 0..3")
    if not 0 < config["timeout_seconds"] <= 3600 or config["max_pixels"] < 16:
        raise ValueError("Invalid timeout or pixel budget")
    if not config["variants"]:
        raise ValueError("At least one preprocessing variant is required")
    names = set()
    for v in config["variants"]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", v["id"]) or v["id"] in names:
            raise ValueError("Variant IDs must be safe and unique")
        names.add(v["id"])
        if set(v) - {"id", "grayscale", "contrast", "threshold", "scale", "rotation"}:
            raise ValueError("Unknown preprocessing field")
        for key, default in [("contrast", 1), ("scale", 1)]:
            if not math.isfinite(v.get(key, default)) or not 0 < v.get(key, default) <= 8:
                raise ValueError(f"Invalid {key}")
        if v.get("rotation", 0) not in (0, 90, 180, 270):
            raise ValueError("Rotation must be explicit clockwise 0/90/180/270 degrees")
        if v.get("threshold") is not None and not 0 <= v["threshold"] <= 255:
            raise ValueError("Threshold must be 0..255")


def load_images(evidence_path):
    """Consume existing manifests; never read reference text/type into the OCR path."""
    evidence_path = Path(evidence_path).resolve()
    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    images = []
    if "clues" in data:
        for row in data["clues"]:
            target = row.get("target_image")
            path = row.get("target_image_reference") if target else row.get("image_reference")
            metadata = target or row.get("image")
            if not path or not metadata:
                raise ValueError("Clue export requires raster image metadata")
            images.append({"id": row["clue_id"], "clue_id": row["clue_id"], "path": path,
                           "sha256": row.get("target_image_sha256") if target else row.get("image_sha256"),
                           "source_pdf": row["source_pdf"], "document_sha256": row["document_sha256"],
                           "page_number": row["page_number"], **{k: metadata[k] for k in (
                               "width", "height", "effective_dpi", "page_to_pixel")}})
    elif "pages" in data and "source" in data:
        for page in data["pages"]:
            for kind, metadata in [("full", page.get("full_page"))] + [(c["id"], c) for c in page.get("crops", [])]:
                if metadata:
                    images.append({"id": f"page-{page['page_number']}-{kind}",
                                   "path": str(evidence_path.parent / page["directory"] / metadata["file"]),
                                   "sha256": None, "source_pdf": data["source"]["filename"],
                                   "document_sha256": data["source"]["sha256"], "page_number": page["page_number"],
                                   **{k: metadata[k] for k in ("width", "height", "effective_dpi", "page_to_pixel")}})
    else:
        raise ValueError("Expected a Phase 1B raster manifest or Phase 1C clue export")
    if len({i["id"] for i in images}) != len(images) or not images:
        raise ValueError("Image IDs must be unique and nonempty")
    for image in images:
        path = Path(image["path"])
        if not path.is_absolute():
            path = evidence_path.parent / path
        image["path"] = str(path.resolve())
        digest = file_sha256(path)
        if image["sha256"] and digest != image["sha256"]:
            raise ValueError(f"Source image hash mismatch: {path}")
        image["sha256"] = digest
        matrix = image["page_to_pixel"]
        if len(matrix) != 6 or not all(math.isfinite(v) for v in matrix) or abs(matrix[0] * matrix[3] - matrix[1] * matrix[2]) < 1e-12:
            raise ValueError("Invalid page-to-image transform")
    return images


def preprocess(image, variant, destination, max_pixels):
    pdf = load_pdf_backend()
    pix = pdf.Pixmap(image["path"])
    if (pix.width, pix.height) != (image["width"], image["height"]):
        raise ValueError("Source image dimensions differ from metadata")
    if pix.alpha:
        raise ValueError("Use opaque composition-correct images, not raw transparent masks")
    if pix.colorspace is None:
        raise ValueError("Raw masks are not supported as OCR inputs")
    if variant.get("grayscale") or variant.get("threshold") is not None:
        pix = pdf.Pixmap(pdf.csGRAY, pix)
    factor = variant.get("contrast", 1)
    if factor != 1:
        lut = bytes(max(0, min(255, round((n - 127.5) * factor + 127.5))) for n in range(256))
        pix = pdf.Pixmap(pix.colorspace, pix.width, pix.height, pix.samples.translate(lut), False)
    scale = variant.get("scale", 1)
    width, height = max(1, round(pix.width * scale)), max(1, round(pix.height * scale))
    if width * height > max_pixels or image["width"] * image["height"] > max_pixels:
        raise ValueError("Preprocessing exceeds pixel budget; no silent downsampling")
    sx, sy = width / pix.width, height / pix.height
    if (width, height) != (pix.width, pix.height):
        pix = pdf.Pixmap(pix, width, height)
    if variant.get("threshold") is not None:
        lut = bytes(255 if n >= variant["threshold"] else 0 for n in range(256))
        pix = pdf.Pixmap(pdf.csGRAY, pix.width, pix.height, pix.samples.translate(lut), False)
    angle = variant.get("rotation", 0)
    transform = {0: [sx, 0, 0, sy, 0, 0], 90: [0, sx, -sy, 0, height, 0],
                 180: [-sx, 0, 0, -sy, width, height], 270: [0, -sx, sy, 0, 0, width]}[angle]
    if angle:
        with pdf.open() as doc:
            page = doc.new_page(width=width, height=height)
            page.insert_image(page.rect, pixmap=pix)
            page.set_rotation(angle)
            pix = page.get_pixmap(colorspace=pix.colorspace, alpha=False)
    dpi = max(1, round(image["effective_dpi"] * (sx + sy) / 2))
    pix.set_dpi(dpi, dpi)
    pix.save(str(destination))
    combined = pdf.Matrix(image["page_to_pixel"]) * pdf.Matrix(transform)
    return {"file": str(destination.resolve()), "sha256": file_sha256(destination), "width": pix.width,
            "height": pix.height, "dpi": dpi, "input_to_processed": transform,
            "page_to_processed": list(combined), "processed_to_page": list(~combined),
            "method": variant}


def parse_tsv(tsv, processed):
    pdf = load_pdf_backend()
    words = []
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t")
    required = {"level", "page_num", "block_num", "par_num", "line_num", "left", "top", "width", "height", "conf", "text"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("Missing Tesseract TSV columns")
    for row in reader:
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
        confidence = float(row["conf"])
        if not math.isfinite(confidence) or not -1 <= confidence <= 100 or min(x, y) < 0 or min(w, h) <= 0 or x+w > processed["width"] or y+h > processed["height"]:
            raise ValueError("Invalid Tesseract word geometry/confidence")
        points = [pdf.Point(px, py) * pdf.Matrix(processed["processed_to_page"])
                  for px, py in [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]]
        words.append({"text": row["text"], "confidence": confidence if confidence >= 0 else None,
                      "bbox_processed": [x, y, x+w, y+h], "polygon_page": [list(p) for p in points],
                      "bbox_page": [min(p.x for p in points), min(p.y for p in points),
                                    max(p.x for p in points), max(p.y for p in points)],
                      "line_id": [int(row[k]) for k in ("page_num", "block_num", "par_num", "line_num")]})
    return words


def geographic_candidates(text):
    """Conservative exploratory rules; no ground-truth labels or GIS lookup."""
    candidates = []
    lines = text.upper().splitlines()
    for line in lines:
        project = re.search(r"\b(?:HWY|HIGHWAY)\s+\d+\s+FORCE\s+MAIN\b", line)
        road = re.search(r"\bNC\s+\d+(?:\s*[-–—]\s*[A-Z ]+\s+ROAD)?\b", line)
        generic = re.search(r"\b[A-Z]+(?:\s+[A-Z]+){0,3}\s+(?:ROAD|STREET|DRIVE|LANE)\b", line)
        for kind, match, rule in [("project_name", project, "project-title"), ("street_name", road or generic, "road-label")]:
            if match:
                candidates.append({"kind": kind, "text": match[0], "rule": rule, "review_status": "unreviewed"})
    joined = " ".join(line.strip() for line in lines if line.strip())
    landmark = re.fullmatch(r"[A-Z ]{2,100}\b(?:CEMETERY|STORAGE)", joined)
    if landmark:
        candidates.append({"kind": "landmark", "text": landmark[0], "rule": "landmark-suffix", "review_status": "unreviewed"})
    warnings = []
    for line in lines:
        if re.search(r"\bSTA\.?\s*\d+\+|\b\d+[ -]*(?:INCH|LF|PVC|HDPE)\b|\d+['\"]", line):
            warnings.append({"text": line, "category": "engineering_annotation", "status": "review_required",
                             "reason": "Station, dimension or material text can be mistaken for geographic information"})
    return candidates, warnings


def recognize(processed, base, engine, config):
    args = tesseract_command(processed, base, engine, config)
    start = time.monotonic()
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=config["timeout_seconds"], check=False)
    except subprocess.TimeoutExpired as exc:
        (base.parent / "engine.log").write_text(str(exc), encoding="utf-8")
        raise RuntimeError("Tesseract timeout") from exc
    (base.parent / "engine.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Tesseract exited {result.returncode}: {result.stderr.strip()}")
    raw = base.with_suffix(".txt").read_bytes().decode("utf-8")
    tsv = base.with_suffix(".tsv").read_text(encoding="utf-8")
    words = parse_tsv(tsv, processed)
    # Keep raw engine text file; exclude one engine-added terminal newline from prediction text.
    text = raw.replace("\r\n", "\n").removesuffix("\n")
    candidates, warnings = geographic_candidates(text)
    return {"status": "recognized" if text.strip() else "empty", "text": text, "raw_text": raw,
            "words": words, "entities": candidates, "engineering_warnings": warnings,
            "elapsed_seconds": time.monotonic() - start, "command": args,
            "confidence_mean": (sum(w["confidence"] for w in words if w["confidence"] is not None) /
                                sum(w["confidence"] is not None for w in words))
                               if any(w["confidence"] is not None for w in words) else None}


def tesseract_command(processed, base, engine, config):
    args = [engine["executable"], processed["file"], str(base), "-l", config["language"],
            "--oem", str(config["oem"]), "--psm", str(config["psm"]), "--dpi", str(processed["dpi"])]
    if engine.get("tessdata_dir"):
        args += ["--tessdata-dir", engine["tessdata_dir"]]
    args += ["txt", "tsv"]
    return args


def run_baseline(evidence_path, output, *, config=None, executable=None, tessdata_dir=None,
                 ground_truth_path=None, prepare_only=False):
    config = {**DEFAULT_CONFIG, **(config or {})}
    validate_config(config)
    images = load_images(evidence_path)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    engine = probe_tesseract(executable, tessdata_dir)
    if engine["ready"] and not all(lang in engine["languages"] for lang in config["language"].split("+")):
        engine.update(ready=False, error="Requested language data is unavailable")
    truth = json.loads(Path(ground_truth_path).read_text(encoding="utf-8")) if ground_truth_path else None
    accepted = [r for r in truth["clues"] if analyst_accepted(r)] if truth else []
    output.mkdir(parents=True)
    report = {"schema_version": 1, "run_id": str(uuid.uuid4()), "started_at": now(), "status": "running",
              "evidence": {"path": str(Path(evidence_path).resolve()), "sha256": file_sha256(evidence_path)},
              "engine": engine, "config": config, "prepare_only": prepare_only,
              "evaluation": {"accepted_references": len(accepted),
                             "excluded_references": len(truth["clues"]) - len(accepted) if truth else 0,
                             "status": "pending" if accepted else "blocked_no_analyst_ground_truth" if truth else "not_requested"},
              "images": images, "results": [], "comparison": []}
    if ground_truth_path:
        report["ground_truth"] = {"path": str(Path(ground_truth_path).resolve()), "sha256": file_sha256(ground_truth_path)}
    log = (output / "ocr.log").open("w", encoding="utf-8")
    try:
        for variant in config["variants"]:
            variant_results = []
            for index, image in enumerate(images, 1):
                job = output / variant["id"] / f"image-{index:04d}"
                job.mkdir(parents=True)
                record = {"image_id": image["id"], "source_image_sha256": image["sha256"],
                          "started_at": now(),
                          "source_image_reference": image["path"], "preprocessing": variant,
                          "tesseract_version": engine.get("version"), "tesseract_executable": engine.get("executable"),
                          "ocr_configuration": {k: config[k] for k in ("language", "oem", "psm", "timeout_seconds")},
                          "source_pdf": image["source_pdf"], "document_sha256": image["document_sha256"],
                          "page_number": image["page_number"], "clue_id": image.get("clue_id"),
                          "variant": variant["id"], "status": "failed", "text": None, "entities": [],
                          "words": [], "confidence_mean": None, "command": None}
                report["results"].append(record)
                variant_results.append(record)
                try:
                    record["processed"] = preprocess(image, variant, job / "input.png", config["max_pixels"])
                    if prepare_only:
                        record["status"] = "prepared_only"
                    elif not engine["ready"]:
                        record.update(status="blocked_engine", error=engine.get("error"))
                    else:
                        record["command"] = tesseract_command(record["processed"], job / "ocr", engine, config)
                        record.update(recognize(record["processed"], job / "ocr", engine, config))
                    if file_sha256(image["path"]) != image["sha256"]:
                        raise ValueError("Source image changed during OCR; discard result")
                except Exception as exc:
                    record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                record["finished_at"] = now()
                write_json(job / "result.json", record)
                log.write(f"{now()} {variant['id']} {image['id']}: {record['status']} {record.get('error', '')}\n")
                log.flush()
            predictions = {"run": {"engine": "tesseract", "version": engine.get("version"), "variant": variant,
                                   "evidence_sha256": report["evidence"]["sha256"]},
                           "predictions": [{"clue_id": r["clue_id"], "text": r["text"], "entities": r["entities"]}
                                           for r in variant_results if r["clue_id"] and r["status"] in {"recognized", "empty"}]}
            write_json(output / variant["id"] / "predictions.json", predictions)
            comparison = {"variant": variant["id"], "counts": dict(Counter(r["status"] for r in variant_results)),
                          "prepared": sum("processed" in r for r in variant_results), "metrics": None}
            if accepted and not prepare_only and engine["ready"]:
                # Never align gold with another crop or a stale image merely because IDs match.
                by_id = {i.get("clue_id"): i for i in images if i.get("clue_id")}
                if not all(r["clue_id"] in by_id and r.get("target_image_sha256") == by_id[r["clue_id"]]["sha256"] for r in accepted):
                    comparison["evaluation_error"] = "Accepted target image hashes/IDs do not match OCR inputs"
                else:
                    accepted_ids = {r["clue_id"] for r in accepted}
                    pred = {**predictions, "predictions": [r for r in predictions["predictions"] if r["clue_id"] in accepted_ids]}
                    comparison["metrics"] = score_predictions({"clues": accepted}, pred)
                    write_json(output / variant["id"] / "scores.json", comparison["metrics"])
            report["comparison"].append(comparison)
        report["status"] = ("partial" if any(r["status"] == "failed" for r in report["results"]) else
                            "prepared_only" if prepare_only else "blocked_engine" if not engine["ready"] else "complete")
        report["evaluation"]["status"] = ("scored" if any(c["metrics"] for c in report["comparison"])
                                              else report["evaluation"]["status"])
        if accepted and report["evaluation"]["status"] != "scored":
            report["evaluation"]["status"] = ("not_run_prepare_only" if prepare_only else
                                              "blocked_engine" if not engine["ready"] else "blocked_evidence_alignment")
        scored = [c for c in report["comparison"] if c["metrics"] and c["counts"].get("recognized", 0)]
        report["best_variants"] = None
        if scored:
            best_exact = max(c["metrics"]["transcription"]["exact_accuracy"] for c in scored)
            report["best_variants"] = {"exact_accuracy": [c["variant"] for c in scored
                if c["metrics"]["transcription"]["exact_accuracy"] == best_exact], "scope": "this accepted pilot subset only"}
            for metric in ("character_accuracy", "word_accuracy"):
                defined_text = [c for c in scored if c["metrics"]["transcription"][metric] is not None]
                if defined_text:
                    maximum = max(c["metrics"]["transcription"][metric] for c in defined_text)
                    report["best_variants"][metric] = [c["variant"] for c in defined_text
                        if c["metrics"]["transcription"][metric] == maximum]
            defined = [c for c in scored if c["metrics"]["entities"]["micro"]["f1"] is not None]
            if defined:
                best_f1 = max(c["metrics"]["entities"]["micro"]["f1"] for c in defined)
                report["best_variants"]["entity_f1"] = [c["variant"] for c in defined
                    if c["metrics"]["entities"]["micro"]["f1"] == best_f1]
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        log.close()
        report["finished_at"] = now()
        write_json(output / "ocr-run.json", report)
        write_comparison(output, report)
        from .ocr_report import write_visual_report
        write_visual_report(report, output)
    return report


def write_comparison(output, report):
    columns = ["variant", "prepared", "recognized", "empty", "blocked_engine", "failed",
               "exact_accuracy", "character_error_rate", "character_accuracy", "word_error_rate", "word_accuracy",
               "entity_precision", "entity_recall", "entity_f1", "entity_false_positives"]
    with (output / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        for row in report["comparison"]:
            metrics = row["metrics"]
            writer.writerow({"variant": row["variant"], "prepared": row["prepared"],
                             **{k: row["counts"].get(k, 0) for k in columns[2:6]},
                             **({"exact_accuracy": metrics["transcription"]["exact_accuracy"],
                                 "character_error_rate": metrics["transcription"]["character_error_rate"],
                                 **{k: metrics["transcription"][k] for k in ("character_accuracy", "word_error_rate", "word_accuracy")},
                                 "entity_false_positives": metrics["entities"]["micro"]["false_positive"],
                                 **{f"entity_{k}": metrics["entities"]["micro"][k] for k in ("precision", "recall", "f1")}}
                                if metrics else {})})
    lines = ["# Local OCR baseline comparison", "", f"Run status: {report.get('status', 'interrupted')}",
             f"Engine ready: {report['engine']['ready']}", f"Evaluation: {report['evaluation']}", "",
             "| Variant | Prepared | OCR statuses | Exact | Character accuracy | Word accuracy | Entity precision | Entity recall | Entity F1 | False positives |",
             "| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["comparison"]:
        metrics = row["metrics"]
        lines.append(f"| {row['variant']} | {row['prepared']} | {row['counts']} | " +
                     (f"{metrics['transcription']['exact_accuracy']} | {metrics['transcription']['character_accuracy']} | "
                      f"{metrics['transcription']['word_accuracy']} | {metrics['entities']['micro']['precision']} | "
                      f"{metrics['entities']['micro']['recall']} | {metrics['entities']['micro']['f1']} | {metrics['entities']['micro']['false_positive']} |"
                      if metrics else "not measured | not measured | not measured | not measured | not measured | not measured | not measured |"))
    lines += ["", f"Best measured variants: {report.get('best_variants')}",
              "No preprocessing winner can be inferred from confidence alone. Inspect accepted-reference scores and failure cases.",
              "Candidates remain unreviewed. Engineering-annotation warnings are possible confounders, not confirmed false positives."]
    (output / "COMPARISON.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
