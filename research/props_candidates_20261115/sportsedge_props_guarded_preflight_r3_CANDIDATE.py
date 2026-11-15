#!/usr/bin/env python3
"""SportsEdge player-prop fail-closed preflight (RESEARCH CANDIDATE, not production).

Launches the unchanged v0.4 numeric candidate ONLY after identity / CSV / numeric checks
pass. A blocked run creates no output file. Affected-game quarantine is NOT supported
until an immutable event_id is present on every board/roster/OUT record, so any
identity ambiguity blocks the entire invocation. No promotions/bets are authorized.

Usage:
 python sportsedge_props_guarded_preflight_r3_CANDIDATE.py board.csv players.csv \
   --engine sportsedge_props_v0_4_identitywarn_CANDIDATE.py --rosters roster.csv \
   [--outlist outs.csv] [--teams teams.csv] --out output.csv [--receipt receipt.json]

No IDs in the legacy v0.4 schema: PASS means safe enough to execute for PAPER tests,
NOT identity/provenance-admitted. Missing athlete IDs and event-time source manifests
still block promotion regardless of a successful preflight.
"""
import argparse, csv, json, math, pathlib, subprocess, sys, unicodedata

KNOWN_ALIASES = {'NOP':'NO','BRK':'BKN','UTA':'UTAH','SAS':'SA','GSW':'GS'}
DATA_COLS = {'players':['sport','player','team','games','minutes','pts','reb','ast','threes'],
             'rosters':['team','player','minutes','pts','reb','ast','threes'],
             'board':['sport','player','team','market'],
             'outlist':['player']}
NUMERIC_COLS = ['minutes','pts','reb','ast','threes']

def norm(s):
    s = unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode()
    return ''.join(c for c in s.lower() if c.isalnum())

def team(t): return KNOWN_ALIASES.get((t or '').strip().upper(),(t or '').strip().upper())

def read_csv(path,label,issues,require=True):
    if not path:
        if require: issues.append({'code':'MISSING_FILE','where':label})
        return []
    try:
        with open(path,encoding='utf-8-sig',newline='') as fh:
            reader=csv.DictReader(fh)
            fields=reader.fieldnames or []
            for field in DATA_COLS[label]:
                if field not in fields: issues.append({'code':'MISSING_COLUMN','where':label,'field':field})
            if len(fields)!=len(set(fields)):
                issues.append({'code':'DUPLICATE_HEADER','where':label})
            rows=list(reader)
    except (OSError,UnicodeError,csv.Error) as exc:
        issues.append({'code':'CSV_READ_ERROR','where':label,'reason':str(exc)[:150]});return []
    if not rows: issues.append({'code':'EMPTY_FILE','where':label});return []
    for idx,r in enumerate(rows,2):
        if None in r: issues.append({'code':'EXTRA_CELLS','where':label,'row':idx})
        for k in DATA_COLS[label]:
            if not (r.get(k) or '').strip():
                issues.append({'code':'BLANK_REQUIRED','where':label,'row':idx,'field':k})
    return rows

def audit(board_file,players_file,roster_file,out_file):
    issues=[]
    board=read_csv(board_file,'board',issues)
    players=read_csv(players_file,'players',issues)
    roster=read_csv(roster_file,'rosters',issues,require=True)
    outs=read_csv(out_file,'outlist',issues,require=False) if out_file else []
    byp={}; byr={}; outkeys=set()
    for label,rows,target in [('players',players,byp),('rosters',roster,byr)]:
        for idx,r in enumerate(rows,2):
            key=norm(r.get('player'))
            if not key:
                issues.append({'code':'INVALID_NAME','where':label,'row':idx});continue
            if key in target:
                issues.append({'code':'DUPLICATE_OR_COLLIDING_IDENTITY','where':label,'row':idx,'player':r.get('player'),
                               'previous_player':target[key].get('player'),'previous_team':target[key].get('team')})
            else: target[key]=r
            for field in NUMERIC_COLS:
                raw=(r.get(field) or '').strip()
                try: value=float(raw)
                except (ValueError,TypeError): value=float('nan')
                if not math.isfinite(value) or (field=='minutes' and value<0) or (field!='minutes' and value<0):
                    issues.append({'code':'INVALID_NUMERIC','where':label,'row':idx,'field':field,'value':raw})
    for key,p in byp.items():
        r=byr.get(key)
        if r is not None and team(p.get('team'))!=team(r.get('team')):
            issues.append({'code':'PLAYERS_ROSTER_TEAM_MISMATCH','player':p.get('player'),
                           'players_team':p.get('team'),'roster_team':r.get('team')})
    for idx,r in enumerate(board,2):
        if (r.get('sport') or '').upper()!='NBA':continue
        key=norm(r.get('player'));p=byp.get(key)
        if p is None:
            issues.append({'code':'BOARD_PLAYER_UNMATCHED','row':idx,'player':r.get('player')});continue
        if team(r.get('team'))!=team(p.get('team')):
            issues.append({'code':'BOARD_TEAM_MISMATCH','row':idx,'player':r.get('player'),
                           'board_team':r.get('team'),'players_team':p.get('team')})
    for idx,r in enumerate(outs,2):
        key=norm(r.get('player'))
        if key in outkeys:
            issues.append({'code':'DUPLICATE_OUT','row':idx,'player':r.get('player')})
        outkeys.add(key)
        if key not in byp and key not in byr:
            issues.append({'code':'UNMATCHED_OUT','row':idx,'player':r.get('player')})
        elif key in byp and key not in byr:
            issues.append({'code':'OUT_NOT_IN_ROSTER','row':idx,'player':r.get('player')})
    return issues,{'board_rows':len(board),'players_rows':len(players),'roster_rows':len(roster),
                   'outs_rows':len(outs),'identity_basis':'normalized_name_only_UNVERIFIED',
                   'admission':'PAPER_0u','production_approved':False}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('board');ap.add_argument('players');ap.add_argument('--engine',required=True)
    ap.add_argument('--rosters',required=True);ap.add_argument('--outlist');ap.add_argument('--teams')
    ap.add_argument('--out',required=True);ap.add_argument('--receipt')
    a=ap.parse_args()
    issues,meta=audit(a.board,a.players,a.rosters,a.outlist)
    receipt={'status':'BLOCK' if issues else 'PAPER_PREFLIGHT_PASS',
             'issues':issues,'meta':meta,'engine':'v0.4_candidate_unchanged'}
    out=pathlib.Path(a.out)
    if issues:
        # Never leave a prior successful output where downstream can mistake it for fresh.
        if out.exists():out.unlink()
        print(json.dumps(receipt,indent=2),file=sys.stderr)
        if a.receipt:pathlib.Path(a.receipt).write_text(json.dumps(receipt,indent=2)+'\n')
        return 2
    cmd=[sys.executable,a.engine,a.board,a.players,'--rosters',a.rosters,'--out',a.out]
    if a.outlist:cmd+=['--outlist',a.outlist]
    if a.teams:cmd+=['--teams',a.teams]
    cp=subprocess.run(cmd,check=False)
    if cp.returncode!=0:
        if out.exists():out.unlink()
        receipt['status']='ENGINE_FAILED';receipt['engine_returncode']=cp.returncode
    if a.receipt:pathlib.Path(a.receipt).write_text(json.dumps(receipt,indent=2)+'\n')
    return cp.returncode

if __name__=='__main__':sys.exit(main())
