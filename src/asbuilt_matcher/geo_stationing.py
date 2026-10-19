"""Station-range continuity evidence, without converting stationing to geography."""

import itertools
import re

from .clue_review import analyst_accepted

STATIONS = re.compile(r'\bSTA\.?\s*(\d+)\+(\d{2}(?:\.\d+)?)\s+TO\s+STA\.?\s*(\d+)\+(\d{2}(?:\.\d+)?)\b', re.I)


def station_range(text):
    match = STATIONS.fullmatch(text.strip())
    if not match:
        return None
    a, b, c, d = map(float, match.groups())
    start, end = 100 * a + b, 100 * c + d
    if b >= 100 or d >= 100 or end <= start:
        return None
    return {'start': start, 'end': end, 'numeric_span': end - start,
            'units': 'station units; no geographic distance conversion', 'text': text}


def sheet_relationships(drawings, observations=None):
    observations = observations or {'observations': []}
    observed = {(o['document_sha256'], o['page_number']): o for o in observations.get('observations', [])}
    result = []
    for left, right in itertools.combinations(drawings, 2):
        ranges = [[(c, station_range(c['text'])) for c in d['accepted_clues'] if c['kind'] == 'station_range' and analyst_accepted(c)] for d in [left, right]]
        for (lc, lr), (rc, rr) in itertools.product(*ranges):
            if not lr or not rr:
                continue
            before, after, bc, ac, br, ar = (left, right, lc, rc, lr, rr) if lr['end'] == rr['start'] else (right, left, rc, lc, rr, lr)
            continuous = br['end'] == ar['start']
            overlap = max(0, min(lr['end'], rr['end']) - max(lr['start'], rr['start']))
            shared_project = {c['text'].strip().casefold() for c in left['accepted_clues'] if c['kind'] == 'project_name' and analyst_accepted(c)} & {
                c['text'].strip().casefold() for c in right['accepted_clues'] if c['kind'] == 'project_name' and analyst_accepted(c)}
            shared_corridor = ({c.get('corridor_key') for c in left['candidates']} & {c.get('corridor_key') for c in right['candidates']}) - {None}
            bo = observed.get((before['document_sha256'], before['page_number']), {})
            ao = observed.get((after['document_sha256'], after['page_number']), {})
            reciprocal = continuous and any(m.get('neighbor_sheet') in after['sheet_numbers'] for m in bo.get('matchlines', [])) and any(
                m.get('neighbor_sheet') in before['sheet_numbers'] for m in ao.get('matchlines', []))
            result.append({'left_drawing_id': left['drawing_id'], 'right_drawing_id': right['drawing_id'],
                           'station_clue_ids': [lc['clue_id'], rc['clue_id']], 'ranges': [lr, rr],
                           'continuous': continuous, 'overlap_station_units': overlap,
                           'predecessor_drawing_id': before['drawing_id'] if continuous else None,
                           'successor_drawing_id': after['drawing_id'] if continuous else None,
                           'shared_station': br['end'] if continuous else None, 'shared_project': bool(shared_project),
                           'shared_corridor_keys': sorted(shared_corridor), 'reciprocal_matchlines_observed': bool(reciprocal),
                           'shared_station_basis': 'accepted title station ranges; matchline labels alone do not provide station coordinates',
                           'interpretation': 'source_inspection_supports_consecutive_alignment_sections' if reciprocal and shared_project and shared_corridor else
                                             'station_continuity_hypothesis' if continuous else 'overlapping_or_discontinuous_ranges',
                           'observation_review_status': 'AI source inspection; independent analyst review pending',
                           'score_points': 0, 'geographic_endpoints': None,
                           'limitations': ['Station values are alignment references, not geographic coordinates.',
                                           'No station-origin tie, equations, historic alignment or exact unit convention is independently validated.',
                                           'Plan scale in feet and increasing labels do not register either sheet to road centerline.',
                                           'No length, location, ranking points or approval transferred between sheets.']})
    return result
