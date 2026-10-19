"""Optional local registration fits; training residuals are not positional accuracy.

NumPy is loaded only for sufficiently constrained fits. No resampling, GIS writes,
datum conversion, outlier deletion or pooling of adjacent-sheet controls occurs.
"""

import importlib.metadata
import importlib.util
import math
from pathlib import Path
import shutil

from .geo_controls import CRS_UNITS, coordinate_for, independently_approved, load_collection, validate_record
from .geo_eval import validate_location_reference
from .geo_geometry import project, unproject
from .geo_report import _csv
from .pdf_extract import file_sha256, write_json

US_SURVEY_FOOT_M = 1200 / 3937
MINIMUMS = {'rigid': 2, 'similarity': 2, 'affine': 3}


def _metric(value, frame):
    if value['crs'] == 'EPSG:2264':
        return [value['x'] * US_SURVEY_FOOT_M, value['y'] * US_SURVEY_FOOT_M]
    return list(project([value['x'], value['y']], frame['origin']))


def predict_pixel(pixel, model):
    h = model['pixel_to_metric_matrix']
    xy = [h[i][0] * pixel[0] + h[i][1] * pixel[1] + h[i][2] for i in [0, 1]]
    if model['target_crs'] == 'EPSG:2264':
        target = [v / US_SURVEY_FOOT_M for v in xy]
    else:
        target = unproject(xy, model['metric_frame']['origin'])
    return {'metric_xy': xy, 'geographic': {'x': target[0], 'y': target[1], 'crs': model['target_crs'], 'units': CRS_UNITS[model['target_crs']]}}


def _fit(points, target, method, scale, maximum_condition):
    import numpy as np
    x, y = np.asarray(points, dtype=float), np.asarray(target, dtype=float)
    x[:, 1] *= -1  # Image row-down becomes a right-handed source frame.
    xc, yc = x.mean(axis=0), y.mean(axis=0)
    xx, yy = x - xc, y - yc
    spread = float(np.max(np.linalg.norm(x[:, None] - x, axis=2)))
    ground_spread = float(np.max(np.linalg.norm(y[:, None] - y, axis=2)))
    if spread < 1 or ground_spread < .001:
        raise ValueError('Controls have insufficient distinct image/ground separation')
    for values, tolerance in [(x, .001), (y, .001)]:
        if any(float(np.linalg.norm(values[i] - values[j])) < tolerance for i in range(len(x)) for j in range(i)):
            raise ValueError('Duplicate or coincident controls cannot constrain a fit')
    source_s = np.linalg.svd(xx, compute_uv=False)
    target_s = np.linalg.svd(yy, compute_uv=False)
    source_condition = float(source_s[0] / source_s[1]) if len(source_s) > 1 and source_s[1] > 1e-12 else None
    target_condition = float(target_s[0] / target_s[1]) if len(target_s) > 1 and target_s[1] > 1e-12 else None
    if method == 'affine':
        if source_condition is None or target_condition is None or max(source_condition, target_condition) > maximum_condition:
            raise ValueError('Affine controls are collinear or poorly distributed; collect off-alignment controls')
        norm = float(np.sqrt(np.mean(np.sum(xx ** 2, axis=1))))
        coefficients, _, rank, _ = np.linalg.lstsq(xx / norm, yy, rcond=1e-12)
        if rank != 2:
            raise ValueError('Affine design matrix is rank deficient')
        a = coefficients.T / norm
    else:
        u, singular, vt = np.linalg.svd(xx.T @ yy)
        signs = np.eye(2); signs[-1, -1] = 1 if np.linalg.det(vt.T @ u.T) >= 0 else -1
        rotation = vt.T @ signs @ u.T
        fitted_scale = float(np.sum(singular * np.diag(signs)) / np.sum(xx ** 2)) if method == 'similarity' else scale
        if not math.isfinite(fitted_scale) or fitted_scale <= 0:
            raise ValueError('Nonpositive registration scale')
        a = rotation * fitted_scale
    translation = yc - a @ xc
    h = np.eye(3); h[:2, :2] = a; h[:2, 2] = translation
    h = h @ np.diag([1, -1, 1])
    return h.tolist(), {'image_span_pixels': spread, 'ground_span_m': ground_spread,
                        'orientation_flip_beyond_image_y_convention': bool(np.linalg.det(a) < 0),
                        'source_condition_number': source_condition, 'target_condition_number': target_condition,
                        'image_y_convention': 'row-down input; internally negated for rigid/similarity orientation',
                        'maximum_affine_condition_number': maximum_condition,
                        'minimum_fit_is_exactly_determined': len(points) == MINIMUMS[method]}


def _scale_value(scale):
    if not scale:
        return None
    value = scale.get('metres_per_pixel')
    if (type(value) not in (int, float) or not math.isfinite(value) or value <= 0
            or not independently_approved(scale) or not scale.get('source')):
        raise ValueError('Rigid fixed scale requires a positive metres_per_pixel and independent human scale attestation with source')
    return value


def registration_diagnostics(registry, *, target_crs=None, methods=None, rigid_scale=None, minimum_checkpoints=2, maximum_condition=1000):
    target_crs = target_crs or registry['target_crs']
    if target_crs not in CRS_UNITS:
        raise ValueError('Unsupported target CRS')
    methods = methods or list(MINIMUMS)
    if not methods or set(methods) - set(MINIMUMS):
        raise ValueError('Registration method must be rigid, similarity or affine')
    if type(minimum_checkpoints) is not int or minimum_checkpoints < 2:
        raise ValueError('At least two separate checkpoints are required for summary validation')
    if type(maximum_condition) not in (int, float) or not math.isfinite(maximum_condition) or maximum_condition <= 1:
        raise ValueError('maximum_condition must be finite and greater than one')
    fixed_scale = _scale_value(rigid_scale)
    numpy_available = importlib.util.find_spec('numpy') is not None
    result = {'schema_version': 1, 'target_crs': target_crs, 'units': CRS_UNITS[target_crs], 'drawings': [],
              'scope': 'Control-based registration diagnostics, not asset matching or independent footprint acceptance.',
              'coordinate_policy': 'No automatic EPSG:2264/EPSG:4326 datum conversion. Explicit analyst-supplied transformation evidence required for mixed CRS.',
              'numpy': {'available': numpy_available, 'version': importlib.metadata.version('numpy') if numpy_available else None},
              'datum_conversion': {'automatic_conversion_implemented': False,
                                   'pyproj_available': importlib.util.find_spec('pyproj') is not None,
                                   'required_for_mixed_crs': 'Analyst-supplied transformed X/Y with explicit operation, datum/grid notes and source/output binding.'},
              'minimum_checkpoints': minimum_checkpoints, 'positional_accuracy_reported': False}
    for drawing in registry['drawings']:
        accepted, excluded = [], []
        for row in registry['records']:
            if row['record_type'] != 'control' or row['drawing_id'] != drawing['drawing_id']:
                continue
            reason = None
            if not independently_approved(row):
                reason = 'not_independently_analyst_approved'
            else:
                try:
                    validate_record(row, registry, complete=True)
                    coordinate = coordinate_for(row, target_crs)
                    if coordinate is None:
                        reason = f'missing_documented_coordinate_transformation_to_{target_crs}'
                except ValueError as exc:
                    reason = str(exc)
            if reason:
                excluded.append({'id': row['id'], 'reason': reason})
            else:
                accepted.append((row, coordinate))
        controls = [(r, p) for r, p in accepted if r['role'] == 'fit']
        checkpoints = [(r, p) for r, p in accepted if r['role'] == 'checkpoint']
        origin = [sum(p[k] for _, p in controls) / len(controls) for k in ['x', 'y']] if controls and target_crs == 'EPSG:4326' else None
        frame = {'type': 'WGS84 local east/north tangent plane', 'origin': origin, 'units': 'metre'} if origin else {
            'type': 'EPSG:2264 easting/northing multiplied by 1200/3937', 'units': 'metre', 'datum_conversion': False}
        targets = [_metric(p, frame) for _, p in controls]
        if origin and any(math.dist(p, [0, 0]) > 250000 for p in targets):
            raise ValueError('Control set exceeds the bounded WGS84 county projection')
        sheet = {'drawing_id': drawing['drawing_id'], 'source': drawing['source'], 'approved_fit_controls': len(controls),
                 'approved_checkpoint_candidates': len(checkpoints), 'excluded': excluded, 'methods': [],
                 'approved_adjacent_sheet_ties': sum(r['record_type'] == 'tie' and independently_approved(r) and drawing['drawing_id'] in [r['left_drawing_id'], r['right_drawing_id']] for r in registry['records'])}
        for method in methods:
            missing = []
            if len(controls) < MINIMUMS[method]:
                missing.append(f'Need {MINIMUMS[method] - len(controls)} additional independently approved, complete fit control(s) in {target_crs}; minimum {MINIMUMS[method]}.')
            if method == 'rigid' and fixed_scale is None:
                missing.append('Need independently documented fixed image-to-ground scale for a rigid fit.')
            if not numpy_available:
                missing.append('Existing NumPy unavailable; no package installation attempted.')
            assessment = {'method': method, 'status': 'insufficient_controls' if missing else 'ready', 'missing_evidence': missing,
                          'model': None, 'fit_residuals': [], 'fit_rms_m': None, 'checkpoint_residuals': [],
                          'checkpoint_rmse_m': None, 'checkpoint_agreement_reported': False, 'validation_status': 'not_fitted',
                          'positional_accuracy_reported': False, 'excluded_checkpoints': [],
                          'limitations': ['Fit residuals describe training agreement, not geographic accuracy.',
                                          'Historical road, parcel and landmark changes can cause false correspondences.',
                                          'Minimum controls do not establish robust or production-quality registration.',
                                          'Cross-sheet ties and station values do not supply geographic coordinates.']}
            if not missing:
                try:
                    h, geometry = _fit([r['pixel'] for r, _ in controls], targets, method, fixed_scale, maximum_condition)
                except ValueError as exc:
                    assessment.update(status='insufficient_geometry', validation_status='not_fitted')
                    assessment['missing_evidence'].append(str(exc))
                else:
                    model = {'method': method, 'target_crs': target_crs, 'metric_frame': frame,
                             'pixel_to_metric_matrix': h, 'fit_control_ids': [r['id'] for r, _ in controls],
                             'rigid_scale_evidence': rigid_scale if method == 'rigid' else None, 'geometry_diagnostics': geometry}
                    assessment.update(status='fitted', model=model, validation_status='pending_independent_checkpoints')
                    pixels = [r['pixel'] for r, _ in controls]
                    geometry['image_bbox_fraction'] = [(max(p[i] for p in pixels) - min(p[i] for p in pixels)) / drawing['image'][dim] for i, dim in [(0, 'width'), (1, 'height')]]
                    retained_checkpoint_locations = []
                    for row, coordinate in controls + checkpoints:
                        prediction = predict_pixel(row['pixel'], model)
                        observed = _metric(coordinate, frame)
                        dx, dy = [prediction['metric_xy'][i] - observed[i] for i in [0, 1]]
                        residual = {'id': row['id'], 'role': row['role'], 'pixel': row['pixel'],
                                    'observed': coordinate, 'predicted': prediction['geographic'], 'dx_m': dx, 'dy_m': dy,
                                    'radial_error_m': math.hypot(dx, dy), 'estimated_reference_accuracy_m': row.get('estimated_accuracy_m')}
                        if row['role'] == 'fit':
                            assessment['fit_residuals'].append(residual)
                        elif any(math.dist(row['pixel'], fit['pixel']) < .5 or math.dist(observed, target) < .001 for (fit, _), target in zip(controls, targets)):
                            assessment['excluded_checkpoints'].append({'id': row['id'], 'reason': 'checkpoint duplicates a fitting location/pixel'})
                        elif any(math.dist(row['pixel'], px) < .5 or math.dist(observed, target) < .001 for px, target in retained_checkpoint_locations):
                            assessment['excluded_checkpoints'].append({'id': row['id'], 'reason': 'checkpoint duplicates another checkpoint location/pixel'})
                        elif target_crs == 'EPSG:4326' and math.dist(observed, [0, 0]) > 250000:
                            assessment['excluded_checkpoints'].append({'id': row['id'], 'reason': 'checkpoint outside bounded county metre projection'})
                        else:
                            assessment['checkpoint_residuals'].append(residual)
                            retained_checkpoint_locations.append((row['pixel'], observed))
                    assessment['fit_rms_m'] = math.sqrt(sum(r['radial_error_m'] ** 2 for r in assessment['fit_residuals']) / len(controls))
                    cp = assessment['checkpoint_residuals']
                    if len(cp) >= minimum_checkpoints:
                        assessment['checkpoint_rmse_m'] = math.sqrt(sum(r['radial_error_m'] ** 2 for r in cp) / len(cp))
                        assessment['checkpoint_agreement_reported'] = True
                        known = all(r['estimated_reference_accuracy_m'] is not None for r in cp)
                        assessment['validation_status'] = 'checkpoint_agreement_measured' if known else 'checkpoint_agreement_measured_reference_accuracy_unknown'
                        assessment['positional_accuracy_reported'] = known
                        assessment['limitations'].append('Checkpoint agreement is relative to supplied reference coordinates; no survey certification or statistical confidence interval.')
                    else:
                        assessment['missing_evidence'].append(f'Need {minimum_checkpoints - len(cp)} additional independent approved checkpoint(s), separate from fitting locations.')
            if assessment['model'] is None and len(checkpoints) < minimum_checkpoints:
                assessment['missing_evidence'].append(f'Need {minimum_checkpoints - len(checkpoints)} separate independently approved checkpoint(s) for later validation; checkpoints are never fitting inputs.')
            sheet['methods'].append(assessment)
        result['drawings'].append(sheet)
    result['cross_sheet_policy'] = 'Each sheet fitted independently. Approved image ties are supplemental evidence only; no control or extent propagation.'
    result['positional_accuracy_reported'] = any(m['positional_accuracy_reported'] for d in result['drawings'] for m in d['methods'])
    return result


def independent_checkpoint_references(registry):
    """Reuse localization's reference validator; never export fitting predictions."""
    references, pending = [], []
    for r in registry['records']:
        if r['record_type'] != 'control' or r['role'] != 'checkpoint' or not independently_approved(r):
            continue
        validate_record(r, registry, complete=True)
        coordinate = coordinate_for(r, 'EPSG:4326')
        if coordinate is None or r.get('estimated_accuracy_m') is None:
            pending.append({'id': r['id'], 'reason': 'Need documented EPSG:4326 conversion and known reference accuracy for localization evaluator export'})
            continue
        xy = [coordinate['x'], coordinate['y']]
        fit_records = [f for f in registry['records'] if f['record_type'] == 'control' and f['role'] == 'fit'
                       and f['drawing_id'] == r['drawing_id'] and independently_approved(f)]
        leaked = False
        for fit in fit_records:
            value = coordinate_for(fit, 'EPSG:4326')
            if math.dist(fit['pixel'], r['pixel']) < .5 or value and math.dist(project([value['x'], value['y']], xy), [0, 0]) < .001:
                leaked = True
        if leaked:
            pending.append({'id': r['id'], 'reason': 'Checkpoint duplicates fitting evidence; not an independent location reference'})
            continue
        location = {'kind': 'control_point', 'crs': 'EPSG:4326', 'geometry': {'type': 'Point', 'coordinates': [coordinate['x'], coordinate['y']]},
                    'source': r['evidence']['source'] + ' / ' + r['evidence']['source_reference'],
                    'accuracy_m': r['estimated_accuracy_m'], 'independently_determined': True, 'control_id': r['id']}
        validate_location_reference(location)
        references.append({'drawing_id': r['drawing_id'], 'location': location})
    return {'scope': 'Independently approved checkpoint observations only. Human area/candidate decisions remain separate; no fitted predictions exported.',
            'references': references, 'pending': pending}


def assess_registration(registry_path, output, **options):
    registry_path = Path(registry_path).resolve()
    registry = load_collection(registry_path)
    result = registration_diagnostics(registry, **options)
    result['inputs'] = {'registry_path': str(registry_path), 'registry_sha256': file_sha256(registry_path)}
    result['implementation'] = {name: file_sha256(Path(__file__).parent / name) for name in ['geo_registration.py', 'geo_controls.py', 'geo_geometry.py']}
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(registry_path, output / 'controls-input.json')
    write_json(output / 'registration.json', result)
    write_json(output / 'independent-checkpoint-references.json', independent_checkpoint_references(registry))
    rows = [{**{k: d[k] for k in ['drawing_id', 'approved_fit_controls', 'approved_checkpoint_candidates']},
             **{k: m[k] for k in ['method', 'status', 'fit_rms_m', 'checkpoint_rmse_m', 'validation_status', 'missing_evidence']}}
            for d in result['drawings'] for m in d['methods']]
    _csv(output / 'registration.csv', ['drawing_id', 'method', 'status', 'approved_fit_controls', 'approved_checkpoint_candidates',
                                      'fit_rms_m', 'checkpoint_rmse_m', 'validation_status', 'missing_evidence'], rows)
    residuals = [{'drawing_id': d['drawing_id'], 'method': m['method'], **r} for d in result['drawings'] for m in d['methods']
                 for r in m['fit_residuals'] + m['checkpoint_residuals']]
    _csv(output / 'residuals.csv', ['drawing_id', 'method', 'id', 'role', 'pixel', 'observed', 'predicted', 'dx_m', 'dy_m', 'radial_error_m', 'estimated_reference_accuracy_m'], residuals)
    lines = ['# Registration feasibility', '', 'Training RMS is not positional accuracy. Each sheet is assessed independently.', '']
    for d in result['drawings']:
        lines.extend([f"## {d['source']['source_pdf']} / {d['source']['sheet']}", '',
                      f"Approved usable fit controls: {d['approved_fit_controls']}; checkpoint candidates: {d['approved_checkpoint_candidates']}.", ''])
        for m in d['methods']:
            lines.append(f"- {m['method']}: {m['status']}; validation: {m['validation_status']}. " + ' '.join(m['missing_evidence']))
        lines.append('')
    (output / 'FEASIBILITY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return result
