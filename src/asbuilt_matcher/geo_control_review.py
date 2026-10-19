"""Offline drawing/GIS correspondence collection; browser changes are decision drafts."""

from html import escape
import json
from pathlib import Path
import re
import shutil
import uuid
import xml.etree.ElementTree as ET

from .clues import now
from .geo_controls import CRS_UNITS, independently_approved, load_collection, safe_file
from .geo_geometry import parts, project, vertices
from .geo_reference import read_json
from .geo_report import _csv, _map, evaluation_template, write_html
from .geo_stream import collection_events
from .pdf_extract import file_sha256, load_pdf_backend, write_json


def _reference_features(run):
    references = []
    needed = {s['native_id'] for d in run['drawings'] for c in d['candidates'] if c.get('match_type') == 'road_corridor' for s in c['supporting_features']}
    for dataset in run.get('reference_datasets', []):
        if dataset['kind'] != 'roads':
            continue
        path = Path(dataset['path'])
        if file_sha256(path) != dataset['sha256']:
            raise ValueError('Road reference snapshot changed; control collection requires original source')
        for event, f in collection_events(path):
            if event == 'feature' and f['properties'].get(dataset['fields']['id']) in needed:
                references.append({'id': 'roads:' + str(f['properties'][dataset['fields']['id']]), 'native_id': f['properties'][dataset['fields']['id']],
                                   'kind': 'roads', 'geometry': f['geometry'], 'source': str(path), 'source_sha256': dataset['sha256'],
                                   'source_date': dataset.get('metadata', {}).get('exported_at'), 'model_input_landmark': False})
    seen = set()
    for landmark in run.get('supplemental_landmarks', {}).get('landmarks', []):
        for parcel in landmark.get('parcels', []):
            if parcel['native_id'] in seen: continue
            seen.add(parcel['native_id'])
            references.append({'id': 'parcels:' + parcel['native_id'], 'native_id': parcel['native_id'], 'kind': 'parcels',
                               'geometry': parcel['geometry'], 'source': 'Frozen county parcel containment evidence; ownership unverified',
                               'source_sha256': parcel['source_sha256'], 'source_date': None, 'model_input_landmark': False})
    return {'schema_version': 1, 'crs': 'EPSG:4326', 'scope': 'Reference geometry context. Vertex selection proposes a correspondence; it does not establish feature identity.', 'features': references}


def create_collection(run_path, config_path, output):
    run_path, config_path = Path(run_path).resolve(), Path(config_path).resolve()
    run, config = read_json(run_path), read_json(config_path)
    if config.get('target_crs') not in CRS_UNITS:
        raise ValueError('Collection target CRS must be explicit')
    drawings = {d['drawing_id']: d for d in run['drawings']}
    entries, seen = [], set()
    pdf = load_pdf_backend()
    for item in config.get('drawings', []):
        if item.get('drawing_id') not in drawings or item['drawing_id'] in seen:
            raise ValueError('Collection drawing IDs must be known and unique')
        seen.add(item['drawing_id']); drawing = drawings[item['drawing_id']]
        manifest_path = (config_path.parent / item['raster_manifest']).resolve()
        manifest = read_json(manifest_path)
        source = Path(manifest['source']['path'])
        if manifest['source']['sha256'] != drawing['document_sha256'] or file_sha256(source) != drawing['document_sha256']:
            raise ValueError('Raster/source PDF hash differs from frozen drawing identity')
        page = next(p for p in manifest['pages'] if p['page_number'] == drawing['page_number'])
        if page.get('status') != 'complete' or not page.get('composition_policy'):
            raise ValueError('A complete composition-correct raster is required')
        image_path = (manifest_path.parent / page['directory'] / page['full_page']['file']).resolve()
        if manifest_path.parent not in image_path.parents:
            raise ValueError('Raster evidence path escapes manifest directory')
        pixmap = pdf.Pixmap(image_path)
        if (pixmap.width, pixmap.height) != (page['full_page']['width'], page['full_page']['height']):
            raise ValueError('Composition image dimensions differ from raster manifest')
        sheet = item['sheet']
        if not re.fullmatch('[A-Za-z0-9_-]+', sheet):
            raise ValueError('Sheet identifier must be a safe nonblank label')
        if sheet not in drawing['sheet_numbers']:
            raise ValueError('Sheet label differs from independently accepted drawing clue')
        entries.append((item, drawing, manifest_path, source, image_path, page))
    if not entries or len({item['sheet'] for item, *_ in entries}) != len(entries):
        raise ValueError('At least one uniquely labeled sheet is required')
    reference_features = _reference_features(run)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    registry = {'schema_version': 1, 'kind': 'geographic_control_collection', 'snapshot_id': str(uuid.uuid4()), 'created_at': now(),
                'target_crs': config['target_crs'], 'pixel_convention': 'Original unrotated composition image; top-left edge origin, X right, Y down; pixel centre is (column+0.5,row+0.5). No derivative/crop coordinates.',
                'parent': None, 'drawings': [], 'records': [], 'operation_history': [], 'bound_files': {},
                'model_input_reference_locations': run.get('model_input_reference_locations', []),
                'source_run_sha256': file_sha256(run_path)}
    def copy(source, relative):
        target = safe_file(output, relative); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target); registry['bound_files'][relative] = file_sha256(target)
    copy(run_path, 'localization-input.json'); copy(config_path, 'collection-config-input.json')
    write_json(output / 'reference-features.json', reference_features)
    registry['bound_files']['reference-features.json'] = file_sha256(output / 'reference-features.json')
    for item, drawing, manifest_path, source, image_path, page in entries:
        sheet = item['sheet']
        copy(source, f'sources/{sheet}.pdf'); copy(image_path, f'images/{sheet}.png'); copy(manifest_path, f'evidence/{sheet}-raster-manifest.json')
        registry['drawings'].append({'drawing_id': drawing['drawing_id'],
                                    'source': {'source_pdf': drawing['source_pdf'], 'pdf_identifier': drawing['document_sha256'], 'document_sha256': drawing['document_sha256'],
                                               'sheet': sheet, 'page_number': drawing['page_number'], 'bundle_file': f'sources/{sheet}.pdf'},
                                    'image': {'bundle_file': f'images/{sheet}.png', 'original_path': str(image_path), 'sha256': file_sha256(image_path),
                                              **{k: page['full_page'][k] for k in ['width', 'height', 'page_to_pixel', 'bbox', 'effective_dpi']}},
                                    'raster_manifest_sha256': file_sha256(manifest_path)})
    for row in (run.get('source_observations') or {}).get('observations', []):
        for image in row.get('image_references', []):
            relative = image['frozen_image']; path = safe_file(run_path.parent, relative)
            if file_sha256(path) != image['sha256']:
                raise ValueError('Prior source inspection crop hash mismatch')
            copy(path, relative)
    write_json(output / 'controls.json', registry)
    write_control_review(output / 'controls.json')
    return registry


def _interactive_map(drawing, run, features):
    parent = next((d for d in run['drawings'] if d['drawing_id'] == drawing['drawing_id']), None)
    candidates = parent.get('narrowed_candidates') or parent['candidates']
    candidate = next((c for c in candidates if c.get('coverage')), None)
    if not candidate:
        return '<p>No reference map available. Enter independently obtained GIS coordinates manually.</p>'
    wanted = {r['landmark_id'] for r in parent.get('landmark_assessment', {}).get('matches', [])}
    landmarks = [r for r in run.get('supplemental_landmarks', {}).get('landmarks', []) if r['landmark_id'] in wanted]
    origin = run['distance_model']['origin']
    markup = _map(candidate, {}, origin, landmarks)
    root = ET.fromstring(markup[:markup.index('</svg>') + 6])
    low = [float(root.attrib[k]) for k in ['data-low-x', 'data-low-y']]; scale = float(root.attrib['data-scale'])
    points, context = [], []
    for index, f in enumerate(features['features']):
        commands = []
        for part in parts(f['geometry']):
            for ring in (part if 'Polygon' in f['geometry']['type'] else [part]):
                positions = [project(p, origin) for p in ring]
                commands.append('M ' + ' L '.join(f'{20+(p[0]-low[0])*scale:.3f},{360-(p[1]-low[1])*scale:.3f}' for p in positions)
                                + (' Z' if 'Polygon' in f['geometry']['type'] else ''))
        color = '#8a9baa' if f['kind'] == 'roads' else '#7da271'
        context.append(f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="1" opacity=".7"><title>Source context: {escape(f["kind"])} {escape(str(f["native_id"]))}</title></path>')
        for vertex, p in enumerate(vertices(f['geometry'])):
            q = project(p, origin); x, y = 20 + (q[0] - low[0]) * scale, 360 - (q[1] - low[1]) * scale
            if 0 <= x <= 660 and 0 <= y <= 380:
                points.append(f'<circle class="reference-pick" data-feature="{index}" data-vertex="{vertex}" cx="{x:.3f}" cy="{y:.3f}" r="3" fill="#6b3ead" tabindex="0"><title>Propose a correspondence to {escape(f["kind"])} {escape(str(f["native_id"]))}, vertex {vertex}; analyst identity check required</title></circle>')
    boundary = markup.index('>') + 1
    markup = markup[:boundary] + ''.join(context) + markup[boundary:]
    return markup.replace('</svg>', ''.join(points) + '</svg>')


def write_control_review(registry_path):
    registry_path = Path(registry_path).resolve(); output = registry_path.parent
    registry = load_collection(registry_path); run = read_json(output / 'localization-input.json')
    features = read_json(output / 'reference-features.json')
    write_html(run, None, output)
    prior_html = (output / 'REVIEW.html').read_text(encoding='utf-8')
    prior_html = prior_html.replace('<h1>Geographic localization review</h1>', '<h1>Geographic localization review</h1><p><a href="REVIEW.html">Open control collection</a></p>')
    (output / 'GEOGRAPHIC_REVIEW.html').write_text(prior_html, encoding='utf-8')
    write_json(output / 'geographic-evaluation-template.json', evaluation_template(run, output / 'localization-input.json'))
    template = {'schema_version': 1, 'registry_sha256': file_sha256(registry_path), 'operations': [],
                'instructions': 'Offline edits are drafts. Fill real image/GIS evidence, retain original values, and apply into a NEW snapshot. Verified requires an independent human, complete evidence and a distinct evidence author.',
                'control_template': {'action': 'add_control', 'operation_id': None, 'author': None, 'reviewer_type': 'human', 'reason': None,
                                     'values': {'drawing_id': None, 'pixel': None, 'geographic': None, 'transformed_geographic': None,
                                                'feature_type': None, 'description': None, 'reference_feature_id': None, 'estimated_accuracy_m': None,
                                                'role': 'fit', 'independent_of_fit': False, 'historical_change_notes': '',
                                                'evidence': {'source': None, 'source_date': None, 'source_reference': None, 'point_identity': None,
                                                             'historical_consistency': None, 'independently_determined': False, 'model_input_landmark': False}}}}
    template['tie_template'] = {'action': 'add_tie', 'operation_id': None, 'author': None, 'reviewer_type': 'human', 'reason': None,
                               'values': {'left_drawing_id': None, 'right_drawing_id': None, 'left_pixel': None, 'right_pixel': None,
                                          'description': None, 'station_text': None, 'station_verified': False,
                                          'historical_change_notes': '', 'evidence': template['control_template']['values']['evidence']}}
    template['review_template'] = {'action': 'review', 'operation_id': None, 'id': None, 'author': None, 'reviewer_type': 'human',
                                   'reason': None, 'independent': False, 'status': None}
    write_json(output / 'decisions-template.json', template)
    rows = []
    for record in registry['records']:
        rows.append({**record, 'independently_approved': independently_approved(record)})
    _csv(output / 'controls.csv', ['id', 'record_type', 'drawing_id', 'source', 'image_sha256', 'pixel', 'geographic', 'transformed_geographic',
                                 'feature_type', 'description', 'reference_feature_id', 'role', 'estimated_accuracy_m', 'verification_status',
                                 'author', 'proposer_type', 'verification', 'independently_approved', 'history', 'original'], [r for r in rows if r['record_type'] == 'control'])
    _csv(output / 'ties.csv', ['id', 'left_drawing_id', 'right_drawing_id', 'sources', 'left_pixel', 'right_pixel', 'description',
                             'station_text', 'station_verified', 'verification_status', 'author', 'proposer_type', 'verification',
                             'independently_approved', 'history', 'original'], [r for r in rows if r['record_type'] == 'tie'])
    write_json(output / 'approved-correspondences.json', {'schema_version': 1, 'registry_sha256': file_sha256(registry_path),
                                                        'records': [r for r in registry['records'] if independently_approved(r)]})
    panels = []
    for index, d in enumerate(registry['drawings']):
        image = d['image']
        panels.append(f'<section class="sheet" data-sheet="{index}" {"hidden" if index else ""}><h2>{escape(d["source"]["sheet"])} / {escape(d["source"]["source_pdf"])}</h2>'
                      f'<div class="pair"><div><label>Drawing zoom <input class="zoom" type="range" min="1" max="10" step=".25" value="1"></label><div class="viewport"><svg class="drawing" data-drawing="{index}" viewBox="0 0 {image["width"]} {image["height"]}"><image href="{image["bundle_file"]}" width="{image["width"]}" height="{image["height"]}"/><g class="markers"></g></svg></div><p>Click the original composition image to record pixel X/Y. Zoom and scroll for detail.</p></div>'
                      f'<div><h3>Geographic reference context</h3>{_interactive_map(d,run,features)}<p>Purple vertices select exact source geometry coordinates as proposals. Red landmark input points cannot be selected as controls. Source geometry corners may not identify the same physical feature in the drawing.</p></div></div></section>')
    data = {'registry': registry, 'registry_sha256': file_sha256(registry_path), 'reference_features': features}
    payload = json.dumps(data, ensure_ascii=False).replace('<', chr(92) + 'u003c').replace('&', chr(92) + 'u0026')
    options = ''.join(f'<option value="{i}">{escape(d["source"]["sheet"])}</option>' for i, d in enumerate(registry['drawings']))
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Independent geographic control collection</title>
<style>body{font:16px system-ui;margin:1.5rem;color:#172a36}h1{font-size:1.6rem}.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem}.viewport{height:480px;overflow:auto;background:#eee;border:1px solid #999}.drawing{display:block;width:100%;cursor:crosshair}.pair svg:not(.drawing){width:100%;background:#f5f9fa}.reference-pick{cursor:pointer}label{display:inline-block;margin:.35rem}input,select,textarea,button{font:inherit;max-width:100%}input[type=text]{width:19rem}input[type=number]{width:10rem}textarea{width:25rem;height:4rem}fieldset{margin:1rem 0}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbc;padding:.4rem;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f6;padding:1rem}.notice{background:#fff4d5;padding:1rem}.error{color:#a00000}button{margin:.3rem}.markers circle{fill:#e63b26;stroke:white;stroke-width:2px;vector-effect:non-scaling-stroke}@media(max-width:900px){.pair{grid-template-columns:1fr}}</style>
<h1>Independent geographic control collection</h1><p><a href="GEOGRAPHIC_REVIEW.html">Corridor, landmarks, stationing and source crop review</a> · <a href="controls.json">Frozen registry</a> · <a href="decisions-template.json">Decision template</a></p>
<p class="notice">No real controls or ground coordinates are prefilled. Browser edits and approvals are <strong>draft operations</strong>. Download decisions and run <code>controls-apply</code> into a new directory to validate and preserve them. Source images and earlier snapshots stay unchanged. This page does not fit or approve a drawing location.</p>
<label>Sheet <select id="sheet-select">OPTIONS</select></label><label>Mode <select id="mode"><option value="control">Geographic control/checkpoint</option><option value="tie">Adjacent-sheet image tie (no ground coordinate)</option></select></label>
PANELS
<fieldset><legend>Actor and audit reason</legend><label>Name <input id="author" type="text"></label><label>Actor type <select id="reviewer-type"><option value="human">Human analyst</option><option value="ai">AI suggestion</option></select></label><label>Reason <input id="reason" type="text"></label></fieldset>
<fieldset><legend>Proposed correspondence</legend><p id="editing">New record</p><label>Description <input id="description" type="text"></label>
<div id="control-fields"><label>Pixel X <input id="pixel-x" type="number" step="any"></label><label>Pixel Y <input id="pixel-y" type="number" step="any"></label><label>Role <select id="role"><option value="fit">Fit control</option><option value="checkpoint">Held-out checkpoint</option></select></label><label><input id="independent-fit" type="checkbox"> Checkpoint collected independently of fitting</label><br>
<label>GIS CRS <select id="crs"><option>EPSG:2264</option><option>EPSG:4326</option></select></label><label>Geographic X <input id="geo-x" type="number" step="any"></label><label>Geographic Y <input id="geo-y" type="number" step="any"></label><label>Feature type <input id="feature-type" type="text"></label><label>GIS feature ID <input id="feature-id" type="text"></label><label>Estimated accuracy (m, blank if unknown) <input id="accuracy" type="number" step="any" min="0"></label>
<p>No automatic datum conversion. To record externally transformed coordinates, use the JSON decision template with explicit operation/input/output provenance.</p></div>
<div id="tie-fields" hidden><label>Left sheet <select id="left-sheet">OPTIONS</select></label><label>Left X <input id="left-x" type="number" step="any"></label><label>Left Y <input id="left-y" type="number" step="any"></label><button id="pick-left" type="button">Use current image pick for left</button><br><label>Right sheet <select id="right-sheet">OPTIONS</select></label><label>Right X <input id="right-x" type="number" step="any"></label><label>Right Y <input id="right-y" type="number" step="any"></label><button id="pick-right" type="button">Use current image pick for right</button><label>Station text (optional) <input id="station" type="text"></label><label><input id="station-verified" type="checkbox"> This tied feature's station was independently checked in both sheets</label></div>
<label>Geographic/source evidence <input id="source" type="text"></label><label>Source date (blank if unknown) <input id="source-date" type="date"></label><label>Evidence/reference identifier <input id="source-reference" type="text"></label><br><label>Why this is the same physical point <textarea id="point-identity"></textarea></label><label>Historical consistency / changes <textarea id="historical"></textarea></label><label><input id="independent-evidence" type="checkbox"> Location/identity established independently; not copied from landmark prediction</label>
<p><button id="save" type="button">Queue proposal / edit</button><button id="new" type="button">Start new record</button></p></fieldset>
<fieldset><legend>Independent review of selected record</legend><p>Use a human reviewer distinct from the latest evidence author. Corrections reset acceptance. Never approve using title station numbers or proximity alone.</p><label><input id="independent-review" type="checkbox"> I performed an independent review</label><button id="approve" type="button">Queue independent approval</button><button id="reject" type="button">Queue rejection</button><button id="unreadable" type="button">Queue unreadable decision</button></fieldset>
<p id="message" role="status"></p><h2>Correspondence records</h2><table><thead><tr><th>ID</th><th>Type / sheet</th><th>Description</th><th>Origin</th><th>Committed status</th><th>Action</th></tr></thead><tbody id="records"></tbody></table>
<h2>Decision draft</h2><p><button id="download" type="button">Download decisions JSON</button><label>Load prior draft <input id="draft-file" type="file" accept=".json"></label></p><p>Apply: <code>python scripts/run_asbuilt.py controls-apply &lt;bundle&gt;/controls.json &lt;downloaded-decisions.json&gt; --output &lt;new-bundle-directory&gt;</code>. Reopen the newly generated review to see committed statuses.</p><pre id="queue"></pre><script id="collection-data" type="application/json">PAYLOAD</script><script src="control-review.js"></script></html>'''
    html = html.replace('OPTIONS', options).replace('PANELS', ''.join(panels)).replace('PAYLOAD', payload)
    (output / 'REVIEW.html').write_text(html, encoding='utf-8')
    shutil.copyfile(Path(__file__).parent / 'assets/control_review.js', output / 'control-review.js')
    write_json(output / 'review-provenance.json', {'registry_sha256': file_sha256(registry_path),
               'implementation': {name: file_sha256(Path(__file__).parent / name) for name in ['geo_control_review.py', 'geo_controls.py', 'geo_report.py', 'assets/control_review.js']}})
