"""Representative PDF study orchestration, reports and hash-bound analyst review.

This supplements the legacy presence-only batch inventory without changing its
outputs. All new runs and review snapshots require new directories.
"""

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
from html import escape
import json
import logging
import math
from pathlib import Path
import uuid

from .batch import write_csv
from .clues import now, review_identity
from .pdf_extract import file_sha256, load_pdf_backend, write_json
from .pdf_classify import LABELS, criteria_with_defaults
from .pdf_inspect import inspect_document

LOGGER = logging.getLogger(__name__)
PRIMARY_CLASSES = {"predominantly_raster", "predominantly_vector", "hybrid_raster_vector", "text_rich_digital", "indeterminate"}


def _csv(path, rows, fields):
    write_csv(path, fields, [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in r.items()} for r in rows])


def _summarize(pages):
    count = len(pages)
    labels = Counter(label for p in pages for label in p["classification"]["labels"])
    primary = Counter(p["classification"]["primary_class"] for p in pages)
    return {"pages": count, "primary_counts": dict(primary),
            "overlapping_categories": {key: {"pages": labels[key], "percent": round(100 * labels[key] / count, 2) if count else None} for key in sorted(LABELS)},
            "base_native_text_pages": sum(p.get("text", {}).get("nonspace_characters", 0) > 0 for p in pages),
            "usable_native_text_candidate_pages": sum(p["classification"].get("usable_native_text_candidate", False) for p in pages),
            "base_vector_pages": sum(p.get("vectors", {}).get("path_count", 0) > 0 for p in pages),
            "base_vector_paths": sum(p.get("vectors", {}).get("path_count", 0) for p in pages),
            "annotation_pages": sum(bool(p.get("annotations")) for p in pages),
            "annotations": sum(len(p.get("annotations", [])) for p in pages),
            "native_scale_statement_pages": sum(bool(p.get("candidates", {}).get("scale_statements")) for p in pages)}


def _page_rows(report):
    rows = []
    for doc in report["documents"]:
        for page in doc["pages"]:
            text, vectors = page.get("text", {}), page.get("vectors", {})
            images = page.get("images") or {}
            resolutions = [dpi for im in images.get("occurrences", []) for dpi in (im.get("effective_dpi_x"), im.get("effective_dpi_y")) if dpi is not None]
            row = {"page_id": page["page_id"], "relative_path": doc["relative_path"], "cohort": doc["cohort"],
                   "sha256": doc["sha256"], "page_number": page["page_number"], "status": page["status"],
                   "rotation": page.get("rotation"), **page.get("dimensions", {}), "boxes": page.get("boxes"),
                   "native_characters": text.get("characters"), "native_words": text.get("word_count"),
                   "native_nonspace_characters": text.get("nonspace_characters"), "text_cells_4x4": text.get("occupied_cell_count"),
                   "suspect_character_fraction": text.get("suspect_character_fraction"),
                   "invisible_text_characters": text.get("render_character_counts", {}).get("invisible", 0),
                   "composite_characters": page.get("annotation_separation", {}).get("composite_text_characters"),
                   "native_vector_paths": vectors.get("path_count"), "vector_operations": vectors.get("operations"),
                   "composite_vector_paths": page.get("annotation_separation", {}).get("composite_vector_paths"),
                   "base_image_count": page.get("images", {}).get("occurrence_count") if page.get("images") else None,
                   "composite_image_count": page.get("composite_images", {}).get("occurrence_count") if page.get("composite_images") else None,
                   "raster_coverage": page.get("images", {}).get("coverage_bbox_union") if page.get("images") else None,
                   "annotation_count": len(page.get("annotations", [])), "fonts": page.get("fonts"),
                   "annotation_types": dict(Counter(a["type"][1] for a in page.get("annotations", []))),
                   "effective_image_dpi_min": min(resolutions) if resolutions else None,
                   "effective_image_dpi_max": max(resolutions) if resolutions else None,
                   "red_color_native_paths": len(vectors.get("red_color_path_indices", [])),
                   "geospatial_candidates": page.get("geospatial", {}).get("candidates") if page.get("geospatial") else None,
                   "primary_class": page["classification"]["primary_class"], "labels": page["classification"]["labels"],
                   "processing_paths": page["classification"]["processing_paths"],
                   "scale_statements": page.get("candidates", {}).get("scale_statements", []),
                   "graphic_scale_candidate_segments": len(page.get("graphical_scale_candidates", [])),
                   "effective_scale_verified": False, "registration_status": "not_registered",
                   "verification_status": "unreviewed", "preview": f"{page['directory']}/composite.png" if page.get("preview") else None,
                   "native_text": f"{page['directory']}/native-text.txt" if page.get("text") else None,
                   "warnings": page.get("warnings", []), "errors": page["errors"]}
            rows.append(row)
    return rows


def _write_review(output, report, rows):
    report_hash = file_sha256(output / "inspection.json")
    template = {"schema_version": 1, "run_id": report["run_id"], "inspection_sha256": report_hash,
                "reviewer": "", "reviewer_type": "unspecified", "independent": False,
                "decisions": [{"page_id": r["page_id"], "action": "unreviewed", "primary_class": r["primary_class"],
                               "labels": r["labels"], "reason": ""} for r in rows]}
    write_json(output / "classification-decisions.template.json", template)
    _csv(output / "classification-review.csv", [dict(r, analyst_action="unreviewed", corrected_primary_class="", corrected_labels="", reviewer="", reviewer_type="", independent="", reason="") for r in rows],
         ["page_id", "relative_path", "cohort", "sha256", "page_number", "primary_class", "labels", "processing_paths", "preview", "warnings", "errors", "analyst_action", "corrected_primary_class", "corrected_labels", "reviewer", "reviewer_type", "independent", "reason"])
    cards = []
    for row in rows:
        cls = escape(row["primary_class"])
        image = f'<a href="{escape(row["preview"], quote=True)}"><img loading="lazy" src="{escape(row["preview"], quote=True)}" alt="Composition-correct page, annotations included"></a>' if row["preview"] else "<p>Preview unavailable; inspect error.</p>"
        options = ''.join(f'<option value="{v}" {"selected" if v == row["primary_class"] else ""}>{v}</option>' for v in sorted(PRIMARY_CLASSES))
        checks = ''.join(f'<label><input type="checkbox" class="label" value="{label}" {"checked" if label in row["labels"] else ""}>{label}</label> ' for label in sorted(LABELS))
        text_link = f'<p><a href="{escape(row["native_text"], quote=True)}">Base native text</a></p>' if row["native_text"] else '<p>Native text unavailable; inspect errors.</p>'
        cards.append(f'<article data-page="{escape(row["page_id"], quote=True)}"><h2>{escape(row["relative_path"])} — p{row["page_number"]}</h2>'
                     f'<p>{escape(row["cohort"])}; automated: {cls}; original PDF rotation {row["rotation"]}°.</p>'
                     f'<div class="pair">{image}<div><pre>{escape(json.dumps({k: row[k] for k in ("native_characters", "native_vector_paths", "raster_coverage", "annotation_count", "scale_statements", "warnings", "errors")}, indent=2, ensure_ascii=False))}</pre>'
                     + text_link)
        cards[-1] += ('<label>Action <select class="action"><option>unreviewed</option><option>confirm</option><option>correct</option><option>reject</option><option>unreadable</option></select></label>'
                      f'<p>Primary <select class="primary">{options}</select></p><p>{checks}</p><label>Evidence/reason <textarea class="reason"></textarea></label></div></div></article>')
    payload = json.dumps(template, ensure_ascii=True).replace("<", "\\u003c")
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>PDF classification review</title>'
            '<style>body{font:16px system-ui;margin:24px}article{border-top:2px solid #778;padding:12px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{max-width:100%;max-height:800px}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:95%;height:70px}label{display:inline-block;margin:4px}header{position:sticky;top:0;background:#fff;padding:10px;border:1px solid #aaa}@media(max-width:900px){.pair{display:block}}</style>'
            '<h1>Selected-sample PDF classification review</h1><p>Automated labels are unreviewed. Previews show the unrotated page, including annotations; open an image for details. '
            'Reduced previews do not establish full-resolution legibility. Colors are not proof of redlines. No classification accuracy or geographic accuracy is established.</p>'
            '<header><label>Reviewer <input id="reviewer"></label><label>Type <select id="type"><option>unspecified</option><option>human</option><option>ai</option></select></label>'
            '<label><input type="checkbox" id="independent">Independent review attestation</label><button id="download">Download decisions</button><span id="message"></span></header>'
            + ''.join(cards) + f'<script>const template={payload};' + r'''
document.querySelectorAll('article .primary').forEach(s=>s.onchange=()=>{
const a=s.closest('article');a.querySelectorAll('.label').forEach(e=>{if(e.value===s.value)e.checked=true;});
});
document.querySelector('#download').onclick=()=>{
const out=structuredClone(template);out.reviewer=document.querySelector('#reviewer').value;
out.reviewer_type=document.querySelector('#type').value;out.independent=document.querySelector('#independent').checked;
out.decisions=[...document.querySelectorAll('article')].map(a=>({page_id:a.dataset.page,action:a.querySelector('.action').value,primary_class:a.querySelector('.primary').value,labels:[...a.querySelectorAll('.label:checked')].map(e=>e.value),reason:a.querySelector('.reason').value}));
if(!out.reviewer.trim() || out.decisions.some(d=>d.action!=='unreviewed'&&!d.reason.trim())){document.querySelector('#message').textContent='Reviewer and reasons for all reviewed pages are required.';return;}
if(out.independent&&out.reviewer_type!=='human'){document.querySelector('#message').textContent='Independent acceptance requires an explicitly identified human reviewer.';return;}
if(out.decisions.some(d=>d.action!=='unreviewed'&&!d.labels.includes(d.primary_class))){document.querySelector('#message').textContent='Include the chosen primary class among the checked labels.';return;}
const url=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='classification-decisions.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};</script></html>''')
    (output / "REVIEW.html").write_text(html, encoding="utf-8")


def write_reports(report, output):
    rows = _page_rows(report)
    document_rows = []
    for doc in report["documents"]:
        meta = doc.get("metadata") or {}
        recommendations = sorted({path for p in doc["pages"] for path in p["classification"]["processing_paths"]})
        doc["processing_recommendations"] = recommendations or ["manual_document_review"]
        # Keep standalone document evidence consistent with the consolidated report.
        write_json(output / doc["directory"] / "document.json", doc)
        document_rows.append({k: doc.get(k) for k in ("relative_path", "filename", "cohort", "sha256", "size_bytes", "header_pdf_version", "page_count", "status", "source_unchanged", "needs_password", "is_encrypted", "restrictions", "is_repaired", "warnings", "errors")} |
                             {"producer": meta.get("producer"), "creator": meta.get("creator"), "metadata": meta,
                              "primary_page_counts": dict(Counter(p["classification"]["primary_class"] for p in doc["pages"])),
                              "native_text_pages": sum(p.get("text", {}).get("nonspace_characters", 0) > 0 for p in doc["pages"]),
                              "native_vector_pages": sum(p.get("vectors", {}).get("path_count", 0) > 0 for p in doc["pages"]),
                              "processing_recommendations": doc["processing_recommendations"]})
    fields = list(rows[0]) if rows else ["page_id", "relative_path", "page_number", "primary_class"]
    _csv(output / "pages.csv", rows, fields)
    _csv(output / "documents.csv", document_rows, list(document_rows[0]) if document_rows else ["relative_path", "status"])
    for filename, columns in {
        "native-text.csv": ["page_id", "relative_path", "page_number", "native_characters", "composite_characters", "native_words", "text_cells_4x4", "suspect_character_fraction", "invisible_text_characters", "native_text"],
        "vectors.csv": ["page_id", "relative_path", "page_number", "native_vector_paths", "composite_vector_paths", "vector_operations", "red_color_native_paths"],
        "scales.csv": ["page_id", "relative_path", "page_number", "scale_statements", "graphic_scale_candidate_segments"],
        "annotations.csv": ["page_id", "relative_path", "page_number", "annotation_count", "annotation_types", "red_color_native_paths", "warnings"],
        "raster-hybrid.csv": ["page_id", "relative_path", "page_number", "primary_class", "base_image_count", "composite_image_count", "raster_coverage", "effective_image_dpi_min", "effective_image_dpi_max", "processing_paths"],
        "registration-readiness.csv": ["page_id", "relative_path", "page_number", "scale_statements", "effective_scale_verified", "geospatial_candidates", "registration_status", "processing_paths", "warnings"],
    }.items():
        _csv(output / filename, rows, columns)
    write_json(output / "inspection.json", report)
    _write_review(output, report, rows)
    lines = ["# Representative PDF study", "", f"Run: {report['run_id']}. Status: **{report['status']}**.", "",
             report["sample_description"], "", f"Selected PDFs: {len(report['documents'])}; observed page records: {len(rows)}. Failed documents remain in documents.csv and inspection.json.", "",
             "Counts describe this selected sample only. Categories overlap. Automated classifications have no independent acceptance; classification accuracy is not measured.", "",
             "| Cohort | Documents | Observed pages |", "| --- | ---: | ---: |"]
    for cohort, stats in report["cohorts"].items():
        lines.append(f"| {cohort} | {stats['documents']} | {stats['pages']} |")
    lines.extend(["", "| Automated category | Pages | Percent of observed sample pages |", "| --- | ---: | ---: |"])
    for label, value in report["summary"]["overlapping_categories"].items():
        lines.append(f"| {label} | {value['pages']} | {value['percent']} |")
    lines.extend(["", "## Per-document processing recommendations", ""])
    for doc in report["documents"]:
        counts = dict(Counter(p["classification"]["primary_class"] for p in doc["pages"]))
        lines.extend([f"- **{doc['relative_path']}** ({doc['cohort']}, {doc['page_count']} pages; {doc['status']}): {counts}. Paths: {', '.join(doc['processing_recommendations'])}."])
    lines.extend(["", "## Interpretation and limits", "",
                  "Base native text/path/image evidence excludes separate PDF annotation appearances. Intact previews and composite-text.txt preserve the visible annotated source. No original is saved or replaced.", "",
                  "Native text is preferred where usable; labels converted to outlines still need selective OCR. OCR was not run by this inspection. Candidates are not imported into previously approved clue registries.", "",
                  "Image coverage is the clipped union of occurrence bounding boxes, not visible ink. Small logos or annotation stamps alone do not force hybrid classification. Searchable scans remain raster unless substantial base vector linework is also detected.", "",
                  "Red-colored paths, polygons and comments are review evidence only. Flattened edits cannot reliably be separated into design versus as-built content. Detailed annotations and styles are retained per page.", "",
                  "Scale text and nearby horizontal segments are unverified candidates. NTS and differently scaled plan/profile views must remain distinct. Resizing cannot be ruled out from page size or metadata. No effective ground resolution or registration is inferred.", "",
                  "Geospatial inspection checks page/catalog LGIDict and viewport GEO measures. A detected structure requires external CRS/control validation. No detections does not certify absence of proprietary referencing.", "",
                  "No sheet-location truth is created: geographic controls and independent checkpoints must be collected using Phase 2B.3. Sub-point vector coordinates are drawing precision, not geographic accuracy.", "",
                  "Open REVIEW.html to inspect previews and download decisions. Apply decisions to a NEW snapshot with pdf-study-review. Empty templates confer no acceptance. CSV worksheets are also available.", "",
                  "## Failures and excluded non-PDF inputs", "", json.dumps({"errors": report["errors"], "non_pdf_inputs": report["non_pdf_inputs"]}, indent=2), "",
                  "## Repeated evidence", "", "Repeated base content and full-page raster pixel digests are diagnostics, not proof of independent drawings or sheet coverage. MD5 image digests identify decoded pixels only; SHA-256 remains the source evidence identifier.", "", json.dumps(report["repeated_evidence"], indent=2), ""])
    (output / "ASSESSMENT.md").write_text("\n".join(lines), encoding="utf-8")


def run_study(config_path, output):
    config_path, output = Path(config_path).resolve(), Path(output).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    directory = (config_path.parent / config["input_directory"]).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"Set input_directory in {config_path}: {directory}")
    if output == directory or output in directory.parents or directory in output.parents:
        raise ValueError("Study output must be outside the PDF input tree")
    if output.exists():
        raise FileExistsError(output)
    criteria = criteria_with_defaults(config.get("criteria"))
    settings = {"preview_dpi": config.get("preview_dpi", 72), "max_preview_pixels": config.get("max_preview_pixels", 2200000)}
    if type(config.get("recursive", False)) is not bool:
        raise ValueError("recursive must be boolean")
    if (type(settings["preview_dpi"]) not in (int, float) or not math.isfinite(settings["preview_dpi"]) or settings["preview_dpi"] <= 0
            or type(settings["max_preview_pixels"]) is not int or settings["max_preview_pixels"] < 16):
        raise ValueError("Invalid preview settings")
    backend = load_pdf_backend()
    paths = sorted((p for p in (directory.rglob("*") if config.get("recursive") else directory.iterdir()) if p.is_file()),
                   key=lambda p: p.relative_to(directory).as_posix())
    sources = [p for p in paths if p.suffix.lower() == ".pdf"]
    prior = set(config.get("prior_pilot_files", []))
    selected_names = {p.relative_to(directory).as_posix() for p in sources}
    if prior - selected_names:
        raise ValueError("prior_pilot_files refers to PDF(s) outside the selected sample")
    output.mkdir(parents=True)
    report = {"schema_version": 1, "run_id": str(uuid.uuid4()), "started_at": now(),
              "input_directory": str(directory), "config_path": str(config_path), "config_sha256": file_sha256(config_path),
              "sample_description": config.get("sample_description", "Selected local sample; not an archive-wide estimate"),
              "pymupdf_version": str(backend.VersionBind), "criteria": criteria, "settings": settings,
              "coordinates": "Unrotated visible page points, top-left origin, 72 points/inch; no GIS transform",
              "documents": [], "errors": [], "non_pdf_inputs": [{"relative_path": p.relative_to(directory).as_posix(), "size_bytes": p.stat().st_size,
                                                                        "sha256": file_sha256(p), "status": "not_inspected_non_pdf"} for p in paths if p.suffix.lower() != ".pdf"],
              "classification_accuracy": None, "ground_truth_status": "No independently accepted classification references supplied"}
    write_json(output / "config-input.json", config)
    handler = logging.FileHandler(output / "inspection.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    previous_level = LOGGER.level
    LOGGER.setLevel(logging.INFO)
    try:
        for number, source in enumerate(sources, 1):
            relative = source.relative_to(directory).as_posix()
            LOGGER.info("Inspecting %d/%d %s", number, len(sources), relative)
            doc_dir = f"documents/document-{number:04d}"
            try:
                doc = inspect_document(source, output / doc_dir, settings, criteria)
            except Exception as exc:
                try:
                    source_hash = file_sha256(source)
                except OSError:
                    source_hash = None
                (output / doc_dir).mkdir(parents=True, exist_ok=True)
                doc = {"sha256": source_hash, "size_bytes": source.stat().st_size, "page_count": None, "pages": [],
                       "status": "failed", "source_unchanged": None, "errors": [{"stage": "document", "error": f"{type(exc).__name__}: {exc}"}]}
            doc.update(filename=source.name, relative_path=relative, cohort="prior_pilot_comparison" if relative in prior else "new_representative", directory=doc_dir)
            for page in doc["pages"]:
                page["page_id"] = f"{doc['sha256']}:{relative}:{page['page_number']}"
                page["source_sha256"] = doc["sha256"]
                if page.get("directory"):
                    page["directory"] = f"{doc_dir}/{page['directory']}"
                    write_json(output / page["directory"] / "page.json", page)
            report["documents"].append(doc)
            report["errors"].extend(dict(e, relative_path=relative) for e in doc["errors"])
            if doc["errors"]:
                LOGGER.error("%s: %s", relative, doc["errors"])
        pages = [p for d in report["documents"] for p in d["pages"]]
        report["summary"] = _summarize(pages)
        report["cohorts"] = {cohort: dict(_summarize([p for d in report["documents"] if d["cohort"] == cohort for p in d["pages"]]),
                                         documents=sum(d["cohort"] == cohort for d in report["documents"])) for cohort in ("new_representative", "prior_pilot_comparison")}
        base, rasters = defaultdict(list), defaultdict(list)
        for doc in report["documents"]:
            for page in doc["pages"]:
                if page.get("directory") and page.get("vectors") and page.get("text") and page.get("images"):
                    fingerprint = [page["bounds"], file_sha256(output / page["directory"] / "native-vectors.json"),
                                   file_sha256(output / page["directory"] / "native-text.txt"),
                                   [(im["digest"], im["bbox"]) for im in page["images"]["occurrences"]]]
                    digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
                    if page["vectors"]["path_count"] or page["text"]["characters"] or page["images"]["occurrence_count"]:
                        base[digest].append({"relative_path": doc["relative_path"], "page_number": page["page_number"]})
                    if page["images"]["coverage_bbox_union"] >= criteria["raster_dominance"]:
                        for im in page["images"]["occurrences"]:
                            rasters[im["digest"]].append({"relative_path": doc["relative_path"], "page_number": page["page_number"]})
        report["repeated_evidence"] = {"identical_base_content_fingerprints": [{"sha256": k, "pages": v} for k, v in base.items() if len(v) > 1],
                                       "repeated_full_scan_pixel_digests": [{"md5": k, "pages": v} for k, v in rasters.items() if len(v) > 1]}
        report.update(status="empty" if not sources else "partial" if report["errors"] else "complete", finished_at=now())
        write_reports(report, output)
        LOGGER.info("Finished %s: %d documents, %d pages", report["status"], len(sources), len(pages))
    finally:
        LOGGER.removeHandler(handler)
        LOGGER.setLevel(previous_level)
        handler.close()
    return report


def apply_study_review(inspection_path, decisions_path, output):
    """Keep automated evidence immutable; append validated decisions to a new snapshot.

    Review is local attestation, not authentication. AI decisions remain in history
    but cannot establish independently accepted classification references.
    """
    inspection_path, decisions_path, output = Path(inspection_path).resolve(), Path(decisions_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    original = json.loads(inspection_path.read_text(encoding="utf-8"))
    decision = json.loads(decisions_path.read_text(encoding="utf-8"))
    is_snapshot = "inspection_path" in original and "reviews" in original
    base_path = Path(original["inspection_path"]) if is_snapshot else inspection_path
    base_hash = original["inspection_sha256"] if is_snapshot else file_sha256(base_path)
    if file_sha256(base_path) != base_hash or decision.get("inspection_sha256") != base_hash or decision.get("run_id") != original["run_id"]:
        raise ValueError("Review does not match original inspection hash/run")
    if is_snapshot and decision.get("parent_snapshot_sha256") != file_sha256(inspection_path):
        raise ValueError("Further corrections must bind parent_snapshot_sha256 to the current snapshot")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    pages = {p["page_id"]: p for d in base["documents"] for p in d["pages"]}
    sources = {p["page_id"]: d for d in base["documents"] for p in d["pages"]}
    reviews = deepcopy(original.get("reviews", {})) if is_snapshot else {}
    seen = set()
    checked_sources = set()
    for entry in decision.get("decisions", []):
        pid, action = entry.get("page_id"), entry.get("action")
        if pid not in pages or pid in seen:
            raise ValueError("Unknown or duplicate page_id")
        seen.add(pid)
        if action == "unreviewed":
            continue
        if action not in {"confirm", "correct", "reject", "unreadable"}:
            raise ValueError("Unknown review action")
        automated = pages[pid]["classification"]
        identity = review_identity(decision.get("reviewer"), entry.get("reason"), decision.get("reviewer_type"),
                                   decision.get("independent"), automated["author"])
        labels, primary = entry.get("labels"), entry.get("primary_class")
        if primary not in PRIMARY_CLASSES or not isinstance(labels, list) or not labels or any(v not in LABELS for v in labels) or len(set(labels)) != len(labels) or primary not in labels:
            raise ValueError("Valid primary class and unique supported labels including primary are required")
        if action == "confirm" and (primary != automated["primary_class"] or set(labels) != set(automated["labels"])):
            raise ValueError("Confirm must retain automated classes; use correct for changes")
        accepted = action in {"confirm", "correct"} and identity["reviewer_type"] == "human" and identity["independent"]
        source = sources[pid]
        source_path = (Path(base["input_directory"]) / source["relative_path"]).resolve()
        if source_path not in checked_sources and source.get("sha256"):
            if file_sha256(source_path) != source["sha256"]:
                raise ValueError("PDF source evidence changed since inspection")
            checked_sources.add(source_path)
        if accepted and not source.get("sha256"):
            raise ValueError("Independent acceptance requires a known PDF source hash")
        page = pages[pid]
        for artifact in page.get("artifacts", []):
            evidence_path = (base_path.parent / page["directory"] / artifact["file"]).resolve()
            if base_path.parent not in evidence_path.parents or file_sha256(evidence_path) != artifact["sha256"]:
                raise ValueError("Page evidence changed since inspection")
        history = deepcopy(reviews.get(pid, {}).get("history", []))
        event = {"action": action, "primary_class": primary, "labels": labels, "identity": identity,
                 "independently_accepted": accepted, "decisions_sha256": file_sha256(decisions_path)}
        history.append(event)
        reviews[pid] = dict(event, automated=automated, history=history)
    result = {"schema_version": 1, "run_id": original["run_id"], "snapshot_id": str(uuid.uuid4()), "created_at": now(),
              "inspection_path": str(base_path), "inspection_sha256": base_hash,
              "parent_path": str(inspection_path), "parent_sha256": file_sha256(inspection_path), "reviews": reviews,
              "independently_accepted_pages": sum(r["independently_accepted"] for r in reviews.values()),
              "classification_accuracy": None, "accuracy_status": "Not scored: reviews alone do not establish a blinded independent classification evaluation"}
    output.mkdir(parents=True)
    write_json(output / "classification-review.json", result)
    write_json(output / "decisions-input.json", decision)
    _csv(output / "classification-review.csv", [dict(page_id=pid, **r) for pid, r in reviews.items()],
         ["page_id", "action", "primary_class", "labels", "independently_accepted", "identity", "automated", "history"])
    return result
