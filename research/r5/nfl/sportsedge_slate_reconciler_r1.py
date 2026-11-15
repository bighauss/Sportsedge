#!/usr/bin/env python3
"""Catch silent full-game drops by reconciling captured board rows to DK slate registry.

No scores, odds or game identity inferred. A missing game fails the batch.
This prevents a PHI/BOS-style omission passing unnoticed downstream.
"""
import csv
import json
from collections import Counter
from pathlib import Path

MAINS={'SPREAD','TOTAL','ML'}

def rows(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def key(r):
    return (r.get('sport','').strip().upper(),r.get('away','').strip().casefold(),r.get('home','').strip().casefold())

def reconcile(slate_file,board_files):
    slate=rows(slate_file);rows_all=[r for f in board_files for r in rows(f)]
    expected={key(r):r for r in slate};found={}
    for r in rows_all:found.setdefault(key(r),[]).append(r)
    missing=[];malformed=[];extras=[]
    for k,slate_row in expected.items():
        if k not in found:
            missing.append({'sport':k[0],'away':slate_row['away'],'home':slate_row['home'],
                  'dk_event_id':slate_row.get('dk_event_id',''),'reason':'GAME_MISSING_FROM_BOARD'})
            continue
        got=Counter(r.get('market','').upper() for r in found[k])
        for m in MAINS:
            if got[m] != 1:
                malformed.append({'event_id':slate_row.get('dk_event_id',''),
                        'sport':k[0],'market':m,'count':got[m],'reason':'MAIN_MISSING_OR_DUPLICATE'})
    for k,r in found.items():
        if k not in expected:extras.append({'sport':k[0],'away':r[0].get('away'), 'home':r[0].get('home'),
                                                'reason':'BOARD_EVENT_NOT_ON_SLATE'})
    keys=Counter(key(x) for x in slate)
    dups=[k for k,n in keys.items() if n>1]
    result={'slate_games':len(slate),'distinct_expected_games':len(expected),
            'board_rows':len(rows_all),'covered_games':len(expected)-len(missing),
            'missing_games':missing,'missing_or_duplicate_mains':malformed,
            'unscheduled_board_events':extras,'duplicated_slate_keys':dups,
            'verdict':'PASS' if not (missing or malformed or extras or dups) else 'BLOCK'}
    return result

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--slate',required=True);ap.add_argument('--boards',nargs='+',required=True)
    ap.add_argument('--output',required=True)
    a=ap.parse_args();d=reconcile(a.slate,a.boards)
    Path(a.output).write_text(json.dumps(d,indent=2)+'\n')
    print(json.dumps({k:d[k] for k in ('slate_games','covered_games','board_rows','verdict')}))
