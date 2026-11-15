#!/usr/bin/env python3
"""Research-only starter baseline for COUNT player props (e.g. catches, assists).

This is a deliberately simple Poisson opportunity × efficiency baseline, NOT a
SportsEdge production model or a claimed betting edge. Never guess missing inputs.
No past outcomes of the target contest are read; all game logs must precede
prediction_at_utc; roster, injury, opponent and minutes projections must be
snapshotted independently before the contest.

Usage: python prop_research_baseline.py game_logs.csv frozen_prop_request.json

Required game log columns: player_id, team_id, event_id, event_start_utc,
  event_final_at_utc, minutes, opportunities, counting_stat
Required request fields: player_id, team_id, event_id, event_start_utc,
  prediction_at_utc, projected_minutes, projected_opportunities_per_minute,
  projected_efficiency_per_opportunity, opponent_multiplier, line, direction,
  odds_american, roster_verified_at_utc, feature_asof_utc

No cross-player identity join or chance-based default is allowed. This code is
for measured candidate validation only. No model, threshold, or historical pick
is modified by running it.
"""
import csv,datetime as dt,json,math,sys,statistics


def time(s):
    t=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('Timestamp needs UTC/offset')
    return t

def poisson_cdf(k,lam):
    # Stable enough for typical low-count player props; refuse extreme / yardage use.
    if lam <=0 or lam>=100:raise ValueError('Poisson baseline supports 0<mean<100; use another frozen family for high-volume stats')
    if k<0:return 0.
    term=math.exp(-lam);tot=term
    for j in range(1,k+1):term*=lam/j;tot+=term
    return min(1.,tot)

def calc(logs,req):
    required=['player_id','team_id','event_id','event_start_utc','prediction_at_utc',
              'projected_minutes','projected_opportunities_per_minute','projected_efficiency_per_opportunity',
              'opponent_multiplier','line','direction','odds_american','roster_verified_at_utc','feature_asof_utc']
    miss=[k for k in required if req.get(k) in (None,'')]
    if miss:raise ValueError('Missing real pregame inputs: '+','.join(miss))
    predict=time(req['prediction_at_utc']);game=time(req['event_start_utc'])
    if predict>=game:raise ValueError('Prediction not pregame')
    if time(req['feature_asof_utc'])>predict or time(req['roster_verified_at_utc'])>predict:raise ValueError('Lookahead in feature/roster timestamp')
    p_id=req['player_id'];team=req['team_id'];seen=set();hist=[]
    for r in logs:
        if not {'player_id','team_id','event_id','event_start_utc','event_final_at_utc','minutes','opportunities','counting_stat'}.issubset(r):
            raise ValueError('Game logs missing required fields')
        if r['player_id']!=p_id:continue
        if r['event_id'] in seen:raise ValueError('Duplicate player game ID')
        seen.add(r['event_id'])
        if time(r['event_start_utc'])>=game:continue
        if time(r['event_final_at_utc'])>predict:continue   # known only after result available
        if float(r['minutes'])<0 or float(r['opportunities'])<0 or float(r['counting_stat'])<0:raise ValueError('Negative historical raw stat')
        if float(r['counting_stat'])>float(r['opportunities']):raise ValueError('Counting stat exceeds opportunities')
        if float(r['minutes'])==0:continue
        if r['team_id']!=team:raise ValueError('Historical player/team change requires explicit identity mapping; do not auto blend')
        hist.append(r)
    if len(hist)<10:raise ValueError('At least 10 eligible, pregame-released player games required, found '+str(len(hist)))
    hist.sort(key=lambda r:time(r['event_start_utc']),reverse=True)
    recent=hist[:20]
    mins=sum(float(r['minutes']) for r in recent)
    opps=sum(float(r['opportunities']) for r in recent)
    successes=sum(float(r['counting_stat']) for r in recent)
    if mins<=0 or opps<=0:raise ValueError('Missing opportunity volume')
    observed_oppspm=opps/mins;observed_eff=successes/opps
    # This baseline uses preregistered OUT-OF-SAMPLE request projections, not
    # observed rate as an excuse to backfill missing projected features.
    projected_minutes=float(req['projected_minutes']);opp_rate=float(req['projected_opportunities_per_minute']);
    efficiency=float(req['projected_efficiency_per_opportunity']);opp_mult=float(req['opponent_multiplier'])
    if not (0<projected_minutes<=60 and 0<opp_rate<100 and 0<=efficiency<=1 and 0<opp_mult<=3):
        raise ValueError('Input range invalid; not allowed to clamp unseen data silently')
    mu=projected_minutes*opp_rate*efficiency*opp_mult
    if not (0<mu<100):raise ValueError('Projected mean out of range')
    line=float(req['line']);direction=req['direction'].upper()
    if direction not in ('OVER','UNDER'):raise ValueError('Need over/under')
    # For integer counts: if integer line, exact equality is a push; for .5 lines no push.
    k=math.floor(line)
    p_over=1-poisson_cdf(k,mu)
    p_under=poisson_cdf(math.ceil(line)-1,mu)
    p_push=poisson_cdf(int(line),mu)-poisson_cdf(int(line)-1,mu) if line.is_integer() else 0.
    pw,pl=(p_over,p_under) if direction=='OVER' else (p_under,p_over)
    price=int(req['odds_american'])
    if price==0 or abs(price)<100:raise ValueError('Invalid American odds')
    profit=(price/100 if price>0 else 100/-price)
    return {'status':'UNVALIDATED_RESEARCH_PAPER_0U', 'player_id':p_id,'team_id':team,'event_id':req['event_id'],
            'pre_kickoff':True,'n_historical_games_used':len(recent),'historical_opportunities_per_minute':opps/mins,
            'historical_efficiency_per_opportunity':successes/opps,
            'projected_mean':mu,'projected_median':'NOT_COMPUTED',
            'Poisson_p_over':p_over,'Poisson_p_under':p_under,'Poisson_p_push':p_push,
            'selection':direction+' '+str(line),'win_p_unconditional':pw,'lose_p_unconditional':pl,
            'estimated_ev_per_dollar':pw*profit-pl,
            'explicit_warning':'Poisson baseline ignores overdispersion and will need a completely unseen validation window; not a production recommendation'}

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit(__doc__)
    with open(sys.argv[1],newline='') as f:logs=list(csv.DictReader(f))
    print(json.dumps(calc(logs,json.load(open(sys.argv[2]))),indent=2))
