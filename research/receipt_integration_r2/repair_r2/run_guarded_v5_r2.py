#!/usr/bin/env python3
"""R2 receipt-bytes + R1 claim/market/temporal gate + unchanged v5 runner.

Not a production adapter. Only a research execution can be performed; no wagers.
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'repair_r1'))
from guarded_v5_receipt_runner import run as r1_run
from receipt_evidence_gate import audit_evidence

def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(board,snapshot,receipts,engine,output_dir,execute=False,slate=None):
    dest=Path(output_dir).resolve()
    dest.mkdir(parents=True,exist_ok=False)
    initial={'board':file_sha(board),'snapshot':file_sha(snapshot),'engine':file_sha(engine)}
    evidence=audit_evidence(snapshot,receipts)
    report={'stage':'R2','verdict':'BLOCK','evidence':evidence,'initial_hashes':initial,
            'engine_invoked':False,'official_counted':0,'research_only':True}
    (dest/'receipt_evidence_report.json').write_text(json.dumps(report,indent=2)+'\n')
    if evidence['verdict']!='BYTE_LINKAGE_PASS_NOT_PROVIDER_AUTHENTICATED':return report
    # The R1 wrapper still enforces structural evidence, source model/venue,
    # v5 pin, spread consistency and entire-board receipt linkage.
    r1=r1_run(board,snapshot,engine,dest/'r1_research',run_engine=execute,slate=slate)
    report['r1_preflight_verdict']=r1['verdict']
    report['engine_invoked']=r1['verdict']=='RESEARCH_ONLY_RUN_COMPLETE'
    final={k:file_sha(v) for k,v in [('board',board),('snapshot',snapshot),('engine',engine)]}
    report['final_hashes']=final
    if final != initial:report['verdict']='BLOCK_SOURCE_MUTATED_DURING_RUN'
    elif execute and r1['verdict']=='RESEARCH_ONLY_RUN_COMPLETE':
        report['verdict']='RESEARCH_EXECUTED_NOT_DEPLOYED'
    elif not execute and r1['verdict']=='PREFLIGHT_PASS_RESEARCH_ONLY':
        report['verdict']='R2_PREFLIGHT_PASS_RESEARCH_ONLY'
    else:report['verdict']='BLOCK'
    (dest/'receipt_evidence_report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--board',required=True);p.add_argument('--snapshot',required=True)
    p.add_argument('--receipt-dir',required=True);p.add_argument('--engine',required=True)
    p.add_argument('--output-dir',required=True);p.add_argument('--slate');p.add_argument('--execute-research',action='store_true')
    a=p.parse_args();r=run(a.board,a.snapshot,a.receipt_dir,a.engine,a.output_dir,a.execute_research,a.slate)
    print(json.dumps({k:r[k] for k in ('verdict','engine_invoked','official_counted')},indent=2))
    raise SystemExit(0 if r['verdict'].startswith(('R2_PREFLIGHT_PASS','RESEARCH_EXECUTED')) else 2)
