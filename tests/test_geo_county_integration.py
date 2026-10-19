from copy import deepcopy
import json
from pathlib import Path

import pytest

from asbuilt_matcher.geo_geometry import geometry_distance, point_distance, project, unproject
from asbuilt_matcher.geo_reference import import_references, read_json
from asbuilt_matcher.geolocate import locate_documents
from asbuilt_matcher.geo_report import localize

EXAMPLE=Path(__file__).resolve().parents[1]/'examples/phase2b'


def accepted(kind,text,clue_id):
    row=read_json(EXAMPLE/'accepted-clues.json')['clues'][0]
    row.update(kind=kind,text=text,original_text=text,clue_id=clue_id)
    return row


def seven_config(tmp_path):
    config=read_json(EXAMPLE/'reference-config.json')
    for d in config['datasets']:
        d['path']=str((EXAMPLE/d['path']).resolve())
    polygon={'type':'Polygon','coordinates':[[[-78.21,34.04],[-78.19,34.04],[-78.19,34.06],[-78.21,34.06],[-78.21,34.04]]]}
    for kind,label in [('addresses','12 NORTH PINE ROAD'),('town_limits','TEST TOWN'),('townships','TEST TOWNSHIP'),('postal_zones','28400')]:
        fields={'id':'source_id','name':'label'}
        geometry=polygon
        props={'source_id':kind+'-1','label':label}
        if kind=='addresses':
            fields={'id':'source_id','address_number':'num','prefix_direction':'dir','street_name':'base','street_suffix':'type'}
            props={'source_id':kind+'-1','num':'12','dir':'NORTH','base':'PINE','type':'ROAD'}
            geometry={'type':'Point','coordinates':[-78.2,34.05]}
        path=tmp_path/(kind+'.geojson')
        path.write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':props,'geometry':geometry}]}),encoding='utf-8')
        config['datasets'].append({'id':kind,'kind':kind,'path':str(path),'fields':fields,'metadata':{'authority':'Synthetic fixture','source_layer':kind,'synthetic':True}})
    path=tmp_path/'config.json'; path.write_text(json.dumps(config),encoding='utf-8')
    return path


def test_all_seven_layers_import_components_and_context_support(tmp_path):
    catalog=import_references(seven_config(tmp_path),tmp_path/'refs')
    assert len(catalog['datasets'])==7 and not catalog['errors']
    address=next(f for f in catalog['features'] if f['kind']=='addresses')
    assert address['values']['address']=='12 NORTH PINE ROAD'
    assert address['properties']['num']=='12'
    clues={'clues':[accepted('address','12 N Pine Rd','a'),accepted('municipal_name','TEST TOWN','m'),accepted('township_name','TEST TOWNSHIP','t'),accepted('postal_zone','28400','z')]}
    result=locate_documents(clues,catalog)
    best=result['drawings'][0]['candidates'][0]
    assert result['drawings'][0]['status']=='proposed_area'
    assert {e['kind'] for e in best['evidence']}=={'address','municipal_name','township_name','postal_zone'}
    assert len(best['spatial_context'])==3
    assert best['analyst_review_status']=='pending'
    output=localize(EXAMPLE/'accepted-clues.json',tmp_path/'run',references_path=tmp_path/'refs/references.json')
    assert output['distance_model']['units']=='metres'


def test_context_cannot_create_location_or_qualify_single_street(tmp_path):
    catalog=import_references(seven_config(tmp_path),tmp_path/'refs')
    c=accepted('municipal_name','TEST TOWN','m')
    d=locate_documents({'clues':[c]},catalog)['drawings'][0]
    assert not d['candidates'] and d['status']=='insufficient_evidence'
    d=locate_documents({'clues':[c,accepted('street_name','SYNTHETIC PINE ROAD','road')]},catalog)['drawings'][0]
    assert d['status']=='insufficient_evidence'


def test_wrong_address_number_and_conflicting_boundary_not_forced(tmp_path):
    catalog=import_references(seven_config(tmp_path),tmp_path/'refs')
    d=locate_documents({'clues':[accepted('address','13 N PINE RD','a')]},catalog)['drawings'][0]
    assert not d['candidates']
    d=locate_documents({'clues':[accepted('address','12 NORTH PINE ROAD','a'),accepted('postal_zone','99999','z')]},catalog)['drawings'][0]
    assert d['status']=='ambiguous' and d['candidates'][0]['missing']


def test_missing_files_are_incremental_not_processing_errors(tmp_path):
    path=seven_config(tmp_path)
    (tmp_path/'addresses.geojson').unlink()
    result=import_references(path,tmp_path/'refs')
    assert result['status']=='complete' and not result['errors']
    assert result['missing_datasets'][0]['id']=='addresses'


def test_subdivision_phase_stays_explicit(tmp_path):
    catalog=import_references(seven_config(tmp_path),tmp_path/'refs')
    for f in catalog['features']:
        if f['kind']=='subdivisions': f['values']['phase']='2'
    d=locate_documents({'clues':[accepted('subdivision_name','SYNTHETIC ALPHA ESTATES PHASE 2','s'),accepted('street_name','SYNTHETIC PINE ROAD','r')]},catalog)['drawings'][0]
    assert d['candidates'][0]['evidence']
    assert any(e['kind']=='subdivision_name' for e in d['candidates'][0]['evidence'])
    d=locate_documents({'clues':[accepted('subdivision_name','SYNTHETIC ALPHA ESTATES PHASE 3','s')]},catalog)['drawings'][0]
    assert not d['candidates']


@pytest.mark.parametrize('point',[[-78.2,34.05],[-78.65,33.9],[-77.85,34.3]])
def test_ellipsoidal_projected_round_trip_and_point_distance(point):
    origin=[-78.2,34.05]
    assert unproject(project(point,origin),origin)==pytest.approx(point,abs=1e-9)
    geometry={'type':'Point','coordinates':point}
    assert point_distance(point,geometry,origin)==0
    assert geometry_distance(geometry,geometry,origin)==0


def test_projected_metre_scale_against_wgs84_equatorial_arc():
    # At the equator a one-milliradian longitude change has ENU east distance
    # a*sin(.001); this is an analytic ellipsoid check, not an implementation mirror.
    import math
    x,y=project([math.degrees(.001),0],[0,0])
    assert x==pytest.approx(6378.1359369776,abs=1e-5)
    assert y==pytest.approx(0,abs=1e-10)
