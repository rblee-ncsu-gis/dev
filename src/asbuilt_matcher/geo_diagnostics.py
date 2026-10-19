"""Read-only road field inspection with exact source evidence and geometries."""

from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .geo_names import normalize_name
from .geo_stream import collection_events
from .pdf_extract import file_sha256, write_json

TERMS = ["NC 211", "NC Highway 211", "Southport-Supply Road", "Southport Supply Road SE", "Supply Road"]


def diagnose_roads(path, output, *, id_field="GlobalID", name_field="FULLNAME", route_fields=None):
    path,output=Path(path).resolve(),Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    before=file_sha256(path)
    route_fields=route_fields or ["STATERDNUM"]
    fields=set(); related=[]; unnamed=[]; name_routes=Counter(); field_hits=Counter()
    route_count=0; total=0
    for event,feature in collection_events(path):
        if event!='feature':continue
        total+=1
        props=feature.get('properties',{})
        fields.update(props)
        inspected={k:v for k,v in props.items() if k in route_fields or k in {id_field,name_field}
                   or re.search(r'name|alias|alternate|route|prefix|suffix|^type$',k,re.I)}
        hits=[]
        for field,value in inspected.items():
            if field==id_field or value is None:continue
            text=normalize_name(str(value),street=True)
            reasons=[]
            if field in route_fields and re.fullmatch(r'(?:NC\s*(?:HWY\s*)?)?211',text):
                reasons.append('route token 211; route class requires corroboration')
            if 'SUPPLY' in text.split():
                reasons.append('SUPPLY text inspection; not an alias approval')
            if re.search(r'(?<!\d)211(?!\d)',text) and field not in route_fields:
                reasons.append('211 text inspection')
            if reasons:
                hits.append({'field':field,'value':value,'reasons':reasons})
                field_hits[field]+=1
        route_match=any(str(props.get(f,'')).strip()=='211' for f in route_fields)
        route_count+=route_match
        record={'source_index':total-1,'native_id':props.get(id_field),'source_values':inspected,
                'matched_fields':hits,'geometry':feature.get('geometry')}
        if hits:
            related.append(record)
            name_routes[(str(props.get(name_field)),str(props.get(route_fields[0])))]+=1
        if props.get(name_field) is None or not str(props.get(name_field)).strip():
            record['has_route_identifier']=any(props.get(f) is not None and str(props[f]).strip() for f in route_fields)
            unnamed.append(record)
    if file_sha256(path)!=before:
        raise ValueError('Road export changed during inspection')
    output.mkdir(parents=True,exist_ok=False)
    summary={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),
             'source':{'path':str(path),'sha256':before},'diagnostic_terms':TERMS,
             'field_mapping':{'id':id_field,'official_name':name_field,'route_fields':route_fields},
             'actual_fields':sorted(fields),'total_features':total,'related_features':len(related),
             'route_211_features':route_count,'field_hit_counts':dict(field_hits),
             'name_route_counts':[{'name':name,'route':route,'count':count} for (name,route),count in sorted(name_routes.items())],
             'unnamed_count':len(unnamed),'unnamed_with_route_identifier':sum(bool(r['has_route_identifier']) for r in unnamed),
             'scope':'Diagnostic search results, not automatic aliases, geographic truth or drawing locations.'}
    write_json(output/'diagnostics.json',summary)
    for filename,records in [('related-roads.geojson',related),('unnamed-roads.geojson',unnamed)]:
        write_json(output/filename,{'type':'FeatureCollection','features':[
            {'type':'Feature','id':r['native_id'],'properties':{k:v for k,v in r.items() if k!='geometry'},'geometry':r['geometry']} for r in records]})
    with (output/'source-values.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,['source_index','native_id','source_values','matched_fields']);writer.writeheader()
        for r in related:
            writer.writerow({k:json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],(dict,list)) else r[k] for k in writer.fieldnames})
    lines=['# Road-name diagnosis','',f'Source SHA-256: `{before}`. {total:,} source features.',
           f'{route_count} route-field values equal 211; {len(related)} related diagnostic features.',
           f'{len(unnamed)} unnamed features; {summary["unnamed_with_route_identifier"]} have a route identifier.','',
           'Actual fields: '+', '.join(sorted(fields)),'','| FULLNAME | route value | features |','| --- | --- | ---: |']
    lines += [f'| {r["name"]} | {r["route"]} | {r["count"]} |' for r in summary['name_route_counts']]
    lines += ['','Each matching source value, native ID and original geometry is preserved in related-roads.geojson.',
              'Unnamed exclusions are preserved in unnamed-roads.geojson. No source geometry was repaired or changed.',
              'The strict matcher previously compared the complete drawing label against FULLNAME only; route/name aliases were absent.',
              'Route-number and direction guards are intentional. Corridor recovery must not imply a drawing footprint.']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary
