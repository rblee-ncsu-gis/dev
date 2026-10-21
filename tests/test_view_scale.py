"""Synthetic numeric checks only; these are not county scale-accuracy examples."""

from copy import deepcopy
import math

import pytest

from asbuilt_matcher.clues import review_identity
from asbuilt_matcher.view_scale import (assess_scale, measure, points_page, revision, validate_scale, validate_view)
from asbuilt_matcher.views import _record, _scale_spec

BOUNDS = [0, 0, 500, 500]


def view(mode='isotropic', kind='engineering_plan'):
    return _record('synthetic', {'bbox': BOUNDS, 'view_type': kind, 'engineering_relevance': 'engineering',
                                'reading_orientation': 0, 'scale_mode': mode,
                                'distortion_notes': 'SYNTHETIC uniform plotting assumption'})


def approved(record):
    record = deepcopy(record)
    record['verification_status'] = 'verified'
    record['verification'] = review_identity('Synthetic independent analyst', 'SYNTHETIC independent test review', 'human', True,
                                              record['last_evidence_author'])
    return record


def bar(v, **kwargs):
    return _record(kwargs.pop('id', 'bar'), _scale_spec(v, kind='bar', endpoints=[[10, 50], [82, 50]],
        ground_distance=40, ground_unit='foot', source_reference='SYNTHETIC reference A',
        text='SYNTHETIC graphic bar', use='current_view', applicability_confirmed=True,
        distortion_checked=True, **kwargs))


def test_printed_statement_is_not_effective_calibration():
    v = approved(view())
    statement = approved(_record('s', _scale_spec(v, paper_inches=1, ground_distance=40, ground_unit='foot',
        text='1 inch = 40 feet', source_reference='SYNTHETIC printed statement', source_method='native_text',
        use='current_view', applicability_confirmed=True)))
    result = assess_scale(v, [statement], BOUNDS, {})
    assert result['status'] == 'unresolved' and result['axes'] == {}
    assert result['evidence'][0]['metres_per_page_point'] == pytest.approx(40 * .3048 / 72)


def test_accepted_bar_and_view_calibrate_page_distance_only():
    v = approved(view())
    b = approved(bar(v))
    result = assess_scale(v, [b], BOUNDS, {})
    assert result['status'] == 'calibrated_effective_view_scale'
    assert result['axes']['isotropic']['metres_per_page_point'] == pytest.approx(40 * .3048 / 72)
    assert result['map_crs'] is None and not result['geographic_registration']
    assert result['validation']['status'] == 'not_measured_no_independent_check'


def test_ai_bar_and_rejected_view_do_not_calibrate():
    v = approved(view())
    assert assess_scale(v, [bar(v)], BOUNDS, {})['axes'] == {}
    v['verification_status'] = 'rejected'
    assert assess_scale(v, [approved(bar(v))], BOUNDS, {})['status'] == 'unresolved'


@pytest.mark.parametrize('mode,kind', [('not_to_scale', 'detail_inset'), ('isotropic', 'vicinity_map'), ('isotropic', 'administrative_supporting')])
def test_context_and_nts_never_gain_plan_scale(mode, kind):
    v = approved(view(mode, kind))
    result = assess_scale(v, [approved(bar(v))], BOUNDS, {})
    assert result['axes'] == {}
    assert result['status'] in {'not_to_scale', 'not_applicable_to_engineering_calibration'}


def test_profile_needs_both_independent_axis_measurements():
    v = approved(view('anisotropic', 'engineering_profile'))
    h = approved(bar(v, axis='horizontal'))
    assert assess_scale(v, [h], BOUNDS, {})['axes'] == {}
    vertical = approved(bar(v, id='vertical', axis='vertical'))
    vertical['spec'].update(endpoints=[[50, 100], [50, 172]], ground_distance=4)
    result = assess_scale(v, [h, vertical], BOUNDS, {})
    assert result['status'] == 'calibrated_effective_view_scale'
    assert result['axes']['horizontal']['metres_per_page_point'] / result['axes']['vertical']['metres_per_page_point'] == pytest.approx(10)


def test_conflicting_bar_and_printed_scope_remain_unresolved():
    v = approved(view())
    b = approved(bar(v))
    s = approved(_record('printed', _scale_spec(v, paper_inches=1, ground_distance=60, ground_unit='foot', text='1 inch = 60 feet',
        source_reference='SYNTHETIC nominal plot', use='current_view', applicability_confirmed=True)))
    result = assess_scale(v, [b, s], BOUNDS, {})
    assert result['status'] == 'conflicting_evidence' and result['axes'] == {}
    # Explicit reviewed nominal-only scope resolves which evidence applies; never silently choose a ratio.
    s['spec']['use'] = 'nominal_only'
    assert assess_scale(v, [b, s], BOUNDS, {})['status'] == 'calibrated_effective_view_scale'


def test_resized_or_distorted_plot_needs_explicit_review():
    v = approved(view())
    b = approved(bar(v))
    b['spec']['distortion_checked'] = False
    assert assess_scale(v, [b], BOUNDS, {})['status'] == 'unresolved'
    b['spec']['distortion_checked'] = True
    v['spec']['distortion_notes'] = ''
    assert assess_scale(v, [b], BOUNDS, {})['axes'] == {}


def test_scope_revision_retains_old_acceptance_but_blocks_current_calibration():
    v = approved(view()); b = approved(bar(v)); old = deepcopy(b)
    v['spec']['bbox'] = [1, 1, 499, 499]
    result = assess_scale(v, [b], BOUNDS, {})
    assert result['status'] == 'unresolved'
    assert not result['evidence'][0]['current_view_revision']
    assert b == old and b['verification_status'] == 'verified'


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_crop_and_orientation_matrix_roundtrip(angle):
    pdf = pytest.importorskip('pymupdf')
    matrix = pdf.Matrix(2, 0, 0, 2, -20, -40) * pdf.Matrix(angle)
    points = [pdf.Point(20, 30) * matrix, pdf.Point(92, 30) * matrix]
    # Translate to a positive pixel box as the existing OCR/preparation path does.
    shift = pdf.Matrix(1, 0, 0, 1, -min(p.x for p in points)+10, -min(p.y for p in points)+10)
    matrix *= shift
    im = {'width': 300, 'height': 300, 'page_to_pixel': list(matrix)}
    s = bar(view())['spec']; s.update(coordinate_space='image', image_id='crop', endpoints=[list(pdf.Point(p)*matrix) for p in [[20,30],[92,30]]])
    recovered = points_page(s, BOUNDS, {'crop': im})
    assert all(math.dist(a, b) < 1e-5 for a, b in zip(recovered, [[20,30],[92,30]]))
    assert measure(s, BOUNDS, {'crop': im})['span_page_points'] == pytest.approx(72)


def test_error_only_against_independent_held_out_measurement():
    v = approved(view()); b = approved(bar(v))
    check = bar(v, id='check')
    check['spec'].update(kind='checkpoint', endpoints=[[100,60],[244,60]], ground_distance=80,
                         source_reference='SYNTHETIC independently measured B', independent_of_calibration=True)
    assert assess_scale(v, [b, check], BOUNDS, {})['validation']['measurements'] == []
    checked = assess_scale(v, [b, approved(check)], BOUNDS, {})
    assert checked['validation']['measurements'][0]['relative_error_percent'] == pytest.approx(0)
    check['spec']['source_reference'] = b['spec']['source_reference']
    assert assess_scale(v, [b, approved(check)], BOUNDS, {})['validation']['measurements'] == []


def test_derived_or_reversed_duplicate_measurement_is_not_a_checkpoint():
    v = approved(view()); b = approved(bar(v)); c = deepcopy(b); c['id']='dup'
    c['spec'].update(kind='checkpoint', independent_of_calibration=True, source_reference='SYNTHETIC derived crop')
    c['spec']['endpoints'].reverse()
    assert assess_scale(v,[b,c],BOUNDS,{})['validation']['measurements'] == []


@pytest.mark.parametrize('field,value', [('ground_distance',0),('ground_unit','feet?'),('paper_inches',float('nan')),
    ('coordinate_space','EPSG:2264'),('applicability_confirmed','yes'),('endpoints',[[10,10],[10,10]]),('endpoints',[[0,0],[600,0]])])
def test_invalid_measurements(field,value):
    s = bar(view())['spec'];s[field]=value
    with pytest.raises(ValueError):validate_scale(s,BOUNDS,{})


def test_unknown_ground_distance_is_measured_span_not_calibration():
    s=bar(view())['spec'];s['ground_distance']=None
    assert measure(s,BOUNDS,{})['status']=='measured_span_ground_unknown'
    with pytest.raises(ValueError,match='Approved'):validate_scale(s,BOUNDS,{},complete=True)


def test_profile_axis_must_follow_its_reading_orientation():
    v=approved(view('anisotropic','engineering_profile'))
    h=approved(bar(v,axis='horizontal'))
    h['spec']['endpoints']=[[50,100],[50,172]]
    result=assess_scale(v,[h],BOUNDS,{})
    assert result['axes']=={}
    assert 'direction conflicts' in ' '.join(result['missing_evidence'])


def test_profile_cannot_inherit_a_single_isotropic_plan_bar():
    v=approved(view('isotropic','engineering_profile'));b=approved(bar(v))
    result=assess_scale(v,[b],BOUNDS,{})
    assert result['axes']=={}
    assert 'profiles require separately' in ' '.join(result['missing_evidence'])


def test_literal_scale_transcription_can_be_accepted_with_unknown_foot_definition():
    v=approved(view())
    s=_record('literal',_scale_spec(v,text='1 INCH = 40 FEET',ground_distance=40,paper_inches=1,
        ground_unit=None,source_reference='SYNTHETIC source text'))
    validate_scale(s['spec'],BOUNDS,{},complete=True)
    result=assess_scale(v,[approved(s),approved(bar(v))],BOUNDS,{})
    assert result['status']=='unresolved' and result['axes']=={}
    assert result['evidence'][0]['measurement_stage']=='analyst_verified_statement'


def test_explicitly_excluded_stale_evidence_does_not_block_new_scope():
    v=approved(view());old=approved(bar(v))
    v['spec']['bbox']=[1,1,499,499]
    old['spec']['use']='excluded'
    current=approved(bar(v,id='new'))
    assert assess_scale(v,[old,current],BOUNDS,{})['status']=='calibrated_effective_view_scale'
