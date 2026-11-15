#!/usr/bin/env python3
"""SportsEdge R1 fail-closed event/price/projection admission audit (standard library).

NEW snapshots only: never rewrite past model values or decisions. The caller supplies
PRE-EXISTING independently captured odds and model projections. Nothing is inferred
from the final score, from the closing price, or from other post-decision fields.
Passing structural checks is NOT authentication of a sportsbook offer or +EV.
"""
from __future__ import annotations
import argparse,csv,datetime as dt,hashlib,json,math,re
from collections import Counter,defaultdict
from decimal import Decimal,InvalidOperation
from pathlib import Path

REQUIRED=(
 'event_id','sport','book','market','period','side','odds_american',
 'snapshot_id','quote_id','quote_receipt_sha256','captured_at_utc','decision_at_utc',
 'game_start_utc','max_quote_age_minutes','model_prediction_at_utc','features_asof_utc',
 'rules_effective_at_utc','model_sha256','rules_sha256','model_version',
 'rules_version','projection_mode','projection_source_period','probability_type','model_p','model_push_p',
 'status','event_source_id','home_team_id','away_team_id','team_id','venue_id','neutral_site','venue_verified_at_utc',
 'source_model_home_proj','source_model_away_proj',
 'emitted_model_home_proj','emitted_model_away_proj')
VALID_SPORTS={'NFL','CFB','CBB','NBA','NHL','MLB','PGA','UFC'}
VALID_PERIODS={'FG','1H','1Q','2H','2Q','3Q','4Q'}
VALID_STATUS={'CARD','PAPER','WITHHELD','MODEL_DOUBTED','CLOSED','NON_COUNTED','RESEARCH'}
SIDES={'home','away','over','under','yes','no','draw'}
DEC=Decimal

def number(v,field):
    if v is None or str(v).strip()=='':raise ValueError('MISSING:'+field)
    try:n=DEC(str(v).strip())
    except (InvalidOperation,TypeError):raise ValueError('BAD_NUMBER:'+field)
    if not n.is_finite():raise ValueError('NONFINITE:'+field)
    return n

def utc(x,field):
    if not str(x or '').strip():raise ValueError('MISSING_TIME:'+field)
    try:t=dt.datetime.fromisoformat(str(x).replace('Z','+00:00'))
    except ValueError:raise ValueError('BAD_TIME:'+field)
    if t.tzinfo is None:raise ValueError('NAIVE_TIME:'+field)
    return t.astimezone(dt.timezone.utc)

def odds_break_even(odds):
    a=number(odds,'odds_american')
    if a!=a.to_integral_value() or abs(a)<100 or a==0:raise ValueError('BAD_ODDS')
    return DEC(100)/(DEC(100)+a) if a>0 else -a/(DEC(100)-a)

def odds_profit(odds):
    a=number(odds,'odds_american')
    odds_break_even(odds)
    return a/DEC(100) if a>0 else DEC(100)/(-a)

def expected_roi(model_p,odds,push=0,probability_type='unconditional_win'):
    p=number(model_p,'model_p');q=number(push,'model_push_p')
    if not (DEC(0)<=q<DEC(1) and DEC(0)<=p<=DEC(1)):
        raise ValueError('INVALID_PROBABILITIES')
    if probability_type=='conditional_on_no_push':
        pw=(DEC(1)-q)*p
    elif probability_type=='unconditional_win':
        pw=p
    else:raise ValueError('UNKNOWN_PROBABILITY_TYPE')
    if pw+q>DEC(1):raise ValueError('WIN_PLUS_PUSH_EXCEEDS_ONE')
    pl=DEC(1)-pw-q
    return pw*odds_profit(odds)-pl

def hash_valid(value):return bool(re.fullmatch('[0-9a-fA-F]{64}',str(value or '')))

def boolval(x, field):
    if str(x).lower() not in ('true','false'):raise ValueError('MISSING_OR_INVALID_BOOLEAN:'+field)
    return str(x).lower()=='true'

def checks(r):
    """Returns (fatal_errors, research_warnings, derived_measures)."""
    errors=[];warn=[];derived={}
    def error(code):errors.append(code)
    for k in REQUIRED:
        if str(r.get(k,'')).strip()=='':error('MISSING:'+k)
    if errors:return sorted(set(errors)),warn,derived
    for k in ('model_sha256','rules_sha256','quote_receipt_sha256'):
        if not hash_valid(r[k]):error('INVALID_SHA256:'+k)
    if r['sport'] not in VALID_SPORTS:error('UNKNOWN_SPORT')
    if r['home_team_id']==r['away_team_id']:error('SAME_HOME_AWAY_TEAM_ID')
    if r['team_id'] not in (r['home_team_id'],r['away_team_id']):error('TEAM_NOT_IN_EVENT')
    if r['projection_mode']=='PROJECTION':
        if not r.get('source_home_team_id') or not r.get('source_away_team_id'):error('MISSING_PROJECTION_TEAM_IDS')
        elif (r['source_home_team_id'],r['source_away_team_id'])!=(r['home_team_id'],r['away_team_id']):
            error('PROJECTION_TEAM_BINDING_MISMATCH')
    if r['period'] not in VALID_PERIODS:error('UNKNOWN_PERIOD')
    if r['side'].lower() not in SIDES:error('UNKNOWN_SIDE')
    if r['status'] not in VALID_STATUS:error('UNKNOWN_STATUS')
    if r['projection_mode'] not in ('PROJECTION','ANCHOR'):error('UNKNOWN_PROJECTION_MODE')
    if r['projection_source_period']!=r['period']:error('PROJECTION_PERIOD_MISMATCH')
    if r['market'].strip().lower() in ('unknown','') or 'close' in r['market'].lower():error('INVALID_MARKET')
    if r.get('actual_result') or r.get('final_score'):
        warn.append('POSTGAME_FIELDS_PRESENT_IGNORED_FOR_ADMISSION')
    try:
        capture=utc(r['captured_at_utc'],'captured_at_utc')
        decision=utc(r['decision_at_utc'],'decision_at_utc')
        start=utc(r['game_start_utc'],'game_start_utc')
        model=utc(r['model_prediction_at_utc'],'model_prediction_at_utc')
        feat=utc(r['features_asof_utc'],'features_asof_utc')
        rule=utc(r['rules_effective_at_utc'],'rules_effective_at_utc')
        venue_t=utc(r['venue_verified_at_utc'],'venue_verified_at_utc')
        if capture>decision:error('QUOTE_OBSERVED_AFTER_DECISION')
        if model>decision:error('MODEL_CREATED_AFTER_DECISION')
        if decision>=start:error('DECISION_NOT_BEFORE_START')
        if feat>model:error('FEATURE_LOOKAHEAD')
        if rule>decision:error('RULES_POSTDATED_DECISION')
        if venue_t>decision:error('VENUE_LOOKAHEAD')
        age=number(r['max_quote_age_minutes'],'max_quote_age_minutes')
        if age<=0:error('INVALID_MAX_QUOTE_AGE')
        if DEC(str((decision-capture).total_seconds()))/DEC(60)>age:error('STALE_QUOTE')
        for key in ('injury_asof_utc','roster_asof_utc','starter_asof_utc','news_asof_utc','projection_source_created_at_utc'):
            if r.get(key) and utc(r[key],key)>model:error('LOOKAHEAD:'+key)
    except ValueError as e:error(str(e))
    try:
        for k in ('source_model_home_proj','source_model_away_proj','emitted_model_home_proj','emitted_model_away_proj'):
            number(r[k],k)
        p_home=number(r['source_model_home_proj'],'source_model_home_proj')
        p_away=number(r['source_model_away_proj'],'source_model_away_proj')
        e_home=number(r['emitted_model_home_proj'],'emitted_model_home_proj')
        e_away=number(r['emitted_model_away_proj'],'emitted_model_away_proj')
        tol=DEC('0.000001')
        if abs(p_home-e_home)>tol or abs(p_away-e_away)>tol:
            error('PROJECTION_SOURCE_MISMATCH')
        # Site flag must be explicit and verified. A default False is not evidence of the venue.
        boolval(r['neutral_site'],'neutral_site')
        if r['projection_mode']=='PROJECTION' and not r.get('source_projection_sha256'):
            error('MISSING_SOURCE_PROJECTION_HASH')
        if r.get('source_projection_sha256') and not hash_valid(r['source_projection_sha256']):
            error('INVALID_SOURCE_PROJECTION_HASH')
        if r.get('model_home_margin'):
            if abs(number(r['model_home_margin'],'model_home_margin')-(e_home-e_away))>tol:
                error('MARGIN_DOES_NOT_MATCH_PROJECTIONS')
        if r.get('model_game_total'):
            if abs(number(r['model_game_total'],'model_game_total')-(e_home+e_away))>tol:
                error('TOTAL_DOES_NOT_MATCH_PROJECTIONS')
        if r.get('book_home_spread'):
            market_margin=-number(r['book_home_spread'],'book_home_spread')
            margin_gap=(e_home-e_away)-market_margin
            derived['model_vs_market_margin_gap']=str(margin_gap)
            if abs(margin_gap)>=DEC(6):warn.append('MARKET_DISAGREEMENT_MARGIN_6PT')
        elif r['sport'] in ('NFL','CFB','CBB','NBA') and r['market'].lower() in ('ml','moneyline'):
            error('ML_MISSING_PAIRED_BOOK_SPREAD')
        if r.get('book_game_total'):
            gap=e_home+e_away-number(r['book_game_total'],'book_game_total')
            derived['model_vs_market_total_gap']=str(gap)
            if abs(gap)>=DEC(6):warn.append('MARKET_DISAGREEMENT_TOTAL_6PT')
        if 'team_total' in r['market'].lower() or r['market'].upper() in ('HOME_TT','AWAY_TT'):
            if not r.get('book_team_total'):error('TEAM_TOTAL_MISSING_PAIRED_MARKET')
            elif r['side'].lower() in ('over','under'):
                if r.get('selection_team_position') not in ('home','away'):error('UNVERIFIED_TEAM_TOTAL_SIDE')
                else:
                    v=e_home if r['selection_team_position']=='home' else e_away
                    gap=v-number(r['book_team_total'],'book_team_total')
                    derived['model_vs_market_team_total_gap']=str(gap)
                    if abs(gap)>=DEC(6):warn.append('MARKET_DISAGREEMENT_TEAM_TOTAL_6PT')
        # A pre-registered 6-pt control flags *all* markets, not only spread rows.
        if any('MARKET_DISAGREEMENT' in w for w in warn):error('DISAGREEMENT_REVIEW_HOLD')
    except ValueError as e:error(str(e))
    try:
        p=number(r['model_p'],'model_p')
        if not (DEC(0)<=p<=DEC(1)):error('INVALID_MODEL_P')
        implied=odds_break_even(r['odds_american']);derived['raw_break_even']=str(implied)
        ev=expected_roi(r['model_p'],r['odds_american'],r['model_push_p'],r['probability_type'])
        derived['recomputed_ev_per_unit']=str(ev)
        if r.get('claimed_ev') not in ('',None):
            if abs(number(r['claimed_ev'],'claimed_ev')-ev)>DEC('0.000001'):
                error('EXPECTED_VALUE_MISMATCH')
    except ValueError as e:error(str(e))
    # Props MUST have canonical, point-in-time roster mappings; never infer a player from name similarity.
    market=r['market'].lower()
    if 'player' in market or 'prop' in market or market in ('attd','first_td','td_2plus'):
        if not r.get('player_id'):error('PLAYER_ID_MISSING')
        if not r.get('player_team_id') or not r.get('team_id'):error('PLAYER_TEAM_ID_MISSING')
        elif r['player_team_id']!=r['team_id']:error('PLAYER_TEAM_MISMATCH')
        if not r.get('roster_asof_utc'):error('ROSTER_ASOF_MISSING')
        if not r.get('roster_source_id'):error('ROSTER_SOURCE_MISSING')
    if r['sport']=='CFB' and market in ('ml','moneyline','spread','total','team_total'):
        if not r.get('starting_qb_id') or not r.get('starter_asof_utc'):
            error('CFB_STARTER_UNVERIFIED')
    if r.get('quote_verification')!='INDEPENDENT_RECEIPT_VERIFIED':
        # A hash & an assertion in the input file cannot prove the book really offered the quote.
        warn.append('EXTERNAL_QUOTE_NOT_INDEPENDENTLY_VERIFIED')
    return sorted(set(errors)),sorted(set(warn)),derived

def audit_rows(rows):
    if not rows:return {'status':'FAIL_CLOSED','summary':{'n':0},'rows':[]}
    results=[];seen_quotes=set();seen_selections=set()
    for i,r in enumerate(rows,2):
        errors,warnings,derived=checks(r)
        qkey=(r.get('book'),r.get('quote_id'))
        if all(qkey):
            if qkey in seen_quotes:errors.append('DUPLICATE_BOOK_QUOTE_ID')
            seen_quotes.add(qkey)
        # Missing identity cannot count as duplicate. Already rejected as MISSING.
        skey=(r.get('event_id'),r.get('book'),r.get('period'),r.get('market').strip().lower() if r.get('market') else '',
              r.get('side').strip().lower() if r.get('side') else '',r.get('line'),r.get('team_id'),r.get('player_id'),r.get('decision_at_utc'))
        if all(skey[j] for j in (0,1,2,3,4,8)):
            if skey in seen_selections:errors.append('DUPLICATE_SELECTION_DECISION')
            seen_selections.add(skey)
        results.append({'row':i,'snapshot_id':r.get('snapshot_id'),'errors':sorted(set(errors)),
                        'warnings':warnings,'derived':derived,
                        'structural_admitted':not bool(errors),
                        'official_countable':False})
    # Always paper: certified independent receipts, execution slips, and preregistered forward validation are outside this file.
    counts=Counter(x for a in results for x in a['errors'])
    return {'status':'PASS_STRUCTURAL_RESEARCH_ONLY' if all(not a['errors'] for a in results) else 'FAIL_CLOSED',
            'summary':{'n':len(results),'admitted_structurally':sum(a['structural_admitted'] for a in results),
                       'rejected':sum(bool(a['errors']) for a in results),'official_counted':0,'error_counts':dict(counts)},
            'rows':results,
            'scope':'Point-in-time STRUCTURAL gate only; not book quote authentication or profitability validation.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('snapshot_csv');ap.add_argument('--report',required=True);args=ap.parse_args()
    with Path(args.snapshot_csv).open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    report=audit_rows(rows);path=Path(args.report)
    if path.exists():raise SystemExit('REFUSE_OVERWRITE_EXISTING_AUDIT')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['summary'],indent=2))
    return 0 if report['status']=='PASS_STRUCTURAL_RESEARCH_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
