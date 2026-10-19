"""Fabricated control evidence only; never approvals for C7/C8."""

from copy import deepcopy
import json
import re
from pathlib import Path
import uuid

import pytest

from asbuilt_matcher.cli import main
from asbuilt_matcher.geo_controls import apply_control_operations, apply_controls, coordinate_for, independently_approved, load_collection
from asbuilt_matcher.geo_control_review import create_collection
from asbuilt_matcher.pdf_extract import file_sha256, load_pdf_backend, write_json
from asbuilt_matcher.raster import prepare_rasters


def collection():
    drawings = []
    for sheet, char in [('SYNTHETIC-A', 'a'), ('SYNTHETIC-B', 'b')]:
        drawings.append({'drawing_id': char * 64 + ':1', 'source': {'source_pdf': sheet + '.pdf', 'pdf_identifier': char * 64,
                         'document_sha256': char * 64, 'sheet': sheet, 'page_number': 1, 'bundle_file': 'sources/' + sheet + '.pdf'},
                         'image': {'width': 1000, 'height': 800, 'sha256': char * 64}})
    return {'schema_version': 1, 'kind': 'geographic_control_collection', 'target_crs': 'EPSG:2264', 'drawings': drawings,
            'records': [], 'operation_history': [], 'bound_files': {}, 'model_input_reference_locations': []}


def values(registry, pixel=None, xy=None, role='fit'):
    xy = xy or [2000100, 100100]
    return {'drawing_id': registry['drawings'][0]['drawing_id'], 'pixel': pixel or [100, 100],
            'geographic': {'x': xy[0], 'y': xy[1], 'crs': 'EPSG:2264', 'units': 'US survey foot'}, 'transformed_geographic': None,
            'feature_type': 'Fabricated test corner', 'description': 'SYNTHETIC control, not a real location', 'reference_feature_id': 'SYNTHETIC-REF',
            'estimated_accuracy_m': None, 'role': role, 'independent_of_fit': role == 'checkpoint', 'historical_change_notes': 'Fabricated unchanged feature',
            'evidence': {'source': 'Synthetic independent reference', 'source_date': '2020-01-01', 'source_reference': 'SYNTHETIC-REF / vertex',
                         'point_identity': 'Fabricated physical identity', 'historical_consistency': 'Synthetic unchanged geometry',
                         'independently_determined': True, 'model_input_landmark': False}}


def operation(action='add_control', **kwargs):
    return {'operation_id': str(uuid.uuid4()), 'action': action, 'author': 'Synthetic proposer', 'reviewer_type': 'human',
            'independent': False, 'reason': 'Fabricated test evidence only', **kwargs}


def add(registry, key='one', **kwargs):
    return apply_control_operations(registry, {'operations': [operation(id=key, values=values(registry, **kwargs))]})


def approve(registry, key='one', **kwargs):
    args = {'id': key, 'status': 'verified', 'author': 'Synthetic independent reviewer', 'independent': True, **kwargs}
    return apply_control_operations(registry, {'operations': [operation('review', **args)]})


def test_edit_preserves_original_and_history_and_resets_acceptance():
    original = collection(); r = add(original); r = approve(r)
    old = deepcopy(r); point = r['records'][0]
    assert independently_approved(point)
    r = apply_control_operations(r, {'operations': [operation('edit', id='one', author='Synthetic corrector', values={'pixel': [110, 120]})]})
    p = r['records'][0]
    assert p['pixel'] == [110, 120] and p['original']['pixel'] == [100, 100]
    assert p['verification_status'] == 'unverified' and p['verification'] is None
    assert p['history'][-1]['before']['verification_status'] == 'verified'
    assert p['history'][-1]['after']['pixel'] == [110, 120]
    assert r['records'][0]['original'] == old['records'][0]['original']
    assert original['records'] == [] and old['records'][0]['pixel'] == [100, 100]
    with pytest.raises(ValueError, match='distinct'):
        approve(r, author='Synthetic corrector')


@pytest.mark.parametrize('actor,independent', [('ai', False), ('ai', True), ('human', False)])
def test_ai_or_nonindependent_review_cannot_approve(actor, independent):
    r = add(collection())
    with pytest.raises(ValueError):
        apply_control_operations(r, {'operations': [operation('review', id='one', status='verified', reviewer_type=actor,
                                                             independent=independent, author='Other synthetic reviewer')]})


@pytest.mark.parametrize('pixel', [[1000, 5], [-1, 5], [4, float('nan')], [True, 5]])
def test_invalid_original_image_coordinates_rejected(pixel):
    with pytest.raises(ValueError, match='Pixel'):
        add(collection(), pixel=pixel)


def test_incomplete_point_can_be_drafted_but_not_approved():
    r = collection(); v = values(r); v.update(pixel=None, geographic=None)
    r = apply_control_operations(r, {'operations': [operation(id='one', values=v)]})
    with pytest.raises(ValueError, match='Pixel'):
        approve(r)


def test_rejected_and_unreadable_records_are_retained():
    for status in ['rejected', 'unreadable']:
        r = add(collection())
        r = apply_control_operations(r, {'operations': [operation('review', id='one', status=status)]})
        assert len(r['records']) == 1 and r['records'][0]['original']
        assert not independently_approved(r['records'][0])


def test_model_landmark_points_and_unindependent_evidence_cannot_be_promoted():
    r = collection(); v = values(r); v['geographic'] = {'x': -78.1, 'y': 34, 'crs': 'EPSG:4326', 'units': 'degree'}
    r['model_input_reference_locations'] = [{'geometry': {'type': 'Point', 'coordinates': [-78.1, 34]}}]
    r = apply_control_operations(r, {'operations': [operation(id='one', values=v)]})
    with pytest.raises(ValueError, match='Model-input'):
        approve(r)
    r = add(collection()); r['records'][0]['evidence']['independently_determined'] = False
    with pytest.raises(ValueError, match='Independent control evidence'):
        approve(r)


def test_checkpoint_approval_requires_heldout_attestation():
    r = add(collection(), role='checkpoint'); r['records'][0]['independent_of_fit'] = False
    with pytest.raises(ValueError, match='Checkpoint'):
        approve(r)


def test_duplicate_operations_and_immutable_source_binding_rejected():
    r = collection(); op = operation(id='one', values=values(r))
    r = apply_control_operations(r, {'operations': [op]})
    with pytest.raises(ValueError, match='previously applied'):
        apply_control_operations(r, {'operations': [op]})
    with pytest.raises(ValueError, match='immutable'):
        apply_control_operations(r, {'operations': [operation('edit', id='one', values={'drawing_id': 'different'})]})


def test_crs_units_and_nonfinite_geographic_coordinates_rejected():
    for geographic in [{'x': 1, 'y': 2, 'crs': 'EPSG:2264', 'units': 'metre'},
                       {'x': 1, 'y': 91, 'crs': 'EPSG:4326', 'units': 'degree'},
                       {'x': float('inf'), 'y': 2, 'crs': 'EPSG:2264', 'units': 'US survey foot'}]:
        r = collection(); v = values(r); v['geographic'] = geographic
        with pytest.raises(ValueError):
            apply_control_operations(r, {'operations': [operation(id='one', values=v)]})


def test_explicit_external_transformation_preserves_both_coordinates():
    r = add(collection()); p = r['records'][0]
    assert coordinate_for(p, 'EPSG:4326') is None
    converted = {'x': -78.2, 'y': 34, 'crs': 'EPSG:4326', 'units': 'degree',
                 'transformation': {'source_crs': 'EPSG:2264', 'target_crs': 'EPSG:4326',
                                   'input_xy': [p['geographic']['x'], p['geographic']['y']], 'output_xy': [-78.2, 34], 'axis_order': 'x,y',
                                   'operation': 'Fabricated test operation, no real datum conversion', 'software': 'Synthetic', 'software_version': 'test',
                                   'source': 'Synthetic conversion evidence', 'performed_at': '2026-10-19T00:00:00Z', 'datum_notes': 'Synthetic only',
                                   'grid_notes': 'Synthetic only', 'ballpark': False}}
    p['transformed_geographic'] = converted
    assert coordinate_for(p, 'EPSG:4326') == converted
    p['geographic']['x'] += 1
    with pytest.raises(ValueError, match='bind original'):
        coordinate_for(p, 'EPSG:4326')


def test_cross_sheet_ties_need_both_image_picks_and_station_verification():
    r = collection(); v = {'left_drawing_id': r['drawings'][0]['drawing_id'], 'right_drawing_id': r['drawings'][1]['drawing_id'],
                          'left_pixel': [100, 100], 'right_pixel': [200, 200], 'description': 'SYNTHETIC matchline feature',
                          'station_text': '78+75', 'station_verified': False, 'evidence': values(r)['evidence'], 'historical_change_notes': ''}
    r = apply_control_operations(r, {'operations': [operation('add_tie', id='one', values=v)]})
    with pytest.raises(ValueError, match='Station-tagged'):
        approve(r)
    r = apply_control_operations(r, {'operations': [operation('edit', id='one', values={'station_verified': True})]})
    r = approve(r)
    assert independently_approved(r['records'][0]) and 'geographic' not in r['records'][0]
    v['geographic'] = {'x': 0, 'y': 0}
    with pytest.raises(ValueError, match='Unsupported'):
        apply_control_operations(collection(), {'operations': [operation('add_tie', id='bad', values=v)]})


@pytest.fixture
def bundle(tmp_path):
    pdf = load_pdf_backend(); drawings = []; manifests = []; refs_path = tmp_path / 'roads.geojson'
    geometry = {'type': 'LineString', 'coordinates': [[-78.2, 34], [-78.195, 34.0001], [-78.19, 34]]}
    write_json(refs_path, {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': geometry, 'properties': {'GlobalID': 'SYNTHETIC-ROAD', 'FULLNAME': 'SYNTHETIC ROAD'}}]})
    for sheet in ['C7', 'C8']:
        source = tmp_path / f'SYNTHETIC-{sheet}.pdf'
        with pdf.open() as doc:
            page = doc.new_page(width=100, height=80); page.insert_text((10, 20), 'SYNTHETIC ' + sheet, fontsize=7); doc.save(source)
        raster = tmp_path / f'raster-{sheet}'; prepare_rasters(source, raster, dpi=72)
        digest = file_sha256(source)
        c = {'candidate_id': sheet, 'rank': 1, 'score': 1, 'qualified': False, 'match_type': 'road_corridor', 'localization_level': 'road_corridor',
             'bbox': [-78.2, 34, -78.19, 34.001], 'evidence': [], 'bonuses': [], 'conflicts': [], 'missing': [], 'spatial_context': [], 'limitations': [],
             'supporting_features': [{'dataset_id': 'roads', 'native_id': 'SYNTHETIC-ROAD'}],
             'coverage': {'geometry': {'type': 'MultiLineString', 'coordinates': [geometry['coordinates']]}, 'reference_length_m': 1000}}
        drawings.append({'drawing_id': digest + ':1', 'document_sha256': digest, 'source_pdf': source.name, 'page_number': 1, 'sheet_numbers': [sheet],
                         'status': 'corridor_identified', 'accepted_clues': [], 'candidates': [c], 'diagnostics': {}})
        manifests.append({'drawing_id': digest + ':1', 'sheet': sheet, 'raster_manifest': str(raster / 'raster-manifest.json')})
    run = {'run_id': 'SYNTHETIC', 'status': 'complete', 'reference_status': 'complete', 'drawings': drawings, 'cross_sheet': [],
           'distance_model': {'origin': [-78.2, 34]}, 'reference_datasets': [{'id': 'roads', 'kind': 'roads', 'path': str(refs_path), 'sha256': file_sha256(refs_path), 'fields': {'id': 'GlobalID'}, 'metadata': {}}]}
    run_path, config = tmp_path / 'run.json', tmp_path / 'config.json'; write_json(run_path, run)
    write_json(config, {'target_crs': 'EPSG:2264', 'drawings': manifests})
    output = tmp_path / 'bundle'
    assert main(['controls-init', str(run_path), '--config', str(config), '--output', str(output)]) == 0
    return output


def test_empty_bundle_preserves_imagery_and_has_offline_collection(bundle):
    registry = load_collection(bundle / 'controls.json')
    assert registry['records'] == [] and len(registry['drawings']) == 2
    html = (bundle / 'REVIEW.html').read_text(encoding='utf-8')
    assert 'original composition' in html and 'GIS CRS' in html and 'draft operations' in html
    assert 'class="reference-pick"' in html and 'Geographic control/checkpoint' in html
    assert '<script src="control-review.js">' in html
    assert (bundle / 'GEOGRAPHIC_REVIEW.html').is_file()
    assert read_registry_hash(bundle) == file_sha256(bundle / 'controls.json')
    for d in registry['drawings']:
        assert file_sha256(bundle / d['image']['bundle_file']) == d['image']['sha256']


def read_registry_hash(bundle):
    return json.loads((bundle / 'decisions-template.json').read_text())['registry_sha256']


def test_apply_creates_new_snapshot_and_rejects_stale_or_tampered_evidence(bundle, tmp_path):
    registry = load_collection(bundle / 'controls.json'); v = values(registry, pixel=[10, 10])
    decision = tmp_path / 'decisions.json'
    write_json(decision, {'registry_sha256': file_sha256(bundle / 'controls.json'), 'operations': [operation(id='one', values=v)]})
    before = (bundle / 'controls.json').read_bytes()
    result = apply_controls(bundle / 'controls.json', decision, tmp_path / 'next')
    assert len(result['records']) == 1 and (bundle / 'controls.json').read_bytes() == before
    assert result['parent']['registry_sha256'] == file_sha256(bundle / 'controls.json')
    assert load_collection(tmp_path / 'next/controls.json')['records'][0]['original']['pixel'] == [10, 10]
    d = json.loads(decision.read_text()); d['registry_sha256'] = '0' * 64; write_json(decision, d)
    with pytest.raises(ValueError, match='SHA-256'):
        apply_controls(bundle / 'controls.json', decision, tmp_path / 'stale')
    assert not (tmp_path / 'stale').exists()
    image = bundle / registry['drawings'][0]['image']['bundle_file']; image.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_collection(bundle / 'controls.json')


def test_schema_and_blank_template_do_not_contain_real_control_coordinates(bundle):
    schema = json.loads((Path(__file__).resolve().parents[1] / 'docs/geographic_control.schema.json').read_text())
    assert set(schema['$defs']['geographic']['properties']['crs']['enum']) == {'EPSG:2264', 'EPSG:4326'}
    template = json.loads((bundle / 'decisions-template.json').read_text())
    assert template['operations'] == [] and template['control_template']['values']['pixel'] is None
    assert template['control_template']['values']['geographic'] is None


def test_offline_payload_roundtrips_literal_markup_as_data(bundle, tmp_path):
    r = load_collection(bundle / 'controls.json'); v = values(r, pixel=[10, 10])
    v['description'] = 'SYNTHETIC </script><script>bad()</script> & evidence'
    path = tmp_path / 'decisions-markup.json'
    write_json(path, {'registry_sha256': file_sha256(bundle / 'controls.json'), 'operations': [operation(id='markup', values=v)]})
    apply_controls(bundle / 'controls.json', path, tmp_path / 'markup')
    html = (tmp_path / 'markup/REVIEW.html').read_text(encoding='utf-8')
    data = re.search(r'<script id="collection-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert '<script>' not in data
    assert json.loads(data)['registry']['records'][0]['description'] == v['description']
