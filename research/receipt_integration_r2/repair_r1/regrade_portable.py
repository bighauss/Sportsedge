#!/usr/bin/env python3
"""Regrade archived Nov-9 portable selections into a NEW immutable correction ledger.

This does not modify the original census, probabilities, quotes, or qualification.
Historical results below are independent, manually reviewed final-score fixtures.
Use only for research; the archive itself does not prove pregame quotes.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,re
from collections import Counter
from pathlib import Path

# Score source citations and half-score orientation are recorded in README.
FINAL_SCORES = {
    'Mississippi Valley @ Washington': {'away': 'Mississippi Valley', 'home': 'Washington',
      'fg_away': 64, 'fg_home': 77, 'h1_away': 33, 'h1_home': 43},
    'Rice @ Stanford': {'away': 'Rice', 'home': 'Stanford',
      'fg_away': 73, 'fg_home': 91, 'h1_away': 29, 'h1_home': 45},
    'Portland @ Hawaii': {'away': 'Portland', 'home': 'Hawaii',
      'fg_away': 73, 'fg_home': 66, 'h1_away': 40, 'h1_home': 36},
}

def hashfile(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def classify(pick, game):
    """Returns period, exact family, side/team/line, with unambiguous dispatch."""
    info=FINAL_SCORES[game]
    per='1H' if pick.startswith('1H ') else 'FG'
    s=pick[3:] if per=='1H' else pick
    names=(info['away'], info['home'])
    m=re.fullmatch(r'(.+) ML',s)
    if m:
        if m[1] not in names:raise ValueError('unknown ML team '+str(pick))
        return per,'ML',m[1],None,None
    # Team totals MUST be before game totals (G-18 historical defect).
    m=re.fullmatch(r'(.+) (Over|Under) (\d+(?:\.\d+)?)',s)
    if m:
        if m[1] not in names:raise ValueError('unknown team-total team '+str(pick))
        return per,'TEAM_TOTAL',m[1],m[2].lower(),float(m[3])
    m=re.fullmatch(r'(Over|Under) (\d+(?:\.\d+)?)',s)
    if m:return per,'TOTAL',None,m[1].lower(),float(m[2])
    m=re.fullmatch(r'(.+) ([+-]\d+(?:\.\d+)?)',s)
    if m:
        if m[1] not in names:raise ValueError('unknown spread team '+str(pick))
        return per,'SPREAD',m[1],None,float(m[2])
    raise ValueError('cannot classify pick '+repr(pick))

def settle(game,pick):
    per,fam,team,side,line=classify(pick,game)
    fin=FINAL_SCORES[game]; p='h1' if per=='1H' else 'fg'
    a=fin[p+'_away'];h=fin[p+'_home']
    if fam=='ML':v=(a-h) if team==fin['away'] else (h-a)
    elif fam=='SPREAD':v=((a-h) if team==fin['away'] else (h-a))+line
    elif fam=='TOTAL':v=(a+h-line)*(1 if side=='over' else -1)
    elif fam=='TEAM_TOTAL':
        team_score=a if team==fin['away'] else h
        v=(team_score-line)*(1 if side=='over' else -1)
    else:raise AssertionError(fam)
    return 'W' if v>1e-9 else 'L' if v< -1e-9 else 'P'

def run(src, dest):
    data=json.loads(Path(src).read_text());ledger=[];changes=[];old_count=Counter();new_count=Counter()
    for ix,r in enumerate(data,1):
        if r['source']!='portable_nov9':continue
        result=settle(r['game'],r['pick'])
        old=r.get('outcome')
        rec={
          'original_census_row':ix,'source':r['source'],'game':r['game'],'pick':r['pick'],
          'original_result':old,'corrected_result':result,'changed':int(old!=result),
          'model_p_unchanged':r['model_p'],'odds_unchanged':r['price'],
          'ev_unchanged':r['ev'],'reason':'G18_RESULT_DISPATCH' if old!=result else 'UNCHANGED',
          'verified_score_source':'manual-final-fixture-see-README'
        }
        ledger.append(rec)
        if old!=result:changes.append(rec)
        old_count[old]+=1;new_count[result]+=1
    if len(ledger)!=496:raise ValueError(f'Expected 496 Nov9 archived rows, got {len(ledger)}')
    if len(changes)!=70:raise ValueError(f'Expected 70 result-only corrections; got {len(changes)}: inspect score fixtures')
    if Counter((r['original_result'],r['corrected_result']) for r in changes)!=Counter({('L','W'):35,('W','L'):35}):
        raise ValueError('Unexpected correction directions')
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    for fname,entries in [('nov9_portable_evaluation_derived.csv',ledger),('nov9_grade_corrections_only.csv',changes)]:
        with (dest/fname).open('w',newline='') as fp:
            w=csv.DictWriter(fp,fieldnames=list(entries[0]));w.writeheader();w.writerows(entries)
    stats={'source_sha256':hashfile(src),'original_rows':len(data),'portable_rows_regraded':len(ledger),
         'grade_corrections':len(changes),'grade_flips':{'L_to_W':35,'W_to_L':35},
         'old_portable_result_counts':dict(old_count),'corrected_portable_result_counts':dict(new_count),
         'source_archive_modified':False, 'quotes_and_probabilities_modified':False}
    (dest/'nov9_grade_ledger_manifest.json').write_text(json.dumps(stats,indent=2)+'\n')
    return stats

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('source_census');ap.add_argument('output_dir');args=ap.parse_args()
    print(json.dumps(run(args.source_census,args.output_dir),indent=2))
