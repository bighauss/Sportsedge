#!/usr/bin/env python3
"""Fail-closed NFL R1 results->ratings deterministic reproduction gate.

This confirms numerical lineage from an immutable supplied results CSV via the
pinned SportsEdge R1 model code to the ratings used for projection. It does NOT
independently authenticate NFL game outcomes, establish capture precommitment,
or certify betting edge. Historical/forward evidence stays PAPER 0u.
"""
import csv
import datetime as dt
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

MODEL_SHA='a06b857563221fd8b2b13639827aa0ddd5f39aa2ea1dd488cb25554f67ec7418'
REQUIRED=('sport','date','home','away','home_pts','away_pts','neutral')

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def check(history,model_code,ratings,asof):
    out={'status':'BLOCK','reasons':[],'results_rows':0,'reproduction_exact':False,'release_status':'PAPER_0U'}
    try:
        asof_date=dt.date.fromisoformat(asof)
        model_hash=digest(model_code);out['model_code_sha256']=model_hash
        if model_hash!=MODEL_SHA:
            out['reasons'].append('MODEL_CODE_SHA_NOT_APPROVED_R1');return out
        rows=[]
        with open(history,newline='',encoding='utf-8-sig') as f:
            reader=csv.DictReader(f,restkey=None,restval=None)
            cols=reader.fieldnames or []
            if len(cols)!=len(set(cols)) or not set(REQUIRED).issubset(cols):
                out['reasons'].append('HISTORY_SCHEMA_INVALID');return out
            for i,r in enumerate(reader,2):
                if None in r or any(v is None for v in r.values()):
                    out['reasons'].append('HISTORY_RAGGED_ROW_'+str(i));return out
                if r['sport']!='NFL' or not r['home'].strip() or not r['away'].strip() or r['home'].casefold().strip()==r['away'].casefold().strip():
                    out['reasons'].append('HISTORY_INVALID_IDENTITY_ROW_'+str(i));return out
                d=dt.date.fromisoformat(r['date'])
                if not d<asof_date:
                    out['reasons'].append('HISTORY_FUTURE_OR_ASOF_GAME_ROW_'+str(i));return out
                for p in ('home_pts','away_pts'):
                    if not r[p].strip().isdigit() or not 0<=int(r[p])<=150:
                        out['reasons'].append('HISTORY_SCORE_INVALID_ROW_'+str(i));return out
                if r['neutral'] not in ('0','1'):
                    out['reasons'].append('HISTORY_NEUTRAL_INVALID_ROW_'+str(i));return out
                rows.append(r)
        out['results_rows']=len(rows)
        if not rows:
            out['reasons'].append('HISTORY_EMPTY');return out
        identities=[(r['date'],r['home'].casefold().strip(),r['away'].casefold().strip()) for r in rows]
        if len(set(identities))!=len(identities):
            out['reasons'].append('HISTORY_DUPLICATE_GAME');return out
        out['results_sha256']=digest(history)
        out['rating_source_sha256']=digest(ratings)
        with tempfile.TemporaryDirectory(prefix='se_nfl_lineage_') as tmp:
            generated=Path(tmp)/'ratings.csv'
            cmd=[sys.executable,str(Path(model_code).resolve()),'fit',str(Path(history).resolve()),'--asof',asof_date.isoformat(),'--out',str(generated)]
            p=subprocess.run(cmd,cwd=tmp,capture_output=True,text=True,timeout=60)
            if p.returncode!=0 or not generated.is_file():
                out['reasons'].append('MODEL_R1_REFIT_FAILED');out['subprocess_exit']=p.returncode;return out
            out['recomputed_rating_sha256']=digest(generated)
            if generated.read_bytes()!=Path(ratings).read_bytes():
                out['reasons'].append('RATINGS_SOURCE_NOT_REPRODUCED');return out
        out['status']='PASS';out['reproduction_exact']=True
        return out
    except (OSError,UnicodeError,csv.Error,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
        out['reasons'].append('RESULTS_LINEAGE_INPUT_OR_RUNTIME:'+str(exc));return out
