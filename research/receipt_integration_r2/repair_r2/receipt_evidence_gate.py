#!/usr/bin/env python3
"""R2: cryptographically tie every frozen quote row to a distinct captured quote JSON.

This verifies byte integrity and normalized metadata, NOT independent sportsbook
origin or real-world offer availability. No source record may be synthesized here.
PAPER / 0u until third-party time/source authentication and execution are verified.
"""
from __future__ import annotations
import csv, hashlib, json, stat
from decimal import Decimal
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'repair_r1'))
from integrity_gate import utc, number, odds_break_even, hash_valid

QUOTE_FIELDS = ('provider','source_url','provider_event_id','event_id','quote_id',
                'book','sport','market','period','side','line','team_id',
                'odds_american','observed_at_utc','ingested_at_utc','game_start_utc')

def canonical_line(v, market):
    if str(market).upper() == 'ML':
        if str(v or '0').strip() in ('','0','+0','-0'): return Decimal(0)
    return number(v,'line')

def checked_receipt(receipt_dir, row):
    """Return SHA and quoted field linkage; fail closed on missing or forged bytes.
    Provider-quoted JSON is a frozen adapter record; provider signature not assumed.
    """
    want = str(row.get('quote_receipt_sha256') or '').lower()
    if not hash_valid(want): raise ValueError('MISSING_OR_INVALID_QUOTE_SHA256')
    base = Path(receipt_dir).resolve(strict=True)
    if not base.is_dir():raise ValueError('RECEIPTS_NOT_DIRECTORY')
    target = base / (want+'.json')
    if not target.exists():raise ValueError('RAW_QUOTE_RECEIPT_MISSING')
    if target.is_symlink() or not target.is_file():raise ValueError('RECEIPT_NOT_REGULAR_FILE')
    # Hash the original bytes, before parsing. Do not trust any claimed SHA field.
    b = target.read_bytes()
    if not b or len(b)>2_000_000:raise ValueError('RECEIPT_SIZE_INVALID')
    if hashlib.sha256(b).hexdigest()!=want:raise ValueError('RECEIPT_BYTES_HASH_MISMATCH')
    try: q=json.loads(b.decode('utf-8'))
    except (ValueError,UnicodeError) as e:raise ValueError('RECEIPT_JSON_INVALID') from e
    if not isinstance(q,dict):raise ValueError('RECEIPT_QUOTE_NOT_OBJECT')
    for k in QUOTE_FIELDS:
        if not str(q.get(k,'')).strip():raise ValueError('RECEIPT_MISSING:'+k)
    # The expected provenance is a quote recorded by an adapter from an actual
    # provider response. Reject self-asserted hash-only evidence.
    if q['provider'] not in ('DraftKings','DK','BestBook','Pinnacle','Circa','FanDuel','BetMGM','Other'):
        raise ValueError('UNRECOGNIZED_PROVIDER')
    if not str(q['source_url']).startswith('https://'):
        raise ValueError('SOURCE_URL_NOT_HTTPS')
    for k in ('event_id','quote_id','book','sport','period','side','team_id','player_id'):
        if str(q[k]).strip()!=str(row.get(k,'')).strip():raise ValueError('RECEIPT_ROW_MISMATCH:'+k)
    if str(q['provider_event_id']).strip()!=str(row.get('event_source_id','')).strip():
        raise ValueError('PROVIDER_EVENT_ID_MISMATCH')
    if str(q['market']).strip().upper()!=str(row.get('market','')).strip().upper():
        raise ValueError('RECEIPT_ROW_MISMATCH:market')
    if canonical_line(q['line'], q['market']) != canonical_line(row.get('line'),row.get('market')):
        raise ValueError('RECEIPT_ROW_MISMATCH:line')
    if number(q['odds_american'],'odds_american') != number(row.get('odds_american'),'odds_american'):
        raise ValueError('RECEIPT_ROW_MISMATCH:odds_american')
    odds_break_even(q['odds_american'])
    observed=utc(q['observed_at_utc'],'observed_at_utc')
    ingested=utc(q['ingested_at_utc'],'ingested_at_utc')
    captured=utc(row.get('captured_at_utc'),'captured_at_utc')
    decision=utc(row.get('decision_at_utc'),'decision_at_utc')
    start=utc(q['game_start_utc'],'game_start_utc')
    if start!=utc(row.get('game_start_utc'),'game_start_utc'):raise ValueError('START_TIME_MISMATCH')
    if not observed <= ingested <= captured <= decision < start:raise ValueError('RECEIPT_TEMPORAL_ORDER_INVALID')
    if (decision-observed).total_seconds()>60*float(number(row.get('max_quote_age_minutes'),'max_quote_age_minutes')):
        raise ValueError('RECEIPT_QUOTE_STALE')
    return {'quote_id':q['quote_id'],'sha256':want,'event_id':q['event_id'],
            'observed_at_utc':observed.isoformat(),'ingested_at_utc':ingested.isoformat()}

def audit_evidence(snapshot_csv,receipt_dir):
    raw=Path(snapshot_csv).read_bytes();source_sha=hashlib.sha256(raw).hexdigest()
    try:rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    except (csv.Error,UnicodeError) as e:
        return {'verdict':'BLOCK','error':'INVALID_SNAPSHOT_CSV','source_sha256':source_sha,'rows':[]}
    results=[];seen=set()
    for i,row in enumerate(rows,2):
        if None in row:results.append({'row':i,'error':'EXTRA_SNAPSHOT_CELLS'});continue
        try:
            q=checked_receipt(receipt_dir,row)
            if q['sha256'] in seen:raise ValueError('RECEIPT_FILE_REUSED')
            seen.add(q['sha256']);results.append({'row':i,'status':'LINKED','sha256':q['sha256'],'quote_id':q['quote_id']})
        except (ValueError,OSError,KeyError) as e:results.append({'row':i,'error':str(e)})
    failed=sum('error' in x for x in results)
    return {'verdict':'BYTE_LINKAGE_PASS_NOT_PROVIDER_AUTHENTICATED' if rows and not failed else 'BLOCK',
        'source_sha256':source_sha,'n_rows':len(rows),'linked_rows':len(rows)-failed,'failed_rows':failed,
        'externally_authenticated':False,'official_counted':0,'rows':results}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--receipts',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();dest=Path(a.out)
    if dest.exists():raise SystemExit('REFUSE_OVERWRITE_EXISTING_EVIDENCE_REPORT')
    res=audit_evidence(a.snapshot,a.receipts);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(res,indent=2)+'\n')
    print(json.dumps({k:res[k] for k in ('verdict','n_rows','linked_rows','failed_rows','official_counted')},indent=2))
    raise SystemExit(0 if res['verdict'].startswith('BYTE_LINKAGE_PASS') else 2)
