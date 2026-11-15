#!/usr/bin/env python3
"""PIT-gated independent projection overlay for SportsEdge V5 input boards.

Only joins frozen external own-model forecasts; NEVER derives projections from
DK odds/ANCHOR. Missing games stay blank. Source, version and cutoff required.
Projection CSV columns: sport,home,away,home_proj,away_proj,asof_ct,start_ct,
model_version,source_file_sha256. Withheld: mismatched/duplicated/late rows.
"""
import csv
import datetime as dt
import math
import json
from pathlib import Path

KEY=('sport','home','away')
PROJ=('sport','home','away','home_proj','away_proj','asof_ct','start_ct','model_version','source_file_sha256')

def load(path,required):
    with open(path,newline='',encoding='utf-8-sig') as f:
        rd=csv.DictReader(f);names=rd.fieldnames or []
        if len(names)!=len(set(names)):raise ValueError('DUPLICATE_HEADERS')
        if not set(required).issubset(names):raise ValueError('MISSING_HEADERS:'+','.join(sorted(set(required)-set(names))))
        return [{k:(v or '').strip() for k,v in row.items()} for row in rd]

def clock(s):
    try:
        t=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
        return t.astimezone(dt.timezone.utc) if t.tzinfo and t.utcoffset() is not None else None
    except ValueError:return None

def valid_proj(r):
    try:
        vals=[float(r[x]) for x in ('home_proj','away_proj')]
        if not all(math.isfinite(x) and x>=0 for x in vals):return False
    except ValueError:return False
    a,b=clock(r['asof_ct']),clock(r['start_ct'])
    return bool(a and b and a<b and r['model_version'] and len(r['source_file_sha256'])==64
                and all(c in '0123456789abcdef' for c in r['source_file_sha256'].lower()))

def overlay(board_path,projections_path,output_path,report_path):
    board=load(board_path,KEY+('home_proj','away_proj','market','price_a','price_b'))
    proj=load(projections_path,PROJ)
    mapping={};problems=[]
    for r in proj:
        k=tuple(r[x].casefold() for x in KEY)
        if k in mapping:
            problems.append({'game':k,'reason':'DUPLICATE_PROJECTION'});mapping[k]=None
        elif not valid_proj(r):
            problems.append({'game':k,'reason':'PIT_OR_PROVENANCE_INVALID'});mapping[k]=None
        else:mapping[k]=r
    games=set(tuple(r[x].casefold() for x in KEY) for r in board)
    matched=0;unchanged=0;new=[]
    for r in board:
        k=tuple(r[x].casefold() for x in KEY)
        p=mapping.get(k)
        if p and not r['home_proj'] and not r['away_proj']:
            r=dict(r);r['home_proj']=p['home_proj'];r['away_proj']=p['away_proj'];matched+=1
        else:unchanged+=1
        new.append(r)
    Path(output_path).parent.mkdir(parents=True,exist_ok=True)
    with open(output_path,'w',newline='',encoding='utf-8') as f:
        if new:
            w=csv.DictWriter(f,fieldnames=list(new[0]));w.writeheader();w.writerows(new)
    result={'board_rows':len(board),'updated_rows':matched,'unchanged_rows':unchanged,
            'games':len(games),'independent_projected_games':sum(1 for k in games if mapping.get(k)),
            'projection_problems':problems,'status':'CANDIDATE_NOT_PROMOTED'}
    Path(report_path).write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--board',required=True);p.add_argument('--projections',required=True)
    p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    a=p.parse_args();print(json.dumps(overlay(a.board,a.projections,a.output,a.report),indent=2))
