#!/usr/bin/env python3
"""Normalize two-sided SportsEdge/DK snapshots into ID-keyed one-side prices.

NO fallback to team-name joins, NO post-kickoff price, NO backfilled quote time.
A 'close' is the last RECEIPTED pre-start price; it is never an engine input.
Research-only price arithmetic / CLV reporting, not line availability proof.
"""
from __future__ import annotations
import csv,datetime as dt,json,re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from integrity_gate import number,utc,odds_break_even,hash_valid


def market_kind(value):
    s=str(value).strip().upper().replace(' ', '_')
    period='FG'
    for prefix in ('1H_','1Q_','2H_','2Q_','3Q_','4Q_'):
        if s.startswith(prefix):period=prefix[:-1];s=s[len(prefix):];break
    if s not in ('SPREAD','ML','TOTAL','HOME_TT','AWAY_TT'):
        raise ValueError('UNSUPPORTED_TWO_SIDED_MARKET:'+s)
    return period,s


def linear(v):
    d=number(v,'line')
    return str(d.normalize()) if d else '0'


def convert_two_sided(row):
    """Explicit book contract: price_a = home/over, price_b = away/under.
    This function never guesses event/line/timestamp/roster identity.
    """
    required=('event_id','sport','book','home_team_id','away_team_id','market','price_a','price_b',
              'captured_at_utc','game_start_utc','quote_id_a','quote_id_b','receipt_sha_a','receipt_sha_b')
    for k in required:
        if not str(row.get(k) or '').strip():raise ValueError('MISSING:'+k)
    cap=utc(row['captured_at_utc'],'captured_at_utc');start=utc(row['game_start_utc'],'game_start_utc')
    if cap>=start:raise ValueError('AFTER_KICKOFF')
    if row['home_team_id']==row['away_team_id']:raise ValueError('SAME_HOME_AWAY_ID')
    if not hash_valid(row['receipt_sha_a']) or not hash_valid(row['receipt_sha_b']):
        raise ValueError('MISSING_RECEIPT_HASH')
    odds_break_even(row['price_a']);odds_break_even(row['price_b'])
    period,market=market_kind(row['market'])
    # Explicit period in its own field may not conflict with market prefixed period.
    if row.get('period') and row['period']!=period:raise ValueError('PERIOD_CONFLICT')
    if market!='ML' and str(row.get('line') or '').strip()=='':raise ValueError('MISSING_LINE')
    line='0' if market=='ML' else linear(row['line'])
    if market=='SPREAD':
        side_a,side_b='home','away';line_a,line_b=line,linear(-number(line,'line'))
        team_a,team_b=row['home_team_id'],row['away_team_id']
    elif market=='ML':
        side_a,side_b='home','away';line_a,line_b='0','0'
        team_a,team_b=row['home_team_id'],row['away_team_id']
    else:
        side_a,side_b='over','under';line_a=line_b=line
        team_a=team_b=(row['home_team_id'] if market=='HOME_TT' else row['away_team_id'] if market=='AWAY_TT' else '')
    out=[]
    for price,qid,receipt,side,ln,team in [
        (row['price_a'],row['quote_id_a'],row['receipt_sha_a'],side_a,line_a,team_a),
        (row['price_b'],row['quote_id_b'],row['receipt_sha_b'],side_b,line_b,team_b)]:
        out.append({'event_id':row['event_id'],'sport':row['sport'],'book':row['book'],
            'market':market,'period':period,'side':side,'team_id':team,'player_id':'',
            'line':ln,'odds_american':str(int(number(price,'odds'))),
            'captured_at_utc':utc(row['captured_at_utc'],'captured_at_utc').isoformat(),
            'game_start_utc':utc(row['game_start_utc'],'game_start_utc').isoformat(),
            'quote_id':qid,'receipt_sha256':receipt})
    return out


def selection_key(r):
    """Works for canonical one-side snapshots and normalized display strings."""
    e=str(r.get('event_id') or '').strip()
    if not e:raise ValueError('EVENT_ID_REQUIRED')
    sport=str(r.get('sport') or '').strip().upper()
    market=str(r.get('market') or '').strip().upper().replace(' ','_')
    per=str(r.get('period') or 'FG').strip().upper()
    side=str(r.get('side') or '').strip().lower()
    if side not in ('home','away','over','under','yes','no','draw'):raise ValueError('SIDE_REQUIRED')
    line='0' if market=='ML' else linear(r.get('line'))
    player=str(r.get('player_id') or '').strip()
    team=str(r.get('team_id') or '').strip()
    if 'PROP' in market and not player:raise ValueError('PLAYER_ID_REQUIRED')
    if not player and not team and market in ('ML','SPREAD','HOME_TT','AWAY_TT'):
        raise ValueError('TEAM_ID_REQUIRED')
    return (e,sport,market,per,side,line,team,player,str(r.get('book') or '').strip().lower())


def match_closes(entries,closes):
    """One result per original selection; prevent duplicate counting by normalized ID key.
    Same-side separate capture times are options for quotes, NOT extra bets.
    Market prices must have verified receipt pointers and end before actual start.
    """
    close_by={};issues=[]
    for i,r in enumerate(closes,2):
        try:
            key=selection_key(r)
            if not hash_valid(r.get('receipt_sha256')):raise ValueError('BAD_RECEIPT_SHA')
            t=utc(r['captured_at_utc'],'captured_at_utc')
            if t>=utc(r['game_start_utc'],'game_start_utc'):raise ValueError('POST_KICKOFF_CLOSE')
            odds_break_even(r['odds_american'])
            if key in close_by and close_by[key][0]==t and close_by[key][1]['odds_american']!=r['odds_american']:
                raise ValueError('CONFLICTING_SAME_TIME_CLOSE')
            if key not in close_by or t>close_by[key][0]:close_by[key]=(t,r)
        except (ValueError,KeyError) as e:issues.append({'kind':'close','row':i,'code':str(e)})
    seen=set();matches=[]
    for i,r in enumerate(entries,2):
        try:
            key=selection_key(r)
            if key in seen:raise ValueError('DUPLICATE_ENTRY_BET')
            seen.add(key)
            if key not in close_by:raise ValueError('NO_MATCHED_CLOSE')
            at,close=close_by[key]
            entry_time=utc(r['captured_at_utc'],'captured_at_utc')
            if entry_time>at:raise ValueError('CLOSE_BEFORE_ENTRY')
            # Signed implied probability of selected side, no-vig only after *both* sides attached.
            matches.append({'event_id':key[0],'sport':key[1],'market':key[2], 'period':key[3],
             'side':key[4],'line':key[5],'entry_price':r['odds_american'],
             'closing_price':close['odds_american'],'entry_break_even':str(odds_break_even(r['odds_american'])),
             'close_break_even':str(odds_break_even(close['odds_american'])),
             'close_move_probability_points':str((odds_break_even(close['odds_american'])-odds_break_even(r['odds_american']))*100),
             'same_line_comparison_only':True})
        except (ValueError,KeyError) as e:issues.append({'kind':'entry','row':i,'code':str(e)})
    return {'matched':matches,'issues':issues,'status':'PAPER_ONLY' if not issues else 'INCOMPLETE_RESEARCH_ONLY'}

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--two-sided',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    with open(args.two_sided,newline='',encoding='utf-8-sig') as f:rs=list(csv.DictReader(f))
    ans=[];issues=[]
    for i,r in enumerate(rs,2):
        try:ans.extend(convert_two_sided(r))
        except ValueError as e:issues.append({'row':i,'code':str(e)})
    target=Path(args.out)
    if target.exists():raise SystemExit('REFUSE_OVERWRITE')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'one_price_per_row':ans,'rejected_rows':issues,'status':'RESEARCH_ONLY'},indent=2)+'\n')
    print(f'two-sided input rows={len(rs)} output endpoints={len(ans)} rejected={len(issues)}')
