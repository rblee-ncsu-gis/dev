"""Landmark-anchored reference-road sections, separately from drawing footprints."""

from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
import shutil
import uuid

from .geo_corridors import _id
from .clue_review import analyst_accepted
from .geo_geometry import bounds, extent_diagonal, parts, point_distance, project
from .geo_landmarks import match_landmarks, validate_landmarks
from .geo_reference import read_json
from .geo_report import _csv, evaluation_template, write_html
from .geo_stationing import sheet_relationships
from .geo_stream import collection_events
from .pdf_extract import file_sha256, write_json

DEFAULTS = {'maximum_landmark_offset_m': 1000, 'maximum_anchor_spread_m': 2000, 'nearest_tie_m': 0.5}


def attach_source_lineage(result):
    """Recover exact source line-part IDs when the original road snapshot exists.

    Never use a current replacement export to relabel frozen geometry. Matching
    requires both the snapshot hash and identical coordinates, not nearest IDs.
    """
    needed = {}
    for d in result['drawings']:
        parents = {c['candidate_id']: c for c in d['candidates']}
        for c in d['narrowed_candidates']:
            c['source_lineage'] = []
            parent = parents[c['parent_candidate_id']]
            for index in c['line_part_indexes_in_parent']:
                line = parent['coverage']['geometry']['coordinates'][index]
                needed.setdefault(tuple(map(tuple, line)), []).append((c, index, parent))
    issues = []
    for dataset in result.get('reference_datasets', []):
        if dataset['kind'] != 'roads' or not needed:
            continue
        path = Path(dataset['path'])
        if not path.is_file() or file_sha256(path) != dataset['sha256']:
            issues.append({'dataset_id': dataset['id'], 'reason': 'Original road snapshot unavailable or changed; no substitute IDs assigned.'})
            continue
        for event, feature in collection_events(path):
            if event != 'feature' or not feature.get('geometry'):
                continue
            native_id = (feature.get('properties') or {}).get(dataset['fields']['id'])
            if feature['geometry']['type'] not in {'LineString', 'MultiLineString'}:
                continue
            for part_index, line in enumerate(parts(feature['geometry'])):
                for c, index, parent in needed.get(tuple(map(tuple, line)), []):
                    support = [s for s in parent['supporting_features'] if s['dataset_id'] == dataset['id'] and s['native_id'] == native_id]
                    if support:
                        c['source_lineage'].append({'parent_line_part_index': index, 'source_line_part_index': part_index,
                                                    'dataset_id': dataset['id'], 'native_id': native_id, 'source_sha256': dataset['sha256']})
                        if support[0] not in c['supporting_features']:
                            c['supporting_features'].append(deepcopy(support[0]))
        if file_sha256(path) != dataset['sha256']:
            raise ValueError('Road source changed during exact lineage resolution')
    for d in result['drawings']:
        for c in d['narrowed_candidates']:
            c['source_lineage_status'] = 'resolved' if {s['parent_line_part_index'] for s in c['source_lineage']} == set(c['line_part_indexes_in_parent']) else 'incomplete; use frozen parent geometry and part indexes'
    result['source_lineage_issues'] = issues


def narrow_corridors(run, landmarks, *, settings=None, observations=None):
    validate_landmarks(landmarks)
    options = {**DEFAULTS, **(settings or {})}
    if set(options) != set(DEFAULTS) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in options.values()):
        raise ValueError('Narrowing settings must be known positive finite metre thresholds')
    result = deepcopy(run)
    origin = run.get('distance_model', {}).get('origin')
    if origin is None:
        raise ValueError('A frozen corridor run with a local distance origin is required')
    result['supplemental_landmarks'] = deepcopy(landmarks)
    result['narrowing_settings'] = options
    result['model_input_reference_locations'] = [
        {'landmark_id': row['landmark_id'], 'point_id': p['point_id'], 'geometry': p['geometry']}
        for row in landmarks['landmarks'] for p in row.get('reference_points', [])]
    for drawing in result['drawings']:
        drawing['narrowed_candidates'] = []
        drawing['landmark_assessment'] = {'matches': [], 'missing': [], 'conflicts': []}
        assessment = drawing['landmark_assessment']
        matched = {}
        for clue in drawing['accepted_clues']:
            if clue['kind'] != 'landmark' or not analyst_accepted(clue):
                continue
            found = match_landmarks(clue, landmarks)
            if len(found) != 1:
                target = assessment['conflicts'] if found else assessment['missing']
                target.append({'clue_id': clue['clue_id'], 'text': clue['text'], 'reason': 'ambiguous reference label' if found else 'no source-corroborated reference label'})
                continue
            landmark = found[0]
            matched.setdefault(landmark['landmark_id'], {'reference': landmark, 'clue_ids': []})['clue_ids'].append(clue['clue_id'])
        for group in matched.values():
            row = group['reference']
            assessment['matches'].append({'landmark_id': row['landmark_id'], 'name': row['name'], 'clue_ids': group['clue_ids'],
                                          'point_count': len(row.get('reference_points', [])), 'parcel_count': len(row.get('parcels', [])),
                                          'verification_status': row['verification_status'], 'positional_accuracy_m': row.get('positional_accuracy_m')})
            if not row.get('reference_points'):
                assessment['missing'].append({'landmark_id': row['landmark_id'], 'reason': 'address unresolved; no coordinates invented'})
        for parent in drawing['candidates']:
            if parent.get('match_type') != 'road_corridor':
                continue
            lines = parent['coverage']['geometry']['coordinates']
            relations = []
            if not lines:
                continue
            chosen = set()
            conflicts = deepcopy(assessment['conflicts'])
            anchor_points = []
            for group in matched.values():
                row = group['reference']
                for point in row.get('reference_points', []):
                    p = point['geometry']['coordinates']
                    if math.dist(project(p, origin), (0, 0)) > 250000:
                        raise ValueError('Landmark outside bounded county projection; check coordinate order/CRS')
                    distances = [point_distance(p, {'type': 'LineString', 'coordinates': line}, origin) for line in lines]
                    nearest = min(distances)
                    indexes = [i for i, d in enumerate(distances) if d <= nearest + options['nearest_tie_m']]
                    supported = nearest <= options['maximum_landmark_offset_m']
                    relations.append({'landmark_id': row['landmark_id'], 'point_id': point['point_id'], 'clue_ids': group['clue_ids'],
                                      'minimum_corridor_distance_m': round(nearest, 2), 'nearest_line_part_indexes': indexes,
                                      'within_search_threshold': supported, 'positional_accuracy_m': point.get('positional_accuracy_m'),
                                      'basis': point['basis'], 'geometry': point['geometry']})
                    if supported:
                        chosen.update(indexes)
                        anchor_points.append(p)
                    else:
                        conflicts.append({'landmark_id': row['landmark_id'], 'point_id': point['point_id'], 'reason': 'reference point too far from corridor under configured search threshold'})
            spread = max((math.dist(project(a, origin), project(b, origin)) for a in anchor_points for b in anchor_points), default=0)
            if spread > options['maximum_anchor_spread_m']:
                conflicts.append({'reason': 'landmark anchors too dispersed for one review locality', 'anchor_spread_m': round(spread, 2)})
            if parent.get('conflicts'):
                conflicts.append({'reason': 'original corridor has unresolved conflicting evidence'})
            assessment.setdefault('corridor_relationships', []).append({'parent_candidate_id': parent['candidate_id'], 'relations': relations,
                                                                        'anchor_spread_m': round(spread, 2), 'conflicts': conflicts})
            # An unresolved conflicting landmark is never resolved by selecting
            # whichever point is closest. Missing evidence remains explicit.
            if not chosen or conflicts:
                continue
            selected = [line for i, line in enumerate(lines) if i in chosen]
            geometry = {'type': 'MultiLineString', 'coordinates': selected}
            length = sum(math.dist(project(a, origin), project(b, origin)) for line in selected for a, b in zip(line, line[1:]))
            original_length = parent['coverage']['reference_length_m']
            if length >= original_length - 0.01:
                continue
            b = bounds(geometry)
            landmark_count = len({r['landmark_id'] for r in relations if r['within_search_threshold']})
            candidate = {'candidate_id': _id([drawing['drawing_id'], parent['candidate_id'], sorted(chosen), sorted(matched)]),
                         'parent_candidate_id': parent['candidate_id'], 'rank': len(drawing['narrowed_candidates']) + 1,
                         'score': round(parent['score'] + 10 * landmark_count, 3), 'qualified': False,
                         'match_type': 'landmark_corridor_section', 'localization_level': 'landmark_review_locality',
                         'bbox': b, 'crs': 'EPSG:4326', 'area_diagonal_m': round(extent_diagonal(b, origin), 2),
                         'supporting_features': [], 'evidence': deepcopy(parent['evidence']),
                         'bonuses': [{'basis': 'distinct source-corroborated landmark identities; repeated units/labels count once', 'points': 10 * landmark_count}],
                         'conflicts': [], 'missing': deepcopy(assessment['missing']), 'spatial_context': [],
                         'landmark_relations': relations, 'line_part_indexes_in_parent': sorted(chosen),
                         'landmark_count': landmark_count, 'anchor_spread_m': round(spread, 2),
                         'coverage': {'geometry': geometry, 'reference_length_m': round(length, 2), 'line_part_count': len(selected),
                                      'parent_reference_length_m': original_length, 'retained_linework_fraction': round(length / original_length, 6),
                                      'method': 'Whole nearest original corridor line parts for every matched landmark point; ties retained. No buffer, connector or drawing footprint.'},
                         'positional_accuracy_m': None, 'analyst_review_status': 'pending',
                         'evidence_still_needed': ['Independently established sheet extent/endpoints or control evidence.', 'Analyst review of source-era landmark identity, address units and source observations.'],
                         'limitations': ['Review locality anchored by landmarks; does not bound full drawing coverage.',
                                         'Nearest road geometry is an explicit hypothesis, not a confirmed facility access point or alignment.',
                                         'Source road segmentation controls extent; bbox is a display extent, not a footprint or uncertainty interval.',
                                         'Thresholds are configurable search policy, not positional accuracy or statistical confidence.',
                                         'Parcel containment supplies context only; no ownership, parcel approval or facility outline inferred.']}
            drawing['narrowed_candidates'].append(candidate)
        drawing['narrowing_status'] = 'landmark_review_locality_generated' if drawing['narrowed_candidates'] else 'not_narrowed'
        drawing['geographic_resolution']['landmark_review_locality_generated'] = bool(drawing['narrowed_candidates'])
    result['stationing_relationships'] = sheet_relationships(result['drawings'], observations)
    result['source_observations'] = observations or {'observations': []}
    result['narrowing_policy'] = 'Original candidates and scores retained verbatim; narrowed sections ranked separately. Landmark model inputs are excluded from independent ground truth.'
    return result


def run_narrowing(run_path, landmarks_path, output, *, settings=None, observations_path=None):
    run_path, landmarks_path = Path(run_path).resolve(), Path(landmarks_path).resolve()
    parent = read_json(run_path)
    observations = read_json(observations_path) if observations_path else None
    images = []
    if observations:
        known = {(d['document_sha256'], d['page_number']) for d in parent['drawings']}
        for row in observations.get('observations', []):
            if (row['document_sha256'], row['page_number']) not in known or row.get('reviewer_type') != 'ai' or row.get('verification_status') != 'pending':
                raise ValueError('Source observations must identify an existing drawing and remain pending AI observations')
            pdf = (Path(observations_path).resolve().parent / row['pdf_path']).resolve()
            if file_sha256(pdf) != row['document_sha256']:
                raise ValueError('Source observation PDF hash mismatch')
            for entry in row.get('image_references', []):
                image_path = (Path(observations_path).resolve().parent / entry['path']).resolve()
                if image_path.suffix.lower() != '.png' or file_sha256(image_path) != entry['sha256']:
                    raise ValueError('Source observation image hash/format mismatch')
                name = f'{len(images):02d}-{image_path.name}'
                images.append((image_path, name))
                entry['frozen_image'] = 'source-inspection/' + name
    result = narrow_corridors(parent, read_json(landmarks_path), settings=settings, observations=observations)
    attach_source_lineage(result)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if images:
        (output / 'source-inspection').mkdir()
        for path, name in images:
            shutil.copyfile(path, output / 'source-inspection' / name)
    result['parent_run_id'] = parent['run_id']
    result.update(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat())
    result['narrowing_inputs'] = {k: {'path': str(p), 'sha256': file_sha256(p)} for k, p in [
        ('parent_run', run_path), ('landmarks', landmarks_path)]}
    shutil.copyfile(run_path, output / 'parent-localization-input.json')
    shutil.copyfile(landmarks_path, output / 'landmarks-input.json')
    if observations_path:
        p = Path(observations_path).resolve()
        result['narrowing_inputs']['observations'] = {'path': str(p), 'sha256': file_sha256(p)}
        shutil.copyfile(p, output / 'observations-input.json')
    result['narrowing_implementation'] = {name: file_sha256(Path(__file__).parent / name) for name in [
        'geo_narrowing.py', 'geo_landmarks.py', 'geo_stationing.py', 'geo_geometry.py', 'geo_report.py', 'geo_eval.py']}
    write_json(output / 'localization.json', result)
    rows, documents, relations = [], [], []
    for di, d in enumerate(result['drawings']):
        documents.append({k: d[k] for k in ['drawing_id', 'source_pdf', 'sheet_numbers', 'narrowing_status', 'landmark_assessment']})
        for group in ['candidates', 'narrowed_candidates']:
            for ci, c in enumerate(d[group]):
                rows.append({'source_pdf': d['source_pdf'], 'drawing_id': d['drawing_id'], 'record_group': group,
                             **{k: c.get(k) for k in ['candidate_id', 'parent_candidate_id', 'rank', 'score', 'qualified', 'localization_level', 'bbox', 'landmark_count', 'analyst_review_status']},
                             'reference_length_m': c.get('coverage', {}).get('reference_length_m'),
                             'candidate_details_reference': f'localization.json#/drawings/{di}/{group}/{ci}'})
        for cr in d['landmark_assessment'].get('corridor_relationships', []):
            for relation in cr['relations']:
                relations.append({'source_pdf': d['source_pdf'], 'parent_candidate_id': cr['parent_candidate_id'], **relation})
    _csv(output / 'candidates.csv', ['source_pdf', 'drawing_id', 'record_group', 'candidate_id', 'parent_candidate_id', 'rank', 'score', 'qualified', 'localization_level', 'bbox', 'reference_length_m', 'landmark_count', 'analyst_review_status', 'candidate_details_reference'], rows)
    _csv(output / 'drawings.csv', ['drawing_id', 'source_pdf', 'sheet_numbers', 'narrowing_status', 'landmark_assessment'], documents)
    _csv(output / 'landmark-distances.csv', ['source_pdf', 'parent_candidate_id', 'landmark_id', 'point_id', 'minimum_corridor_distance_m', 'nearest_line_part_indexes', 'within_search_threshold', 'positional_accuracy_m', 'clue_ids', 'basis', 'geometry'], relations)
    write_html(result, None, output)
    write_json(output / 'evaluation-template.json', evaluation_template(result, output / 'localization.json'))
    (output / 'localization.log').write_text('\n'.join(f"{d['source_pdf']}: {d['narrowing_status']}; original {len(d['candidates'])}, narrowed {len(d['narrowed_candidates'])}" for d in result['drawings']) + '\n', encoding='utf-8')
    return result
