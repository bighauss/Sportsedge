#!/usr/bin/env python3
"""One-command, *research-only* NFL pipeline: completed scores -> ratings ->
projections -> pinned v5 guards -> research picks. Nothing places wagers.

Requires a user/capture-supplied DK board and independent full-slate manifest;
this tool contains NO sportsbook scraper or credential integration and does not
establish entry/close provenance. Results must predate --asof-ct. Output is
create-only: it will never overwrite an earlier run or receipt.

Example:
  python sportsedge_run_it_nfl_r1.py \\
    --board fixtures/board_2026-11-12_1808CT_NFL_WAS.csv \\
    --slate fixtures/nfl_slate_from_20261112_0901CT_DK_scan.csv \\
    --history fixtures/nfl_games_2026_thru_20261109.csv \\
    --captured-utc 2026-11-12T18:08:00-06:00 \\
    --asof-ct 2026-11-10T00:00:00-06:00 \\
    --engine sportsedge_v5.py \\
    --model-code sportsedge_nfl_ratings_r1_CLAUDE.py --out output
"""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from sportsedge_nfl_results_lineage_r1 import MODEL_SHA
from sportsedge_nfl_daily_lane_r5 import V5_SHA, run

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run_once(board,slate,history,captured_utc,asof_ct,engine,model_code,out,preflight_only=False):
    output=Path(out).resolve()
    # A prior evidence record must never be overwritten, even by --preflight-only.
    try:output.mkdir(parents=True,exist_ok=False)
    except FileExistsError:
        return {'status':'BLOCK','reasons':['OUTPUT_ALREADY_EXISTS_UNCHANGED'],'release_status':'PAPER_0U','out':str(output)}
    report={'status':'BLOCK','reasons':[],'release_status':'PAPER_0U',
            'admission':False,'placed_bets':0,'engine_unchanged':True,'preflight_only':preflight_only}
    try:
        inputs={'board':board,'slate':slate,'history':history,'engine':engine,'model_code':model_code}
        report['input_sha256']={k:sha(v) for k,v in inputs.items()}
        if report['input_sha256']['engine']!=V5_SHA:
            report['reasons']=['ENGINE_SHA_MISMATCH'];return report
        if report['input_sha256']['model_code']!=MODEL_SHA:
            report['reasons']=['MODEL_CODE_SHA_MISMATCH'];return report
        timestamp=dt.datetime.fromisoformat(asof_ct)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            report['reasons']=['ASOF_TIME_NO_OFFSET'];return report
        capture=dt.datetime.fromisoformat(captured_utc)
        if capture.tzinfo is None or capture.utcoffset() is None or not(timestamp<capture):
            report['reasons']=['CAPTURE_CLOCK_NOT_AFTER_MODEL_ASOF'];return report
        ratings=output/'nfl_ratings_generated.csv'
        scoresdir=output/'generated_scores';scoresdir.mkdir(exist_ok=False)
        cmds=[
            [sys.executable,str(Path(model_code).resolve()),'fit',str(Path(history).resolve()),'--asof',timestamp.date().isoformat(),'--out',str(ratings)],
            [sys.executable,str(Path(model_code).resolve()),'scores',str(ratings),'--board',str(Path(board).resolve()),'--slate',str(Path(slate).resolve()),'--asof-ct',asof_ct,'--captured-ct',captured_utc,'--out-dir',str(scoresdir)]
        ]
        for idx,cmd in enumerate(cmds,1):
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=90,cwd=str(output))
            (output/f'model_stage_{idx}.stdout.txt').write_text(proc.stdout)
            (output/f'model_stage_{idx}.stderr.txt').write_text(proc.stderr)
            if proc.returncode!=0:
                report['reasons']=['OWN_MODEL_STAGE_FAILED_'+str(idx)];return report
        scores=scoresdir/'nfl_scores.csv'
        if not scores.is_file() or not ratings.is_file():
            report['reasons']=['OWN_MODEL_OUTPUT_ABSENT'];return report
        report['generated_sha256']={'ratings':sha(ratings),'projections':sha(scores)}
        result=run(board,scores,ratings,captured_utc,engine,slate,output/'guarded_lane',
                   preflight_only=preflight_only,history_file=history,model_code=model_code)
        report['lane_verdict']=result['verdict']
        report['lane_report_sha256']=sha(output/'guarded_lane'/'nfl_daily_lane_report.json')
        report['results_to_ratings_lineage']=result.get('results_to_ratings_lineage',{})
        report['source_recomputation']=result.get('source_recomputation',{})
        report['pricing_invoked']=result.get('pricing_invoked',False)
        report['research_picks']=result.get('guarded_runner',{}).get('priced_rows',0)
        if result['verdict'] in ('PREFLIGHT_PASS','RESEARCH_RUN_COMPLETE'):
            report['status']=result['verdict']
        else:
            report['reasons']=result.get('refusals',[]) or ['LANE_REJECTED']
        return report
    except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired,ImportError) as e:
        report['reasons']=['PIPELINE_INPUT_OR_RUNTIME:'+type(e).__name__+':'+str(e)]
        return report
    finally:
        (output/'RUN_RECEIPT.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')

def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('board','slate','history','captured-utc','asof-ct','engine','model-code','out'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--preflight-only',action='store_true')
    args=p.parse_args(argv)
    z=run_once(args.board,args.slate,args.history,args.captured_utc,args.asof_ct,args.engine,args.model_code,args.out,args.preflight_only)
    print(json.dumps({'status':z['status'],'reasons':z.get('reasons',[]),'release_status':z['release_status'],'research_picks':z.get('research_picks',0)}))
    return 0 if z['status'] in ('PREFLIGHT_PASS','RESEARCH_RUN_COMPLETE') else 2

if __name__=='__main__':raise SystemExit(main())
