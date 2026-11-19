#!/usr/bin/env python3
"""CBB availability efficiency modifier: STRICT point-in-time, TRAIN-only shadow fit.

No sportsbook prices or production model calls. Every record is an externally
supplied claim, NOT independently authenticated evidence. Unknown statuses block.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import mean
from random import Random
from collections import Counter

REPO = Path(__file__).resolve().parents[2]
UTC = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$')
SHA = re.compile(r'^[0-9a-f]{64}$')
RIDGES = (0.01, 0.1, 1.0, 10.0, 100.0)  # preregistered before data fit
EVENT_KEYS = frozenset('event_id season home_id away_id conference_id forecast_utc tip_utc torvik_pub_utc torvik_cap_utc availability_pub_utc availability_cap_utc final_pub_utc final_cap_utc torvik_sha256 availability_sha256 final_sha256 venue venue_verified availability_census_complete home_p away_p poss home_final away_final players'.split())
PLAYER_KEYS = frozenset('player_id team_id status planned_minutes published_utc captured_utc source_sha256'.split())
VENUES = frozenset(('TRUE_HOME', 'NEUTRAL'))

class Blocked(ValueError):
    pass

def _time(x):
    if type(x) is not str or not UTC.fullmatch(x):
        raise Blocked('UTC_Z_TIME_REQUIRED')
    try:
        return datetime.fromisoformat(x[:-1] + '+00:00')
    except ValueError as exc:
        raise Blocked('INVALID_UTC_TIME') from exc

def _hash(x):
    if type(x) is not str or not SHA.fullmatch(x):
        raise Blocked('SOURCE_SHA256_INVALID')

def _num(x, low, high):
    if type(x) not in (float, int) or not math.isfinite(x) or not low <= x <= high:
        raise Blocked('BOUNDED_FINITE_NUMBER_REQUIRED')
    return float(x)

def parse_event(e, allowed_conferences):
    if type(e) is not dict or set(e) != EVENT_KEYS:
        raise Blocked('EXACT_EVENT_SCHEMA_REQUIRED_NO_ODDS_OR_LATE_FEATURES')
    if type(e['event_id']) is not str or not e['event_id'].strip():
        raise Blocked('EVENT_ID_REQUIRED')
    if type(e['season']) is not int or not 2000 <= e['season'] <= 2100:
        raise Blocked('SEASON_INVALID')
    if any(type(e[k]) is not str or not e[k].strip() for k in ('home_id','away_id','conference_id')):
        raise Blocked('TEAM_OR_CONFERENCE_ID_INVALID')
    if e['home_id'] == e['away_id'] or e['conference_id'] not in allowed_conferences:
        raise Blocked('UNAPPROVED_CONFERENCE_OR_TEAM_PAIR')
    if e['venue'] not in VENUES or e['venue_verified'] is not True:
        raise Blocked('VENUE_NOT_VERIFIED')
    if e['availability_census_complete'] is not True:
        raise Blocked('OFFICIAL_AVAILABILITY_CENSUS_INCOMPLETE')
    for field in ('torvik_sha256','availability_sha256','final_sha256'):
        _hash(e[field])
    times = {k:_time(e[k]) for k in ('forecast_utc','tip_utc','torvik_pub_utc',
        'torvik_cap_utc','availability_pub_utc','availability_cap_utc',
        'final_pub_utc','final_cap_utc')}
    if not (times['torvik_pub_utc'] <= times['torvik_cap_utc'] <= times['forecast_utc']
            < times['tip_utc'] < times['final_pub_utc'] <= times['final_cap_utc']):
        raise Blocked('TORVIK_OR_FINAL_LOOKAHEAD')
    if not (times['availability_pub_utc'] <= times['availability_cap_utc'] <= times['forecast_utc']):
        raise Blocked('AVAILABILITY_LOOKAHEAD')
    points = {k:_num(e[k],0,250) for k in ('home_p','away_p','home_final','away_final')}
    poss = _num(e['poss'],40,100)
    if type(e['players']) is not list:
        raise Blocked('PLAYER_CENSUS_REQUIRED')
    seen = set()
    missing = {e['home_id']:0.0,e['away_id']:0.0}
    all_planned = {e['home_id']:0.0,e['away_id']:0.0}
    for player in e['players']:
        if type(player) is not dict or set(player) != PLAYER_KEYS:
            raise Blocked('EXACT_PLAYER_SCHEMA_REQUIRED')
        if type(player['player_id']) is not str or not player['player_id'].strip():
            raise Blocked('PLAYER_ID_REQUIRED')
        team = player['team_id']
        key = (team,player['player_id'])
        if team not in missing or key in seen:
            raise Blocked('PLAYER_TEAM_OR_DUPLICATE_ID')
        seen.add(key)
        _hash(player['source_sha256'])
        if player['source_sha256'] != e['availability_sha256']:
            raise Blocked('PLAYER_SOURCE_HASH_MISMATCH')
        if not (_time(player['published_utc']) <= _time(player['captured_utc']) <= times['forecast_utc']):
            raise Blocked('PLAYER_STATUS_FUTURE_SOURCE')
        if player['status'] not in ('OUT','ACTIVE'):
            raise Blocked('UNFITTED_PARTICIPATION_STATUS')
        mins = _num(player['planned_minutes'],0,40)
        all_planned[team] += mins
        if player['status'] == 'OUT':
            missing[team] += mins
    if any(v > 200.000001 for v in all_planned.values()):
        raise Blocked('TEAM_MINUTES_EXCEED_200')
    return {'id':e['event_id'],'forecast':times['forecast_utc'],
            'tip':times['tip_utc'],'final_captured':times['final_cap_utc'],
            'venue':e['venue'],'poss':poss,'base':(points['home_p'],points['away_p']),
            'final':(points['home_final'],points['away_final']),
            'x':(missing[e['home_id']]/200,missing[e['away_id']]/200)}

def admit(rows, allowed_conferences):
    if type(rows) is not list or type(allowed_conferences) is not list or not allowed_conferences:
        raise Blocked('NONEMPTY_INPUT_AND_PREREGISTERED_CONFERENCE_ALLOWLIST_REQUIRED')
    if any(type(x) is not str or not x for x in allowed_conferences) or len(set(allowed_conferences)) != len(allowed_conferences):
        raise Blocked('INVALID_ALLOWLIST')
    counts = {}
    for r in rows:
        if type(r) is dict:
            key = r.get('event_id')
            if type(key) is str:
                counts[key] = counts.get(key,0)+1
    valid,rejected=[],[]
    for idx,row in enumerate(rows):
        try:
            if type(row) is dict and type(row.get('event_id')) is str and counts[row['event_id']] > 1:
                raise Blocked('DUPLICATE_EVENT_ALL_COPIES_BLOCKED')
            valid.append(parse_event(row,set(allowed_conferences)))
        except (Blocked,KeyError,ValueError,TypeError) as exc:
            rejected.append({'index':idx,'event_id':row.get('event_id') if type(row) is dict else None,'reason':str(exc)})
    return valid,rejected

def _design(events):
    output=[]
    for event in events:
        own,opp=event['x']
        scale=event['poss']/100.0
        hp,ap=event['base'];hf,af=event['final']
        output.extend([((scale*own,scale*opp), hf-hp),
                       ((scale*opp,scale*own), af-ap)])
    return output

def fit(events, ridge):
    a=b=c=d=e=0.0
    for (x,z),y in _design(events):
        a+=x*x; b+=x*z; c+=z*z; d+=x*y; e+=z*y
    a+=ridge;c+=ridge
    det=a*c-b*b
    if det<=1e-15:
        raise Blocked('SINGULAR_TRAINING_DESIGN')
    return ((c*d-b*e)/det,(a*e-b*d)/det)

def predict(event, coeff):
    own,opp=event['x']
    m=event['poss']/100.0
    hp,ap=event['base']
    return (hp+m*(coeff[0]*own+coeff[1]*opp),
            ap+m*(coeff[0]*opp+coeff[1]*own))

def scores(events, coeff=None):
    abs_err=[];sq=[]
    for event in events:
        pred = event['base'] if coeff is None else predict(event,coeff)
        for x,y in zip(pred,event['final']):
            abs_err.append(abs(x-y));sq.append((x-y)**2)
    return {'points_mae':round(mean(abs_err),6) if abs_err else None,
            'points_rmse':round(math.sqrt(mean(sq)),6) if sq else None}


def paired_event_bootstrap(events, coeff, *, repeats=1000, seed=0):
    """Paired game-cluster uncertainty; descriptive, not a release test.

    Both team results stay in the same resampled game. A game with alternate
    card legs never becomes additional independent statistical evidence.
    """
    n = len(events)
    if n < 30:
        return {'unique_games': n, 'interval_95': None,
                'reason': 'INSUFFICIENT_30_UNIQUE_EVENTS'}
    if type(repeats) is not int or repeats < 200 or repeats > 5000:
        raise Blocked('BOOTSTRAP_REPLICATIONS_INVALID')
    paired=[]
    for e in events:
        baseline=e['base']
        candidate=predict(e,coeff)
        actual=e['final']
        paired.append((
            sum(abs(p-y) for p,y in zip(baseline,actual)) / 2,
            sum(abs(p-y) for p,y in zip(candidate,actual)) / 2,
            sum((p-y)**2 for p,y in zip(baseline,actual)) / 2,
            sum((p-y)**2 for p,y in zip(candidate,actual)) / 2))
    rng=Random(seed)
    mae_deltas=[];rmse_deltas=[]
    for _ in range(repeats):
        sample=[paired[rng.randrange(n)] for _ in range(n)]
        mae_deltas.append(mean(x[0]-x[1] for x in sample))
        rmse_deltas.append(
            math.sqrt(mean(x[2] for x in sample)) -
            math.sqrt(mean(x[3] for x in sample)))
    def interval(values):
        values.sort()
        return [round(values[int(.025*(repeats-1))],6),
                round(values[int(.975*(repeats-1))],6)]
    return {'unique_games':n, 'bootstrap_repeats':repeats,
            'delta_sign':'baseline_minus_candidate_positive_improves',
            'mae_improvement':round(mean(x[0]-x[1] for x in paired),6),
            'mae_improvement_95':interval(mae_deltas),
            'rmse_improvement':round(
                math.sqrt(mean(x[2] for x in paired))-
                math.sqrt(mean(x[3] for x in paired)),6),
            'rmse_improvement_95':interval(rmse_deltas)}

def evaluate(rows, allowed_conferences, *, cutoff_utc, min_train=100, min_holdout=50):
    if (type(min_train) is not int or min_train < 100 or
            type(min_holdout) is not int or min_holdout < 50):
        raise Blocked('PREREGISTERED_100_TRAIN_AND_50_HOLDOUT_MINIMUMS')
    valid,rejected = admit(rows, allowed_conferences)
    cutoff=_time(cutoff_utc)
    train=sorted([r for r in valid if r['final_captured'] < cutoff],key=lambda x:(x['forecast'],x['id']))
    holdout=sorted([r for r in valid if r['forecast'] >= cutoff],key=lambda x:(x['forecast'],x['id']))
    excluded=len(valid)-len(train)-len(holdout)
    result={'status':'RESEARCH_ONLY_NOT_ADMITTED','original_rows':len(rows),
            'rejected':rejected, 'reject_counts':dict(Counter(r['reason'] for r in rejected)),
            'excluded_unreleased_at_cutoff':excluded,
            'train_n':len(train),'holdout_n':len(holdout),'source_authenticated':False,
            'market_close_compared':False,'production_ready':False,
            'official_counted':0,'stake_u':0}
    if len(train)<min_train or len(holdout)<min_holdout:
        result['reason']='INSUFFICIENT_PIT_TRAIN_OR_UNTOUCHED_HOLDOUT'
        return result
    cut=max(1,int(len(train)*.8))
    validation=train[cut:]
    earliest=min(r['forecast'] for r in validation)
    internal=[r for r in train[:cut] if r['final_captured'] < earliest]
    if len(internal)<max(1,int(min_train*.6)) or not validation:
        result['reason']='INSUFFICIENT_CHRONOLOGICAL_INNER_TRAIN'
        return result
    candidates=[]
    for ridge in RIDGES:
        coeff=fit(internal,ridge)
        candidates.append((scores(validation,coeff)['points_rmse'],ridge))
    _,chosen=min(candidates)
    coeff=fit(train,chosen)
    result.update(status='SHADOW_COEFFICIENTS_FITTED_NO_PROMOTION',ridge=chosen,
                  coeff_eff_own_absent=round(coeff[0],8),
                  coeff_eff_opponent_absent=round(coeff[1],8),
                  prior_only_validation_n=len(validation),
                  historical_baseline=scores(holdout),
                  heldout_candidate=scores(holdout,coeff),
                  paired_holdout_uncertainty=paired_event_bootstrap(holdout,coeff),
                  by_venue={v:{'n':sum(x['venue']==v for x in holdout),
                               'baseline':scores([x for x in holdout if x['venue']==v]),
                               'candidate':scores([x for x in holdout if x['venue']==v],coeff)}
                            for v in sorted(VENUES)},
                  warning='Not original-source authentication or market-close benchmark; no production use')
    return result

def _private_path(s):
    p=Path(os.path.abspath(s)).resolve()
    if p==REPO or REPO in p.parents:
        raise Blocked('RAW_EVIDENCE_OR_FITTED_REPORT_MUST_STAY_OUTSIDE_PUBLIC_GIT')
    return p

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_json')
    parser.add_argument('--report',required=True)
    parser.add_argument('--cutoff-utc',required=True)
    parser.add_argument('--conferences',required=True,
                        help='Frozen comma-separated official source policy allowlist; never inferred')
    a=parser.parse_args(argv)
    raw=_private_path(a.private_json).read_bytes()
    if not raw or len(raw)>20_000_000:
        raise Blocked('EMPTY_OR_OVERSIZE_PRIVATE_INPUT')
    rows=json.loads(raw)
    result=evaluate(rows,a.conferences.split(','),cutoff_utc=a.cutoff_utc)
    result['input_sha256']=hashlib.sha256(raw).hexdigest()
    output=_private_path(a.report)
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(output,flags,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(result,f,sort_keys=True,indent=2,allow_nan=False)
        f.write('\n')
        f.flush();os.fsync(f.fileno())
    print(json.dumps({k:result[k] for k in ('status','train_n','holdout_n','official_counted')},sort_keys=True))

if __name__=='__main__':
    main()
