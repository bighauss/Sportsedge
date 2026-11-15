#!/usr/bin/env python3
"""Candidate R1: mandatory receipt+identity preflight BEFORE inherited v5 wrapper.

Fail closed. Uses the unmodified v5 SHA 72ccaad7...; new outputs PAPER/0u.
Needs original board with event/quote IDs AND paired one-side receipt snapshots.
The original 2026-11-11 legacy boards cannot meet this contract; no backfill.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,sys
from pathlib import Path
from integrity_gate import audit_rows,number,utc
from closing_pair_guard import convert_two_sided,selection_key

V5_SHA='72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f'

def read(path):
    with open(path,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def validate_linkage(board,receipts,engine_hash):
    """Every priced board endpoint is linked to exactly one already-receipted side."""
    problems=[];pair_endpoints=[]
    by_quote={}
    for i,r in enumerate(receipts,2):
        if r.get('model_sha256')!=engine_hash:problems.append({'source':'receipt','row':i,'error':'MODEL_SHA_NOT_PINNED_TO_V5'})
        key=(r.get('book'),r.get('quote_id'))
        if key in by_quote:problems.append({'source':'receipt','row':i,'error':'DUPLICATE_BOOK_QUOTE_ID'})
        by_quote[key]=r
    used=set()
    for i,r in enumerate(board,2):
        try:
            # Conversion enforces 2-sided contract and timestamps. It will
            # reject legacy lines without event IDs, not infer them from team names.
            sides=convert_two_sided(r)
            if str(r.get('home_proj') or '').strip()=='' or str(r.get('away_proj') or '').strip()=='':
                raise ValueError('BOARD_MISSING_OWN_SCORE_PROJECTIONS')
            for side in sides:
                key=(side['book'],side['quote_id'])
                snap=by_quote.get(key)
                if snap is None:raise ValueError('PRICE_ENDPOINT_HAS_NO_FROZEN_RECEIPT')
                if key in used:raise ValueError('RECEIPT_REUSED_BY_MULTIPLE_BOARD_ROWS')
                used.add(key)
                if selection_key(snap)!=selection_key(side):raise ValueError('RECEIPT_MARKET_OR_SELECTION_MISMATCH')
                if int(number(snap['odds_american'],'odds_american'))!=int(number(side['odds_american'],'odds_american')):
                    raise ValueError('BOARD_QUOTE_PRICE_DIFFERS_FROM_RECEIPT')
                if utc(snap['captured_at_utc'],'captured_at_utc')!=utc(side['captured_at_utc'],'captured_at_utc'):
                    raise ValueError('BOARD_QUOTE_TIME_DIFFERS_FROM_RECEIPT')
                if (number(snap['emitted_model_home_proj'],'emitted_model_home_proj')!=number(r['home_proj'],'home_proj') or
                    number(snap['emitted_model_away_proj'],'emitted_model_away_proj')!=number(r['away_proj'],'away_proj')):
                    raise ValueError('BOARD_PROJECTION_DIFFERS_FROM_FROZEN_RECEIPT')
                pair_endpoints.append(key)
        except (ValueError,KeyError) as e:
            problems.append({'source':'board','row':i,'error':str(e)})
    missing=set(by_quote)-used
    for book,qid in sorted(missing):problems.append({'source':'receipt','quote_id':qid,'error':'UNUSED_RECEIPT_OR_BOARD_COVERAGE_GAP'})
    return {'verdict':'PASS' if not problems else 'FAIL_CLOSED','board_rows':len(board),
            'receipt_rows':len(receipts),'matched_endpoints':len(used),'issues':problems}

def preread(board_path,snapshot_path,engine_path):
    digest=hashlib.sha256(Path(engine_path).read_bytes()).hexdigest()
    b,r=read(board_path),read(snapshot_path)
    admitted=audit_rows(r)
    join=validate_linkage(b,r,digest)
    issues=[]
    if digest!=V5_SHA:issues.append('V5_ENGINE_HASH_MISMATCH')
    if admitted['status']!='PASS_STRUCTURAL_RESEARCH_ONLY':issues.append('POINT_IN_TIME_ADMISSION_FAILED')
    if join['verdict']!='PASS':issues.append('BOARD_RECEIPT_JOIN_FAILED')
    return {'verdict':'PREFLIGHT_PASS_RESEARCH_ONLY' if not issues else 'BLOCK',
       'issues':issues,'engine_sha256':digest,'board_sha256':hashlib.sha256(Path(board_path).read_bytes()).hexdigest(),
       'receipt_file_sha256':hashlib.sha256(Path(snapshot_path).read_bytes()).hexdigest(),
       'row_admission':admitted,'board_linkage':join,'official_counted':0}

def run(board_path,snapshot_path,engine_path,output_dir,run_engine=False,slate=None):
    target=Path(output_dir).resolve()
    if target.exists():raise FileExistsError('REFUSE_OVERWRITE_EXISTING_OUTPUT_DIR')
    target.mkdir(parents=True)
    rep=preread(board_path,snapshot_path,engine_path)
    (target/'preflight.json').write_text(json.dumps(rep,indent=2)+'\n')
    if rep['verdict']=='BLOCK' or not run_engine:return rep
    # Load the existing read-only guarded engine only AFTER receipt admission.
    # R3 wrapper's v5 SHA and input guard operate independently of this R1 layer.
    from importlib import util
    root=Path(__file__).resolve().parents[2]/'r5'/'nfl'
    if not (root/'sportsedge_guarded_v5_runner_r3.py').exists():
        raise RuntimeError('EXISTING_R3_GUARDED_ENGINE_WRAPPER_NOT_PACKAGED')
    sys.path.insert(0,str(root))
    from sportsedge_guarded_v5_runner_r3 import run_guarded
    res=run_guarded(board_path,engine_path,target/'guarded_v5',slate=slate,run_engine=True)
    rep['guarded_v5_verdict']=res.get('verdict');rep['guarded_v5_reason']=res.get('reason')
    rep['verdict']='RESEARCH_ONLY_RUN_COMPLETE' if res.get('verdict')=='RESEARCH_RUN_COMPLETE' else 'BLOCK'
    (target/'execution_receipt.json').write_text(json.dumps(rep,indent=2)+'\n')
    return rep

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--board',required=True);ap.add_argument('--snapshot',required=True)
    ap.add_argument('--engine',required=True);ap.add_argument('--output-dir',required=True)
    ap.add_argument('--run-engine',action='store_true');ap.add_argument('--slate')
    a=ap.parse_args();result=run(a.board,a.snapshot,a.engine,a.output_dir,a.run_engine,a.slate)
    print(json.dumps({k:result[k] for k in ('verdict','issues','official_counted')},indent=2))
    raise SystemExit(0 if result['verdict'].startswith(('PREFLIGHT_PASS','RESEARCH_ONLY_RUN')) else 2)
