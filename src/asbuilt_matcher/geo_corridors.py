"""Connected reference-road components, explicitly coarser than drawing areas."""

import hashlib
import json
import math

from .geo_geometry import bounds, extent_diagonal, geometry_distance, parts, project


def _id(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:20]


def road_components(feature_keys, features, origin, gap_m):
    """Group endpoints in a metre grid; crossings alone do not imply connectivity.

    A multipart feature can span components. Split its parts for connectivity,
    retaining original feature keys; never invent connectors across gaps.
    """
    nodes=[]
    for key in sorted(set(feature_keys)):
        f=features[key]
        for part in parts(f['geometry']):
            nodes.append({'feature_key':key,'line':part,'level':f['values'].get('level')})
    parent=list(range(len(nodes))); grid={}
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    def join(i,j):
        a,b=find(i),find(j)
        if a!=b:parent[max(a,b)]=min(a,b)
    for i,node in enumerate(nodes):
        for endpoint in [node['line'][0],node['line'][-1]]:
            p=project(endpoint,origin);cell=(math.floor(p[0]/gap_m),math.floor(p[1]/gap_m))
            for dx in [-1,0,1]:
                for dy in [-1,0,1]:
                    for j,q in grid.get((cell[0]+dx,cell[1]+dy),[]):
                        levels=node['level'],nodes[j]['level']
                        if levels[0] is not None and levels[1] is not None and str(levels[0])!=str(levels[1]):continue
                        if math.dist(p,q)<=gap_m:join(i,j)
            grid.setdefault(cell,[]).append((i,p))
    groups={}
    for i,node in enumerate(nodes):groups.setdefault(find(i),[]).append(node)
    return list(groups.values())


def corridor_candidates(groups, matches, features, origin, settings, document_id):
    result=[]
    for key,found in sorted(matches.items()):
        if key[0]!='street_name' or not found:continue
        by_feature={m['feature_key']:m for m in found}
        for component in road_components(by_feature,features,origin,settings['corridor_gap_m']):
            keys=sorted({n['feature_key'] for n in component})
            evidence_matches=[by_feature[k] for k in keys]
            best=max(evidence_matches,key=lambda m:(m['match_type']=='exact',m['match_type']=='normalized',m['similarity']))
            factor=1 if best['match_type']=='exact' else .93 if best['match_type']=='normalized' else .85 if best['match_type']=='scoped_alias' else .65*best['similarity']
            points=round(30*factor,3)
            lines=[n['line'] for n in component]
            geometry={'type':'MultiLineString','coordinates':lines}
            b=bounds(geometry)
            corridor_key=_id([keys,lines])
            conflicts,missing,overlaps=[],[],[]
            for other_key,rows in groups.items():
                if other_key==key:continue
                item={'clue_ids':[c['clue_id'] for c in rows],'kind':other_key[0],'text':rows[0]['text']}
                nearby=[m for m in matches.get(other_key,[]) if geometry_distance(geometry,features[m['feature_key']]['geometry'],origin)<=settings['spatial_tolerance_m']]
                if nearby:
                    overlaps.append({**item,'matches':nearby,'points':0,'basis':'overlap with broad corridor; does not establish drawing area'})
                elif matches.get(other_key):
                    conflicts.append({**item,'reason':'matching references lie away from this corridor'})
                else:
                    missing.append({**item,'reason':'no reference label match'})
            length=sum(math.dist(project(a,origin),project(c,origin)) for line in lines for a,c in zip(line,line[1:]))
            result.append({'candidate_id':_id([document_id,corridor_key,key]),'corridor_key':corridor_key,
                'score':round(points-12*len(conflicts)-6*len(missing),3),'qualified':False,
                'match_type':'road_corridor','localization_level':'road_corridor','crs':'EPSG:4326','bbox':b,
                'area_diagonal_m':round(extent_diagonal(b,origin),2),'anchor_feature_keys':keys,'intersection':None,
                'evidence':[{'kind':'street_name','text':groups[key][0]['text'],'clue_ids':[c['clue_id'] for c in groups[key]],
                             'points':points,'duplicate_reference_alias':False,'best_match_type':best['match_type'],
                             'matches':evidence_matches}],
                'bonuses':[],'conflicts':conflicts,'missing':missing,'spatial_context':[],
                'corridor_overlaps':overlaps,
                'penalties':{'conflicting_group_points':-12,'missing_group_points':-6},
                'supporting_features':[{'feature_key':k,'dataset_id':features[k]['dataset_id'],'native_id':features[k]['native_id'],
                                       'kind':'roads','bbox':features[k]['bbox']} for k in keys],
                'coverage':{'geometry':geometry,'bbox':b,'feature_count':len(keys),'line_part_count':len(lines),
                            'reference_length_m':round(length,2),'connection_gap_m':settings['corridor_gap_m'],
                            'method':'endpoint-proximity components; no geometry dissolve or gap connectors'},
                'evidence_still_needed':['Independently established geographic reference for this sheet.',
                    'Verified intersection, parcel/address, landmark reference or control evidence to narrow the drawing area.'],
                'limitations':['Reference-road corridor only; no drawing footprint or precise location established.',
                    'Bounding box encloses the lines and can contain unrelated areas; it is not a drawing area or uncertainty interval.',
                    'Endpoint proximity does not establish at-grade network connectivity; reference length can include parallel/overlapping linework.',
                    'Scope is the configured road-name/route subset, not the complete statewide route.'],
                'analyst_review_status':'pending'})
    unique={}
    for candidate in sorted(result,key=lambda c:(-c['score'],c['candidate_id'])):
        key=candidate['corridor_key']
        if key not in unique:
            unique[key]=candidate
            candidate['alternate_label_evidence']=[]
        else:
            # Multiple accepted names for the same physical reference component
            # are additional audit evidence, not independent corridor candidates.
            unique[key]['alternate_label_evidence'].extend(candidate['evidence'])
    return list(unique.values())
