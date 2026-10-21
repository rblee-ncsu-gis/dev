"""Offline view-boundary/scale review on the existing immutable evidence model."""

from html import escape
import json
from pathlib import Path
import os
import shutil

from .pdf_extract import file_sha256
from .view_scale import VIEW_TYPES, RELEVANCE


def write_view_review(registry, output):
    script = Path(__file__).parent / 'assets' / 'view_review.js'
    shutil.copyfile(script, output / 'view_review.js')
    payload = {'registry': registry, 'registry_sha256': file_sha256(output / 'views.json')}
    data = json.dumps(payload, ensure_ascii=True).replace('<', '\\u003c')
    options = lambda values: ''.join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in sorted(values))
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>View and scale review</title>
<style>body{font:16px system-ui;margin:20px;color:#172839}header{background:#eef3f5;padding:12px}label{display:inline-block;margin:5px}input[type=number]{width:90px}textarea{width:95%;min-height:55px}.layout{display:grid;grid-template-columns:3fr 2fr;gap:18px}.canvas{overflow:auto;border:1px solid #aaa;max-height:850px}.drawing{display:block;width:100%;min-width:650px;touch-action:none}.drawing .boundary{fill:#19a2ef22;stroke:#0070b9;stroke-width:3;pointer-events:none}.drawing .bar{stroke:#e38200;stroke-width:4;pointer-events:none}.error{color:#ac1f1f}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f6;padding:8px}button{margin:4px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:5px}@media(max-width:1000px){.layout{display:block}}</style>
<h1>Engineering view and scale review</h1>
<p>Proposals are unapproved. Page border, printed scale and locality hints do not establish a registered engineering view. Separate scopes preserve earlier approvals. No geographic coordinates are assigned.</p>
<header><label>Actor <input id="author"></label><label>Type <select id="reviewer-type"><option>unspecified</option><option>human</option><option>ai</option></select></label>
<label><input type="checkbox" id="independent">Independent human review attestation</label><label>Reason <input id="reason" size="48"></label><button id="download">Download queued decisions</button><p id="message" role="status"></p></header>
<label>View <select id="view-select"></select></label><label>Zoom <input id="zoom" type="range" min="1" max="5" step=".25" value="1"></label>
<div class="layout"><section><p id="source"></p><p id="recommendation"></p><label>Pick mode <select id="pick-mode"><option value="boundary">Drag proposed boundary</option><option value="bar">Click bar endpoint 1 then 2</option></select></label><div class="canvas"><svg class="drawing" xmlns="http://www.w3.org/2000/svg"><image/><rect class="boundary"/><line class="bar"/></svg></div><p id="pick-readout"></p><p><a id="prepared-image">Open prepared crop in proposed reading orientation</a>. Zoom/refine raster picks and document uncertainty; display clicks do not imply subpixel accuracy.</p><h2>Native versus OCR evidence</h2><div id="comparison"></div><h2>Preparation / calibration status</h2><pre id="assessment"></pre></section>
<section><h2>View proposal</h2><p id="view-status"></p>
<label>X0 <input type="number" id="x0" step="any"></label><label>Y0 <input type="number" id="y0" step="any"></label><label>X1 <input type="number" id="x1" step="any"></label><label>Y1 <input type="number" id="y1" step="any"></label>
<label>Type <select id="view-type">VIEW_TYPES</select></label><label>Relevance <select id="relevance">RELEVANCE</select></label>
<label>Reading clockwise <select id="orientation"><option>0</option><option>90</option><option>180</option><option>270</option></select> degrees</label>
<label>Scale scope <select id="scale-mode"><option>unknown</option><option>isotropic</option><option>anisotropic</option><option>not_to_scale</option></select></label>
<label>Resizing/distortion assessment <textarea id="distortion"></textarea></label><p>Boundary edits affect current view acceptance only. Prior scale evidence/history remain; changed scope requires explicit reconfirmation.</p>
<button id="save-view">Queue view correction</button><button id="approve-view">Accept view</button><button id="reject-view">Reject view</button><button id="unreadable-view">Unreadable view</button>
<h2>Scale evidence</h2><select id="scale-select"><option value="">New scale evidence</option></select><button id="new-scale">New</button><p id="scale-status"></p>
<label>Actual native segment candidate <select id="native-segment"><option value="">None</option></select></label><button id="use-segment">Use native endpoints</button>
<label>Kind <select id="kind"><option>bar</option><option>statement</option><option>checkpoint</option></select></label><label>Axis <select id="axis"><option>isotropic</option><option>horizontal</option><option>vertical</option></select></label>
<label>Coordinates <select id="coordinates"><option>page</option><option>image</option></select></label><label>Bound image <select id="image-id"></select></label>
<label>Endpoint 1 X <input type="number" id="a-x" step="any"></label><label>Y <input type="number" id="a-y" step="any"></label><label>Endpoint 2 X <input type="number" id="b-x" step="any"></label><label>Y <input type="number" id="b-y" step="any"></label>
<label>Ground distance <input type="number" id="ground" step="any"></label><label>Units <select id="unit"><option value="">Unknown</option><option>foot</option><option>US_survey_foot</option><option>metre</option></select></label><label>Statement paper inches <input type="number" id="paper" step="any"></label>
<label>Transcription / description <textarea id="scale-text"></textarea></label><label>Method <select id="method"><option>manual_transcription</option><option>native_text</option><option>ocr</option><option>native_vector</option><option>raster_manual</option></select></label><label>Evidence reference <input id="reference" size="55"></label>
<label>Applicability <select id="use"><option>unresolved</option><option>current_view</option><option>nominal_only</option><option>excluded</option></select></label><label><input id="applicable" type="checkbox">Applies to this view/axis</label><label><input id="distortion-checked" type="checkbox">Resizing/distortion checked</label><label><input id="held-out" type="checkbox">Independent of calibration (checkpoint only)</label>
<label>Uncertainty / limitations <textarea id="scale-notes"></textarea></label><p id="measurement"></p>
<button id="calculate">Preview measurement</button><button id="save-scale">Queue scale evidence</button><button id="approve-scale">Accept scale evidence</button><button id="reject-scale">Reject scale evidence</button><button id="unreadable-scale">Unreadable scale evidence</button>
<p>Accepting text or a measured bar does not automatically calibrate. Effective scale also requires an accepted view, applicable axis, distortion assessment and consistent accepted measurements.</p></section></div>
<h2>Queued operations</h2><pre id="queue"></pre><script id="view-data" type="application/json">PAYLOAD</script><script src="view_review.js"></script></html>'''
    html = html.replace('VIEW_TYPES', options(VIEW_TYPES)).replace('RELEVANCE', options(RELEVANCE)).replace('PAYLOAD', data)
    (output / 'REVIEW.html').write_text(html, encoding='utf-8')


def write_text_comparison(rows, targets, folder, run_folder, output):
    by_id = {t['id']: t for t in targets}
    relative = lambda p: Path(os.path.relpath(p, folder)).as_posix()
    cards = []
    for row in rows:
        target = by_id[row['view_id']]
        cards.append(f'<article id="{escape(row["view_id"])}"><h2>{escape(row["view_id"])} / {escape(row["variant"])}</h2>'
            f'<p>{escape(row["status"])}; word confidence {row["confidence_mean"]}. Accuracy is unmeasured.</p>'
            f'<a href="{escape(relative(Path(target["path"])), quote=True)}"><img loading="lazy" src="{escape(relative(Path(target["path"])), quote=True)}" alt="Composition-correct OCR target"></a>'
            f'<div class="pair"><section><h3>Base native text</h3><pre>{escape(row["native_text"] or "No native text in selected focus.")}</pre></section>'
            f'<section><h3>OCR output</h3><pre>{escape(row["ocr_text"] or "No recognition text.")}</pre></section></div></article>')
    (folder / 'comparison.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Native versus OCR</title>'
        '<style>body{font:16px system-ui;margin:24px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{max-width:95%;max-height:400px}pre{white-space:pre-wrap}article{border-top:1px solid #aaa}</style>'
        '<h1>Selective native / OCR comparison</h1><p>Recognitions are unverified; names, dimensions, stationing and scale text may conflict. No merging or clue approval is performed. Duplicate/derived targets are not independent accuracy cases.</p>'
        f'<p><a href="{escape(relative(run_folder / "REVIEW.html"), quote=True)}">Existing OCR visual report: word boxes, confidence and source derivatives</a></p>'
        + ''.join(cards) + '</html>', encoding='utf-8')
