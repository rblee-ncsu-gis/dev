from copy import deepcopy
import csv
import json
from pathlib import Path

import pytest

from asbuilt_matcher.geo_aliases import compile_aliases,match_alias
from asbuilt_matcher.geo_reference import load_references,read_json,import_references
from asbuilt_matcher.geolocate import locate_documents
from asbuilt_matcher.geo_corridors import road_components
from asbuilt_matcher.geo_diagnostics import diagnose_roads
from asbuilt_matcher.geo_eval import evaluate_localization
from asbuilt_matcher.geo_report import localize

EXAMPLE=Path(__file__).resolve().parents[1]/'examples/phase2b'


@pytest.fixture
def setup():
    catalog=load_references(EXAMPLE/'reference-config.json')
    for f in catalog['features']:
        if f['kind']=='roads':f['properties']['ROUTE']='211'
    dataset=next(d for d in catalog['datasets'] if d['kind']=='roads')
    registry={'schema_version':1,'entries':[{'id':'synthetic-alias','enabled':True,'status':'source_corroborated',
        'sources':[{'type':'synthetic','evidence':'Fabricated alias fixture, not a real county decision'}],
        'scope':{'dataset_id':dataset['id'],'source_sha256':dataset['sha256'],'feature_ids':['A-PINE','B-PINE'],
                 'field_values':{'ROUTE':['211'],'NAME_TEXT':['SYNTHETIC PINE']}},
        'aliases':[{'text':'NC 211 - SUPPLY ROAD','category':'candidate_relationship'},
                   {'text':'NC 211','category':'route_number'},{'text':'NC HIGHWAY 211','category':'route_number'}]}]}
    clue=deepcopy(read_json(EXAMPLE/'accepted-clues.json')['clues'][0]);clue['text']='NC 211 - SUPPLY ROAD'
    return catalog,registry,clue


def test_scoped_alias_preserves_transcription_source_and_type(setup):
    catalog,registry,clue=setup
    before=deepcopy(clue)
    compiled=compile_aliases(registry,catalog)
    f=next(f for f in catalog['features'] if f['native_id']=='A-PINE')
    m=match_alias(clue['text'],f,compiled)
    assert m['match_type']=='scoped_alias' and m['alias']['analyst_approved'] is False
    assert m['alias']['source_field_values']['ROUTE']=='211'
    assert m['alias']['category']=='candidate_relationship' and m['alias']['sources']
    assert clue==before
    assert match_alias('NC 217',f,compiled) is None
    assert match_alias('SUPPLY',f,compiled) is None
    assert match_alias('SUPPLY ROAD',f,compiled) is None


@pytest.mark.parametrize('label',['SUPPLY','ROAD','SUPPLY ROAD'])
def test_generic_equivalences_rejected(setup,label):
    catalog,registry,_=setup
    registry['entries'][0]['aliases']=[{'text':label,'category':'candidate_relationship'}]
    with pytest.raises(ValueError,match='Generic'):compile_aliases(registry,catalog)


def test_wrong_snapshot_or_field_values_do_not_enable_alias(setup):
    catalog,registry,_=setup
    registry['entries'][0]['scope']['source_sha256']='stale'
    with pytest.raises(ValueError,match='snapshot'):compile_aliases(registry,catalog)
    registry['entries'][0]['scope']['source_sha256']=catalog['datasets'][0]['sha256']
    registry['entries'][0]['scope']['field_values']['ROUTE']=['217']
    with pytest.raises(ValueError,match='constraints'):compile_aliases(registry,catalog)


def test_geographic_scope_is_enforced_without_clipping(setup):
    catalog,registry,_=setup
    registry['entries'][0]['scope']['bbox']=[-78.21,34.04,-78.19,34.06]
    # The other same-named synthetic road is outside this explicit area.
    with pytest.raises(ValueError,match='geographic scope'):compile_aliases(registry,catalog)


def test_disabled_and_missing_ids_and_false_approval(setup):
    catalog,registry,clue=setup
    registry['entries'][0]['enabled']=False
    assert not compile_aliases(registry,catalog)['entries']
    registry['entries'][0]['enabled']=True
    registry['entries'][0]['scope']['feature_ids'].append('MISSING')
    with pytest.raises(ValueError,match='missing'):compile_aliases(registry,catalog)
    registry['entries'][0]['scope']['feature_ids'].pop()
    registry['entries'][0]['status']='analyst_approved'
    with pytest.raises(ValueError,match='human'):compile_aliases(registry,catalog)


def test_disconnected_corridors_preserved_and_no_footprint_claim(setup):
    catalog,registry,clue=setup
    baseline=locate_documents({'clues':[clue]},catalog)
    assert not baseline['drawings'][0]['candidates']
    d=locate_documents({'clues':[clue]},catalog,alias_registry=registry)['drawings'][0]
    assert d['status']=='ambiguous_corridors' and len(d['candidates'])==2
    assert all(c['match_type']=='road_corridor' and not c['qualified'] for c in d['candidates'])
    assert all(c['coverage']['feature_count']==1 and c['coverage']['geometry']['type']=='MultiLineString' for c in d['candidates'])
    assert all(c['analyst_review_status']=='pending' and c['evidence_still_needed'] for c in d['candidates'])
    assert d['geographic_resolution']=={'name_recognized':True,'roadway_or_route_matched':True,'candidate_area_generated':False,'drawing_footprint_verified':False}


def test_single_scoped_corridor_and_multiple_aliases_do_not_inflate(setup):
    catalog,registry,clue=setup
    registry['entries'][0]['scope']['feature_ids']=['A-PINE']
    first=locate_documents({'clues':[clue]},catalog,alias_registry=registry)['drawings'][0]
    assert first['status']=='corridor_identified' and len(first['candidates'])==1
    repeated=deepcopy(clue);repeated.update(clue_id='repeat',text='NC HIGHWAY 211')
    d=locate_documents({'clues':[clue,repeated]},catalog,alias_registry=registry)['drawings'][0]
    assert len(d['candidates'])==1
    assert d['candidates'][0]['score']==first['candidates'][0]['score']
    assert d['candidates'][0]['alternate_label_evidence']


def test_conflicting_subdivision_does_not_force_location(setup):
    catalog,registry,clue=setup
    registry['entries'][0]['scope']['feature_ids']=['A-PINE']
    other=deepcopy(clue);other.update(clue_id='other',kind='subdivision_name',text='SYNTHETIC BETA ESTATES')
    d=locate_documents({'clues':[clue,other]},catalog,alias_registry=registry)['drawings'][0]
    corridor=next(c for c in d['candidates'] if c['match_type']=='road_corridor')
    assert corridor['conflicts'] and not corridor['qualified']
    assert d['status']!='proposed_area'


def test_endpoint_grouping_preserves_gaps_and_grade_separation(setup):
    catalog,_,_=setup
    f=deepcopy(next(f for f in catalog['features'] if f['native_id']=='A-PINE'))
    g=deepcopy(f);g['feature_key']='new';g['geometry']['coordinates']=[[-78.195,34.05],[-78.19,34.05]]
    features={f['feature_key']:f,g['feature_key']:g};origin=catalog['distance_origin']
    assert len(road_components(list(features),features,origin,5))==1
    g['values']['level']=1;f['values']['level']=0
    assert len(road_components(list(features),features,origin,5))==2
    g['values']['level']=0;g['geometry']['coordinates'][0]=[-78.194,34.05]
    assert len(road_components(list(features),features,origin,5))==2


def test_diagnostics_preserve_actual_geometries_and_unnamed_routes(tmp_path):
    path=tmp_path/'roads.geojson'
    rows=[{'type':'Feature','properties':{'GlobalID':'one','FULLNAME':'SOUTHPORT-SUPPLY RD SE','STATERDNUM':'211'},
           'geometry':{'type':'LineString','coordinates':[[-78.2,34],[-78.19,34]]}},
          {'type':'Feature','properties':{'GlobalID':'two','FULLNAME':None,'STATERDNUM':'211'},
           'geometry':{'type':'LineString','coordinates':[[-78.1,34],[-78.09,34]]}}]
    path.write_text(json.dumps({'type':'FeatureCollection','features':rows}),encoding='utf-8');before=path.read_bytes()
    result=diagnose_roads(path,tmp_path/'out')
    assert result['route_211_features']==2 and result['unnamed_with_route_identifier']==1
    assert read_json(tmp_path/'out/related-roads.geojson')['features'][0]['geometry']==rows[0]['geometry']
    assert path.read_bytes()==before


def test_csv_is_compact_while_json_retains_large_alias_evidence(tmp_path,setup):
    catalog,registry,clue=setup
    payload='x'*140000
    registry['entries'][0]['sources'][0]['evidence']=payload
    references=tmp_path/'references.json';references.write_text(json.dumps(catalog),encoding='utf-8')
    clues=tmp_path/'clues.json';clues.write_text(json.dumps({'clues':[clue]}),encoding='utf-8')
    aliases=tmp_path/'aliases.json';aliases.write_text(json.dumps(registry),encoding='utf-8')
    run=localize(clues,tmp_path/'run',references_path=references,alias_registry_path=aliases)
    with (tmp_path/'run/candidates.csv').open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    assert len(rows)==2 and all(r['candidate_details_reference'].startswith('localization.json#/') for r in rows)
    assert 'geometry' not in json.loads(rows[0]['coverage'])
    assert run['drawings'][0]['candidates'][0]['evidence'][0]['matches'][0]['alias']['sources'][0]['evidence']==payload


@pytest.mark.parametrize('kind',['area','intersection','control_point','footprint'])
def test_independent_reference_types_and_corridor_metric_guard(tmp_path,setup,kind):
    catalog,registry,clue=setup
    # Persist the synthetic, augmented catalog without changing any fixture file.
    references=tmp_path/'references.json';references.write_text(json.dumps(catalog),encoding='utf-8')
    clues=tmp_path/'clues.json';clues.write_text(json.dumps({'clues':[clue]}),encoding='utf-8')
    aliases=tmp_path/'aliases.json';aliases.write_text(json.dumps(registry),encoding='utf-8')
    run=localize(clues,tmp_path/'run',references_path=references,alias_registry_path=aliases)
    assert (tmp_path/'run/aliases-input.json').read_bytes()==aliases.read_bytes()
    html=(tmp_path/'run/REVIEW.html').read_text(encoding='utf-8')
    assert '<svg' in html and 'road_corridor' in html and 'Drawing footprint is not established' in html
    review=read_json(tmp_path/'run/evaluation-template.json');r=review['reviews'][0]
    point=kind in {'intersection','control_point'}
    geometry={'type':'Point','coordinates':[-78.2,34.05]} if point else {'type':'Polygon','coordinates':[[[-78.21,34.04],[-78.19,34.04],[-78.19,34.06],[-78.21,34.06],[-78.21,34.04]]]}
    r.update(reviewer='Synthetic independent reviewer',reviewer_type='human',independent_review=True,
             reviewed_at='2026-10-19T00:00:00Z',reason='Synthetic independently fixed reference',truth_status='localizable',
             evaluation_scope='geographic_localization',complete_candidate_review=True,
             correct_locations=[{'kind':kind,'geometry':geometry,'crs':'EPSG:4326','source':'Independent synthetic reference',
                                 'independently_determined':True,'accuracy_m':10}])
    for decision in r['candidate_decisions']:decision['decision']='correct'
    path=tmp_path/'review.json';path.write_text(json.dumps(review),encoding='utf-8')
    with pytest.raises(ValueError,match='corridor hit'):
        evaluate_localization(tmp_path/'run/localization.json',path,tmp_path/'bad')
    r['evaluation_scope']='corridor_recovery';path.write_text(json.dumps(review),encoding='utf-8')
    result=evaluate_localization(tmp_path/'run/localization.json',path,tmp_path/'evaluated')
    assert result['summary']['candidate_recall'] is None and result['summary']['top_k_recall']['1'] is None
    assert result['corridor_recovery']['reviewed_drawings']==1
    assert result['corridor_recovery']['correct_corridor_in_candidates']==1
