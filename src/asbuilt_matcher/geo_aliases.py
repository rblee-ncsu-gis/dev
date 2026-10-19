"""Scoped, versioned road aliases; never broad or transitive word equivalences."""

import re
from .geo_names import normalize_name

CATEGORIES={'official_name','route_number','historical_name','abbreviation','analyst_approved','candidate_relationship'}


def compile_aliases(registry, catalog):
    if registry is None:
        return {'entries':[],'query_index':{}}
    if registry.get('schema_version')!=1 or not isinstance(registry.get('entries'),list):
        raise ValueError('Invalid alias registry schema')
    datasets={d['id']:d for d in catalog['datasets']} if catalog else {}
    road_features={f['feature_key']:f for f in catalog['features'] if f['kind']=='roads'} if catalog else {}
    entries=[]; index={}; seen=set()
    for entry in registry['entries']:
        key=entry.get('id')
        if not isinstance(key,str) or not key.strip() or key in seen:
            raise ValueError('Alias IDs must be unique nonblank strings')
        seen.add(key)
        if entry.get('enabled') is not True:
            continue
        if entry.get('status') not in {'source_corroborated','analyst_approved'} or not entry.get('sources'):
            raise ValueError('Enabled aliases require explicit source corroboration or analyst approval')
        if entry['status']=='analyst_approved':
            approval=entry.get('approval',{})
            if approval.get('reviewer_type')!='human' or not all(approval.get(k) for k in ['reviewer','reviewed_at','reason']):
                raise ValueError('Analyst-approved aliases require an explicit human review record')
        scope=entry.get('scope',{})
        dataset=datasets.get(scope.get('dataset_id'))
        if not dataset or dataset.get('kind')!='roads' or dataset['sha256']!=scope.get('source_sha256'):
            raise ValueError(f'Stale or missing reference snapshot for alias {key}')
        allowed=scope.get('feature_ids')
        conditions=scope.get('field_values')
        if not isinstance(allowed,list) or not allowed or not isinstance(conditions,dict) or not conditions:
            raise ValueError('Aliases require explicit feature IDs and source-field constraints')
        if len({str(v) for v in allowed})!=len(allowed):
            raise ValueError('Duplicate alias-scope feature IDs')
        selected={}
        allowed_ids={str(v) for v in allowed}
        for f in road_features.values():
            if f['dataset_id']!=scope['dataset_id'] or str(f['native_id']) not in allowed_ids:continue
            if not all(isinstance(values,list) and values and f['properties'].get(field) in values for field,values in conditions.items()):
                raise ValueError(f'Alias source-field constraints no longer agree: {key}')
            selected[f['feature_key']]=f
        if {str(f['native_id']) for f in selected.values()}!={str(v) for v in allowed}:
            raise ValueError('Alias-scope features are missing from this imported snapshot')
        bbox=scope.get('bbox')
        if bbox is not None:
            if not isinstance(bbox,list) or len(bbox)!=4 or not -180<=bbox[0]<=bbox[2]<=180 or not -80<=bbox[1]<=bbox[3]<=80:
                raise ValueError('Alias geographic scope must be a WGS84 bbox')
            if any(not (bbox[0]-1e-9<=f['bbox'][0]<=f['bbox'][2]<=bbox[2]+1e-9
                        and bbox[1]-1e-9<=f['bbox'][1]<=f['bbox'][3]<=bbox[3]+1e-9) for f in selected.values()):
                raise ValueError('Alias features fall outside the configured geographic scope')
        aliases=entry.get('aliases',[])
        if not aliases:
            raise ValueError('Alias entry needs explicit labels')
        compiled={**entry,'allowed_keys':set(selected)}
        entries.append(compiled)
        for alias in aliases:
            if alias.get('category') not in CATEGORIES or not isinstance(alias.get('text'),str):
                raise ValueError('Alias labels require an explicit supported category and text')
            text=normalize_name(alias['text'],street=True)
            if (len(text.split())<2 and not re.fullmatch(r'NC\s*\d+',text)) or text in {'SUPPLY','ROAD','SUPPLY RD'}:
                raise ValueError('Generic word/road aliases are not allowed')
            if alias['category']=='analyst_approved' and entry['status']!='analyst_approved':
                raise ValueError('Source-corroborated aliases cannot claim analyst approval')
            index.setdefault(text,[]).append((compiled,alias))
    return {'entries':entries,'query_index':index}


def match_alias(query, feature, compiled):
    if not compiled or feature['kind']!='roads':return None
    for entry,alias in compiled['query_index'].get(normalize_name(query,street=True),[]):
        if feature['feature_key'] not in entry['allowed_keys']:continue
        return {'match_type':'scoped_alias','similarity':1.0,'normalized_query':normalize_name(query,street=True),
                'normalized_reference':normalize_name(str(feature['values']['name']),street=True),
                'alias':{'id':entry['id'],'label':alias['text'],'category':alias['category'],'status':entry['status'],
                         'analyst_approved':entry['status']=='analyst_approved','sources':entry['sources'],
                         'source_sha256':entry['scope']['source_sha256'],
                         'source_field_values':{field:feature['properties'].get(field) for field in entry['scope']['field_values']},
                         'method':'literal normalized alias label plus hash-bound feature/field scope'}}
    return None
