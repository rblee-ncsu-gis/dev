"""Offline, read-only visual inspection of an OCR run; no engine or approvals."""

import html
import json
import math
from pathlib import Path
import shutil
from urllib.parse import quote

from .pdf_extract import file_sha256, write_json


def escaped(value):
    return html.escape(str(value), quote=True)


def image_asset(source, digest, output, relative_name):
    """Snapshot external evidence without changing it; never show changed bytes as evidence."""
    try:
        path = Path(source).resolve()
        actual = file_sha256(path)
        if not digest or actual != digest:
            raise ValueError("Image hash mismatch or missing recorded hash")
        if not path.is_relative_to(output):
            destination = output / relative_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and file_sha256(destination) != digest:
                raise FileExistsError("Report snapshot differs from recorded image")
            if not destination.exists():
                shutil.copyfile(path, destination)
            if file_sha256(destination) != digest:
                raise ValueError("Image changed while snapshotting")
            path = destination
        return {"url": quote(path.relative_to(output).as_posix(), safe="/"), "sha256": actual, "error": None}
    except (OSError, TypeError, ValueError) as exc:
        return {"url": None, "error": str(exc)}


def word_overlay(words, processed):
    boxes = []
    for word in words:
        bbox = word.get("bbox_processed", [])
        if len(bbox) != 4 or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in bbox):
            continue
        x0, y0, x1, y1 = bbox
        boxes.append(f'<rect x="{x0}" y="{y0}" width="{max(0, x1-x0)}" height="{max(0, y1-y0)}">'
                     f'<title>{escaped(word.get("text", ""))}; confidence {escaped(word.get("confidence"))}</title></rect>')
    return (f'<svg aria-label="OCR word boxes" viewBox="0 0 {int(processed["width"])} {int(processed["height"])}" '
            f'preserveAspectRatio="none">{"".join(boxes)}</svg>')


def picture(asset, label, *, words=None, processed=None):
    if not asset["url"]:
        return f'<p class="error">Image unavailable: {escaped(asset["error"])}</p>'
    url = escaped(asset["url"])
    overlay = word_overlay(words, processed) if processed and words else ""
    return (f'<a href="{url}" target="_blank" rel="noopener">Open image at full size</a>'
            f'<div class="frame"><img loading="lazy" src="{url}" alt="{escaped(label)}">{overlay}</div>')


def write_visual_report(report, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources, assets = {}, {"sources": {}, "processed": []}
    for index, image in enumerate(report["images"], 1):
        extension = Path(image["path"]).suffix.lower()
        asset = image_asset(image["path"], image["sha256"], output, f"source-images/image-{index:04d}{extension}")
        sources[image["id"]] = asset
        assets["sources"][image["id"]] = asset
    audits = {(comparison["variant"], target["clue_id"]): target
              for comparison in report.get("comparison", []) if comparison.get("metrics")
              for target in comparison["metrics"]["targets"]}
    cards = []
    for index, result in enumerate(report["results"], 1):
        processed = result.get("processed")
        source = sources.get(result["image_id"], {"url": None, "error": "No source metadata"})
        asset = (image_asset(processed["file"], processed["sha256"], output, f"processed-images/image-{index:04d}.png")
                 if processed else {"url": None, "error": "Image preparation did not complete"})
        assets["processed"].append({"image_id": result["image_id"], "variant": result["variant"], **asset})
        text = result.get("text")
        if text is None:
            text = f"No recognition output ({result['status']})."
        elif not text.strip():
            text = "No text detected (empty recognition)."
        words = result.get("words", [])
        word_rows = "".join('<tr>' + ''.join(f'<td>{escaped(word.get(key))}</td>' for key in
                            ("text", "confidence", "bbox_processed", "bbox_page")) + '</tr>' for word in words)
        audit = audits.get((result["variant"], result.get("clue_id")))
        audit_html = (f'<details><summary>Accepted-reference score audit</summary><pre>{escaped(json.dumps(audit, indent=2))}</pre></details>'
                      if audit else '<p>Accuracy and false positives: not measured for this result.</p>')
        metadata = {"source_image_sha256": result["source_image_sha256"],
                    "tesseract_version": result.get("tesseract_version", report.get("engine", {}).get("version")),
                    "ocr_configuration": result.get("ocr_configuration", report.get("config")),
                    "preprocessing": result.get("preprocessing", processed.get("method") if processed else None),
                    "confidence_mean": result.get("confidence_mean"), "command": result.get("command"),
                    "error": result.get("error")}
        cards.append(f'<article data-variant="{escaped(result["variant"])}" data-status="{escaped(result["status"])}">'
                     f'<h2>{escaped(result["source_pdf"])} · page {result["page_number"]} · {escaped(result["variant"])}</h2>'
                     f'<p>Image ID: <code>{escaped(result["image_id"])}</code> · Status: <strong>{escaped(result["status"])}</strong></p>'
                     '<div class="columns"><section><h3>Original source crop</h3>' + picture(source, "Original source crop") +
                     '</section><section><h3>Processed image and word boxes</h3>' +
                     picture(asset, "Processed OCR input", words=words, processed=processed) +
                     f'</section><section><h3>Detected text</h3><pre>{escaped(text)}</pre>' + audit_html +
                     f'<details><summary>Attempt configuration and provenance</summary><pre>{escaped(json.dumps(metadata, indent=2))}</pre></details>'
                     f'<details><summary>Unreviewed entity candidates / engineering warnings</summary><pre>{escaped(json.dumps({"entities": result.get("entities", []), "warnings": result.get("engineering_warnings", [])}, indent=2))}</pre></details>'
                     '</section></div>'
                     f'<details><summary>Words ({len(words)}): confidence and bounding boxes</summary><table><thead><tr>'
                     '<th>Text</th><th>Confidence</th><th>Processed pixels</th><th>Original page points</th>'
                     f'</tr></thead><tbody>{word_rows}</tbody></table></details></article>')
    variants = sorted({r["variant"] for r in report["results"]})
    statuses = sorted({r["status"] for r in report["results"]})
    def options(values):
        return '<option value="">All</option>' + ''.join(f'<option>{escaped(value)}</option>' for value in values)
    document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local OCR visual review</title><style>
body{font-family:system-ui,sans-serif;background:#f3f5f7;color:#18252e;margin:0;padding:24px}
header,article{background:white;border:1px solid #d5dde4;border-radius:8px;padding:20px;margin:0 0 20px}
h1{margin-top:0}h2{font-size:1.1rem}.columns{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}
section{min-width:0}.frame{position:relative;margin-top:10px}.frame img{display:block;width:100%;height:auto}
svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}rect{fill:#24b9bd18;stroke:#087d91;stroke-width:1;vector-effect:non-scaling-stroke}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f7;padding:12px}code,td{overflow-wrap:anywhere}
details{margin:14px 0}summary{cursor:pointer}table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{border:1px solid #d5dde4;padding:8px;text-align:left}
select{padding:7px;margin:0 20px 0 6px}.error{color:#9b2d19}[hidden]{display:none!important}
@media(max-width:1000px){.columns{grid-template-columns:1fr}}@media print{select{display:none}article{break-inside:avoid}}
</style></head><body>'''
    document += (f'<header><h1>Local OCR visual review</h1><p>Run: {escaped(report.get("run_id"))} · '
                 f'Status: {escaped(report.get("status"))} · Results: {len(cards)}</p>'
                 f'<p>Evaluation: {escaped(report.get("evaluation"))}</p>'
                 '<p>Read-only inspection. No clue approvals or source edits. AI-reviewed labels are not accepted ground truth. '
                 'Confidence is not accuracy; inspect symbols, dimensions and missed labels.</p>'
                 f'<label>Variant<select id="variant">{options(variants)}</select></label>'
                 f'<label>Status<select id="status">{options(statuses)}</select></label></header>')
    document += "\n".join(cards)
    document += '''<script>
for(const select of document.querySelectorAll('select'))select.addEventListener('change',()=>{
const variant=document.getElementById('variant').value,status=document.getElementById('status').value;
for(const card of document.querySelectorAll('article'))card.hidden=!!((variant&&card.dataset.variant!==variant)||(status&&card.dataset.status!==status));
});</script></body></html>'''
    (output / "REVIEW.html").write_text(document, encoding="utf-8")
    write_json(output / "visual-assets.json", assets)
    return {"results": len(cards), "report": str(output / "REVIEW.html")}


def report_from_file(run_path, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    data = json.loads(Path(run_path).read_text(encoding="utf-8"))
    return write_visual_report(data, output)
