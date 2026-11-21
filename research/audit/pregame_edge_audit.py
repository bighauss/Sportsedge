#!/usr/bin/env python3
"""Read-only SportsEdge edge diagnostics. Never promotes or places wagers.

Input CSV fields: sport,event_id,period,market,side,line,price_american,p_model,
model_asof_utc,captured_utc,game_start_utc,quote_sha256,model_sha256
Optional: book,player_id,player,result,settled_utc,source.
All timestamps must be timezone-aware; receipt hashes must be 64 hex chars.
"""
import argparse
import csv
import io
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

def identity_key(row):
    """Structured selection key; never collapse distinct player stat markets."""
    val=lambda k:str(row.get(k) or '').strip().casefold()
    market=val('market').replace('moneyline','ml').replace('money_line','ml')
    period={'full_game':'fg','fullgame':'fg','h1':'1h',
            'first_half':'1h'}.get(val('period'),val('period'))
    line=val('line')
    if market=='ml' and line in ('','0','0.0','+0','-0'):
        line='0'
    elif line and len(line)<=32 and re.fullmatch(r'[+-]?\\d+(?:\\.\\d+)?',line):
        try:
            line=format(Decimal(line).normalize(),'f')
        except InvalidOperation:
            pass
    return (val('sport'),val('event_id'),period,market,val('side'),
            line,val('player_id'),val('team_id'),val('stat'))

def identity(row):
    """Printable diagnostic identity; duplicate detection uses the tuple."""
    return '|'.join(identity_key(row))

def audit_rows(rows, snapshot_sha256, *, max_age_minutes=120, top_n=20):
    rows=list(rows)
    # Flag every copy of a duplicate, regardless of source row order.  Selecting
    # the first copy silently can favor a stale quote or retrospectively edited
    # probability; the operator must reconcile duplicate raw evidence instead.
    identity_counts=Counter(identity_key(row) for row in rows)
    valid=[]; rejected=[]; claimed=[]
    cluster_by_row={}
    for number, row in enumerate(rows, 2):
        flags=[]
        is_ml=(row.get('market') or '').strip().casefold() in ('ml','moneyline','money_line')
        missing=[name for name in REQUIRED if not str(row.get(name) or '').strip()
                 and not (name=='line' and is_ml)]
        if missing: flags.append('MISSING_FIELDS:' + ','.join(missing))
        key=identity(row)
        if identity_counts[identity_key(row)] > 1: flags.append('DUPLICATE_CANONICAL_SELECTION')
        if (row.get('sport') or '').strip().upper() not in ALLOWED: flags.append('UNKNOWN_SPORT')
        if 'PROP' in (row.get('market') or '').upper() and not (row.get('player_id') or '').strip():
            flags.append('MISSING_PLAYER_ID')
        for field in ('quote_sha256','model_sha256'):
            if not HASH.fullmatch((row.get(field) or '').strip()):
                flags.append('INVALID_OR_MISSING_' + field.upper())
        # Compute the *claimed* EV before chronology checks so suspicious
        # longshots, stale quotes and missing receipts remain visible in the
        # adversarial top-N. These are NEVER certified or eligible wagers.
        value=None
        try:
            p=float(row.get('p_model') or '')
            if not math.isfinite(p) or not (0 < p < 1): raise ValueError('probability out of range')
            odds, decimal=price(row.get('price_american') or '')
            if odds > 400: flags.append('LONGSHOT_METHOD_SENSITIVITY_REQUIRED')
            value={'line':(row.get('line') or '').strip(), 'p_model':p,
                   'american':odds, 'implied_probability':round(1/decimal,8),
                   'raw_ev_per_dollar':round(p*decimal-1,8)}
        except (ValueError,TypeError,OverflowError) as e:
            flags.append('INVALID_ODDS_OR_MODEL_PROBABILITY:' + type(e).__name__)

        decision_clock='NOT_ATTESTED'
        quote_age_at_selection=None
        try:
            model_t=timestamp(row.get('model_asof_utc') or '')
            quote_t=timestamp(row.get('captured_utc') or '')
            start_t=timestamp(row.get('game_start_utc') or '')
            if model_t > quote_t: flags.append('MODEL_AFTER_CAPTURE')
            if quote_t >= start_t: flags.append('QUOTE_NOT_PREGAME')
            if (start_t-quote_t).total_seconds() > max_age_minutes*60:
                flags.append('QUOTE_OLDER_THAN_MAX_AGE')
            if row.get('selected_utc'):
                chosen_t=timestamp(row['selected_utc'])
                quote_age_at_selection=(chosen_t-quote_t).total_seconds()
                decision_clock='DECLARED_NOT_AUTHENTICATED'
                if chosen_t < model_t: flags.append('SELECTION_BEFORE_MODEL')
                if chosen_t < quote_t: flags.append('QUOTE_AFTER_SELECTION')
                if chosen_t >= start_t: flags.append('SELECTION_NOT_PREGAME')
                if quote_age_at_selection > 300: flags.append('QUOTE_OLDER_THAN_300S_AT_SELECTION')
            # Kickoff-relative max_age_minutes is a research lookback window,
            # not the Gate A 300-second decision-time freshness policy.
        except (ValueError,TypeError,OverflowError) as e:
            flags.append('INVALID_NUMERIC_OR_TIMESTAMP:' + type(e).__name__)
        rec={'row':number,'identity':key,'flags':sorted(set(flags)),
             'source':(row.get('source') or '').strip(),
             'book':(row.get('book') or '').strip(),
             'selection_clock_status':decision_clock,
             'quote_age_at_selection_seconds':quote_age_at_selection,
             **(value or {})}
        if value is not None:
            claimed.append(rec)
            # Keep structured identity; splitting identity(row)'s printable
            # pipe-delimited string conflates fields when an ID contains '|'.
            v=lambda k: str(row.get(k) or '').strip().casefold()
            market=v('market').replace('moneyline','ml').replace('money_line','ml')
            period={'full_game':'fg','fullgame':'fg','h1':'1h',
                    'first_half':'1h'}.get(v('period'),v('period'))
            cluster_by_row[number]=(v('sport'),v('event_id'),period,
                                    market,v('side'),v('player_id'),
                                    v('team_id'),v('stat'))
        if rec['flags']:
            rejected.append(rec)
        else:
            valid.append(rec)
    rank=lambda x: (-x['raw_ev_per_dollar'], x['identity'], x['row'])
    valid.sort(key=rank)
    claimed.sort(key=rank)
    # One highest-claimed-EV representative per game/period/family/direction.
    # This is a concentration diagnostic only; the full rung universe remains.
    clusters=[]
    seen=set()
    for rec in claimed:
        cluster=cluster_by_row[rec['row']]
        if cluster not in seen:
            seen.add(cluster)
            clusters.append(rec)
    return {'status':'RESEARCH_ONLY_PAPER_0U', 'snapshot_sha256':snapshot_sha256,
            'max_age_minutes':max_age_minutes,'total_rows':len(valid)+len(rejected),
            'diagnostic_eligible':len(valid),'flagged_rows':len(rejected),
            'top_edges':valid[:top_n], 'flagged':rejected,
            'top_claimed_edges_including_flagged':claimed[:top_n],
            'top_claimed_clusters_including_flagged':clusters[:top_n],
            'computable_claimed_edges':len(claimed),
            'claimed_clusters':len(clusters),
            'quote_age_basis':'KICKOFF_LOOKBACK_RESEARCH_NOT_SELECTION_FRESHNESS',
            'selection_freshness_required_for_admission_seconds':300,
            'admission_allowed':False,'source_authenticated':False,
            'disclaimer':'Claims include rejected rows for investigation. Declared timestamps and hashes do not authenticate original sources, calibration, selection eligibility or actual EV. PAPER/0u.'}

def strict_csv_rows(data: bytes):
    """No dropped blank records, ragged rows, duplicate headers or broken CSV.

    csv.reader understands quoted multiline fields, including blank physical
    lines inside quotes, unlike text.splitlines() preflight shortcuts.
    """
    if not isinstance(data,bytes) or not data:
        raise ValueError('EMPTY_OR_NONBYTES_CSV')
    try:
        text=data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('INVALID_UTF8_CSV') from exc
    if '\\x00' in text:
        raise ValueError('CSV_NUL_BYTE')
    try:
        reader=csv.reader(io.StringIO(text,newline=''),strict=True)
        records=list(reader)
    except csv.Error as exc:
        raise ValueError('MALFORMED_CSV') from exc
    if not records or not records[0]:
        raise ValueError('CSV_HEADER_MISSING')
    headers=records[0]
    if any(not h.strip() for h in headers):
        raise ValueError('CSV_BLANK_HEADER')
    if len({h.strip().casefold() for h in headers}) != len(headers):
        raise ValueError('CSV_DUPLICATE_NORMALIZED_HEADER')
    if any(h != h.strip() for h in headers):
        raise ValueError('CSV_UNNORMALIZED_HEADER')
    rows=[]
    for line_index,values in enumerate(records[1:],2):
        if not values:
            raise ValueError('BLANK_CSV_RECORD')
        if len(values)!=len(headers):
            raise ValueError('RAGGED_CSV_RECORD')
        rows.append(dict(zip(headers,values)))
    return rows


def audit_file(source, *, max_age_minutes=120, top_n=20):
    data=Path(source).read_bytes()
    rows=strict_csv_rows(data)
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
