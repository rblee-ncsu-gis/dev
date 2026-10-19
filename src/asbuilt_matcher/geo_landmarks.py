"""Supplemental, read-only landmark evidence; never drawing ground truth.

Address matches retain every unit and candidate parcel. No address geocoding,
facility centroid calculation, ownership inference or geometry repair occurs.
"""

from datetime import date, datetime, timezone
import logging
import math
from pathlib import Path
import re

from .geo_geometry import bounds, contains, validate_geometry
from .geo_names import normalize_name
from .geo_reference import read_json
from .geo_stream import collection_events
from .pdf_extract import file_sha256, write_json

LOGGER = logging.getLogger(__name__)


def validate_landmarks(document):
    if document.get('schema_version') != 1 or document.get('crs') != 'EPSG:4326':
        raise ValueError('Landmarks require schema_version 1 and explicit EPSG:4326 longitude/latitude')
    rows = document.get('landmarks')
    if not isinstance(rows, list):
        raise ValueError('landmarks must be an array')
    seen = set()
    aoi = document.get('area_of_interest_bbox')
    if aoi is not None and (not isinstance(aoi, list) or len(aoi) != 4
                            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in aoi)
                            or not -180 <= aoi[0] < aoi[2] <= 180 or not -80 <= aoi[1] < aoi[3] <= 80):
        raise ValueError('Landmark area_of_interest_bbox must be a WGS84 extent')
    for row in rows:
        key = row.get('landmark_id')
        if not isinstance(key, str) or not key.strip() or key in seen:
            raise ValueError('Landmark IDs must be unique and nonblank')
        seen.add(key)
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ['name', 'type']):
            raise ValueError('Landmark name and type are required')
        if row.get('verification_status') not in {'unverified', 'source_corroborated'}:
            raise ValueError('Supplemental input status cannot grant analyst acceptance')
        if not isinstance(row.get('aliases', []), list) or any(not isinstance(a, str) or not a.strip() for a in row.get('aliases', [])):
            raise ValueError('Landmark aliases must be explicit nonblank strings')
        if not row.get('sources') or not isinstance(row['sources'], list):
            raise ValueError('Landmark provenance sources are required')
        for source in row['sources']:
            if not isinstance(source, dict) or not source.get('source') or not source.get('accessed_at'):
                raise ValueError('Each source needs source and accessed_at; source_date may be null')
            date.fromisoformat(source['accessed_at'])
            if 'source_date' not in source:
                raise ValueError('Explicit source_date is required (null if unknown)')
            if source['source_date'] is not None:
                date.fromisoformat(source['source_date'])
        accuracy = row.get('positional_accuracy_m')
        if accuracy is not None and (isinstance(accuracy, bool) or not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy) or accuracy <= 0):
            raise ValueError('Known positional accuracy must be positive finite metres; otherwise null')
        if row.get('geometry') is not None:
            validate_geometry(row['geometry'], {'Point'})
        if not row.get('geometry') and not row.get('address'):
            raise ValueError('A landmark needs a published coordinate or address')
        for point in row.get('reference_points', []):
            validate_geometry(point['geometry'], {'Point'})
        point_ids = [p.get('point_id') for p in row.get('reference_points', [])]
        if any(not isinstance(key, str) or not key.strip() for key in point_ids) or len(set(point_ids)) != len(point_ids):
            raise ValueError('Reference point IDs must be unique and nonblank within each landmark')
        coordinates = ([row['geometry']['coordinates']] if row.get('geometry') else []) + [p['geometry']['coordinates'] for p in row.get('reference_points', [])]
        if aoi and any(not (aoi[0] <= p[0] <= aoi[2] and aoi[1] <= p[1] <= aoi[3]) for p in coordinates):
            raise ValueError('Landmark outside configured geographic scope; check coordinate order/CRS')
        for parcel in row.get('parcels', []):
            validate_geometry(parcel['geometry'], {'Polygon', 'MultiPolygon'})
    return document


def match_landmarks(clue, document):
    """Literal normalized labels only; never fuzzy-match a facility into a place."""
    text = normalize_name(clue['text'])
    return [row for row in document['landmarks']
            if row['verification_status'] == 'source_corroborated'
            and text in {normalize_name(s) for s in [row['name'], *row.get('aliases', [])]}]


def _source(config_path, spec):
    if spec.get('crs') != 'EPSG:4326' or spec.get('crs_confirmation') is None:
        raise ValueError('County evidence needs explicit confirmed WGS84 longitude/latitude')
    path = (config_path.parent / spec['path']).resolve()
    digest = file_sha256(path)
    if not re.fullmatch('[a-f0-9]{64}', spec.get('sha256', '')) or digest != spec['sha256']:
        raise ValueError('Supplemental county source SHA-256 mismatch; investigate the new snapshot')
    return path, {**spec, 'path': str(path), 'sha256': digest}


def import_landmarks(config_path, output):
    """Resolve explicit address fields and retain all containing parcel evidence."""
    config_path = Path(config_path).resolve()
    config = validate_landmarks(read_json(config_path))
    sources = {kind: _source(config_path, spec) for kind, spec in config.get('county_sources', {}).items()}
    # Validate inputs before creating the immutable output directory.
    for row in config['landmarks']:
        query = row.get('address_query')
        if query is not None and (not isinstance(query, dict) or not query or 'addresses' not in sources
                                  or any(not isinstance(v, (str, int)) or isinstance(v, bool) for v in query.values())):
            raise ValueError('address_query requires explicit field values and an addresses source')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1, 'crs': 'EPSG:4326', 'created_at': datetime.now(timezone.utc).isoformat(),
              'config': {'path': str(config_path), 'sha256': file_sha256(config_path)},
              'area_of_interest_bbox': config.get('area_of_interest_bbox'),
              'county_sources': {k: v[1] for k, v in sources.items()}, 'landmarks': config['landmarks'],
              'scope': 'Candidate model input only; no independent drawing location acceptance.', 'errors': [], 'processing': {}}
    result['implementation'] = {name: file_sha256(Path(__file__).parent / name) for name in ['geo_landmarks.py', 'geo_geometry.py', 'geo_stream.py']}
    (output / 'config-input.json').write_bytes(config_path.read_bytes())
    points = {}
    for row in result['landmarks']:
        row['reference_points'], row['parcels'] = [], []
        if row.get('geometry'):
            row['reference_points'].append({'point_id': row['landmark_id'] + ':published', 'geometry': row['geometry'],
                                            'basis': 'published coordinate', 'source': row['sources'], 'positional_accuracy_m': row.get('positional_accuracy_m')})
    log = []
    if 'addresses' in sources:
        count = invalid = 0
        path = sources['addresses'][0]
        for event, feature in collection_events(path):
            if event != 'feature':
                continue
            count += 1
            p = feature.get('properties') or {}
            for row in result['landmarks']:
                query = row.get('address_query')
                if not query or not all(str(p.get(k, '')).strip().casefold() == str(v).strip().casefold() for k, v in query.items()):
                    continue
                try:
                    validate_geometry(feature.get('geometry'), {'Point'})
                    if not p.get('GlobalID'):
                        raise ValueError('Address candidate lacks GlobalID')
                except (ValueError, TypeError) as exc:
                    invalid += 1
                    result['errors'].append({'layer': 'addresses', 'native_id': p.get('GlobalID'), 'error': str(exc)})
                    continue
                point = {'point_id': row['landmark_id'] + ':' + str(p['GlobalID']), 'native_id': p['GlobalID'],
                         'geometry': feature['geometry'], 'properties': p, 'basis': 'exact configured county address fields; unit candidates retained',
                         'source_sha256': sources['addresses'][1]['sha256'], 'positional_accuracy_m': None}
                row['reference_points'].append(point)
        result['processing']['addresses'] = {'features_scanned': count, 'invalid_matches': invalid}
        log.append(f'addresses: scanned {count}; invalid matches {invalid}')
    for row in result['landmarks']:
        row['coordinate_status'] = ('published_coordinate' if row.get('geometry') else 'multiple_address_points' if len(row['reference_points']) > 1
                                    else 'single_address_point' if row['reference_points'] else 'address_unresolved')
        for point in row['reference_points']:
            points[point['point_id']] = point['geometry']['coordinates']
    if 'parcels' in sources and points:
        count = bad_bounds = detailed = invalid = 0
        for event, feature in collection_events(sources['parcels'][0]):
            if event != 'feature':
                continue
            count += 1
            try:
                b = bounds(feature['geometry'])
            except (ValueError, TypeError, KeyError, IndexError):
                bad_bounds += 1
                continue
            near = {key: p for key, p in points.items() if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]}
            if not near:
                continue
            detailed += 1
            try:
                validate_geometry(feature['geometry'], {'Polygon', 'MultiPolygon'})
                p = feature.get('properties') or {}
                if not p.get('GlobalID'):
                    raise ValueError('Parcel candidate lacks GlobalID')
            except (ValueError, TypeError) as exc:
                invalid += 1
                result['errors'].append({'layer': 'parcels', 'feature_id': feature.get('id'), 'error': str(exc)})
                continue
            hits = [key for key, point in near.items() if contains(feature['geometry'], point)]
            for row in result['landmarks']:
                matched = sorted(set(hits) & {point['point_id'] for point in row['reference_points']})
                if matched:
                    row['parcels'].append({'native_id': p['GlobalID'], 'properties': p, 'geometry': feature['geometry'], 'bbox': b,
                                          'contains_point_ids': matched, 'source_sha256': sources['parcels'][1]['sha256'],
                                          'basis': 'point in polygon; spatial context only, not facility ownership or drawing footprint'})
        result['processing']['parcels'] = {'features_scanned': count, 'uncomputable_bounds': bad_bounds, 'nearby_geometries_validated': detailed,
                                          'invalid_nearby_geometries': invalid,
                                          'validation_scope': 'Bounds prefilter across export; detailed validation only for point-envelope overlaps. No repair.'}
        log.append(f'parcels: scanned {count}; unavailable bounds {bad_bounds}; nearby checked {detailed}; invalid nearby {invalid}')
    validate_landmarks(result)
    if any(file_sha256(path) != metadata['sha256'] for path, metadata in sources.values()):
        raise ValueError('County source changed during supplemental processing; output must not be used')
    write_json(output / 'landmarks.json', result)
    from .geo_report import _csv
    rows = [{'landmark_id': r['landmark_id'], 'name': r['name'], 'type': r['type'], 'address': r.get('address'),
             'coordinate_status': r['coordinate_status'], 'point_count': len(r['reference_points']), 'parcel_count': len(r['parcels']),
             'positional_accuracy_m': r.get('positional_accuracy_m'), 'verification_status': r['verification_status'],
             'sources': r['sources'], 'details_reference': f'landmarks.json#/landmarks/{i}'} for i, r in enumerate(result['landmarks'])]
    _csv(output / 'landmarks.csv', ['landmark_id', 'name', 'type', 'address', 'coordinate_status', 'point_count', 'parcel_count',
                                  'positional_accuracy_m', 'verification_status', 'sources', 'details_reference'], rows)
    features = []
    for row in result['landmarks']:
        for point in row['reference_points']:
            features.append({'type': 'Feature', 'geometry': point['geometry'], 'properties': {'landmark_id': row['landmark_id'],
                             'name': row['name'], **{k: v for k, v in point.items() if k != 'geometry'}}})
    write_json(output / 'landmark-points.geojson', {'type': 'FeatureCollection', 'features': features})
    (output / 'landmarks.log').write_text('\n'.join(log) + '\n', encoding='utf-8')
    LOGGER.info('Supplemental landmarks written to %s', output)
    return result
