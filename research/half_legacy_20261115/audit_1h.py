#!/usr/bin/env python3
"""SportsEdge 1H audit. Read-only; does NOT publish cards or change the engine.

Inputs are authentic point-in-time 1H model/market snapshots and independently
verified 1H scores. Never fill missing outcomes or probabilities.
"""
import argparse, csv, datetime as dt, json, math, statistics as st
from collections import Counter
from pathlib import Path

FIELDS = ('game_id', 'game_date', 'sport', 'away', 'home', 'captured_ct', 'kickoff_ct',
          'model_1h_total', 'book_1h_total', 'model_1h_margin_home',
          'book_1h_home_spread', 'flagged_1h_total')
RESULT_FIELDS = ('game_id', 'game_date', 'home_1h_points', 'away_1h_points')


def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):
        return None


def read_csv(path, fields):
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        missing=set(fields)-set(reader.fieldnames or ())
        if missing: raise ValueError(f'{path}: missing columns: {sorted(missing)}')
        return list(reader)


def parse_time(value):
    try:
        t=dt.datetime.fromisoformat(value.strip().replace('Z','+00:00'))
        return t if t.tzinfo is not None else None
    except (ValueError, AttributeError): return None


def mean(xs): return round(st.mean(xs),4) if xs else None

def rmse(xs): return round(math.sqrt(st.mean(x*x for x in xs)),4) if xs else None

def wilson(k,n,z=1.959963984540054):
    if not n: return None
    p=k/n; den=1+z*z/n
    middle=(p+z*z/(2*n))/den
    arm=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return [round(max(0,middle-arm),4),round(min(1,middle+arm),4)]


def safe_share(k,n): return {'n':n,'yes':k,'rate':round(k/n,4) if n else None,'wilson_95':wilson(k,n)}


def exact_binomial_vs_half(k,n):
    # Two-sided exact test against 50% solely; not a test of selection bias.
    if not n: return None
    tail=sum(math.comb(n,i) for i in range(0,min(k,n-k)+1))/2**n
    return round(min(1.,2*tail),6)


def prepare(rows):
    valid={}; issues=Counter()
    for r in rows:
        cap=parse_time(r['captured_ct']); start=parse_time(r['kickoff_ct'])
        if not cap or not start: issues['missing_or_unzoned_capture_or_kickoff']+=1; continue
        if cap >= start: issues['not_pregame']+=1; continue
        if (r.get('sport') or '').upper() not in ('CFB','CBB'):
            issues['wrong_sport']+=1; continue
        if not r['game_id'].strip() or not r['game_date'].strip():
            issues['missing_game_identity']+=1;continue
        # Store at most one independently captured pregame snapshot per game.
        key=(r['game_date'],r['sport'].upper(),r['game_id'])
        if key in valid:
            old_cap=parse_time(valid[key]['captured_ct'])
            if cap<=old_cap: issues['older_or_same_snapshot_ignored']+=1;continue
            issues['older_snapshot_replaced']+=1
        valid[key]=r
    return valid,issues


def report(snapshots, scores):
    picked,issues=prepare(snapshots)
    out={'status':'PAPER / 0u; no validated betting edge',
         'sources':{'snapshots_input':len(snapshots),'unique_pregame_games':len(picked),'scored_rows':len(scores)},
         'quality_exclusions_and_dedup':dict(issues)}
    valid_scores={}; score_issues=Counter()
    for r in scores:
        key=(r['game_date'],r['game_id'])
        a=num(r['away_1h_points']); h=num(r['home_1h_points'])
        if a is None or h is None or a<0 or h<0 or not a.is_integer() or not h.is_integer():
            score_issues['invalid_half_scores']+=1; continue
        if key in valid_scores:
            score_issues['duplicate_result_identity']+=1
            if valid_scores[key] != (a,h): score_issues['conflicting_results']+=1
            continue
        valid_scores[key]=(a,h)
    out['result_quality']=dict(score_issues)
    total_rows=[];spread_rows=[];flags=[];dog_under=[]
    for (date,sport,gid),r in picked.items():
        score=valid_scores.get((date,gid)); mt=num(r['model_1h_total']);bt=num(r['book_1h_total'])
        mm=num(r['model_1h_margin_home']);bs=num(r['book_1h_home_spread'])
        flag=(r['flagged_1h_total'] or '').strip().lower()
        if flag not in ('','none','over','under'): issues['bad_flag_label']+=1; flag='none'
        if mt is not None and bt is not None:
            lean='under' if mt<bt else 'over' if mt>bt else 'equal'
            total_rows.append((sport,gid,lean,flag,mt,bt,score))
            if flag in ('over','under'):flags.append((sport,gid,flag,lean))
        if mm is not None and bs is not None and score is not None:
            a,h=score;spread_rows.append((sport,gid,r['away'],r['home'],mm,bs,h-a))
        if bt is not None and bs is not None and score is not None and bs!=0:
            a,h=score
            under=(a+h<bt); over=(a+h>bt)
            # book home spread is NEGATIVE for home favorite
            dog_margin=(a-h)-bs if bs<0 else (h-a)+bs
            dogcover=(dog_margin>0); dogpush=(dog_margin==0)
            if under or over:
                if not dogpush: dog_under.append((sport,abs(bs),dogcover,under,gid))
    out['total_direction']={}
    for sport in ('ALL','CFB','CBB'):
        t=[row for row in total_rows if sport=='ALL' or row[0]==sport]
        f=[row for row in flags if sport=='ALL' or row[0]==sport]
        eligible=[x for x in t if x[2] in ('under','over')]
        out['total_direction'][sport]={
            'model_lean_under_all_evaluated':safe_share(sum(x[2]=='under' for x in eligible),len(eligible)),
            'under_among_flagged':safe_share(sum(x[2]=='under' for x in f),len(f)),
            'flag_vs_model_direction_mismatch':sum(x[2]!=x[3] for x in f),
            'caution':'Counts unique game snapshots; both sides of a sportsbook market are not separate trials.'}
    out['total_calibration']={}
    for sport in ('ALL','CFB','CBB'):
        subset=[x for x in total_rows if x[6] is not None and (sport=='ALL' or x[0]==sport)]
        model_errors=[x[4]-sum(x[6]) for x in subset]
        market_errors=[x[5]-sum(x[6]) for x in subset]
        gaps=[x[4]-x[5] for x in subset]
        out['total_calibration'][sport]={
            'n':len(subset),'model_minus_actual_mean':mean(model_errors),
            'model_vs_actual_mae':mean([abs(v) for v in model_errors]),'model_vs_actual_rmse':rmse(model_errors),
            'book_midpoint_vs_actual_mae':mean([abs(v) for v in market_errors]),
            'book_midpoint_vs_actual_rmse':rmse(market_errors),
            'model_minus_book_mean':mean(gaps),'model_minus_book_abs_mean':mean([abs(v) for v in gaps]),
            'warn':'Descriptive unless a strictly forward, date-locked independent sample is supplied.'}
    out['spread_calibration']={}
    for name,fn in [('ALL',lambda r:True),('CFB',lambda r:r[0]=='CFB'),('CBB',lambda r:r[0]=='CBB'),
                    ('BC (historical team subset)',lambda r:r[0]=='CFB' and any('boston college' in s.lower() for s in r[2:4])),
                    ('Purdue (historical team subset)',lambda r:r[0]=='CFB' and any('purdue' in s.lower() for s in r[2:4]))]:
        sub=[r for r in spread_rows if fn(r)];me=[r[4]-r[6] for r in sub];be=[-r[5]-r[6] for r in sub]
        out['spread_calibration'][name]={'n':len(sub),'model_home_margin_bias':mean(me),'model_mae':mean([abs(x) for x in me]),
            'model_rmse':rmse(me),'book_margin_mae':mean([abs(x) for x in be]),'book_margin_rmse':rmse(be)}
    out['underdog_cover_and_under_joint']={}
    for name,fn in [('ALL',lambda r:True),('CFB',lambda r:r[0]=='CFB'),('CBB',lambda r:r[0]=='CBB'),
                    ('CFB_underdog_spread_12.5_to_20.5',lambda r:r[0]=='CFB' and 12.5<=r[1]<=20.5)]:
        sub=[r for r in dog_under if fn(r)];n=len(sub)
        both=sum(r[2] and r[3] for r in sub);cover=sum(r[2] for r in sub);under=sum(r[3] for r in sub)
        expected=(cover*under/n) if n else None
        den=math.sqrt(cover*(n-cover)*under*(n-under)) if n else 0
        phi=(both*n-cover*under)/den if den else None
        out['underdog_cover_and_under_joint'][name]={
            'n_nonpush':n,'both_hit':both,'cover_count':cover,'under_count':under,
            'both_rate':safe_share(both,n),'expected_both_if_independent_count':round(expected,3) if expected is not None else None,
            'phi_association':round(phi,4) if phi is not None else None,
            'under_given_cover':safe_share(both,cover),
            'warning':'Historical association, not a validated BC same-game parlay price; stratify by total, spread, season and market.'}
    out['quality_exclusions_and_dedup']=dict(issues)
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--snapshots',required=True,help='1H snapshot CSV (see template)')
    p.add_argument('--scores',required=True,help='independently verified first-half score CSV')
    p.add_argument('--output',default='1h_audit_report.json')
    a=p.parse_args()
    result=report(read_csv(a.snapshots,FIELDS),read_csv(a.scores,RESULT_FIELDS))
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':a.output,'games':result['sources']['unique_pregame_games'],
         'scored_totals':result['total_calibration']['ALL']['n'],
         'scored_spreads':result['spread_calibration']['ALL']['n'],'status':result['status']},indent=2))

if __name__=='__main__':main()
