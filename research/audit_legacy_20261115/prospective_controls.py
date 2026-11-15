#!/usr/bin/env python3
"""Fail-closed, read-only prospective SportsEdge audit controls.
The script only VALIDATES snapshots and EVALUATES already frozen predictions.
It does not select bets or change the SportsEdge engine. No internet/API dependencies.

Usage:
  python prospective_controls.py validate path/to/frozen_predictions.csv
  python prospective_controls.py evaluate path/to/frozen_predictions_with_results.csv
  python prospective_controls.py example-schema
"""
from __future__ import annotations
import csv,datetime as dt,hashlib,json,math,sys
from collections import Counter,defaultdict
from pathlib import Path

NEEDED=['event_id','sport','market','period','side','book','odds_american',
        'line','captured_at_utc','prediction_at_utc','event_start_utc','rules_activated_at_utc','max_quote_age_minutes',
        'feature_asof_utc','model_version','model_sha256','rules_version','rules_sha256',
        'model_p','status','source_receipt_id']
OPTIONAL=['player_id','team_id','date','event_final_at_utc','result','net_units',
          'best_available_odds','benchmark_closing_odds','projection_mean','projection_sd',
          'injury_asof_utc','roster_asof_utc','model_input_hash']

def ts(v):
    if not v:raise ValueError('missing UTC timestamp')
    t=dt.datetime.fromisoformat(v.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('naive timestamp')
    return t.astimezone(dt.timezone.utc)
def im(o):
    n=int(o)
    if abs(n)<100:raise ValueError('invalid odds')
    return 100/(100+n) if n>0 else -n/(100-n)
def win(o):return int(o)/100 if int(o)>0 else 100/-int(o)

def read(path):
    with open(path,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def check(path):
    rows=read(path);issues=[]
    if not rows:return {'admitted':0,'rejected':0,'issues':[{'row':0,'issue':'EMPTY_SOURCE'}]}
    for field in NEEDED:
        if field not in rows[0]:issues.append({'row':0,'issue':'MISSING_COLUMN:'+field})
    if any(i['row']==0 for i in issues):return {'admitted':0,'rejected':len(rows),'issues':issues,'status':'FAIL_CLOSED'}
    seen=set();admitted=0
    for i,r in enumerate(rows,2):
        err=[]
        for field in NEEDED:
            if not r.get(field):err.append('MISSING:'+field)
        try:
            capture,pred,start,features=[ts(r[x]) for x in ('captured_at_utc','prediction_at_utc','event_start_utc','feature_asof_utc')]
            if capture>=start:err.append('CAPTURE_AFTER_KICKOFF')
            if pred>=start:err.append('PREDICTION_AFTER_KICKOFF')
            if features>pred:err.append('FEATURE_FUTURE_ASOF')
            if capture>pred:err.append('ODDS_CAPTURE_AFTER_PREDICTION')
            if ts(r['rules_activated_at_utc'])>pred:err.append('RULESET_ACTIVATED_AFTER_PREDICTION')
            try:
                max_quote_age=float(r['max_quote_age_minutes'])
                if max_quote_age<=0:err.append('INVALID_QUOTE_FRESHNESS_LIMIT')
                if (pred-capture).total_seconds()/60 > max_quote_age:err.append('STALE_QUOTE_AT_PREDICTION')
            except (ValueError,TypeError):err.append('INVALID_QUOTE_FRESHNESS_LIMIT')
            for tfield in ('injury_asof_utc','roster_asof_utc'):
                if r.get(tfield) and ts(r[tfield])>pred:err.append(tfield+':LOOKAHEAD')
            # Historical close information can be used in postgame CLV only; never as a pregame feature.
        except (ValueError,KeyError) as e:err.append('INVALID_TIME:'+str(e))
        try:
            pp=float(r['model_p']);im(r['odds_american'])
            if not math.isfinite(pp) or not (0<pp<1):err.append('INVALID_PROBABILITY')
        except (ValueError,TypeError,KeyError):err.append('INVALID_PRICE_OR_PROBABILITY')
        for field in ('model_sha256','rules_sha256'):
            if len(r.get(field,''))!=64 or any(c not in '0123456789abcdefABCDEF' for c in r[field]):err.append('MISSING_OR_BAD_HASH:'+field)
        if r.get('status') not in ('CARD','PAPER','CLOSED','WITHHELD','MODEL_DOUBTED','NON_COUNTED'):
            err.append('UNKNOWN_STATUS')
        if 'PLAYER_PROP' in r.get('market','') and not r.get('player_id'):err.append('MISSING_PLAYER_ID')
        key=tuple(r.get(k) for k in ('event_id','period','market','side','line','player_id','captured_at_utc','book'))
        if key in seen:err.append('DUPLICATE_SNAPSHOT_KEY')
        seen.add(key)
        if err:
            for e in err:issues.append({'row':i,'issue':e})
        else:admitted+=1
    return {'admitted':admitted,'rejected':len(rows)-admitted,'issues':issues,'status':'PASS' if not issues else 'FAIL_CLOSED'}

def evaluate(path):
    admission=check(path)
    if admission['status']!='PASS':return admission
    rows=read(path)
    problems=[]
    for i,r in enumerate(rows,2):
        if not r.get('event_final_at_utc') or r.get('result') not in ('W','L','P'):
            problems.append({'row':i,'issue':'UNVERIFIED_OUTCOME'});continue
        try:
            if ts(r['event_final_at_utc'])<ts(r['event_start_utc']):problems.append({'row':i,'issue':'RESULT_BEFORE_START'})
        except ValueError:problems.append({'row':i,'issue':'INVALID_FINAL_TIME'})
    if problems:return {'status':'FAIL_CLOSED','issues':problems,'n':len(rows)}
    card=[r for r in rows if r['status']=='CARD'];n=len(card);net=[];brier=[];loss=[];wins=0
    for r in card:
        y=1 if r['result']=='W' else (0 if r['result']=='L' else None)
        net.append(win(r['odds_american']) if y==1 else (-1 if y==0 else 0))
        if y is not None:
            p=float(r['model_p']);brier.append((p-y)**2);loss.append(-y*math.log(p)-(1-y)*math.log(1-p));wins+=y
    # max drawdown REQUIRES original settlement timestamp for each result; use final time if exact provider supplies it.
    times=[ts(r['event_final_at_utc']) for r in card]
    if len(times)!=len(set(times)):
        drawdown='NOT_CERTIFIED: same-time settlement ties require a stable, predeclared ordering'
    else:
        ordered=sorted(zip(times,net));cum=0;peak=0;dd=0
        for t,u in ordered:
            cum+=u;peak=max(peak,cum);dd=min(dd,cum-peak)
        drawdown=dd
    return {'status':'RESULT_EVALUATED','card_n':n,'wins':wins,'losses':len(brier)-wins,
       'net_units':sum(net),'roi':sum(net)/n if n else None,'brier':sum(brier)/len(brier) if brier else None,
       'log_loss':sum(loss)/len(loss) if loss else None,'max_drawdown_units':drawdown,
       'caution':'Model comparisons require an independent market baseline with same-timestamp odds. Correlated selections must be clustered by event.'}

def main():
    if len(sys.argv)==2 and sys.argv[1]=='example-schema':
        print(','.join(NEEDED+OPTIONAL));return 0
    if len(sys.argv)!=3 or sys.argv[1] not in ('validate','evaluate'):
        print(__doc__);return 2
    res=check(sys.argv[2]) if sys.argv[1]=='validate' else evaluate(sys.argv[2]);print(json.dumps(res,indent=2))
    return 0 if res.get('status') in ('PASS','RESULT_EVALUATED') else 1
if __name__=='__main__':raise SystemExit(main())
