#!/usr/bin/env python3
"""Read-only SportsEdge edge diagnostics. Never promotes or places wagers.

Input CSV fields: sport,event_id,period,market,side,line,price_american,p_model,
model_asof_utc,captured_utc,game_start_utc,quote_sha256,model_sha256
Optional: book,player_id,player,result,settled_utc,source,p_push.
p_model is unconditional win probability; p_push is unconditional refund probability.
All timestamps must be timezone-aware; receipt hashes must be 64 hex chars.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED = ('sport','event_id','period','market','side','line','price_american',
            'p_model','model_asof_utc','captured_utc','game_start_utc',
            'quote_sha256','model_sha256')
HASH = re.compile(r'^[a-fA-F0-9]{64}$')
ALLOWED = {'NFL','CFB','CBB','NBA','NHL','MLB'}

def timestamp(s):
    if not s or not s.strip():
        raise ValueError('missing timezone-aware time')
    d = dt.datetime.fromisoformat(s.strip().replace('Z', '+00:00'))
    if d.utcoffset() is None:
        raise ValueError('naive time')
    return d.astimezone(dt.timezone.utc)

def price(s):
    v = int(s.strip().replace('−','-').replace('＋','+'))
    if v == 0 or -100 < v < 100 or abs(v) > 100000:
        raise ValueError('invalid American price')
    dec = 1 + (v / 100 if v > 0 else 100 / -v)
    return v, dec

def canonical_line(value):
    try:
        if len(value) > 64 or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', value):
            raise ValueError('invalid line')
        number = Decimal(value)
        if not number.is_finite() or abs(number) > 1000000:
            raise ValueError('invalid line')
        return '0' if number == 0 else format(number, 'f').rstrip('0').rstrip('.') if '.' in format(number, 'f') else format(number, 'f')
    except (InvalidOperation, ValueError):
        raise ValueError('invalid line')

def identity(row):
    val = lambda k:(row.get(k) or '').strip().casefold()
    market = val('market').replace('moneyline','ml').replace('money_line','ml')
    period = {'full_game':'fg','fullgame':'fg','h1':'1h','first_half':'1h'}.get(val('period'),val('period'))
    line = val('line')
    try:
        line = canonical_line(line or '0') if market == 'ml' else canonical_line(line)
    except ValueError:
        pass
    return '|'.join((val('sport'),val('event_id'),period,market,val('side'),line,val('player_id')))

def audit_rows(rows, snapshot_sha256, *, max_age_minutes=120, top_n=20):
    rows=list(rows)
    # Flag every copy of a duplicate, regardless of source row order.  Selecting
    # the first copy silently can favor a stale quote or retrospectively edited
    # probability; the operator must reconcile duplicate raw evidence instead.
    identity_counts=Counter(identity(row) for row in rows)
    valid=[]; rejected=[]
    for number, row in enumerate(rows, 2):
        flags=[]
        is_ml=(row.get('market') or '').strip().casefold() in ('ml','moneyline','money_line')
        missing=[name for name in REQUIRED if not str(row.get(name) or '').strip()
                 and not (name=='line' and is_ml)]
        if missing: flags.append('MISSING_FIELDS:' + ','.join(missing))
        try:
            line = canonical_line((row.get('line') or '').strip() or ('0' if is_ml else ''))
            if is_ml and line != '0': flags.append('INVALID_MONEYLINE_LINE')
        except ValueError:
            flags.append('INVALID_LINE')
        key=identity(row)
        if identity_counts[key] > 1: flags.append('DUPLICATE_CANONICAL_SELECTION')
        if (row.get('sport') or '').strip().upper() not in ALLOWED: flags.append('UNKNOWN_SPORT')
        if 'PROP' in (row.get('market') or '').upper() and not (row.get('player_id') or '').strip():
            flags.append('MISSING_PLAYER_ID')
        for field in ('quote_sha256','model_sha256'):
            if not HASH.fullmatch((row.get(field) or '').strip()):
                flags.append('INVALID_OR_MISSING_' + field.upper())
        value=None
        try:
            p=float(row.get('p_model') or '')
            if not math.isfinite(p) or not (0 < p < 1): raise ValueError('probability out of range')
            odds, decimal=price(row.get('price_american') or '')
            push_text = (row.get('p_push') or '').strip()
            push = None
            if push_text:
                push = float(push_text)
                if not math.isfinite(push) or push < 0 or p + push > 1:
                    raise ValueError('invalid push probability')
            if push is None:
                flags.append('MISSING_PUSH_PROBABILITY')
            model_t=timestamp(row.get('model_asof_utc') or '')
            quote_t=timestamp(row.get('captured_utc') or '')
            start_t=timestamp(row.get('game_start_utc') or '')
            if model_t > quote_t: flags.append('MODEL_AFTER_CAPTURE')
            if quote_t >= start_t: flags.append('QUOTE_NOT_PREGAME')
            if (start_t-quote_t).total_seconds() > max_age_minutes*60:
                flags.append('QUOTE_OLDER_THAN_MAX_AGE')
            if odds > 400: flags.append('LONGSHOT_METHOD_SENSITIVITY_REQUIRED')
            value={'line':(row.get('line') or '').strip(), 'p_model':p,
                   'american':odds, 'implied_probability':round(1/decimal,8),
                   'p_push':push, 'raw_ev_per_dollar':round(p*decimal+push-1,8) if push is not None else None}
        except (ValueError,TypeError,OverflowError) as e:
            flags.append('INVALID_NUMERIC_OR_TIMESTAMP:' + type(e).__name__)
        rec={'row':number,'identity':key,'flags':sorted(set(flags)),
             'source':(row.get('source') or '').strip(),
             'book':(row.get('book') or '').strip(), **(value or {})}
        if rec['flags']:
            rejected.append(rec)
        else:
            valid.append(rec)
    valid.sort(key=lambda x: (-x['raw_ev_per_dollar'], x['identity'], x['row']))
    return {'status':'RESEARCH_ONLY_PAPER_0U', 'snapshot_sha256':snapshot_sha256,
            'max_age_minutes':max_age_minutes,'total_rows':len(valid)+len(rejected),
            'diagnostic_eligible':len(valid),'flagged_rows':len(rejected),
            'top_edges':valid[:top_n], 'flagged':rejected,
            'disclaimer':'No forward edge, calibration, devig or wager authorization is established.'}

def audit_file(source, *, max_age_minutes=120, top_n=20):
    data=Path(source).read_bytes()
    rows=list(csv.DictReader(data.decode('utf-8-sig').splitlines()))
    return audit_rows(rows, hashlib.sha256(data).hexdigest(),
                      max_age_minutes=max_age_minutes,top_n=top_n)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot_csv')
    parser.add_argument('--top',type=int,default=20)
    parser.add_argument('--max-age-minutes',type=int,default=120)
    parser.add_argument('--output',help='create-only JSON report path')
    args=parser.parse_args(argv)
    if args.top < 1 or args.max_age_minutes < 1: parser.error('top and max-age must be positive')
    report=audit_file(args.snapshot_csv,max_age_minutes=args.max_age_minutes,top_n=args.top)
    rendered=json.dumps(report,sort_keys=True,indent=2)+'\n'
    if args.output:
        with Path(args.output).open('x',encoding='utf-8') as file: file.write(rendered)
    else: print(rendered,end='')
    return 0

if __name__=='__main__': raise SystemExit(main())
