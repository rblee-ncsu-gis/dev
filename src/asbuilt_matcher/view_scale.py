"""Per-view scale evidence and guarded calibration; no geographic registration."""

import hashlib
import json
import math

from .geo_controls import independently_approved
from .pdf_extract import load_pdf_backend
from .raster import validate_bbox

VIEW_TYPES = {'engineering_plan', 'engineering_profile', 'subdivision_plat', 'detail_inset',
              'vicinity_map', 'title_block_legend', 'administrative_supporting', 'other_uncertain'}
RELEVANCE = {'engineering', 'context', 'supporting', 'uncertain'}
UNITS = {'metre': 1., 'foot': .3048, 'US_survey_foot': 1200 / 3937}
VIEW_FIELDS = {'bbox', 'view_type', 'reading_orientation', 'engineering_relevance', 'scale_mode', 'distortion_notes'}
SCALE_FIELDS = {'kind', 'axis', 'coordinate_space', 'image_id', 'endpoints', 'ground_distance', 'ground_unit',
                'paper_inches', 'text', 'source_method', 'source_reference', 'source_bbox', 'native_segment',
                'view_revision', 'use', 'applicability_confirmed', 'distortion_checked',
                'independent_of_calibration', 'notes'}


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def revision(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_view(spec, bounds):
    if set(spec) != VIEW_FIELDS:
        raise ValueError('View specification needs exactly the supported boundary/type/orientation/relevance/scale fields')
    if not isinstance(spec['bbox'], list) or not all(number(x) for x in spec['bbox']):
        raise ValueError('View bounds must be finite page-point numbers')
    validate_bbox(spec['bbox'], bounds)
    if (spec['view_type'] not in VIEW_TYPES or spec['engineering_relevance'] not in RELEVANCE
            or type(spec['reading_orientation']) is not int or spec['reading_orientation'] not in {0, 90, 180, 270}
            or spec['scale_mode'] not in {'unknown', 'isotropic', 'anisotropic', 'not_to_scale'}
            or not isinstance(spec['distortion_notes'], str)):
        raise ValueError('Invalid view type, relevance, orientation or scale mode')


def validate_scale(spec, bounds, images, *, complete=False):
    if set(spec) != SCALE_FIELDS:
        raise ValueError('Scale specification needs exactly the supported evidence fields')
    if (spec['kind'] not in {'statement', 'bar', 'checkpoint'} or spec['axis'] not in {'isotropic', 'horizontal', 'vertical'}
            or spec['source_method'] not in {'native_text', 'ocr', 'native_vector', 'raster_manual', 'manual_transcription'}
            or spec['use'] not in {'current_view', 'nominal_only', 'excluded', 'unresolved'}):
        raise ValueError('Invalid scale kind, axis, method or use')
    for k in ['applicability_confirmed', 'distortion_checked', 'independent_of_calibration']:
        if type(spec[k]) is not bool:
            raise ValueError('Scale attestations must be explicit booleans')
    for k in ['text', 'source_reference', 'view_revision', 'notes']:
        if not isinstance(spec[k], str):
            raise ValueError('Scale text, references, revision and notes must be strings')
    if spec['source_bbox'] is not None:
        validate_bbox(spec['source_bbox'], bounds)
    for k in ['ground_distance', 'paper_inches']:
        if spec[k] is not None and (not number(spec[k]) or spec[k] <= 0):
            raise ValueError('Distances must be positive finite numbers or null')
    if spec['ground_unit'] is not None and spec['ground_unit'] not in UNITS:
        raise ValueError('Choose metre, foot or US_survey_foot explicitly')
    if spec['coordinate_space'] not in {'page', 'image'}:
        raise ValueError('Measurement coordinates must be page or image')
    if spec['coordinate_space'] == 'image' and spec['image_id'] not in images:
        raise ValueError('Pixel measurements require a known bound image')
    if spec['coordinate_space'] == 'page' and spec['image_id'] is not None:
        raise ValueError('Page coordinates must not carry an image identity')
    if spec['endpoints'] is not None:
        points_page(spec, bounds, images)
    if spec['native_segment'] is not None:
        ref = spec['native_segment']
        if (not isinstance(ref, dict) or set(ref) != {'path_index', 'item_index'}
                or any(type(v) is not int or v < 0 for v in ref.values())):
            raise ValueError('Native segment needs nonnegative path_index and item_index')
    if complete:
        if not spec['source_reference'].strip() or not spec['text'].strip():
            raise ValueError('Independent scale acceptance requires transcription/description and source reference')
        if spec['kind'] == 'statement':
            # Literal transcription acceptance is separate from interpreting ambiguous
            # FEET, applicability, or numeric scale. It may remain uncalibratable.
            pass
        elif spec['endpoints'] is None or spec['ground_distance'] is None or spec['ground_unit'] is None:
            raise ValueError('Approved graphical/check measurements need endpoints, ground distance and units')
        if spec['source_method'] == 'native_vector' and spec['native_segment'] is None:
            raise ValueError('Native-vector measurement must bind an actual exported segment')
        if spec['kind'] == 'checkpoint' and not spec['independent_of_calibration']:
            raise ValueError('Checkpoint must be explicitly independent of calibration')


def points_page(spec, bounds, images):
    points = spec['endpoints']
    if (not isinstance(points, list) or len(points) != 2
            or any(not isinstance(p, list) or len(p) != 2 or not all(number(v) for v in p) for p in points)):
        raise ValueError('Measurement needs two finite endpoint pairs')
    if spec['coordinate_space'] == 'image':
        image = images[spec['image_id']]
        if any(not 0 <= p[0] <= image['width'] or not 0 <= p[1] <= image['height'] for p in points):
            raise ValueError('Endpoints lie outside the bound image')
        pdf = load_pdf_backend()
        inverse = ~pdf.Matrix(image['page_to_pixel'])
        points = [list(pdf.Point(p) * inverse) for p in points]
    if any(not bounds[0] - 1e-4 <= p[0] <= bounds[2] + 1e-4 or not bounds[1] - 1e-4 <= p[1] <= bounds[3] + 1e-4 for p in points):
        raise ValueError('Endpoints lie outside the source page')
    if math.dist(*points) <= 1e-6:
        raise ValueError('Endpoints must be distinct')
    return points


def measure(spec, bounds, images):
    if spec['kind'] == 'statement':
        span = spec['paper_inches'] * 72 if spec['paper_inches'] else None
        points = None
    else:
        points = points_page(spec, bounds, images) if spec['endpoints'] else None
        span = math.dist(*points) if points else None
    ground = spec['ground_distance'] * UNITS[spec['ground_unit']] if spec['ground_distance'] and spec['ground_unit'] else None
    return {'endpoints_page': points, 'span_page_points': span,
            'metres_per_page_point': ground / span if ground and span else None,
            'ground_distance_m': ground,
            'status': 'measured_unverified' if span and ground else 'detected_statement' if spec['kind'] == 'statement' else 'measured_span_ground_unknown' if span else 'incomplete',
            'ground_resolution_verified': False}


def assess_scale(view, scales, bounds, images, *, tolerance=.02):
    """Derive effective scale only from independently accepted, applicable measurements.

    Printed statements alone never calibrate. Nominal-only statements retain their
    accepted transcription but cannot constrain a resized view's effective scale.
    Calibration is a page-distance relationship, never a GIS placement/accuracy.
    """
    spec, current = view['spec'], revision(view['spec'])
    evidence = []
    for record in scales:
        measured = measure(record['spec'], bounds, images)
        evidence.append({'id': record['id'], 'independently_accepted': independently_approved(record),
                         'measurement_stage': ('analyst_verified_statement' if record['spec']['kind'] == 'statement' else 'measured_graphical_scale') if independently_approved(record) else 'detected_scale_statement' if record['spec']['kind'] == 'statement' else 'unverified_graphical_measurement',
                         'current_view_revision': record['spec']['view_revision'] == current,
                         'verification_status': record['verification_status'], **measured})
    result = {'status': 'unresolved', 'axes': {}, 'evidence': evidence, 'missing_evidence': [],
              'validation': {'status': 'not_measured_no_independent_check', 'measurements': []},
              'geographic_registration': False, 'map_crs': None,
              'limitations': ['Scale is not position or orientation in GIS', 'One bar does not establish spatial distortion across the view',
                              'Foot and US survey foot are distinct; original units retained']}
    if not independently_approved(view):
        result['missing_evidence'].append('Independently accepted view boundary/type/orientation')
    if spec['scale_mode'] == 'not_to_scale':
        result['status'] = 'not_to_scale'
        return result
    if spec['engineering_relevance'] != 'engineering' or spec['view_type'] in {'vicinity_map', 'title_block_legend', 'administrative_supporting', 'other_uncertain'}:
        result['status'] = 'not_applicable_to_engineering_calibration'
        return result
    if spec['scale_mode'] == 'unknown':
        result['missing_evidence'].append('Accepted isotropic versus separate horizontal/vertical scale scope')
    if spec['view_type'] == 'engineering_profile' and spec['scale_mode'] != 'anisotropic':
        result['missing_evidence'].append('Engineering profiles require separately validated horizontal and vertical scales')
    if not spec['distortion_notes'].strip():
        result['missing_evidence'].append('Analyst assessment of resizing/distortion')
    approved = [(r, e) for r, e in zip(scales, evidence) if e['independently_accepted'] and e['current_view_revision']]
    if any(r['spec']['use'] == 'unresolved' for r, _ in approved):
        result['missing_evidence'].append('Resolve applicability of independently accepted scale evidence')
    if any(r['spec']['use'] == 'current_view' and r['spec']['kind'] == 'statement'
           and (not r['spec']['applicability_confirmed'] or e['metres_per_page_point'] is None) for r, e in approved):
        result['missing_evidence'].append('Resolve accepted current-view statement units, numeric interpretation and applicability')
    stale = any(e['independently_accepted'] and not e['current_view_revision']
                and r['spec']['use'] not in {'excluded', 'nominal_only'} for r, e in zip(scales, evidence))
    if stale:
        result['missing_evidence'].append('Reconfirm scale applicability to revised view; previous acceptance is retained')
    needed = ['horizontal', 'vertical'] if spec['scale_mode'] == 'anisotropic' else ['isotropic']
    conflict = False
    def axis_matches(record, measured):
        if record['spec']['axis'] == 'isotropic' or measured['endpoints_page'] is None:
            return True
        a, b = measured['endpoints_page']
        dx, dy = b[0] - a[0], b[1] - a[1]
        theta = math.radians(spec['reading_orientation'])
        x, y = dx * math.cos(theta) - dy * math.sin(theta), dx * math.sin(theta) + dy * math.cos(theta)
        across = abs(y) if record['spec']['axis'] == 'horizontal' else abs(x)
        return across <= .05 * math.hypot(x, y)
    for axis in needed:
        applicable = [(r, e) for r, e in approved if r['spec']['axis'] == axis and r['spec']['use'] == 'current_view'
                      and r['spec']['applicability_confirmed'] and e['metres_per_page_point'] is not None]
        if any(not axis_matches(r, e) for r, e in applicable):
            result['missing_evidence'].append(f'Measurement direction conflicts with declared {axis} axis in reading orientation')
        applicable = [(r, e) for r, e in applicable if axis_matches(r, e)]
        bars = [(r, e) for r, e in applicable if r['spec']['kind'] == 'bar' and r['spec']['distortion_checked']]
        if not bars:
            result['missing_evidence'].append(f'Independent applicable graphical measurement for {axis}')
            continue
        ratios = [e['metres_per_page_point'] for r, e in applicable if r['spec']['kind'] != 'checkpoint']
        if max(ratios) / min(ratios) - 1 > tolerance:
            conflict = True
            result['missing_evidence'].append(f'Conflicting accepted {axis} scale evidence; resolve applicability/resizing')
            continue
        mean = sum(e['metres_per_page_point'] for _, e in bars) / len(bars)
        result['axes'][axis] = {'metres_per_page_point': mean, 'measurement_ids': [r['id'] for r, _ in bars],
                                'assumption': 'Analyst-approved uniform scale scope' if axis == 'isotropic' else 'Axis-specific; no plan/profile inheritance'}
    if conflict:
        result['status'], result['axes'] = 'conflicting_evidence', {}
    elif not result['missing_evidence'] and len(result['axes']) == len(needed):
        result['status'] = 'calibrated_effective_view_scale'
    else:
        # Ratios may be shown as measurements, but never exported as effective scale.
        result['axes'] = {}
    if result['status'] == 'calibrated_effective_view_scale':
        bar_sources = {r['spec']['source_reference'] for r, _ in approved if r['spec']['kind'] == 'bar'}
        bar_points = [e['endpoints_page'] for r, e in approved if r['spec']['kind'] == 'bar']
        for r, e in approved:
            s = r['spec']
            if (s['kind'] != 'checkpoint' or s['use'] != 'current_view' or not s['independent_of_calibration'] or s['source_reference'] in bar_sources
                    or any(all(math.dist(a, b) < 1e-4 for a, b in zip(e['endpoints_page'], pts))
                           or all(math.dist(a, b) < 1e-4 for a, b in zip(e['endpoints_page'], reversed(pts))) for pts in bar_points)):
                continue
            axis = s['axis']
            if axis in result['axes'] and e['ground_distance_m'] and s['applicability_confirmed'] and axis_matches(r, e):
                estimate = result['axes'][axis]['metres_per_page_point'] * e['span_page_points']
                delta = estimate - e['ground_distance_m']
                result['validation']['measurements'].append({'id': r['id'], 'axis': axis, 'distance_error_m': delta,
                                                             'relative_error_percent': 100 * delta / e['ground_distance_m']})
        if result['validation']['measurements']:
            result['validation']['status'] = 'independent_scale_distance_checks_only'
    return result
