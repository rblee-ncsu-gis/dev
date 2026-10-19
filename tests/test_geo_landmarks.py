"""Synthetic landmark, corridor and station evidence; no real analyst approvals."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import re

import pytest

from asbuilt_matcher.cli import main
from asbuilt_matcher.geo_eval import evaluate_localization
from asbuilt_matcher.geo_landmarks import import_landmarks, match_landmarks, validate_landmarks
from asbuilt_matcher.geo_narrowing import attach_source_lineage, narrow_corridors, run_narrowing
from asbuilt_matcher.geo_reference import load_references, read_json
from asbuilt_matcher.geo_report import evaluation_template
from asbuilt_matcher.geo_stationing import sheet_relationships, station_range
from asbuilt_matcher.geolocate import locate_documents
from asbuilt_matcher.pdf_extract import file_sha256, write_json

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/phase2b'


def reference(key='cemetery', name='SYNTHETIC CEMETERY', point=None):
    geometry = {'type': 'Point', 'coordinates': point or [-78.2, 34.0502]}
    return {'landmark_id': key, 'name': name, 'type': 'synthetic', 'aliases': [], 'geometry': geometry,
            'positional_accuracy_m': None, 'verification_status': 'source_corroborated',
            'sources': [{'source': 'Fabricated source, no real location', 'source_date': None, 'accessed_at': '2026-10-19'}],
            'reference_points': [{'point_id': key + ':published', 'geometry': geometry, 'basis': 'synthetic published coordinate', 'positional_accuracy_m': None}], 'parcels': []}


@pytest.fixture
def pilot():
    catalog = load_references(EXAMPLE / 'reference-config.json')
    road = next(f for f in catalog['features'] if f['native_id'] == 'A-PINE')
    road['geometry'] = {'type': 'MultiLineString', 'coordinates': [
        [[-78.21, 34.05], [-78.205, 34.05]], [[-78.205, 34.05], [-78.195, 34.05]], [[-78.195, 34.05], [-78.19, 34.05]]]}
    dataset = next(d for d in catalog['datasets'] if d['kind'] == 'roads')
    aliases = {'schema_version': 1, 'entries': [{'id': 'synthetic', 'enabled': True, 'status': 'source_corroborated',
               'sources': [{'evidence': 'Fabricated source'}], 'scope': {'dataset_id': dataset['id'], 'source_sha256': dataset['sha256'],
               'feature_ids': ['A-PINE'], 'field_values': {'NAME_TEXT': ['SYNTHETIC PINE']}},
               'aliases': [{'text': 'NC 211 - SUPPLY ROAD', 'category': 'candidate_relationship'}]}]}
    seed = read_json(EXAMPLE / 'accepted-clues.json')['clues'][0]
    rows = []
    for cid, kind, text in [('road', 'street_name', 'NC 211 - SUPPLY ROAD'), ('landmark', 'landmark', 'SYNTHETIC CEMETERY'),
                            ('sheet', 'sheet_number', 'C7'), ('station', 'station_range', 'STA. 66+50 TO STA. 78+75'),
                            ('project', 'project_name', 'SYNTHETIC PROJECT')]:
        c = deepcopy(seed); c.update(clue_id=cid, kind=kind, text=text); rows.append(c)
    run = locate_documents({'clues': rows}, catalog, alias_registry=aliases)
    run.update(run_id='synthetic-parent', reference_status='complete', reference_datasets=catalog['datasets'])
    landmarks = {'schema_version': 1, 'crs': 'EPSG:4326', 'area_of_interest_bbox': [-78.5, 33.8, -78, 34.5], 'landmarks': [reference()]}
    return run, landmarks


def test_literal_landmark_matching_preserves_source_and_rejects_near_names(pilot):
    _, document = pilot
    document['landmarks'][0]['aliases'] = ['Cemetery of Synthetic']
    original = deepcopy(document)
    assert match_landmarks({'text': 'cemetery\nof synthetic'}, document)
    assert not match_landmarks({'text': 'SYNTHETIC MEMORIAL CEMETERY'}, document)
    assert document == original
    document['landmarks'][0]['verification_status'] = 'unverified'
    assert not match_landmarks({'text': 'SYNTHETIC CEMETERY'}, document)


@pytest.mark.parametrize('point', [[-78.2, 91], [float('nan'), 34], [True, 34], [34, -78]])
def test_bad_and_reversed_coordinates_rejected(pilot, point):
    _, document = pilot
    document['landmarks'][0]['geometry']['coordinates'] = point
    with pytest.raises(ValueError):
        validate_landmarks(document)


@pytest.mark.parametrize('accuracy', [-1, 0, True, float('inf')])
def test_accuracy_is_not_invented_or_boolean(pilot, accuracy):
    _, document = pilot
    document['landmarks'][0]['positional_accuracy_m'] = accuracy
    with pytest.raises(ValueError, match='accuracy'):
        validate_landmarks(document)


def test_provenance_and_status_cannot_grant_approval(pilot):
    _, document = pilot
    document['landmarks'][0]['verification_status'] = 'analyst_approved'
    with pytest.raises(ValueError, match='acceptance'):
        validate_landmarks(document)
    document['landmarks'][0]['verification_status'] = 'source_corroborated'
    document['landmarks'][0]['sources'][0].pop('source_date')
    with pytest.raises(ValueError, match='source_date'):
        validate_landmarks(document)


def test_narrowing_preserves_full_corridor_and_never_claims_full_sheet(pilot):
    run, landmarks = pilot
    original = deepcopy(run); original_landmarks = deepcopy(landmarks)
    narrowed = narrow_corridors(run, landmarks)
    d = narrowed['drawings'][0]; c = d['narrowed_candidates'][0]
    assert run == original and landmarks == original_landmarks
    assert d['candidates'] == original['drawings'][0]['candidates']
    assert c['line_part_indexes_in_parent'] == [1]
    assert c['coverage']['retained_linework_fraction'] == pytest.approx(.5, abs=.001)
    assert c['qualified'] is False and c['positional_accuracy_m'] is None
    assert c['coverage']['geometry']['coordinates'] == d['candidates'][0]['coverage']['geometry']['coordinates'][1:2]
    assert c['analyst_review_status'] == 'pending' and d['geographic_resolution']['drawing_footprint_verified'] is False


def test_duplicate_units_and_repeated_labels_do_not_inflate_landmark_score(pilot):
    run, landmarks = pilot
    first = narrow_corridors(run, landmarks)['drawings'][0]['narrowed_candidates'][0]
    duplicate = deepcopy(run['drawings'][0]['accepted_clues'][1]); duplicate['clue_id'] = 'duplicate'
    run['drawings'][0]['accepted_clues'].append(duplicate)
    point = deepcopy(landmarks['landmarks'][0]['reference_points'][0]); point['point_id'] = 'another-unit'
    landmarks['landmarks'][0]['reference_points'].append(point)
    second = narrow_corridors(run, landmarks)['drawings'][0]['narrowed_candidates'][0]
    assert second['score'] == first['score'] and second['landmark_count'] == 1
    assert len(second['landmark_relations']) == 2


def test_conflicting_and_ambiguous_landmarks_abstain(pilot):
    run, landmarks = pilot
    far = reference('far', 'OTHER FACILITY', [-78.4, 34.4]); landmarks['landmarks'].append(far)
    clue = deepcopy(run['drawings'][0]['accepted_clues'][1]); clue.update(clue_id='far', text='OTHER FACILITY')
    run['drawings'][0]['accepted_clues'].append(clue)
    d = narrow_corridors(run, landmarks)['drawings'][0]
    assert not d['narrowed_candidates'] and d['landmark_assessment']['corridor_relationships'][0]['conflicts']
    landmarks['landmarks'][1] = reference('duplicate-name')
    d = narrow_corridors(run, landmarks)['drawings'][0]
    assert not d['narrowed_candidates'] and d['landmark_assessment']['conflicts']


def test_near_corridor_but_dispersed_anchors_are_conflicting(pilot):
    run, landmarks = pilot
    row = landmarks['landmarks'][0]
    row['reference_points'][0]['geometry']['coordinates'] = [-78.209, 34.0501]
    other = deepcopy(row['reference_points'][0]); other['point_id'] = 'second'; other['geometry']['coordinates'] = [-78.191, 34.0501]
    row['reference_points'].append(other)
    d = narrow_corridors(run, landmarks, settings={'maximum_anchor_spread_m': 1000})['drawings'][0]
    assert not d['narrowed_candidates']
    assert any('dispersed' in c['reason'] for c in d['landmark_assessment']['corridor_relationships'][0]['conflicts'])


def test_missing_reference_and_ai_clues_do_not_get_promoted(pilot):
    run, landmarks = pilot
    landmarks['landmarks'][0].update(geometry=None, address='Unresolved address', reference_points=[])
    d = narrow_corridors(run, landmarks)['drawings'][0]
    assert not d['narrowed_candidates'] and 'no coordinates invented' in d['landmark_assessment']['missing'][0]['reason']
    run['drawings'][0]['accepted_clues'][1]['reviewer_type'] = 'ai'
    assert not narrow_corridors(run, landmarks)['drawings'][0]['landmark_assessment']['matches']


def test_nearest_ties_retained_and_no_forced_reduction(pilot):
    run, landmarks = pilot
    landmarks['landmarks'][0]['reference_points'][0]['geometry']['coordinates'] = [-78.205, 34.05]
    c = narrow_corridors(run, landmarks)['drawings'][0]['narrowed_candidates'][0]
    assert c['line_part_indexes_in_parent'] == [0, 1]
    parent = run['drawings'][0]['candidates'][0]
    parent['coverage']['geometry']['coordinates'] = [parent['coverage']['geometry']['coordinates'][1]]
    parent['coverage']['reference_length_m'] /= 2
    assert not narrow_corridors(run, landmarks)['drawings'][0]['narrowed_candidates']


def test_search_thresholds_are_validated(pilot):
    for settings in [{'maximum_landmark_offset_m': 0}, {'unknown': 4}, {'nearest_tie_m': True}]:
        with pytest.raises(ValueError):
            narrow_corridors(*pilot, settings=settings)


@pytest.fixture
def supplemental_files(tmp_path):
    address = tmp_path / 'addresses.geojson'; parcel = tmp_path / 'parcels.geojson'
    rows = []
    for key, number, street, xy in [('one', '4711', 'TEST RD', [-78.2, 34.0502]), ('two', '4711', 'TEST RD', [-78.1998, 34.0503]), ('wrong', '4711', 'OTHER RD', [-78.21, 34.05])]:
        rows.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': xy},
                     'properties': {'GlobalID': key, 'ST_NUMB': number, 'ST_NAME': street, 'UNIT_NO': key}})
    write_json(address, {'type': 'FeatureCollection', 'features': rows})
    geometry = {'type': 'Polygon', 'coordinates': [[[-78.201, 34.05], [-78.199, 34.05], [-78.199, 34.051], [-78.201, 34.051], [-78.201, 34.05]]]}
    write_json(parcel, {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {'GlobalID': 'parcel-one'}, 'geometry': geometry},
                                                               {'type': 'Feature', 'properties': {'GlobalID': 'bad'}, 'geometry': None}]})
    row = reference(); row.update(geometry=None, address='4711 TEST RD', address_query={'ST_NUMB': '4711', 'ST_NAME': 'TEST RD'})
    row.pop('reference_points'); row.pop('parcels')
    config = {'schema_version': 1, 'crs': 'EPSG:4326', 'landmarks': [row], 'county_sources': {
        k: {'path': p.name, 'sha256': file_sha256(p), 'crs': 'EPSG:4326', 'crs_confirmation': 'Synthetic fixture declaration'}
        for k, p in [('addresses', address), ('parcels', parcel)]}}
    path = tmp_path / 'config.json'; write_json(path, config)
    return path, address, parcel


def test_supplemental_import_keeps_multiple_units_parcels_hashes_and_sources(tmp_path, supplemental_files):
    config, address, parcel = supplemental_files
    before = {p: p.read_bytes() for p in supplemental_files}
    result = import_landmarks(config, tmp_path / 'out')
    row = result['landmarks'][0]
    assert row['geometry'] is None and row['coordinate_status'] == 'multiple_address_points'
    assert len(row['reference_points']) == 2 and len(row['parcels']) == 1
    assert row['parcels'][0]['contains_point_ids'] == ['cemetery:one', 'cemetery:two']
    assert result['processing']['parcels']['uncomputable_bounds'] == 1
    assert all(p.read_bytes() == b for p, b in before.items())
    assert all(p['source_sha256'] == file_sha256(address) for p in row['reference_points'])
    with pytest.raises(FileExistsError):
        import_landmarks(config, tmp_path / 'out')


def test_changed_source_hash_and_unconfirmed_crs_rejected_before_output(tmp_path, supplemental_files):
    config, address, _ = supplemental_files
    original = config.read_bytes()
    document = read_json(config); document['county_sources']['addresses']['crs_confirmation'] = None
    write_json(config, document)
    with pytest.raises(ValueError, match='confirmed'):
        import_landmarks(config, tmp_path / 'bad-crs')
    assert not (tmp_path / 'bad-crs').exists()
    config.write_bytes(original); address.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA-256'):
        import_landmarks(config, tmp_path / 'stale')
    assert not (tmp_path / 'stale').exists()


def test_missing_county_address_produces_no_invented_coordinate(tmp_path, supplemental_files):
    config, _, _ = supplemental_files
    d = read_json(config); d['landmarks'][0]['address_query']['ST_NUMB'] = '9999'; write_json(config, d)
    result = import_landmarks(config, tmp_path / 'out')
    assert result['landmarks'][0]['coordinate_status'] == 'address_unresolved'
    assert result['landmarks'][0]['reference_points'] == []


def test_station_continuity_reciprocal_matchlines_and_missing_observations(pilot):
    run, _ = pilot
    first = run['drawings'][0]; second = deepcopy(first)
    second.update(drawing_id='second:1', document_sha256='b' * 64, sheet_numbers=['C8'])
    for c in second['accepted_clues']:
        c['clue_id'] += '-second'
        if c['kind'] == 'station_range': c['text'] = 'STA. 78+75 TO STA. 90+25'
    run['drawings'].append(second)
    relation = sheet_relationships(run['drawings'])[0]
    assert relation['continuous'] and relation['shared_station'] == 7875
    assert not relation['reciprocal_matchlines_observed'] and relation['geographic_endpoints'] is None
    observations = {'observations': [{'document_sha256': d['document_sha256'], 'page_number': 1,
                                    'matchlines': [{'neighbor_sheet': other, 'station_value': None}]} for d, other in [(first, 'C8'), (second, 'C7')]]}
    relation = sheet_relationships(run['drawings'], observations)[0]
    assert relation['interpretation'] == 'source_inspection_supports_consecutive_alignment_sections'
    assert relation['predecessor_drawing_id'] == first['drawing_id'] and relation['score_points'] == 0
    # Equal station numbers on unrelated projects cannot establish this relation.
    second['accepted_clues'][-1]['text'] = 'UNRELATED PROJECT'
    assert sheet_relationships(run['drawings'], observations)[0]['interpretation'] == 'station_continuity_hypothesis'
    next(c for c in second['accepted_clues'] if c['kind'] == 'station_range')['text'] = 'STA. 80+00 TO STA. 90+25'
    assert not sheet_relationships(run['drawings'], observations)[0]['continuous']


@pytest.mark.parametrize('text', ['STA. 90+25 TO STA. 78+75', 'STA 78+75', 'STA 78+175 TO STA 90+25', '78+75 TO 90+25'])
def test_unsupported_station_conventions_not_guessed(text):
    assert station_range(text) is None


def test_frozen_outputs_offline_html_and_pending_independent_review(tmp_path, pilot):
    run, landmarks = pilot
    parent = tmp_path / 'parent.json'; refs = tmp_path / 'landmarks.json'
    write_json(parent, run); write_json(refs, landmarks)
    before = parent.read_bytes()
    assert main(['corridor-narrow', str(parent), '--landmarks', str(refs), '--output', str(tmp_path / 'out')]) == 0
    assert parent.read_bytes() == before and (tmp_path / 'out/parent-localization-input.json').read_bytes() == before
    with (tmp_path / 'out/candidates.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert {r['record_group'] for r in rows} == {'candidates', 'narrowed_candidates'}
    assert all(r['candidate_details_reference'].startswith('localization.json#/drawings/') for r in rows)
    html = (tmp_path / 'out/REVIEW.html').read_text(encoding='utf-8')
    assert 'Landmark provenance' in html and 'landmark_corridor_section' in html and 'Drawing footprint is not established' in html
    assert not re.search(r'(?:src|href)=["\']https?://', html)
    for svg in re.findall('<svg.*?</svg>', html, re.S): ET.fromstring(svg)
    evaluation = evaluate_localization(tmp_path / 'out/localization.json', tmp_path / 'out/evaluation-template.json', tmp_path / 'eval')
    assert evaluation['summary']['top_k_recall']['1'] is None
    assert evaluation['summary']['pending_drawings'] == 1 and evaluation['generated_results']['candidate_count'] == 2


def test_model_inputs_and_review_localities_are_not_geographic_ground_truth(tmp_path, pilot):
    run, refs = pilot
    narrowed = narrow_corridors(run, refs); path = tmp_path / 'run.json'; write_json(path, narrowed)
    review = evaluation_template(narrowed, path); r = review['reviews'][0]
    r.update(reviewer='Synthetic human', reviewer_type='human', independent_review=True, reviewed_at='2026-10-19T00:00:00Z',
             reason='Fabricated separate review', truth_status='localizable', complete_candidate_review=True, evaluation_scope='corridor_recovery',
             correct_locations=[{'kind': 'control_point', 'geometry': refs['landmarks'][0]['geometry'], 'crs': 'EPSG:4326',
                                 'accuracy_m': 20, 'independently_determined': True, 'source': 'Copied model input'}])
    for d in r['candidate_decisions']: d['decision'] = 'correct'
    rp = tmp_path / 'review.json'; write_json(rp, review)
    with pytest.raises(ValueError, match='model input'):
        evaluate_localization(path, rp, tmp_path / 'bad')
    r['correct_locations'][0]['geometry'] = {'type': 'Point', 'coordinates': [-78.201, 34.051]}
    r['evaluation_scope'] = 'geographic_localization'
    r['candidate_decisions'][0]['decision'] = 'false_match'; write_json(rp, review)
    with pytest.raises(ValueError, match='corridor hit'):
        evaluate_localization(path, rp, tmp_path / 'bad2')
    r['evaluation_scope'] = 'corridor_recovery'; write_json(rp, review)
    result = evaluate_localization(path, rp, tmp_path / 'valid')
    assert result['corridor_recovery']['correct_corridor_in_candidates'] == 1
    assert result['summary']['candidate_recall'] is None


def test_source_observation_cannot_silently_become_human_acceptance(tmp_path, pilot):
    run, landmarks = pilot
    parent = tmp_path / 'parent.json'; refs = tmp_path / 'refs.json'; observations = tmp_path / 'obs.json'
    write_json(parent, run); write_json(refs, landmarks)
    write_json(observations, {'observations': [{'document_sha256': run['drawings'][0]['document_sha256'], 'page_number': 1,
                                              'reviewer_type': 'human', 'verification_status': 'verified'}]})
    with pytest.raises(ValueError, match='pending AI'):
        run_narrowing(parent, refs, tmp_path / 'bad', observations_path=observations)
    assert not (tmp_path / 'bad').exists()


def test_road_lineage_needs_exact_coordinates_id_and_snapshot(tmp_path, pilot):
    run, landmarks = pilot
    result = narrow_corridors(run, landmarks)
    parent = result['drawings'][0]['candidates'][0]
    road = next(d for d in result['reference_datasets'] if d['kind'] == 'roads')
    path = tmp_path / 'roads.geojson'
    geometry = result['drawings'][0]['narrowed_candidates'][0]['coverage']['geometry']
    write_json(path, {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': geometry, 'properties': {road['fields']['id']: parent['supporting_features'][0]['native_id']}}]})
    road.update(path=str(path), sha256=file_sha256(path))
    attach_source_lineage(result)
    c = result['drawings'][0]['narrowed_candidates'][0]
    assert c['source_lineage_status'] == 'resolved' and len(c['source_lineage']) == 1
    assert c['source_lineage'][0]['parent_line_part_index'] == 1
    path.write_text('{}', encoding='utf-8')
    attach_source_lineage(result)
    assert c['source_lineage'] == [] and result['source_lineage_issues']


def test_ai_station_ranges_cannot_supply_continuity(pilot):
    run, _ = pilot
    second = deepcopy(run['drawings'][0]); second['drawing_id'] = 'second'
    for c in second['accepted_clues']:
        if c['kind'] == 'station_range':
            c.update(text='STA. 78+75 TO STA. 90+25', reviewer_type='ai')
    assert sheet_relationships([run['drawings'][0], second]) == []


def test_mixed_parent_candidates_survive_narrowing_report(tmp_path, pilot):
    run, landmarks = pilot
    area = deepcopy(run['drawings'][0]['candidates'][0])
    area.update(candidate_id='synthetic-existing-area', match_type='reference_area', localization_level='candidate_area')
    area.pop('coverage'); area.pop('corridor_key')
    run['drawings'][0]['candidates'].append(area)
    parent, refs = tmp_path / 'parent.json', tmp_path / 'refs.json'
    write_json(parent, run); write_json(refs, landmarks)
    result = run_narrowing(parent, refs, tmp_path / 'out')
    assert result['drawings'][0]['candidates'] == run['drawings'][0]['candidates']
    with (tmp_path / 'out/candidates.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert len(list(csv.DictReader(stream))) == 3
