"""Known synthetic transforms and independent synthetic checkpoints only."""

from copy import deepcopy
import math

import pytest

from asbuilt_matcher.geo_controls import apply_control_operations
from asbuilt_matcher.geo_geometry import unproject
from asbuilt_matcher.geo_registration import US_SURVEY_FOOT_M, independent_checkpoint_references, predict_pixel, registration_diagnostics
from test_geo_controls import add, approve, collection, operation, values


def register(points, transform, checkpoints=()):
    r = collection()
    for i, (pixel, role) in enumerate([(p, 'fit') for p in points] + [(p, 'checkpoint') for p in checkpoints]):
        r = add(r, key=str(i), pixel=list(pixel), xy=transform(*pixel), role=role)
        r = approve(r, key=str(i))
    return r


def method(result, name):
    return next(m for m in result['drawings'][0]['methods'] if m['method'] == name)


def test_no_controls_reports_exact_missing_evidence_without_fitting():
    result = registration_diagnostics(collection())
    for d in result['drawings']:
        assert d['approved_fit_controls'] == 0
        for m in d['methods']:
            assert m['model'] is None and m['checkpoint_rmse_m'] is None
            assert m['status'] == 'insufficient_controls' and m['missing_evidence']
    assert not result['positional_accuracy_reported']


def test_similarity_two_controls_has_residuals_but_no_accuracy():
    r = register([(100, 100), (900, 100)], lambda x, y: [2000000 + 2 * x, 100000 - 2 * y])
    m = method(registration_diagnostics(r), 'similarity')
    assert m['status'] == 'fitted' and m['fit_rms_m'] < 1e-7
    assert m['checkpoint_rmse_m'] is None and not m['positional_accuracy_reported']
    prediction = predict_pixel([300, 400], m['model'])
    assert [prediction['geographic'][k] for k in ['x', 'y']] == pytest.approx([2000600, 99200])
    assert m['model']['geometry_diagnostics']['minimum_fit_is_exactly_determined']
    assert registration_diagnostics(r)['drawings'][1]['approved_fit_controls'] == 0


def test_rigid_needs_independently_documented_fixed_scale():
    r = register([(100, 100), (900, 100)], lambda x, y: [2000000 + 2 * x, 100000 - 2 * y])
    assert method(registration_diagnostics(r), 'rigid')['model'] is None
    scale = {'metres_per_pixel': 2 * US_SURVEY_FOOT_M, 'source': 'Synthetic scale evidence', 'last_evidence_author': 'Synthetic scale author',
             'verification_status': 'verified', 'verification': {'reviewer': 'Synthetic other reviewer', 'reviewer_type': 'human', 'independent': True,
                                                               'reason': 'Synthetic independent scale check', 'timestamp': '2026-10-19T00:00:00Z'}}
    m = method(registration_diagnostics(r, rigid_scale=scale), 'rigid')
    assert m['status'] == 'fitted' and m['fit_rms_m'] < 1e-7
    with pytest.raises(ValueError, match='scale'):
        registration_diagnostics(r, rigid_scale={'metres_per_pixel': 1})


def test_affine_fit_and_heldout_checkpoint_agreement_are_separate():
    r = register([(100, 100), (900, 100), (100, 700)], lambda x, y: [2000000 + 2 * x + .3 * y, 100000 + .2 * x - 1.5 * y],
                 checkpoints=[(200, 200), (700, 500)])
    m = method(registration_diagnostics(r), 'affine')
    assert m['status'] == 'fitted' and len(m['fit_residuals']) == 3 and len(m['checkpoint_residuals']) == 2
    assert m['fit_rms_m'] < 1e-7 and m['checkpoint_rmse_m'] < 1e-7
    assert m['checkpoint_agreement_reported'] and not m['positional_accuracy_reported']
    assert 'accuracy_unknown' in m['validation_status']
    for row in r['records']:
        if row['role'] == 'checkpoint': row['estimated_accuracy_m'] = .1
    assert method(registration_diagnostics(r), 'affine')['positional_accuracy_reported']


@pytest.mark.parametrize('points', [[(100, 100), (400, 100), (900, 100)], [(100, 100), (400, 100.001), (900, 100)], [(100, 100), (100, 100), (900, 700)]])
def test_affine_rejects_collinear_poorly_distributed_and_duplicate_controls(points):
    r = register(points, lambda x, y: [2000000 + 2 * x, 100000 - 2 * y])
    m = method(registration_diagnostics(r), 'affine')
    assert m['status'] == 'insufficient_geometry' and m['model'] is None


def test_checkpoint_leakage_and_duplicate_checkpoints_do_not_count_as_validation():
    r = register([(100, 100), (900, 100)], lambda x, y: [2000000 + x, 100000 - y], checkpoints=[(100, 100), (300, 300), (300, 300)])
    m = method(registration_diagnostics(r), 'similarity')
    assert len(m['excluded_checkpoints']) == 2 and len(m['checkpoint_residuals']) == 1
    assert m['checkpoint_rmse_m'] is None


def test_ai_review_is_not_a_fit_control_and_ties_do_not_supply_ground_coordinates():
    r = register([(100, 100), (900, 100)], lambda x, y: [2000000 + x, 100000 - y])
    r['records'][0]['verification']['reviewer_type'] = 'ai'
    m = method(registration_diagnostics(r), 'similarity')
    assert m['model'] is None
    assert registration_diagnostics(r)['drawings'][0]['excluded'][0]['reason'] == 'not_independently_analyst_approved'


def test_mixed_crs_does_not_silently_transform_or_relabel():
    r = register([(100, 100), (900, 100)], lambda x, y: [2000000 + x, 100000 - y])
    result = registration_diagnostics(r, target_crs='EPSG:4326')
    assert result['drawings'][0]['approved_fit_controls'] == 0
    assert all('transformation' in e['reason'] for e in result['drawings'][0]['excluded'])
    assert method(result, 'similarity')['model'] is None


def test_epsg4326_uses_documented_metre_frame_not_affine_in_degrees():
    origin = [-78.2, 34]
    r = collection(); r['target_crs'] = 'EPSG:4326'
    for i, pixel in enumerate([[100, 100], [900, 100], [100, 700]]):
        lon, lat = unproject([pixel[0], -pixel[1]], origin)
        v = values(r, pixel=pixel); v['geographic'] = {'x': lon, 'y': lat, 'crs': 'EPSG:4326', 'units': 'degree'}
        r = apply_control_operations(r, {'operations': [operation(id=str(i), values=v)]}); r = approve(r, key=str(i))
    m = method(registration_diagnostics(r), 'affine')
    assert m['status'] == 'fitted' and m['fit_rms_m'] < .001
    p = predict_pixel([200, 200], m['model'])['geographic']; expected = unproject([200, -200], origin)
    assert [p['x'], p['y']] == pytest.approx(expected, abs=1e-7)
    assert 'tangent plane' in m['model']['metric_frame']['type']


def test_independent_localization_reference_export_never_uses_fitting_predictions():
    r = register([(100, 100), (900, 100)], lambda x, y: [2000000 + x, 100000 - y], checkpoints=[(300, 300)])
    export = independent_checkpoint_references(r)
    assert export['references'] == [] and len(export['pending']) == 1
    p = r['records'][-1]; p['geographic'] = {'x': -78.2, 'y': 34, 'crs': 'EPSG:4326', 'units': 'degree'}; p['estimated_accuracy_m'] = 1
    export = independent_checkpoint_references(r)
    assert len(export['references']) == 1 and export['references'][0]['location']['control_id'] == p['id']
    assert all(e['location']['control_id'] not in ['0', '1'] for e in export['references'])


def test_control_correction_invalidates_fit_eligibility():
    r = register([(100, 100), (900, 100)], lambda x, y: [2000000 + x, 100000 - y])
    r = apply_control_operations(r, {'operations': [operation('edit', id='0', values={'description': 'Synthetic corrected identity'})]})
    assert method(registration_diagnostics(r), 'similarity')['model'] is None
