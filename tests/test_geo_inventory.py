from copy import deepcopy
import json
from pathlib import Path

import pytest

from asbuilt_matcher.geo_inventory import inspect_dataset, validate_county
from asbuilt_matcher.geo_reference import import_references, read_json
from asbuilt_matcher.geo_stream import collection_events
from asbuilt_matcher.pdf_extract import file_sha256


def export(path, *, crs=True, features=None):
    data={"type":"FeatureCollection","features":features if features is not None else [
        {"type":"Feature","properties":{"GlobalID":"stable-1","FullName":"Pine Road","Optional":None},"geometry":{"type":"LineString","coordinates":[[-78.2,34],[-78.19,34]]}},
        {"type":"Feature","properties":{"GlobalID":"stable-2","FullName":"Oak Lane","Blank":""},"geometry":{"type":"MultiLineString","coordinates":[[[-78.2,34],[-78.2,34.01]]]}}]}
    if crs:
        data["crs"]={"type":"name","properties":{"name":"urn:ogc:def:crs:EPSG::4326"}}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data),encoding="utf-8")
    return path


def confirmed(path):
    return {"dataset_sha256":file_sha256(path),"status":"confirmed","reviewer_type":"human","reviewer":"Synthetic reviewer",
            "reviewed_at":"2026-10-19T12:00:00Z","reason":"Synthetic mapping test", "fields":{"id":"GlobalID","name":"FullName"}}


def test_metadata_actual_fields_quality_crs_and_no_invented_source(tmp_path):
    path=export(tmp_path/"roads.geojson")
    before=path.read_bytes()
    result=inspect_dataset(path,"roads")
    assert result["feature_count"]==2
    assert result["geometry_types"]=={"LineString":1,"MultiLineString":1}
    assert result["field_profiles"]["Optional"]["null_count"]==1
    assert result["field_profiles"]["Optional"]["missing_count"]==1
    assert result["field_profiles"]["Blank"]["blank_count"]==1
    assert result["coordinate_system"]["confirmation_basis"]=="explicit_file_declaration"
    assert result["source_metadata"]==dict.fromkeys(["source_feature_class","source_crs","database_version","exported_at","data_owner"])
    assert not result["ready_for_import"] and result["mapping_review"]["status"]=="pending"
    assert path.read_bytes()==before


def test_ranges_alone_never_confirm_crs_and_attestation_is_hash_bound(tmp_path):
    path=export(tmp_path/"roads.geojson",crs=False)
    result=inspect_dataset(path,"roads",decision=confirmed(path))
    assert result["coordinate_system"]["coordinate_ranges_compatible"]
    assert result["coordinate_system"]["confirmed_output_crs"] is None
    decision={**confirmed(path),"crs_confirmed":True,"output_crs":"EPSG:4326"}
    assert inspect_dataset(path,"roads",decision=decision)["ready_for_import"]
    decision["dataset_sha256"]="stale"
    assert not inspect_dataset(path,"roads",decision=decision)["ready_for_import"]


def test_confirmed_mapping_rejects_absent_field_and_nonhuman(tmp_path):
    path=export(tmp_path/"roads.geojson")
    decision=confirmed(path); decision["fields"]["name"]="NO_SUCH_FIELD"
    result=inspect_dataset(path,"roads",decision=decision)
    assert result["error_count"] and not result["ready_for_import"]
    decision=confirmed(path); decision["reviewer_type"]="ai"
    assert not inspect_dataset(path,"roads",decision=decision)["ready_for_import"]


def test_incremental_manifest_history_hash_schema_count_changes_and_missing(tmp_path):
    directory=tmp_path/"data"
    export(directory/"roads.geojson")
    a=validate_county(directory,tmp_path/"first")
    assert len(a["missing_datasets"])==6 and a["status"]=="needs_review"
    old=(directory/"export_metadata.json").read_bytes()
    data=read_json(directory/"roads.geojson")
    data["features"].append(deepcopy(data["features"][0]))
    data["features"][0]["properties"]["NEW_FIELD"]=1
    (directory/"roads.geojson").write_text(json.dumps(data),encoding="utf-8")
    b=validate_county(directory,tmp_path/"second")
    assert {"sha256","feature_count","available_fields"} <= set(b["changes"][0]["changes"])
    assert Path(b["previous_manifest"]["path"]).read_bytes()==old
    with pytest.raises(FileExistsError): validate_county(directory,tmp_path/"second")
    (directory/"roads.geojson").unlink()
    c=validate_county(directory,tmp_path/"third")
    assert c["status"]=="awaiting_reference_data" and len(c["missing_datasets"])==7
    assert c["changes"][0]["changes"]==["dataset_removed"]


def test_separate_source_location_and_confirmed_config_import(tmp_path):
    source=tmp_path/"legacy"; path=export(source/"roads.geojson")
    decisions=tmp_path/"decisions.json"
    decision=confirmed(path)
    decision["source_metadata"]={"source_feature_class":"Synthetic.roads","source_crs":"EPSG:2264","database_version":"SyntheticVersion","exported_at":"2026-10-19T00:00:00Z","data_owner":"Synthetic owner"}
    decisions.write_text(json.dumps({"datasets":{"roads":decision}}),encoding="utf-8")
    result=validate_county(tmp_path/"data",tmp_path/"validated",source_directory=source,decisions_path=decisions)
    assert result["ready_datasets"]==["roads"]
    assert not (tmp_path/"data/roads.geojson").exists()
    catalog=import_references(tmp_path/"validated/reference-config.confirmed.json",tmp_path/"imported")
    assert len(catalog["features"])==2
    assert catalog["datasets"][0]["metadata"]["database_version"]=="SyntheticVersion"
    export(path,features=[])
    with pytest.raises(ValueError,match="hash-bound"):
        import_references(tmp_path/"validated/reference-config.confirmed.json",tmp_path/"stale")


def test_bad_geometry_and_incompatible_crs_are_errors(tmp_path):
    path=export(tmp_path/"roads.geojson")
    data=read_json(path)
    data["features"][0]["geometry"]=None
    data["features"][1]["geometry"]={"type":"Point","coordinates":[2300000,150000]}
    data["crs"]["properties"]["name"]="EPSG:2264"
    path.write_text(json.dumps(data),encoding="utf-8")
    r=inspect_dataset(path,"roads")
    assert r["error_count"]>=3 and r["invalid_geometry_count"]==2
    assert not r["coordinate_system"]["confirmed_output_crs"]


def test_point_validation_and_mixed_geometry_count(tmp_path):
    path=export(tmp_path/"addresses.geojson",features=[
        {"type":"Feature","properties":{"ID":"a","Address":"12 Pine Rd"},"geometry":{"type":"Point","coordinates":[-78.2,34]}},
        {"type":"Feature","properties":{"ID":"b","Address":"14 Pine Rd"},"geometry":{"type":"MultiPoint","coordinates":[[-78.2,34],[-78.21,34]]}}])
    r=inspect_dataset(path,"addresses")
    assert r["geometry_types"]=={"Point":1,"MultiPoint":1} and not r["errors"]


def test_crs_attestation_survives_empty_geometry_and_duplicate_ids_are_flagged(tmp_path):
    path=export(tmp_path/'roads.geojson',crs=False)
    data=read_json(path)
    data['features'][0]['geometry']['coordinates']=[]
    data['features'][1]['properties']['GlobalID']='stable-1'
    path.write_text(json.dumps(data),encoding='utf-8')
    decision={**confirmed(path),'crs_confirmed':True,'output_crs':'EPSG:4326'}
    result=inspect_dataset(path,'roads',decision=decision)
    assert result['coordinate_system']['confirmed_output_crs']=='EPSG:4326'
    assert result['field_profiles']['GlobalID']['duplicate_nonblank_count']==1
    assert result['status']=='invalid' and not result['ready_for_import']


def test_approved_mapping_cannot_be_reassigned_or_promoted_by_ai(tmp_path):
    directory=tmp_path/'data';path=export(directory/'roads.geojson')
    decision_path=tmp_path/'decisions.json'
    decision_path.write_text(json.dumps({'datasets':{'roads':confirmed(path)}}),encoding='utf-8')
    validate_county(directory,tmp_path/'validated',decisions_path=decision_path)
    cfg=read_json(tmp_path/'validated/reference-config.confirmed.json')
    cfg['datasets'][0]['fields']['name']='GlobalID'
    tampered=tmp_path/'tampered.json';tampered.write_text(json.dumps(cfg),encoding='utf-8')
    with pytest.raises(ValueError,match='hash-bound'):
        import_references(tampered,tmp_path/'bad')
    cfg['datasets'][0]['fields']['name']='FullName'
    cfg['datasets'][0]['mapping_review']['reviewer_type']='ai'
    tampered.write_text(json.dumps(cfg),encoding='utf-8')
    with pytest.raises(ValueError,match='hash-bound'):
        import_references(tampered,tmp_path/'ai')


def test_stream_spans_chunks_unicode_and_headers_after_features(tmp_path):
    path=export(tmp_path/"roads.geojson")
    data=read_json(path)
    data["features"][0]["properties"]["Long"]="é"*70000
    path.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8-sig")
    events=list(collection_events(path))
    assert [v for k,v in events if k=="feature"]==data["features"]
    assert dict(v for k,v in events if k=="header")["crs"]==data["crs"]


@pytest.mark.parametrize("raw", ['{}','{"type":"FeatureCollection","features":[],}',
    '{"type":"FeatureCollection","features":[{},]}','{"type":"FeatureCollection","features":[]} trailing',
    '{"type":"FeatureCollection","features":[],"features":[]}','{"type":"FeatureCollection","features":{}}'])
def test_bad_stream_rejected(tmp_path,raw):
    path=tmp_path/"bad.geojson"; path.write_text(raw,encoding="utf-8")
    with pytest.raises(ValueError): list(collection_events(path))
