"""Immutable per-view review, preparation and handoff; reuses existing PDF/OCR/control evidence."""

from copy import deepcopy
import json
import math
from pathlib import Path
import re
import shutil
import uuid

from .clues import now, review_identity
from .geo_controls import safe_file, load_collection, independently_approved
from .pdf_extract import file_sha256, load_pdf_backend, write_json
from .pdf_study import _csv
from .raster import render_region, validate_bbox
from .ocr import preprocess, run_baseline
from .view_scale import (VIEW_FIELDS, SCALE_FIELDS, validate_view, validate_scale, revision,
                         assess_scale, measure, points_page, number)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _bind(registry, path):
    path = Path(path).resolve()
    digest = file_sha256(path)
    if str(path) in registry['external_files'] and registry['external_files'][str(path)] != digest:
        raise ValueError('External evidence changed')
    registry['external_files'][str(path)] = digest
    return str(path)


def _asset(registry, output, path):
    registry['bound_files'][Path(path).relative_to(output).as_posix()] = file_sha256(path)


def _copy(registry, output, source, relative):
    dest = safe_file(output, relative)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    _asset(registry, output, dest)
    return relative


def _record(identity, spec, author='phase3b-ai-proposal', actor_type='ai'):
    return {'id': identity, 'spec': deepcopy(spec), 'original': deepcopy(spec),
            'last_evidence_author': author, 'proposer_type': actor_type,
            'verification_status': 'unverified', 'verification': None, 'history': []}


def _scale_spec(view, **values):
    base = {'kind': 'statement', 'axis': 'isotropic', 'coordinate_space': 'page', 'image_id': None,
            'endpoints': None, 'ground_distance': None, 'ground_unit': None, 'paper_inches': None,
            'text': '', 'source_method': 'manual_transcription', 'source_reference': '', 'source_bbox': None,
            'native_segment': None, 'view_revision': revision(view['spec']), 'use': 'unresolved',
            'applicability_confirmed': False, 'distortion_checked': False,
            'independent_of_calibration': False, 'notes': ''}
    return base | values


def prepare_view(registry, view, output):
    """Always include annotations. Never change PDF rotation on disk or assign a map CRS."""
    page = registry['pages'][view['page_id']]
    token = f"{view['id']}-{revision(view['spec'])[:16]}"
    if token in registry['images']:
        view['image_id'] = token
        return
    folder = output / 'images' / token
    folder.mkdir(parents=True)
    pdf = load_pdf_backend()
    with pdf.open(page['source_path']) as doc:
        source_page = doc[page['page_number'] - 1]
        source_page.set_rotation(0)
        rendered = render_region(pdf, source_page, folder / 'unrotated.png', view['spec']['bbox'],
                                 registry['preparation']['dpi'], registry['preparation']['max_pixels'])
    metadata = {'path': str(folder / 'unrotated.png'), 'width': rendered['width'], 'height': rendered['height'],
                'effective_dpi': rendered['effective_dpi'], 'page_to_pixel': rendered['page_to_pixel']}
    # Reuse the OCR adapter's reversible orthogonal orientation transform, without recognizing text.
    processed = preprocess(metadata, {'id': 'reading_orientation', 'rotation': view['spec']['reading_orientation']},
                           folder / 'oriented.png', registry['preparation']['max_pixels'])
    image = {'file': (folder / 'oriented.png').relative_to(output).as_posix(), 'sha256': processed['sha256'],
             'width': processed['width'], 'height': processed['height'], 'bbox': rendered['bbox'],
             'effective_dpi': rendered['effective_dpi'], 'resolution_capped': rendered['resolution_capped'],
             'page_to_pixel': processed['page_to_processed'], 'pixel_to_page': processed['processed_to_page'],
             'unrotated_page_to_pixel': rendered['page_to_pixel'], 'input_to_oriented': processed['input_to_processed'],
             'view_revision': revision(view['spec']), 'page_id': view['page_id'], 'includes_annotations': True,
             'map_crs': None, 'format': 'png', 'original': rendered}
    registry['images'][token] = image
    view['image_id'] = token
    for p in folder.iterdir():
        _asset(registry, output, p)


def _native_segment(page, ref):
    paths = read(page['vectors_path'])
    try:
        item = paths[ref['path_index']]['items'][ref['item_index']]
        if item[0] != 'l':
            raise ValueError('Native segment must be a line operation')
        return item[1:3]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError('Native segment reference is invalid') from exc


def validate_registry(registry, *, prepared=True):
    seen = set()
    for v in registry['views']:
        if v['id'] in seen or not re.fullmatch(r'[A-Za-z0-9_-]+', v['id']):
            raise ValueError('View IDs must be safe and unique')
        seen.add(v['id'])
        page = registry['pages'][v['page_id']]
        if registry['external_files'].get(page['source_path']) != page['document_sha256']:
            raise ValueError('Page identity differs from bound source PDF hash')
        validate_view(v['spec'], page['bounds'])
        if v['verification_status'] == 'verified' and not independently_approved(v):
            raise ValueError('Verified view lacks independent human acceptance')
        image = registry['images'][v['image_id']]
        if image['page_id'] != v['page_id'] or (prepared and image['view_revision'] != revision(v['spec'])):
            raise ValueError('Prepared image differs from current view revision')
        ids = set()
        for s in v['scales']:
            if s['id'] in ids:
                raise ValueError('Duplicate scale ID')
            ids.add(s['id'])
            spec = s['spec']
            validate_scale(spec, page['bounds'], registry['images'], complete=s['verification_status'] == 'verified')
            if spec['coordinate_space'] == 'image' and registry['images'][spec['image_id']]['page_id'] != v['page_id']:
                raise ValueError('Scale image belongs to another page')
            if spec['native_segment'] is not None:
                native = _native_segment(page, spec['native_segment'])
                if spec['endpoints'] is None or any(math.dist(a, b) > 1e-4 for a, b in zip(native, points_page(spec, page['bounds'], registry['images']))):
                    raise ValueError('Measurement endpoints differ from bound native segment')
            if s['verification_status'] == 'verified' and not independently_approved(s):
                raise ValueError('Verified scale lacks independent human acceptance')


def load_views(path):
    path = Path(path).resolve()
    registry = read(path)
    if registry.get('kind') != 'engineering_view_collection' or registry.get('schema_version') != 1:
        raise ValueError('Expected engineering_view_collection schema version 1')
    for name, digest in registry['external_files'].items():
        if file_sha256(name) != digest:
            raise ValueError('External evidence hash mismatch: ' + name)
    for name, digest in registry['bound_files'].items():
        if file_sha256(safe_file(path.parent, name)) != digest:
            raise ValueError('Bound evidence hash mismatch: ' + name)
    if registry.get('control_registry'):
        load_collection(registry['control_registry'])  # Reuse original source/control validation, never mutate it.
    validate_registry(registry)
    return registry


def create_views(study_path, config_path, output):
    study_path, config_path, output = Path(study_path).resolve(), Path(config_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    study, config = read(study_path), read(config_path)
    if study.get('schema_version') != 1 or study.get('status') != 'complete':
        raise ValueError('A complete Phase 3A study is required')
    settings = config.get('preparation', {'dpi': 200, 'max_pixels': 40000000})
    if not number(settings.get('dpi')) or settings['dpi'] <= 0 or type(settings.get('max_pixels')) is not int or settings['max_pixels'] < 16:
        raise ValueError('Positive finite dpi and integer pixel budget required')
    pages = {(d['relative_path'], p['page_number']): (d, p) for d in study['documents'] for p in d['pages']}
    entries = config['views']
    if not entries or len({v['id'] for v in entries}) != len(entries):
        raise ValueError('Nonempty, uniquely identified pilot views required')
    for v in entries:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', v['id']) or not str(v.get('reason', '')).strip():
            raise ValueError('Safe view IDs and selection rationale required')
        d, p = pages[(v['source_pdf'], v['page_number'])]
        validate_view(v['spec'], p['bounds'])
        validate_bbox(v['ocr_focus_bbox'], v['spec']['bbox'])
        if file_sha256(Path(study['input_directory']) / d['relative_path']) != d['sha256']:
            raise ValueError('PDF differs from study source')
    registry = {'schema_version': 1, 'kind': 'engineering_view_collection', 'snapshot_id': str(uuid.uuid4()),
                'created_at': now(), 'parent': None, 'preparation': settings, 'external_files': {}, 'bound_files': {},
                'pages': {}, 'images': {}, 'views': [], 'operation_history': [], 'ocr_comparison': None,
                'sample_selection': 'Pilot proposals under analyst-authorized scope; selection is not classification acceptance',
                'coordinate_system': 'Unrotated MuPDF visible-page points, top-left, 72 points/inch; not map coordinates',
                'map_crs': None, 'intended_future_crs': 'EPSG:2264', 'control_registry': None,
                'accuracy': {'scale_error': None, 'reason': 'No independent accepted check measurements supplied'}}
    _bind(registry, study_path); _bind(registry, config_path)
    controls = None
    if config.get('control_registry'):
        control_path = (config_path.parent / config['control_registry']).resolve()
        controls = load_collection(control_path)
        registry['control_registry'] = _bind(registry, control_path)
    localities = None
    if config.get('locality_run'):
        locality_path = (config_path.parent / config['locality_run']).resolve()
        localities = read(locality_path)
        registry['locality_run'] = _bind(registry, locality_path)
    output.mkdir(parents=True)
    for item in entries:
        d, p = pages[(item['source_pdf'], item['page_number'])]
        pid = p['page_id']
        if pid not in registry['pages']:
            source = Path(study['input_directory']) / d['relative_path']
            for artifact in p['artifacts']:
                path = study_path.parent / p['directory'] / artifact['file']
                if file_sha256(path) != artifact['sha256']:
                    raise ValueError('Study page evidence changed')
                _bind(registry, path)
            page_index = len(registry['pages'])
            preview = _copy(registry, output, study_path.parent / p['directory'] / 'composite.png', f'pages/page-{page_index:03d}.png')
            detail = output / f'pages/page-{page_index:03d}-detail.png'
            with load_pdf_backend().open(source) as source_doc:
                source_page = source_doc[p['page_number']-1]; source_page.set_rotation(0)
                detail_metadata = render_region(load_pdf_backend(), source_page, detail, p['bounds'], settings['dpi'], settings['max_pixels'])
            _asset(registry, output, detail)
            page_image_id = f'page-{page_index:03d}-{d["sha256"][:12]}'
            registry['images'][page_image_id] = {'file': detail.relative_to(output).as_posix(), 'sha256': file_sha256(detail),
                'page_id': pid, 'view_revision': None, 'width': detail_metadata['width'], 'height': detail_metadata['height'],
                'bbox': p['bounds'], 'effective_dpi': detail_metadata['effective_dpi'],
                'resolution_capped': detail_metadata['resolution_capped'], 'page_to_pixel': detail_metadata['page_to_pixel'],
                'pixel_to_page': list(~load_pdf_backend().Matrix(detail_metadata['page_to_pixel'])),
                'includes_annotations': True, 'map_crs': None, 'format': 'png'}
            registry['pages'][pid] = {'source_pdf': d['relative_path'], 'source_path': _bind(registry, source),
                'document_sha256': d['sha256'], 'page_number': p['page_number'], 'drawing_id': f"{d['sha256']}:{p['page_number']}",
                'bounds': p['bounds'], 'original_rotation': p['rotation'], 'rotation_matrix': p['rotation_matrix'],
                'derotation_matrix': p['derotation_matrix'], 'boxes': p['boxes'], 'classification': p['classification'],
                'preview': detail.relative_to(output).as_posix(), 'preview_metadata': detail_metadata,
                'study_preview': preview, 'study_preview_metadata': p['preview'], 'page_image_id': page_image_id,
                'annotations': p['annotations'],
                'text_path': str(study_path.parent / p['directory'] / 'native-text.json'),
                'vectors_path': str(study_path.parent / p['directory'] / 'native-vectors.json'),
                'scale_statements': p.get('candidates', {}).get('scale_statements', []), 'native_segments': []}
            page = registry['pages'][pid]
            # Only nominate actual exported line segments near scale text; no distance is invented.
            if p.get('graphical_scale_candidates'):
                paths = read(page['vectors_path'])
                for candidate in p['graphical_scale_candidates']:
                    for i, op in enumerate(paths[candidate['path_index']]['items']):
                        if op[0] == 'l' and op[1:3] == candidate['endpoints']:
                            page['native_segments'].append({'path_index': candidate['path_index'], 'item_index': i, 'endpoints': op[1:3]})
                            break
        page = registry['pages'][pid]
        view = _record(item['id'], item['spec'])
        view.update(page_id=pid, selection_reason=item['reason'], ocr_focus_bbox=item['ocr_focus_bbox'], scales=[],
                    control_references=[], locality_hint=None)
        if controls:
            matches = [drawing for drawing in controls['drawings'] if drawing['drawing_id'] == page['drawing_id']]
            for drawing in matches:
                view['control_references'].append({'registry_path': registry['control_registry'], 'registry_sha256': file_sha256(registry['control_registry']),
                    'drawing_id': drawing['drawing_id'], 'original_image': drawing['image'],
                    'record_ids': [r['id'] for r in controls['records'] if r.get('drawing_id') == drawing['drawing_id']]})
        if localities:
            match = next((r for r in localities['drawings'] if r['drawing_id'] == page['drawing_id']), None)
            if match:
                view['locality_hint'] = {'source_run': registry['locality_run'], 'sha256': file_sha256(registry['locality_run']),
                    'drawing_id': page['drawing_id'], 'status': 'context_only_not_a_view_extent', 'independently_verified': False,
                    'candidates': match.get('narrowed_candidates', [])}
        prepare_view(registry, view, output)
        for n, statement in enumerate(page['scale_statements']):
            # Keep outside-view footer evidence visible, without asserting applicability.
            view['scales'].append(_record(f"{view['id']}-statement-{n+1}", _scale_spec(view,
                text=statement['text'], source_method='native_text', source_reference=page['text_path'], source_bbox=statement['bbox'],
                paper_inches=float(statement['numeric_groups'][0]) if statement['kind'] == 'feet_per_inch' else None,
                ground_distance=float(statement['numeric_groups'][1]) if statement['kind'] == 'feet_per_inch' else None,
                notes='Native statement only; units and applicable view remain unaccepted. Footer scale may not apply to this region.')))
        if item['spec']['engineering_relevance'] == 'engineering' and page['native_segments']:
            segment = page['native_segments'][0]
            view['scales'].append(_record(f"{view['id']}-native-span", _scale_spec(view,
                kind='bar', endpoints=segment['endpoints'], source_method='native_vector',
                native_segment={k: segment[k] for k in ['path_index', 'item_index']},
                source_reference=page['vectors_path'], text='Native scale-area segment; ground distance unknown',
                notes='Actual segment endpoints only. Analyst must identify bar ticks, ground distance, units and applicable view.')))
        registry['views'].append(view)
    validate_registry(registry)
    write_views(registry, output)
    return registry


def apply_views(registry_path, decisions_path, output):
    registry_path, decisions_path, output = Path(registry_path).resolve(), Path(decisions_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    original, decisions = load_views(registry_path), read(decisions_path)
    if decisions.get('registry_sha256') != file_sha256(registry_path):
        raise ValueError('Decisions do not bind the current parent snapshot')
    result = deepcopy(original)
    _bind(result, registry_path)
    seen = {e['operation_id'] for e in result['operation_history']}
    for operation in decisions.get('operations', []):
        oid = operation.get('operation_id')
        if not isinstance(oid, str) or not oid.strip() or oid in seen:
            raise ValueError('Operation IDs must be nonblank and unreplayed')
        seen.add(oid)
        view = next((v for v in result['views'] if v['id'] == operation.get('view_id')), None)
        if view is None:
            raise ValueError('Unknown view ID')
        action, target = operation.get('action'), operation.get('target')
        if target not in {'view', 'scale'} or action not in {'add', 'edit', 'review'}:
            raise ValueError('Supported operations are add-scale and edit/review view or scale')
        record = view if target == 'view' else next((s for s in view['scales'] if s['id'] == operation.get('scale_id')), None)
        if action == 'add':
            if target != 'scale' or record is not None:
                raise ValueError('Add requires a new scale ID')
            sid = operation.get('scale_id')
            if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
                raise ValueError('Safe scale ID required')
            record = _record(sid, operation['spec'], operation.get('author'), operation.get('reviewer_type', 'unspecified'))
            view['scales'].append(record)
        if record is None:
            raise ValueError('Unknown scale ID')
        before = deepcopy({k: v for k, v in record.items() if k not in {'history', 'scales'}})
        identity = review_identity(operation.get('author'), operation.get('reason'), operation.get('reviewer_type', 'unspecified'),
                                   operation.get('independent', False), record['last_evidence_author'] if action == 'review' else 'phase3b-review-system')
        if action == 'edit':
            # Domain-specific edits are complete specs, preventing silent field loss.
            record.update(spec=deepcopy(operation['spec']), last_evidence_author=operation['author'],
                          verification_status='unverified', verification=None)
        elif action == 'review':
            status = operation.get('status')
            if status not in {'verified', 'rejected', 'unreadable', 'unverified'}:
                raise ValueError('Invalid review status')
            if status == 'verified' and (identity['reviewer_type'] != 'human' or identity['independent'] is not True):
                raise ValueError('Acceptance requires independent human review')
            record.update(verification_status=status, verification=identity)
        page = result['pages'][view['page_id']]
        if target == 'view':
            validate_view(record['spec'], page['bounds'])
        else:
            validate_scale(record['spec'], page['bounds'], result['images'], complete=record['verification_status'] == 'verified')
        effort = operation.get('elapsed_seconds')
        interactions = operation.get('interactions')
        if effort is not None and (not number(effort) or effort < 0):
            raise ValueError('Review elapsed_seconds must be nonnegative or null')
        if interactions is not None and (type(interactions) is not int or interactions < 0):
            raise ValueError('Interactions must be nonnegative integers or null')
        event = {'operation_id': oid, 'action': action, 'identity': identity, 'before': before,
                 'after': deepcopy({k: v for k, v in record.items() if k not in {'history', 'scales'}}),
                 'elapsed_seconds': effort, 'interactions': interactions}
        record['history'].append(event)
        result['operation_history'].append({'operation_id': oid, 'view_id': view['id'], 'target': target,
            'record_id': record['id'], 'action': action, 'elapsed_seconds': effort, 'interactions': interactions,
            'reviewer_type': identity['reviewer_type'], 'timestamp': identity['timestamp']})
    # Validate native endpoint references before output is created, not merely after preparing.
    for view in result['views']:
        for s in view['scales']:
            if s['spec']['native_segment']:
                points = _native_segment(result['pages'][view['page_id']], s['spec']['native_segment'])
                if s['spec']['endpoints'] != points or s['spec']['coordinate_space'] != 'page':
                    raise ValueError('Native endpoints must exactly match exported page coordinates')
    validate_registry(result, prepared=False)
    output.mkdir(parents=True)
    for relative in original['bound_files']:
        _copy(result, output, safe_file(registry_path.parent, relative), relative)
    for view in result['views']:
        prepare_view(result, view, output)
    result.update(snapshot_id=str(uuid.uuid4()), created_at=now(), parent={'registry_path': str(registry_path),
                  'registry_sha256': file_sha256(registry_path), 'decisions_sha256': file_sha256(decisions_path)})
    _copy(result, output, registry_path, f"history/{original['snapshot_id']}/views.json")
    _copy(result, output, decisions_path, f"history/{original['snapshot_id']}/decisions.json")
    validate_registry(result)
    write_views(result, output)
    return result


def write_views(registry, output):
    # Detect concurrent edits after rendering/OCR, as well as changes before loading.
    for path, digest in registry['external_files'].items():
        if file_sha256(path) != digest:
            raise ValueError('External evidence changed during processing: ' + path)
    _copy(registry, output, Path(__file__).parent / 'assets' / 'view_review.js', 'view_review.js')
    rows, scale_rows, accepted = [], [], []
    for view in registry['views']:
        page = registry['pages'][view['page_id']]
        assessment = assess_scale(view, view['scales'], page['bounds'], registry['images'])
        view['scale_assessment'] = assessment
        view['spec_revision'] = revision(view['spec'])
        image = registry['images'][view['image_id']]
        row = {'view_id': view['id'], 'source_pdf': page['source_pdf'], 'document_sha256': page['document_sha256'],
               'page_number': page['page_number'], **view['spec'], 'selection_reason': view['selection_reason'],
               'verification_status': view['verification_status'], 'independently_accepted': independently_approved(view),
               'image_id': view['image_id'], 'image_sha256': image['sha256'], 'calibration_status': assessment['status'],
               'missing_evidence': assessment['missing_evidence'], 'history': view['history']}
        rows.append(row)
        for scale in view['scales']:
            scale_rows.append({'view_id': view['id'], 'scale_id': scale['id'], **scale['spec'],
                'verification_status': scale['verification_status'], 'independently_accepted': independently_approved(scale),
                'measurement': measure(scale['spec'], page['bounds'], registry['images']), 'history': scale['history']})
        if independently_approved(view) and view['spec']['engineering_relevance'] == 'engineering' and view['spec']['view_type'] not in {'administrative_supporting', 'title_block_legend', 'vicinity_map', 'other_uncertain'}:
            accepted.append({'view_id': view['id'], 'view_revision': revision(view['spec']),
                'source': {k: page[k] for k in ['source_pdf', 'source_path', 'document_sha256', 'page_number', 'drawing_id']},
                'accepted_view': view['spec'], 'acceptance': view['verification'],
                'original_page_rotation': page['original_rotation'], 'original_boxes': page['boxes'],
                'raster': image, 'view_page_to_image': image['page_to_pixel'],
                'view_local_points_to_image': list(load_pdf_backend().Matrix(1, 0, 0, 1, view['spec']['bbox'][0], view['spec']['bbox'][1]) * load_pdf_backend().Matrix(image['page_to_pixel'])),
                'native_evidence': {'text': page['text_path'], 'vectors': page['vectors_path']},
                'ocr_evidence': registry.get('ocr_comparison'), 'scale': assessment, 'scale_evidence': view['scales'],
                'control_references': view['control_references'], 'locality_hint': view['locality_hint'],
                'map_crs': None, 'registered': False, 'intended_future_crs': 'EPSG:2264',
                'tiff_preparation': {'input': image['file'], 'output_format': 'TIFF', 'compression': 'lossless',
                    'preserve_annotations': True, 'assign_map_crs': False, 'status': 'future_ArcGIS_conversion_not_executed'},
                'limitations': assessment['limitations'] + assessment['missing_evidence']})
    write_json(output / 'views.json', registry)
    _csv(output / 'views.csv', rows, list(rows[0]) if rows else ['view_id'])
    _csv(output / 'scales.csv', scale_rows, list(scale_rows[0]) if scale_rows else ['view_id', 'scale_id'])
    write_json(output / 'handoff.json', {'schema_version': 1, 'kind': 'arcgis_view_handoff',
        'page_coordinates': {'units': 'PDF point', 'points_per_inch': 72, 'origin': 'visible_page_top_left',
                             'rotation': 'unrotated', 'x_axis': 'right', 'y_axis': 'down', 'map_crs': None},
        'registry_sha256': file_sha256(output / 'views.json'), 'registered': False, 'map_crs': None,
        'intended_future_crs': 'EPSG:2264', 'views': accepted,
        'pending_view_ids': [v['id'] for v in registry['views'] if not independently_approved(v)]})
    write_json(output / 'decisions-template.json', {'registry_sha256': file_sha256(output / 'views.json'), 'operations': []})
    write_json(output / 'review-effort.json', {'operations': len(registry['operation_history']),
        'self_reported_elapsed_seconds': sum(r.get('elapsed_seconds') or 0 for r in registry['operation_history']),
        'interactions': sum(r.get('interactions') or 0 for r in registry['operation_history']),
        'actual_independent_human_acceptances': sum(independently_approved(v) for v in registry['views']),
        'notes': 'Elapsed time is self-reported/active browser-session time, not independently measured labor savings.'})
    from .view_review import write_view_review
    write_view_review(registry, output)


def run_view_ocr(registry_path, output, *, config=None, executable=None):
    registry_path, output = Path(registry_path).resolve(), Path(output).resolve()
    registry = load_views(registry_path)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    result = deepcopy(registry)
    _bind(result, registry_path)
    for relative in registry['bound_files']:
        _copy(result, output, safe_file(registry_path.parent, relative), relative)
    session = str(uuid.uuid4())
    run_folder = output / 'recognition' / session
    compare_folder = output / 'comparisons' / session
    compare_folder.mkdir(parents=True)
    comparison_relative = f'comparisons/{session}/comparison.json'
    pdf, targets, native_rows = load_pdf_backend(), [], []
    for view in result['views']:
        page = result['pages'][view['page_id']]
        # Original suggested focus stays distinct from the accepted boundary. A changed
        # view must contain it; otherwise report missing focus evidence rather than clip silently.
        try:
            validate_bbox(view['ocr_focus_bbox'], view['spec']['bbox'])
        except ValueError:
            native_rows.append({'view_id': view['id'], 'status': 'focus_outside_revised_view', 'native_text': None})
            continue
        folder = output / 'ocr-targets' / session / view['id']; folder.mkdir(parents=True)
        with pdf.open(page['source_path']) as doc:
            pg = doc[page['page_number']-1]; pg.set_rotation(0)
            raw = render_region(pdf, pg, folder / 'unrotated.png', view['ocr_focus_bbox'],
                                result['preparation']['dpi'], result['preparation']['max_pixels'])
        source = {'path': str(folder / 'unrotated.png'), **{k: raw[k] for k in ['width', 'height', 'effective_dpi', 'page_to_pixel']}}
        oriented = preprocess(source, {'id': 'reading_orientation', 'rotation': view['spec']['reading_orientation']},
                              folder / 'oriented.png', result['preparation']['max_pixels'])
        targets.append({'id': view['id'], 'path': str(folder / 'oriented.png'), 'sha256': oriented['sha256'],
            'width': oriented['width'], 'height': oriented['height'], 'effective_dpi': raw['effective_dpi'],
            'page_to_pixel': oriented['page_to_processed'], 'source_pdf': page['source_pdf'],
            'document_sha256': page['document_sha256'], 'page_number': page['page_number']})
        text = read(page['text_path'])
        box = view['ocr_focus_bbox']
        lines = [l for l in text['lines'] if l['bbox'][0] >= box[0] and l['bbox'][1] >= box[1]
                 and l['bbox'][2] <= box[2] and l['bbox'][3] <= box[3]]
        native_rows.append({'view_id': view['id'], 'view_revision': revision(view['spec']), 'bbox': box,
                            'native_text': '\n'.join(l['text'] for l in lines), 'native_lines': lines, 'status': 'ready'})
        for path in folder.iterdir():
            _asset(result, output, path)
    evidence = output / 'ocr-targets.json'
    write_json(evidence, {'schema_version': 1, 'kind': 'view_ocr_targets', 'images': targets})
    if targets:
        ocr = run_baseline(evidence, run_folder, config=config, executable=executable)
        for p in run_folder.rglob('*'):
            if p.is_file():
                _asset(result, output, p)
        by_id = {n['view_id']: n for n in native_rows}
        comparison = [{'view_id': r['image_id'], 'variant': r['variant'], 'status': r['status'],
            'native_text': by_id[r['image_id']]['native_text'], 'ocr_text': r['text'], 'confidence_mean': r['confidence_mean'],
            'entities': r['entities'], 'words': r['words'], 'view_revision': by_id[r['image_id']]['view_revision'],
            'accuracy': None, 'ground_truth': 'No independently accepted view transcription supplied'} for r in ocr['results']]
    else:
        comparison = []
    write_json(output / comparison_relative, {'comparisons': comparison, 'native_focus': native_rows,
               'accuracy': None, 'scoring_status': 'not_scored_no_independent_view_references'})
    _csv(compare_folder / 'comparison.csv', comparison, ['view_id', 'variant', 'status', 'native_text', 'ocr_text', 'confidence_mean', 'entities', 'view_revision', 'accuracy', 'ground_truth'])
    from .view_review import write_text_comparison
    write_text_comparison(comparison, targets, compare_folder, run_folder, output)
    for relative in ['ocr-targets.json', comparison_relative, f'comparisons/{session}/comparison.csv', f'comparisons/{session}/comparison.html']:
        _asset(result, output, output / relative)
    result.update(snapshot_id=str(uuid.uuid4()), created_at=now(), parent={'registry_path': str(registry_path), 'registry_sha256': file_sha256(registry_path)},
                  ocr_comparison={'file': comparison_relative, 'html': f'comparisons/{session}/comparison.html',
                                  'sha256': file_sha256(output / comparison_relative),
                                  'source_registry_sha256': file_sha256(registry_path), 'attempts': len(comparison)})
    result['ocr_comparison']['result_statuses'] = {status: sum(r['status'] == status for r in comparison) for status in sorted({r['status'] for r in comparison})}
    # OCR proposes scale text, never verifies it or adds data to approved clue registries.
    from .pdf_classify import text_candidates
    for row in comparison:
        if row['status'] not in {'recognized', 'empty'}:
            continue
        view = next(v for v in result['views'] if v['id'] == row['view_id'])
        # Reconstruct line strings from TSV page boxes; preserve OCR separately.
        groups = {}
        for word in row['words']:
            groups.setdefault(tuple(word['line_id']), []).append(word)
        lines = [{'text': ' '.join(w['text'] for w in words),
                  'bbox': [min(w['bbox_page'][0] for w in words), min(w['bbox_page'][1] for w in words),
                           max(w['bbox_page'][2] for w in words), max(w['bbox_page'][3] for w in words)]} for words in groups.values()]
        candidates = text_candidates(lines, result['pages'][view['page_id']]['bounds'])
        for index, statement in enumerate(candidates['scale_statements']):
            sid = f"{view['id']}-ocr-{row['variant']}-{index+1}"
            if any(s['id'] == sid for s in view['scales']):
                continue
            view['scales'].append(_record(sid, _scale_spec(view, text=statement['text'], source_method='ocr',
                source_reference=comparison_relative + '#' + view['id'] + ':' + row['variant'], source_bbox=statement['bbox'],
                notes='Unaccepted OCR candidate; symbols/dimensions may be misrecognized.')))
    validate_registry(result)
    write_views(result, output)
    return result
