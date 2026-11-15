"""CFB event census contract R2: independently supplied expected IDs required.
Research-only; validates frozen JSON payloads, not live ESPN availability.
"""
import argparse, csv, hashlib, json, sys
from pathlib import Path
from datetime import datetime, timezone

def parse_time(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('naive_capture_timestamp')
    return d.astimezone(timezone.utc)

def event_ids(payload):
    events=payload.get('events')
    if not isinstance(events,list) or not events: raise ValueError('missing_events')
    ids=[]
    for event in events:
        eid=str(event.get('id','')).strip()
        if not eid: raise ValueError('missing_event_id')
        ids.append(eid)
    if len(set(ids))!=len(ids): raise ValueError('duplicate_event_id')
    return set(ids)

def audit(primary, control, census, team_rows, metadata):
    """Census is independent, immutable event-ID inventory, not derived from either payload."""
    if not metadata.get('independent_census_source_url') or not metadata.get('primary_url') or not metadata.get('control_url'):
        raise ValueError('missing_source_url')
    if metadata['primary_url']==metadata['control_url']:
        raise ValueError('same_source_url')
    captured=parse_time(metadata['captured_at_utc'])
    census_at=parse_time(metadata['census_captured_at_utc'])
    if census_at>captured: raise ValueError('future_census')
    if not metadata.get('independent_census_verified',False): raise ValueError('unverified_census')
    a,b,c=event_ids(primary),event_ids(control),set(census.get('event_ids',[]))
    if not c or len(c)!=len(census.get('event_ids',[])): raise ValueError('bad_census')
    if a!=b or a!=c: raise ValueError('event_census_disagreement')
    mapping={}
    for row in team_rows:
        tid=str(row.get('team_id','')).strip(); name=str(row.get('team_name','')).strip()
        if not tid or not name: raise ValueError('bad_team_mapping')
        if tid in mapping: raise ValueError('duplicate_team_mapping')
        mapping[tid]=name
    missing=[]
    for e in primary['events']:
        comps=e.get('competitions')
        if not isinstance(comps,list) or len(comps)!=1: raise ValueError('invalid_competitions')
        competitors=comps[0].get('competitors',[])
        if len(competitors)!=2: raise ValueError('invalid_competitors')
        teams=[str(x.get('team',{}).get('id','')).strip() for x in competitors]
        if len(set(teams))!=2: raise ValueError('duplicate_competitor')
        missing.extend({'event_id':str(e['id']),'team_id':tid} for tid in teams if tid not in mapping)
    return {'status':'QUARANTINE' if missing else 'CENSUS_VERIFIED_RESEARCH', 'event_count':len(a),'unmapped':missing,
            'note':'Not starter designation, point-in-time projection, or betting-market admission'}

def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('primary','control','census','team_map','metadata'):p.add_argument(name)
    p.add_argument('--out',required=True); args=p.parse_args(argv)
    paths={name:Path(getattr(args,name)) for name in ('primary','control','census','team_map','metadata')}
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()}
    try:
        data={k:json.loads(v.read_text()) for k,v in paths.items() if k!='team_map'}
        with paths['team_map'].open(newline='') as f: rows=list(csv.DictReader(f))
        result=audit(data['primary'],data['control'],data['census'],rows,data['metadata'])
    except (ValueError,KeyError,IndexError,TypeError) as e: result={'status':'QUARANTINE','reason':str(e)}
    result['sha256']=hashes
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return 0 if result['status']=='CENSUS_VERIFIED_RESEARCH' else 4
if __name__=='__main__':sys.exit(main())
