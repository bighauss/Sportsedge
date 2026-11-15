#!/usr/bin/env python3
"""SportsEdge v5 fail-closed, hash-pinned candidate execution wrapper.

A reproducible *wrapper*, not an in-place engine patch. Fails the entire slate
on invalid rows, unverified full-slate coverage, projection disputes, and
wrong engine bytes. Explicit --research-anchor allows ANCHOR only for
non-counted diagnostic use. Leaves the v5 SHA and frozen model unmodified.
"""
import argparse,csv,hashlib,json,math,subprocess,sys,tempfile
from collections import Counter,defaultdict
from pathlib import Path
from sportsedge_board_guard_r1 import guard
from sportsedge_slate_reconciler_r1 import reconcile

V5_SHA='72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fail(reason):raise ValueError(reason)

def projection_check(rows, research_anchor=False):
    grouped=defaultdict(list)
    for r in rows:grouped[(r['sport'],r['home'],r['away'])].append(r)
    issues=[]; projected=0
    for (sport,home,away),game_rows in grouped.items():
        vals=set((r['home_proj'],r['away_proj']) for r in game_rows)
        if len(vals)!=1:issues.append({'game':f'{away} @ {home}','reason':'MIXED_GAME_PROJECTIONS'});continue
        hp,ap=next(iter(vals));empty=not hp and not ap
        if hp=='' and ap!='' or ap=='' and hp!='':
            issues.append({'game':f'{away} @ {home}','reason':'PARTIAL_GAME_PROJECTION'});continue
        if empty:
            if not research_anchor:issues.append({'game':f'{away} @ {home}','reason':'ANCHOR_FORBIDDEN_ON_VALIDATION_PATH'})
            continue
        if sport in ('UFC','DWCS'):
            if not (0<float(hp)<1):issues.append({'game':f'{home} vs {away}','reason':'FIGHT_PROB_INVALID'})
        else:
            if not all(math.isfinite(float(x)) and float(x)>0 for x in (hp,ap)):
                issues.append({'game':f'{away} @ {home}','reason':'SCORES_NONPOSITIVE'})
        projected+=1
    return {'games':len(grouped),'projected_games':projected,'anchor_games':len(grouped)-projected,'issues':issues}

def run_guarded(board,engine,output_dir,slate=None,research_anchor=False,run_engine=True):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    engine=Path(engine).resolve();board=Path(board).resolve()
    if digest(engine)!=V5_SHA:fail('V5_SHA_MISMATCH')
    valid=output_dir/'board_accepted.csv';excluded=output_dir/'board_excluded.csv';report=output_dir/'runner_report.json'
    gr=guard(board,valid,excluded)
    audit={'stage':'PREFLIGHT','input_board_sha256':digest(board),'engine_sha256':digest(engine),
           'guard':gr,'research_anchor':research_anchor,'slate_audit':None,'projection_check':None,
           'pricing_invoked':False,'validation_admitted':False,'verdict':'BLOCK'}
    if gr['excluded_rows']:
        audit['reason']='INPUT_GUARD_QUARANTINE';report.write_text(json.dumps(audit,indent=2)+'\n');return audit
    if slate:
        sl=reconcile(slate,[valid]);audit['slate_audit']=sl
        if sl['verdict']!='PASS':
            audit['reason']='SLATE_COVERAGE_MISSING';report.write_text(json.dumps(audit,indent=2)+'\n');return audit
    with valid.open(newline='') as f: rows=list(csv.DictReader(f))
    pc=projection_check(rows,research_anchor=research_anchor);audit['projection_check']=pc
    if pc['issues']:
        audit['reason']='PROJECTION_GATE_BLOCKED';report.write_text(json.dumps(audit,indent=2)+'\n');return audit
    if not run_engine:
        audit['verdict']='PREFLIGHT_PASS';report.write_text(json.dumps(audit,indent=2)+'\n');return audit
    with tempfile.TemporaryDirectory(prefix='sportsedge_v5_guard_') as tmp:
        # Writes picks.csv ONLY inside the scratch, never into original folder.
        p=subprocess.run([sys.executable,str(engine),str(valid)],cwd=tmp,capture_output=True,text=True,timeout=150)
        audit['pricing_invoked']=True;audit['engine_exit_code']=p.returncode
        (output_dir/'engine_stdout.txt').write_text(p.stdout)
        (output_dir/'engine_stderr.txt').write_text(p.stderr)
        if p.returncode!=0 or not (Path(tmp)/'picks.csv').is_file():
            audit['reason']='V5_EXECUTION_FAILED';report.write_text(json.dumps(audit,indent=2)+'\n');return audit
        priced=list(csv.DictReader((Path(tmp)/'picks.csv').open(newline='')))
        with (output_dir/'picks_research.csv').open('w',newline='') as f:
            data=(Path(tmp)/'picks.csv').read_bytes();f.write(data.decode())
        audit['priced_rows']=len(priced)
        modes=Counter(r['mode'] for r in priced);audit['mode_counts']=dict(modes)
        if not research_anchor and modes.get('ANCHOR',0):
            audit['reason']='ANCHOR_PRICES_IN_VALIDATION_RUN';report.write_text(json.dumps(audit,indent=2)+'\n');return audit
        input_games={(r['sport'],f"{r['away']} @ {r['home']}") for r in rows if r['sport'] not in ('UFC','DWCS','PGA')}
        output_games={(r['sport'],r['game']) for r in priced}
        audit['input_games']=len(input_games);audit['priced_games']=len(output_games)
        audit['games_without_price']=[list(x) for x in sorted(input_games-output_games)]
        if input_games-output_games:
            audit['reason']='SILENT_GAME_DROP';report.write_text(json.dumps(audit,indent=2)+'\n');return audit
        audit['verdict']='RESEARCH_RUN_COMPLETE';audit['reason']='NOT_OOS_VALIDATION_EVIDENCE'
    report.write_text(json.dumps(audit,indent=2)+'\n');return audit

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--board',required=True);p.add_argument('--engine',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--slate');p.add_argument('--research-anchor',action='store_true');p.add_argument('--preflight-only',action='store_true')
    a=p.parse_args();r=run_guarded(a.board,a.engine,a.output_dir,slate=a.slate,research_anchor=a.research_anchor,run_engine=not a.preflight_only)
    print(json.dumps({k:r.get(k) for k in ('verdict','reason','priced_rows','input_games','priced_games')}))
    if r['verdict'] not in ('RESEARCH_RUN_COMPLETE','PREFLIGHT_PASS'):raise SystemExit(2)
