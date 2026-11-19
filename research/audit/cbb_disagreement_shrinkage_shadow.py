#!/usr/bin/env python3
"""CBB model-vs-market shrinkage shadow trial, STRICT chronological PIT.

Never feeds model projection, changes frozen v5, admits market certification or stakes.
Decision-time no-vig market p may be a pricing calibrator; later CLOSE is held
back for independent benchmarking and is NEVER passed into the shrinkage fit.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
import argparse
import json
import math
import os
from pathlib import Path
import re
from statistics import mean, stdev

REPO=Path(__file__).resolve().parents[2]
UTC=re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$')
DIGEST=re.compile(r'^[a-f0-9]{64}$')
FIELDS=frozenset('event_id market_family period selection_side settlement line venue forecast_utc tipoff_utc model_features_published_utc model_features_captured_utc model_fitted_until_utc decision_quote_published_utc decision_quote_captured_utc close_quote_published_utc close_quote_captured_utc final_published_utc final_captured_utc model_sha256 prior_sha256 decision_quote_sha256 close_quote_sha256 final_sha256 p_model p_prior p_market_decision p_market_close outcome'.split())
MARKETS=frozenset(('ML','SPREAD','TOTAL'))
PERIODS=frozenset(('FG','1H'))
VENUES=frozenset(('TRUE_HOME','NEUTRAL'))
GRID_A=(0.0,0.1,0.3,0.6,1.0)
GRID_B=(0.0,2.0,5.0,10.0,20.0) # preregistered; fit by train log-loss, no manual blend
PREREG_MIN_TRAIN=180
PREREG_MIN_HOLDOUT=50

class Rejected(ValueError):
    pass

def _time(s):
    if type(s) is not str or not UTC.fullmatch(s):
        raise Rejected('UTC_Z_TIMESTAMP_REQUIRED')
    try: return datetime.fromisoformat(s[:-1]+'+00:00')
    except ValueError as e: raise Rejected('INVALID_UTC_TIMESTAMP') from e

def _prob(p):
    if type(p) not in (int,float) or not math.isfinite(p) or not 0<p<1:
        raise Rejected('PROBABILITY_MUST_BE_OPEN_UNIT')
    return float(p)

def _row(r):
    if type(r) is not dict or set(r)!=FIELDS:
        raise Rejected('EXACT_FROZEN_DECISION_SCHEMA_REQUIRED')
    for k in ('event_id','selection_side','settlement'):
        if type(r[k]) is not str or not r[k].strip():
            raise Rejected('MARKET_IDENTITY_MISSING')
    if r['market_family'] not in MARKETS or r['period'] not in PERIODS:
        raise Rejected('MARKET_FAMILY_OR_PERIOD_UNSUPPORTED')
    if r['venue'] not in VENUES:
        raise Rejected('VENUE_UNVERIFIED')
    if r['selection_side'] not in ('HOME','AWAY','OVER','UNDER'):
        raise Rejected('SELECTION_SIDE_UNSUPPORTED')
    if r['market_family']=='ML' and r['line']!='':
        raise Rejected('MONEYLINE_MUST_HAVE_EMPTY_LINE')
    if r['market_family']!='ML':
        line=r['line']
        if type(line) is not str or not re.fullmatch(r'[+-]?\d+\.5',line):
            raise Rejected('ONLY_NO_PUSH_HALF_POINT_LINE_SUPPORTED')
        if (r['market_family']=='SPREAD' and r['selection_side'] not in ('HOME','AWAY')) or (r['market_family']=='TOTAL' and r['selection_side'] not in ('OVER','UNDER')):
            raise Rejected('SELECTION_INCOMPATIBLE_WITH_MARKET')
    else:
        if r['selection_side'] not in ('HOME','AWAY'):
            raise Rejected('MONEYLINE_TEAM_SELECTION_REQUIRED')
    if type(r['outcome']) is not int or r['outcome'] not in (0,1):
        raise Rejected('ONLY_SETTLED_BINARY_GRADES')
    for k in ('model_sha256','prior_sha256','decision_quote_sha256','close_quote_sha256','final_sha256'):
        if type(r[k]) is not str or not DIGEST.fullmatch(r[k]):
            raise Rejected('MISSING_OR_INVALID_SOURCE_SHA256')
    times={k:_time(r[k]) for k in (
        'forecast_utc','tipoff_utc','model_features_published_utc','model_features_captured_utc',
        'model_fitted_until_utc','decision_quote_published_utc','decision_quote_captured_utc',
        'close_quote_published_utc','close_quote_captured_utc','final_published_utc','final_captured_utc')}
    freeze=times['forecast_utc'];tip=times['tipoff_utc']
    if not (times['model_fitted_until_utc']<freeze<tip
            and times['model_features_published_utc']<=times['model_features_captured_utc']<=freeze
            and times['decision_quote_published_utc']<=times['decision_quote_captured_utc']<=freeze
            and times['close_quote_published_utc']<=times['close_quote_captured_utc']<tip
            and freeze<=times['close_quote_captured_utc']
            and tip<times['final_published_utc']<=times['final_captured_utc']):
        raise Rejected('LOOKAHEAD_OR_INVALID_BOOK_OR_RESULT_CLOCKS')
    probs=tuple(_prob(r[k]) for k in ('p_model','p_prior','p_market_decision','p_market_close'))
    return {'id':r['event_id'], 'family':r['market_family'],
            'identity':(r['event_id'],r['market_family'],r['period'],r['selection_side'],r['settlement'],r['line']),
            'venue':r['venue'],'forecast':freeze,'final_captured':times['final_captured_utc'],
            'p_model':probs[0],'p_prior':probs[1],'p_decision':probs[2],'p_close':probs[3],
            'outcome':r['outcome']}

def _key(r):
    if type(r) is dict and all(type(r.get(k)) is str for k in
          ('event_id','market_family','period','selection_side','settlement','line')):
        return tuple(r[k] for k in ('event_id','market_family','period','selection_side','settlement','line'))
    return None

def admit(rows):
    if type(rows) is not list:
        raise Rejected('FULL_LEDGER_LIST_REQUIRED')
    counts=Counter(k for r in rows if (k:=_key(r)) is not None)
    qualified=[];blocked=[]
    for i,r in enumerate(rows):
        try:
            if _key(r) is not None and counts[_key(r)]>1:
                raise Rejected('DUPLICATE_DECISION_ALL_COPIES_BLOCKED')
            qualified.append(_row(r))
        except (Rejected,ValueError,KeyError,TypeError,OverflowError) as e:
            blocked.append({'index':i,'reason':str(e),'event_id':r.get('event_id') if type(r) is dict else None})
    return qualified,blocked

def adjusted(p,q,a,b):
    return q+(p-q)*math.exp(-a-b*abs(p-q))

def _loss(p,y):
    p=max(1e-10,min(1-1e-10,p))
    return -y*math.log(p)-(1-y)*math.log1p(-p)

def _score(items,key):
    if not items:return {'n':0,'brier':None,'log_loss':None}
    return {'n':len(items),
       'brier':round(mean((x[key]-x['outcome'])**2 for x in items),8),
       'log_loss':round(mean(_loss(x[key],x['outcome']) for x in items),8)}

def _fit(train):
    # This grid is declared before holdout; no unrestricted market blending.
    return min(((a,b) for a in GRID_A for b in GRID_B),
       key=lambda ab:(mean(_loss(adjusted(x['p_model'],x['p_decision'],*ab),x['outcome'])
                         for x in train),ab))

def _event_ci(items, candidate, baseline):
    by=defaultdict(list)
    for x in items:
        by[x['id']].append((baseline(x)-candidate(x)))
    diff=[mean(v) for v in by.values()]
    if len(diff)<30:return None
    mu=mean(diff);rad=1.96*stdev(diff)/math.sqrt(len(diff))
    return [round(mu-rad,7),round(mu+rad,7)]

def evaluate(rows, *, cutoff_utc, min_train=PREREG_MIN_TRAIN,
             min_holdout=PREREG_MIN_HOLDOUT):
    cutoff=_time(cutoff_utc)
    qualified,blocked=admit(rows)
    report={'status':'PAPER_0U_RESEARCH_NO_PROMOTION','input_rows':len(rows),
            'eligible_rows':len(qualified),'blocked':blocked,
            'source_authenticated':False,'close_only_evaluation':True,
            'market_release_certified':False,'official_counted':0,'approved_stake_u':0,
            'families':{}}
    if type(min_train) is not int or min_train<20 or type(min_holdout) is not int or min_holdout<10:
        raise Rejected('MINIMUM_FOLD_SIZE_WEAK')
    grouped=defaultdict(list)
    for x in qualified:grouped[x['family']].append(x)
    for fam, all_rows in sorted(grouped.items()):
        training=[x for x in all_rows if x['final_captured']<cutoff]
        heldout=[x for x in all_rows if x['forecast']>=cutoff]
        excluded=len(all_rows)-len(training)-len(heldout)
        result={'train_n':len(training),'holdout_n':len(heldout),
                'train_unique_events':len({x['id'] for x in training}),
                'holdout_unique_events':len({x['id'] for x in heldout}),
                'intermediate_cutoff_excluded':excluded,
                'status':'INSUFFICIENT_CHRONOLOGICAL_MATCHED_EVENTS'}
        report['families'][fam]=result
        if (len({x['id'] for x in training})<min_train
                or len({x['id'] for x in heldout})<min_holdout):
            continue
        training.sort(key=lambda x:(x['forecast'],x['id']))
        split=int(.8*len(training))
        internal=training[:split]
        validation=training[split:]
        first_val=min(x['forecast'] for x in validation)
        internal=[x for x in internal if x['final_captured']<first_val]
        if (len({x['id'] for x in internal})<max(10,int(.6*min_train))):
            result['status']='INNER_FIT_OUTCOME_NOT_RELEASED_BEFORE_VALIDATION'
            continue
        a,b=_fit(internal)
        for x in heldout:
            x['p_candidate']=adjusted(x['p_model'],x['p_decision'],a,b)
        def brier(k):
            return lambda x:(x[k]-x['outcome'])**2
        c=brier('p_candidate')
        res={'status':'SHADOW_HOLDOUT_EVALUATED_NO_ADOPTION','fit_a':a,'fit_b':b,
             'inner_fit_n':len(internal),'inner_validation_n':len(validation),
             'inner_validation_candidate_brier':round(mean((adjusted(x['p_model'],x['p_decision'],a,b)-x['outcome'])**2 for x in validation),8),
             'candidate':_score(heldout,'p_candidate'),
             'prior_model':_score(heldout,'p_prior'),
             'market_close':_score(heldout,'p_close'),
             'market_decision':_score(heldout,'p_decision'),
             'unshrunk_model':_score(heldout,'p_model'),
             'candidate_vs_prior_brier_event_cluster95':_event_ci(heldout,c,brier('p_prior')),
             'candidate_vs_close_brier_event_cluster95':_event_ci(heldout,c,brier('p_close')),
             'gap_slices':{},'venues':{}}
        for name,selector in {
            'gap_lt_5pp':lambda x:abs(x['p_model']-x['p_decision'])<.05,
            'gap_5_to_10pp':lambda x:.05<=abs(x['p_model']-x['p_decision'])<.1,
            'gap_10_to_20pp':lambda x:.1<=abs(x['p_model']-x['p_decision'])<.2,
            'gap_ge_20pp':lambda x:abs(x['p_model']-x['p_decision'])>=.2,
            'model_above':lambda x:x['p_model']>x['p_decision'],
            'model_below_equal':lambda x:x['p_model']<=x['p_decision']}.items():
            slice_rows=[x for x in heldout if selector(x)]
            res['gap_slices'][name]={'candidate':_score(slice_rows,'p_candidate'),
                                    'prior':_score(slice_rows,'p_prior'),
                                    'close':_score(slice_rows,'p_close'),
                                    'unique_events':len({x['id'] for x in slice_rows})}
        for venue in sorted(VENUES):
            these=[x for x in heldout if x['venue']==venue]
            res['venues'][venue]={'candidate':_score(these,'p_candidate'),
                                 'prior':_score(these,'p_prior'),
                                 'close':_score(these,'p_close')}
        result.update(res)
    report['warning']='All source clock, venue, original odds and prior-model receipts are self-asserted. Close is eval-only. Event CIs descriptive; no multiple-test promotion decision or +EV claim.'
    return report

def _private_path(p):
    lexical=Path(os.path.abspath(p));resolved=lexical.resolve()
    if any(x==REPO or REPO in x.parents for x in (lexical,resolved)):
        raise Rejected('CONFIDENTIAL_INPUT_OR_REPORT_INSIDE_PUBLIC_REPO')
    if any(x.is_symlink() for x in (lexical,*lexical.parents)):
        raise Rejected('PRIVATE_SYMLINK_FORBIDDEN')
    return lexical

def _unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise Rejected('DUPLICATE_JSON_KEY')
        d[k]=v
    return d

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('private_json');p.add_argument('--report',required=True)
    p.add_argument('--cutoff-utc',required=True)
    a=p.parse_args(argv)
    raw=_private_path(a.private_json).read_bytes()
    if not raw or len(raw)>20_000_000:raise Rejected('EMPTY_OR_OVERSIZE_SOURCE')
    rows=json.loads(raw,object_pairs_hook=_unique,
                    parse_constant=lambda v:(_ for _ in ()).throw(Rejected('NONFINITE_JSON')))
    report=evaluate(rows,cutoff_utc=a.cutoff_utc)
    report['input_sha256']=sha256(raw).hexdigest()
    output=_private_path(a.report)
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(report,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
        f.flush();os.fsync(f.fileno())
    print(json.dumps({'status':report['status'],'input_rows':report['input_rows'],
                      'eligible_rows':report['eligible_rows']},sort_keys=True))

if __name__=='__main__':main()
