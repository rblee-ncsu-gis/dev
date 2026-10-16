from copy import deepcopy
import json
from pathlib import Path

import pytest

from asbuilt_matcher.geo_reference import import_references, load_references, read_catalog, read_json
from asbuilt_matcher.geo_geometry import (contains, geometry_distance, point_distance, road_intersections,
                                         validate_geometry)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/phase2b"


def config_with(tmp_path, data, *, fields=None, crs="EPSG:4326"):
    source = tmp_path / "roads.geojson"
    source.write_text(json.dumps(data), encoding="utf-8")
    config = {"crs": crs, "datasets": [{"id": "roads", "kind": "roads", "path": "roads.geojson",
               "fields": fields or {"id": "ROAD_GUID", "name": ["NAME_TEXT", "SUFFIX"], "aliases": ["ALT_NAMES"]},
               "metadata": {"authority": "Synthetic test", "source_layer": "test", "synthetic": True}}]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_import_preserves_native_identity_mapping_geometry_and_hashes(tmp_path):
    source_hashes = {p.name: p.read_bytes() for p in EXAMPLE.iterdir() if p.is_file()}
    result = import_references(EXAMPLE / "reference-config.json", tmp_path / "out")
    assert result["status"] == "complete" and len(result["features"]) == 8
    road = result["features"][0]
    assert road["native_id"] == "A-PINE" and road["values"]["name"] == "SYNTHETIC PINE ROAD"
    assert road["aliases"] == ["SYNTHETIC PINE RD"]
    assert road["properties"]["ROAD_GUID"] == "A-PINE"
    assert road["geojson_id"] == "road-a1"
    assert read_catalog(tmp_path / "out/references.json")["crs"] == "EPSG:4326"
    assert (tmp_path / "out/import.log").exists()
    assert source_hashes == {p.name: p.read_bytes() for p in EXAMPLE.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):
        import_references(EXAMPLE / "reference-config.json", tmp_path / "out")


@pytest.mark.parametrize("crs", ["EPSG:2264", None, "EPSG:3857"])
def test_explicit_crs_required_and_no_implicit_reprojection(tmp_path, crs):
    path = config_with(tmp_path, read_json(EXAMPLE / "roads.geojson"), crs=crs)
    with pytest.raises(ValueError, match="EPSG:4326"):
        load_references(path)


def test_conflicting_legacy_crs_rejected(tmp_path):
    data = read_json(EXAMPLE / "roads.geojson")
    data["crs"] = {"type": "name", "properties": {"name": "EPSG:2264"}}
    with pytest.raises(ValueError, match="CRS"):
        load_references(config_with(tmp_path, data))


def test_mixed_crs_and_invalid_aoi_configuration_are_not_silently_used(tmp_path):
    path = config_with(tmp_path, read_json(EXAMPLE/"roads.geojson"))
    data = read_json(path)
    data["datasets"][0]["crs"] = "EPSG:2264"
    path.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(ValueError,match="Mixed dataset CRS"):
        load_references(path)
    data["datasets"][0].pop("crs")
    data["area_of_interest_bbox"] = [34,-78,33,-79]
    path.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(ValueError,match="area_of_interest_bbox"):
        load_references(path)


def test_missing_fields_invalid_coordinates_and_duplicate_ids(tmp_path):
    data = read_json(EXAMPLE / "roads.geojson")
    data["features"][0]["properties"].pop("SUFFIX")
    data["features"][1]["geometry"]["coordinates"][0] = [2300000, 150000]
    result = load_references(config_with(tmp_path, data))
    assert result["status"] == "partial" and len(result["errors"]) == 2
    assert len(result["features"]) == 2
    data["features"] = [deepcopy(data["features"][2])] * 2
    with pytest.raises(RuntimeError, match="Duplicate native ID"):
        load_references(config_with(tmp_path, data))


def test_multi_geometries_and_holes_do_not_use_bbox_overlap():
    polygon = {"type": "Polygon", "coordinates": [
        [[-78.3,34],[-78.1,34],[-78.1,34.2],[-78.3,34.2],[-78.3,34]],
        [[-78.22,34.08],[-78.18,34.08],[-78.18,34.12],[-78.22,34.12],[-78.22,34.08]]]}
    assert contains(polygon, [-78.25,34.1])
    assert not contains(polygon, [-78.2,34.1])
    assert point_distance([-78.2,34.1], polygon, [-78.2,34.1]) > 1000
    line = {"type":"MultiLineString", "coordinates":[[[-78.21,34.1],[-78.19,34.1]]]}
    assert geometry_distance(polygon, line, [-78.2,34.1]) > 500
    multipolygon = {"type":"MultiPolygon", "coordinates":[polygon["coordinates"]]}
    validate_geometry(multipolygon, {"MultiPolygon"})
    assert contains(multipolygon, [-78.25,34.1])


def test_intersections_endpoints_parallel_and_collinear():
    line = lambda coords: {"type":"LineString", "coordinates":coords}
    origin = [-78.2,34.05]
    a = line([[-78.21,34.05],[-78.2,34.05]])
    b = line([[-78.2,34.04],[-78.2,34.06]])
    assert road_intersections(a,b,origin)[0] == pytest.approx([-78.2,34.05])
    assert not road_intersections(a,line([[-78.21,34.06],[-78.2,34.06]]),origin)
    assert not road_intersections(a,a,origin)


@pytest.mark.parametrize("coords", [[], [[0,0]], [[0,0],[True,1]], [[0,0],[float('nan'),1]], [[0,0],[0,90]]])
def test_invalid_geometry_rejected(coords):
    with pytest.raises(ValueError):
        validate_geometry({"type":"LineString","coordinates":coords}, {"LineString"})
