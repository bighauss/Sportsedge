#!/usr/bin/env python3
"""Prospective research-only baseline and ablation harness; never edits the original model.

Input must be a standalone, pre-registered features CSV with:
  event_id,event_start_utc,feature_asof_utc,label_available_at_utc,target,market_no_vig_p,
  plus numeric feature columns explicitly supplied on CLI.

This harness refuses samples where any feature timestamp exceeds event start, where
train outcome was not available before the test prediction, or the same event crosses folds.
NO model is trained on the existing SportsEdge files because their detailed point-in-time
features and event chronology are not present.

Usage: python walkforward_research.py frozen_event_features.csv pace,efficiency,injury 150 20
"""
import csv,datetime as dt,sys,json,statistics,math
from pathlib import Path

def ts(v):
    z=dt.datetime.fromisoformat(v.replace('Z','+00:00'))
    if not z.tzinfo:raise ValueError('no timezone')
    return z

def run(path,feature_names,min_train=150,step=20):
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
    except ImportError as e:raise SystemExit('Research requires numpy and scikit-learn: '+str(e))
    with open(path,newline='') as f:rows=list(csv.DictReader(f))
    needed=['event_id','event_start_utc','feature_asof_utc','label_available_at_utc','target','market_no_vig_p',*feature_names]
    if not rows or any(x not in rows[0] for x in needed):raise ValueError('Missing columns in preregistered features dataset')
    ids=[r['event_id'] for r in rows]
    if len(ids)!=len(set(ids)):raise ValueError('Exactly one independent event per training row required')
    for r in rows:
        if ts(r['feature_asof_utc']) >= ts(r['event_start_utc']):raise ValueError('post-start feature')
        if float(r['target']) not in (0,1):raise ValueError('target must be binary')
        if any(x in ('result','closing_odds','postgame_score','target') for x in feature_names):raise ValueError('target leakage')
        for col in feature_names:
            try:float(r[col]) if r[col] else None
            except ValueError:raise ValueError('Non-numeric feature '+col)
    rows.sort(key=lambda r:ts(r['event_start_utc']))
    folds=[]
    for start in range(min_train,len(rows),step):
        test=rows[start:start+step]
        if not test:break
        cutoff=min(ts(r['event_start_utc']) for r in test)
        train=[r for r in rows[:start] if ts(r['label_available_at_utc']) < cutoff]
        if len(train)<min_train:continue
        if not {0,1}.issubset({int(x['target']) for x in train}):continue
        def X(rs,cols):return [[float(r[c]) if r[c] else float('nan') for c in cols] for r in rs]
        y=[int(r['target']) for r in train];yt=[int(r['target']) for r in test]
        case={}
        for name,cols in [('all',feature_names)]+[(f'drop_{c}',[f for f in feature_names if f!=c]) for c in feature_names]:
            if not cols:continue
            model=Pipeline([('impute',SimpleImputer(strategy='median')),('model',LogisticRegression(max_iter=1000))])
            model.fit(X(train,cols),y);pred=model.predict_proba(X(test,cols))[:,1].tolist()
            case[name]={'brier':statistics.mean((a-b)**2 for a,b in zip(pred,yt)),'log_loss':statistics.mean(-b*math.log(max(a,1e-9))-(1-b)*math.log(max(1-a,1e-9)) for a,b in zip(pred,yt))}
        base=[float(r['market_no_vig_p']) for r in test]
        case['market_no_vig_baseline']={'brier':statistics.mean((a-b)**2 for a,b in zip(base,yt)),
            'log_loss':statistics.mean(-b*math.log(max(a,1e-9))-(1-b)*math.log(max(1-a,1e-9)) for a,b in zip(base,yt))}
        folds.append({'test_start_utc':cutoff.isoformat(),'train_n':len(train),'test_n':len(test),'scores':case})
    return {'status':'RESEARCH_ONLY_NO_DEPLOY','n_events':len(rows),'n_folds':len(folds),'folds':folds,'critical_note':'Never choose ablations or thresholds on these test folds; all results are exploratory and require a later untouched test period.'}

if __name__=='__main__':
    if len(sys.argv)!=5:raise SystemExit(__doc__)
    print(json.dumps(run(sys.argv[1],sys.argv[2].split(','),int(sys.argv[3]),int(sys.argv[4])),indent=2))
