"""Immutable control-collection snapshots and explicit independent human review."""

from copy import deepcopy
from datetime import date, datetime
import math
from pathlib import Path
import re
import shutil
import uuid

from .clues import now, review_identity
from .clue_review import analyst_accepted
from .geo_reference import read_json
from .geo_geometry import validate_geometry
from .pdf_extract import file_sha256, write_json

CRS_UNITS = {'EPSG:2264': 'US survey foot', 'EPSG:4326': 'degree'}
CONTROL_FIELDS = {'pixel', 'geographic', 'transformed_geographic', 'feature_type', 'description', 'reference_feature_id',
                  'evidence', 'estimated_accuracy_m', 'role', 'independent_of_fit', 'historical_change_notes'}
TIE_FIELDS = {'left_pixel', 'right_pixel', 'description', 'station_text', 'station_verified', 'evidence', 'historical_change_notes'}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonblank')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _pixel(value, drawing, *, required=False):
    if value is None and not required:
        return
    if (not isinstance(value, list) or len(value) != 2 or not all(_number(v) for v in value)
            or not 0 <= value[0] < drawing['image']['width'] or not 0 <= value[1] < drawing['image']['height']):
        raise ValueError('Pixel X/Y must be finite original-image coordinates inside the bound composition image')


def validate_geographic(value):
    if not isinstance(value, dict) or value.get('crs') not in CRS_UNITS or value.get('units') != CRS_UNITS[value['crs']]:
        raise ValueError('Coordinates need explicit EPSG:2264 / US survey foot or EPSG:4326 / degree')
    if not all(_number(value.get(k)) for k in ['x', 'y']):
        raise ValueError('Geographic X/Y must be finite')
    if value['crs'] == 'EPSG:4326':
        validate_geometry({'type': 'Point', 'coordinates': [value['x'], value['y']]}, {'Point'})


def coordinate_for(control, target_crs):
    """No silent datum conversion. Alternate coordinates require an audited operation."""
    original = control.get('geographic')
    if not original:
        return None
    validate_geographic(original)
    if original['crs'] == target_crs:
        return original
    converted = control.get('transformed_geographic')
    if not converted:
        return None
    validate_geographic(converted)
    operation = converted.get('transformation') or {}
    if (converted['crs'] != target_crs or operation.get('source_crs') != original['crs']
            or operation.get('target_crs') != target_crs or operation.get('input_xy') != [original['x'], original['y']]
            or operation.get('output_xy') != [converted['x'], converted['y']]
            or operation.get('axis_order') != 'x,y' or operation.get('ballpark') is not False):
        raise ValueError('Alternate coordinate transformation must bind original/output X/Y and explicit CRS/axis order; ballpark prohibited')
    for key in ['operation', 'software', 'software_version', 'source', 'performed_at', 'datum_notes', 'grid_notes']:
        _text(operation.get(key), f'transformation.{key}')
    timestamp = datetime.fromisoformat(operation['performed_at'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('Transformation timestamp needs timezone')
    accuracy = operation.get('accuracy_m')
    if accuracy is not None and (not _number(accuracy) or accuracy <= 0):
        raise ValueError('Transformation accuracy must be positive finite metres or null')
    return converted


def independently_approved(record):
    v = record.get('verification') or {}
    return analyst_accepted({'verification_status': record.get('verification_status'), 'reviewer_type': v.get('reviewer_type'),
                             'independent_review': v.get('independent'), 'reviewer': v.get('reviewer'),
                             'review_reason': v.get('reason'), 'review_timestamp': v.get('timestamp'),
                             'extraction_author': record.get('last_evidence_author')})


def _evidence(value, *, required=False):
    if not isinstance(value, dict):
        raise ValueError('Evidence must be an object')
    if value.get('source_date') is not None:
        date.fromisoformat(value['source_date'])
    if value.get('independently_determined') not in (True, False) or type(value.get('independently_determined')) is not bool:
        raise ValueError('Evidence needs boolean independently_determined')
    if required:
        for key in ['source', 'source_reference', 'point_identity', 'historical_consistency']:
            _text(value.get(key), f'evidence.{key}')
        if 'source_date' not in value:
            raise ValueError('Evidence source_date must be explicit; null if unknown')
        if value.get('independently_determined') is not True or value.get('model_input_landmark') is not False:
            raise ValueError('Independent control evidence required; model-input landmarks cannot be promoted')


def _is_model_input(control, registry):
    for crs in CRS_UNITS:
        value = coordinate_for(control, crs)
        if not value or crs != 'EPSG:4326':
            continue
        xy = [value['x'], value['y']]
        if any(xy == p['geometry']['coordinates'][:2] for p in registry.get('model_input_reference_locations', [])):
            return True
    return False


def validate_record(record, registry, *, complete=False):
    drawings = {d['drawing_id']: d for d in registry['drawings']}
    _text(record.get('description'), 'description')
    if record['record_type'] == 'control':
        if record.get('drawing_id') not in drawings:
            raise ValueError('Unknown drawing ID')
        drawing = drawings[record['drawing_id']]
        if record['source'] != drawing['source'] or record['image_sha256'] != drawing['image']['sha256']:
            raise ValueError('Control source PDF/image identity differs from drawing binding')
        _pixel(record.get('pixel'), drawing, required=complete)
        if record.get('geographic') is not None:
            validate_geographic(record['geographic'])
        elif complete:
            raise ValueError('Approved control needs geographic coordinates')
        if record.get('transformed_geographic') is not None:
            if not record.get('geographic') or record['transformed_geographic'].get('crs') == record['geographic']['crs']:
                raise ValueError('Alternate coordinate must document a different CRS from the original')
            coordinate_for(record, record['transformed_geographic']['crs'])
        if record.get('role') not in {'fit', 'checkpoint'} or type(record.get('independent_of_fit')) is not bool:
            raise ValueError('Control needs fit/checkpoint role and independent_of_fit boolean')
        accuracy = record.get('estimated_accuracy_m')
        if accuracy is not None and (not _number(accuracy) or accuracy <= 0):
            raise ValueError('Estimated accuracy must be positive finite metres or null')
        if complete:
            for key in ['feature_type', 'reference_feature_id']:
                _text(record.get(key), key)
            if _is_model_input(record, registry):
                raise ValueError('Model-input landmark coordinate cannot be accepted as independent control')
            if record['role'] == 'checkpoint' and record['independent_of_fit'] is not True:
                raise ValueError('Checkpoint needs explicit independence from fitting')
    elif record['record_type'] == 'tie':
        left, right = record.get('left_drawing_id'), record.get('right_drawing_id')
        if left not in drawings or right not in drawings or left == right:
            raise ValueError('Tie must bind two different known sheets')
        if record['sources'] != [drawings[left]['source'], drawings[right]['source']]:
            raise ValueError('Tie source identities differ from drawing bindings')
        _pixel(record.get('left_pixel'), drawings[left], required=complete)
        _pixel(record.get('right_pixel'), drawings[right], required=complete)
        if type(record.get('station_verified')) is not bool:
            raise ValueError('station_verified must be boolean')
        if complete and record.get('station_text') and record['station_verified'] is not True:
            raise ValueError('Station-tagged tie needs explicit station verification; title continuity alone is insufficient')
    else:
        raise ValueError('Unknown correspondence type')
    _evidence(record.get('evidence'), required=complete)


def safe_file(base, relative):
    path = (base / relative).resolve()
    if base.resolve() not in path.parents:
        raise ValueError('Evidence path escapes collection bundle')
    return path


def load_collection(path):
    path = Path(path).resolve()
    registry = read_json(path)
    if registry.get('schema_version') != 1 or registry.get('kind') != 'geographic_control_collection':
        raise ValueError('Expected geographic control collection schema_version 1')
    if registry.get('target_crs') not in CRS_UNITS:
        raise ValueError('Target CRS must be EPSG:2264 or EPSG:4326')
    seen = set()
    for d in registry['drawings']:
        if d['drawing_id'] in seen:
            raise ValueError('Duplicate drawing binding')
        seen.add(d['drawing_id'])
        if (registry['bound_files'].get(d['source']['bundle_file']) != d['source']['document_sha256']
                or registry['bound_files'].get(d['image']['bundle_file']) != d['image']['sha256']
                or d['drawing_id'] != f"{d['source']['document_sha256']}:{d['source']['page_number']}"):
            raise ValueError('Drawing source/image metadata differs from bound file identities')
        if any(type(d['image'].get(k)) is not int or d['image'][k] <= 0 for k in ['width', 'height']):
            raise ValueError('Original image dimensions must be positive integers')
    for relative, digest in registry['bound_files'].items():
        if file_sha256(safe_file(path.parent, relative)) != digest:
            raise ValueError('Bound evidence hash mismatch: ' + relative)
    ids = set()
    for r in registry['records']:
        if r['id'] in ids:
            raise ValueError('Duplicate correspondence ID')
        ids.add(r['id'])
        validate_record(r, registry, complete=r['verification_status'] == 'verified')
        if r['verification_status'] == 'verified' and not independently_approved(r):
            raise ValueError('Verified correspondence lacks independent human acceptance')
    return registry


def apply_control_operations(registry, decisions):
    result = deepcopy(registry)
    seen = {event['operation_id'] for event in result['operation_history']}
    for op in decisions.get('operations', []):
        oid = op.get('operation_id')
        if not isinstance(oid, str) or not oid.strip() or oid in seen:
            raise ValueError('Operation IDs must be unique, nonblank and not previously applied')
        seen.add(oid)
        action = op.get('action')
        identity = review_identity(op.get('author'), op.get('reason'), op.get('reviewer_type', 'unspecified'),
                                   op.get('independent', False), '')
        if action in {'add_control', 'add_tie'}:
            key = op.get('id') or str(uuid.uuid4())
            if any(r['id'] == key for r in result['records']):
                raise ValueError('Correspondence ID already exists')
            payload = deepcopy(op.get('values', {}))
            drawing_by_id = {d['drawing_id']: d for d in result['drawings']}
            kind = 'control' if action == 'add_control' else 'tie'
            allowed = CONTROL_FIELDS | {'drawing_id'} if kind == 'control' else TIE_FIELDS | {'left_drawing_id', 'right_drawing_id'}
            if set(payload) - allowed:
                raise ValueError('Unsupported correspondence fields')
            r = {'id': key, 'record_type': kind, 'author': op['author'], 'proposer_type': identity['reviewer_type'],
                 'last_evidence_author': op['author'], 'created_at': now(), 'verification_status': 'unverified',
                 'verification': None, 'history': [], **payload}
            if kind == 'control':
                d = drawing_by_id.get(r.get('drawing_id'))
                if not d: raise ValueError('Unknown drawing ID')
                r.update(source=deepcopy(d['source']), image_sha256=d['image']['sha256'])
            else:
                if r.get('left_drawing_id') not in drawing_by_id or r.get('right_drawing_id') not in drawing_by_id:
                    raise ValueError('Unknown tie drawing ID')
                r['sources'] = [deepcopy(drawing_by_id[r[k]]['source']) for k in ['left_drawing_id', 'right_drawing_id']]
            validate_record(r, result)
            r['original'] = deepcopy({k: v for k, v in r.items() if k not in {'history', 'verification'}})
            result['records'].append(r)
            before = None
        else:
            r = next((r for r in result['records'] if r['id'] == op.get('id')), None)
            if r is None: raise ValueError('Unknown correspondence ID')
            before = deepcopy({k: v for k, v in r.items() if k not in {'history', 'original'}})
            if action == 'edit':
                values = op.get('values', {})
                allowed = CONTROL_FIELDS if r['record_type'] == 'control' else TIE_FIELDS
                if not values or set(values) - allowed:
                    raise ValueError('Edit requires supported evidence fields; source identity is immutable')
                r.update(deepcopy(values), last_evidence_author=op['author'], verification_status='unverified', verification=None)
                validate_record(r, result)
            elif action == 'review':
                status = op.get('status')
                if status not in {'unverified', 'verified', 'rejected', 'unreadable'}:
                    raise ValueError('Invalid review status')
                identity = review_identity(op['author'], op['reason'], op.get('reviewer_type', 'unspecified'),
                                           op.get('independent', False), r['last_evidence_author'])
                if status == 'verified':
                    if identity['reviewer_type'] != 'human' or identity['independent'] is not True:
                        raise ValueError('Approval requires independent human review')
                    validate_record(r, result, complete=True)
                r['verification_status'] = status
                r['verification'] = {**identity, 'scope': 'geographic_control' if r['record_type'] == 'control' else 'cross_sheet_correspondence'}
            else:
                raise ValueError('Unsupported control operation')
        after = deepcopy({k: v for k, v in r.items() if k not in {'history', 'original'}})
        event = {'operation_id': oid, 'timestamp': now(), 'action': action, 'author': op['author'], 'reviewer_type': identity['reviewer_type'],
                 'reason': op['reason'], 'before': before, 'after': after}
        r['history'].append(event)
        result['operation_history'].append({'operation_id': oid, 'record_id': r['id'], 'action': action, 'timestamp': event['timestamp']})
    return result


def apply_controls(registry_path, decisions_path, output):
    registry_path, decisions_path = Path(registry_path).resolve(), Path(decisions_path).resolve()
    registry, decisions = load_collection(registry_path), read_json(decisions_path)
    if decisions.get('registry_sha256') != file_sha256(registry_path):
        raise ValueError('Control decisions do not match the frozen registry SHA-256')
    result = apply_control_operations(registry, decisions)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    for relative in registry['bound_files']:
        dest = safe_file(output, relative); dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_file(registry_path.parent, relative), dest)
    result.update(snapshot_id=str(uuid.uuid4()), created_at=now(), parent={'registry_sha256': file_sha256(registry_path),
                  'registry_path': str(registry_path), 'decisions_sha256': file_sha256(decisions_path)})
    shutil.copyfile(registry_path, output / 'parent-registry-input.json')
    shutil.copyfile(decisions_path, output / 'applied-decisions.json')
    write_json(output / 'controls.json', result)
    from .geo_control_review import write_control_review
    write_control_review(output / 'controls.json')
    return result
