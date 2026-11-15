#!/usr/bin/env python3
"""Independent fail-closed preflight for SportsEdge portable-engine board CSVs.

This is a candidate wrapper. It DOES NOT authorize, price or place bets.
Preserves accepted row values; refuses ambiguous games and records all exclusions.

Usage: python sportsedge_board_guard_r1.py input.csv accepted.csv exclusions.csv
"""
import csv
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

COLUMNS = ('sport','home','away','home_proj','away_proj','player','team','proj','market',
           'line','price_a','price_b','sgp','side','home_score','away_score','remaining')
SPORTS = {'NFL','CFB','NBA','CBB','NHL','MLB','PGA','UFC','DWCS'}
PRICE = re.compile(r'^[+-]?(?:[1-9][0-9]*)$')
LINE_MARKETS = {'SPREAD','TOTAL','HOME_TT','AWAY_TT','SCHEDULED'}
GAME_MARKETS = {'ML','SPREAD','TOTAL','HOME_TT','AWAY_TT','SGP','OT','BTTS',
                'REG_HOME','REG_AWAY','REG_DRAW','GTD','SCHEDULED'}
PERIOD_PREFIXES = ('1Q_','2Q_','3Q_','4Q_','1H_','2H_','P1_','P2_','P3_','I1_','F3_','F5_','F7_')


def number(text):
    if text is None or str(text).strip()=="":
        return None
    try: out=float(str(text).strip().replace('−','-'))
    except ValueError: return None
    return out if math.isfinite(out) else None


def real_price(x):
    """Strict American quote, no -99, sub -100, decimals, exponents or blanks."""
    x = (x or '').strip()
    if not x: return True
    if not PRICE.fullmatch(x): return False
    return abs(int(x)) >= 100


def market_base(m):
    for pre in PERIOD_PREFIXES:
        if m.startswith(pre):
            return m[len(pre):]
    return m


def validate_row(r):
    bad=[]
    sport=r['sport'].upper(); m=r['market'].upper(); base=market_base(m)
    if sport not in SPORTS: bad.append('SPORT_UNSUPPORTED')
    if not r['home']: bad.append('HOME_EMPTY')
    if sport!='PGA' and not r['away']: bad.append('AWAY_EMPTY')
    if not m: bad.append('MARKET_EMPTY')
    if m.startswith('SGP') and not r['sgp']: bad.append('SGP_ID_MISSING')
    if r['side'].upper() not in ('','A','B'): bad.append('SIDE_INVALID')
    if r['sgp'] and m!='SGP' and r['side'].upper() not in ('A','B'): bad.append('SGP_LEG_SIDE_MISSING')
    if r['player'] and r['team'] not in (r['home'],r['away']) and sport != 'PGA':bad.append('PLAYER_TEAM_MISMATCH')
    if sport == 'PGA' and r['away'] and m in ('WIN','TOP5','TOP10','TOP20','MAKE_CUT','FRL'):
        bad.append('PGA_GAME_SHAPE_INVALID')
    if not real_price(r['price_a']):bad.append('PRICE_A_INVALID')
    if not real_price(r['price_b']):bad.append('PRICE_B_INVALID')
    if not r['price_a'] and not r['price_b'] and base!='SCHEDULED':bad.append('NO_OFFER')
    for field in ('line','home_proj','away_proj','proj','home_score','away_score','remaining'):
        val=r[field]
        if val and number(val) is None: bad.append(field.upper()+'_NONFINITE_OR_MALFORMED')
    n=number(r['line'])
    if base in LINE_MARKETS and n is None: bad.append('REQUIRED_LINE_MISSING')
    if base in ('TOTAL','HOME_TT','AWAY_TT') and n is not None and n < 0: bad.append('TOTAL_LINE_NEGATIVE')
    if base=='SCHEDULED' and (n is None or n not in (3,5)):bad.append('SCHEDULED_LINE_NOT_3_OR_5')
    for field in ('home_proj','away_proj','proj'):
        v=number(r[field]);
        if v is not None and v < 0:bad.append('NEGATIVE_'+field.upper())
    x=number(r['remaining'])
    if x is not None and (x<=0 or x>1):bad.append('LIVE_REMAINING_INVALID')
    if x is not None and (not r['home_score'] or not r['away_score']):bad.append('LIVE_SCORE_INCOMPLETE')
    return sorted(set(bad))


def guard(input_csv, accepted_csv, excluded_csv):
    with open(input_csv,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        headers=[x.strip().lower() if x else '' for x in (reader.fieldnames or [])]
        if len(headers)!=len(set(headers)):raise ValueError('DUPLICATE_NORMALIZED_HEADERS')
        if not set(COLUMNS).issubset(headers):raise ValueError('MISSING_COLUMNS:'+','.join(sorted(set(COLUMNS)-set(headers))))
        reader.fieldnames=headers
        data=[]
        for row in reader:
            if None in row:raise ValueError('EXTRA_CSV_CELLS line '+str(reader.line_num))
            if all(not (v or '').strip() for v in row.values()):continue
            r={c:(row.get(c) or '').strip() for c in COLUMNS}
            r['sport']=r['sport'].upper();r['market']=r['market'].upper()
            data.append((reader.line_num,r,validate_row(r)))
    folded=defaultdict(set)
    scheds=defaultdict(set)
    bad_scheduled=set()
    for _,r,_ in data:
        key=(r['sport'],r['home'].casefold(),r['away'].casefold())
        folded[key].add((r['sport'],r['home'],r['away']))
        if r['market']=='SCHEDULED':
            if validate_row(r):bad_scheduled.add(key)
            if number(r['line']) is not None:scheds[key].add(number(r['line']))
    accepted=[];excluded=[]
    for line,r,bad in data:
        folded_key=(r['sport'],r['home'].casefold(),r['away'].casefold())
        if len(folded[folded_key])>1:bad.append('GAME_KEY_CASE_VARIANT')
        if len(scheds[folded_key])>1:bad.append('FIGHT_SCHEDULED_ROWS_CONFLICT')
        if folded_key in bad_scheduled:bad.append('FIGHT_SCHEDULED_ROW_INVALID')
        if bad:excluded.append({'source_row':line,'reasons':';'.join(sorted(set(bad))),**r})
        else:accepted.append(r)
    for fn,cols,rows in ((accepted_csv,COLUMNS,accepted),(excluded_csv,('source_row','reasons')+COLUMNS,excluded)):
        Path(fn).parent.mkdir(parents=True,exist_ok=True)
        with open(fn,'w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader();writer.writerows(rows)
    return {'input_rows':len(data),'accepted_rows':len(accepted),'excluded_rows':len(excluded),
            'source':str(input_csv),'accepted':str(accepted_csv),'excluded':str(excluded_csv)}

if __name__=='__main__':
    import json
    if len(sys.argv)!=4:raise SystemExit('usage: board_guard input.csv accepted.csv excluded.csv')
    print(json.dumps(guard(*sys.argv[1:]),indent=2))
