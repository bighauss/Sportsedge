"""Verify one Muse league capture and expose unique events to reconciliation.
Artifact consistency is not origin authentication. Caller must independently pin
COMPLETE.json's digest. No aliases, CBBD IDs, venues or pricing grants inferred.
"""
import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re

COLUMNS=('sport','away','home','market','line','price_a','price_b')
FILES={'board.csv','contracts.json','events.json','comment.raw.json'}


def _json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def _time(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.utcoffset() is None:raise ValueError('timezone required')
    return t


def load_verified_events(directory, *, manifest_sha256, expected_game_count):
    if not isinstance(manifest_sha256,str) or not re.fullmatch('[0-9a-f]{64}',manifest_sha256):
        raise ValueError('independently pinned manifest digest required')
    if type(expected_game_count) is not int or expected_game_count<1:raise ValueError('expected game count required')
    directory=Path(directory);raw_manifest=(directory/'COMPLETE.json').read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest()!=manifest_sha256:raise ValueError('manifest digest mismatch')
    manifest=_json(raw_manifest)
    if set(manifest['output_sha256'])!=FILES:raise ValueError('unsupported or incomplete output set')
    payload={name:(directory/name).read_bytes() for name in FILES}
    if any(hashlib.sha256(raw).hexdigest()!=manifest['output_sha256'][name] for name,raw in payload.items()):
        raise ValueError('output digest mismatch')
    if manifest.get('source_kind')!='GITHUB_RELAY_NOT_BOOK_RECEIPT' or manifest.get('primary_totals_gate_changed') is not False or manifest.get('forecast_execution_complete') is not False:
        raise ValueError('unsupported capture or guard state')
    if type(manifest.get('approved_stake_u')) is not int or manifest['approved_stake_u']!=0:
        raise ValueError('unsupported stake authorization')
    comment=_json(payload['comment.raw.json'])
    if type(comment.get('id')) is not int or manifest['source_url']!=comment.get('html_url') or manifest['source_url']!=f"https://github.com/bighauss/Sportsedge/issues/57#issuecomment-{comment['id']}":
        raise ValueError('source comment mismatch')
    if type(comment['user'].get('id')) is not int or comment['user']['id']!=manifest.get('github_author_id'):
        raise ValueError('source principal mismatch')
    reader=csv.DictReader(io.StringIO(payload['board.csv'].decode('utf-8')))
    if reader.fieldnames!=list(COLUMNS):raise ValueError('unsupported board schema')
    board=list(reader);contracts=_json(payload['contracts.json']);side_events=_json(payload['events.json'])
    if not isinstance(contracts,list) or len(contracts)!=len(board) or not contracts:raise ValueError('contract/CSV denominator mismatch')
    if not isinstance(side_events,list):raise ValueError('events array required')
    known={}
    for event in side_events:
        eid=event['dk_event_id']
        if not isinstance(eid,str) or not eid.isdigit() or eid in known:raise ValueError('invalid or duplicate event record')
        known[eid]={k:event[k] for k in ('dk_event_id','home','away','tipoff_ct')}
    grouped={};identities=set();main_markets={}
    for index,(contract,row) in enumerate(zip(contracts,board),1):
        if type(contract['board_row']) is not int or contract['board_row']!=index:raise ValueError('invalid board row binding')
        if row!={k:str(contract[k]) for k in COLUMNS}:raise ValueError('CSV/contract value mismatch')
        if contract['eligible_for_pricing'] is not False or contract['settlement_rules_verified'] is not False:
            raise ValueError('unexpected pricing or settlement grant')
        if contract['sport']!='CBB' or contract['period']!='FULL_GAME' or contract['market'] not in ('SPREAD','TOTAL','ML'):
            raise ValueError('unsupported contract family')
        if any(type(contract[k]) is not int or abs(contract[k])<100 for k in ('price_a','price_b')):raise ValueError('invalid price')
        line=contract['line']
        if contract['market']=='ML':
            if line!='':raise ValueError('ML line must be empty')
        elif type(line) not in (int,float) or not math.isfinite(line):raise ValueError('invalid line')
        eid=contract['dk_event_id'];event={k:contract[k] for k in ('dk_event_id','home','away','tipoff_ct')}
        if not event['home'] or not event['away'] or event['home']==event['away'] or known.get(eid)!=event:
            raise ValueError('event sidecar or orientation mismatch')
        lo,hi=contract['capture_start_ct'],contract['capture_end_ct']
        if type(contract['source_comment_id']) is not int or contract['source_comment_id']!=comment['id'] or lo!=manifest['capture_start_ct'] or hi!=manifest['capture_end_ct']:
            raise ValueError('capture/source binding mismatch')
        if not _time(lo)<=_time(hi)<_time(event['tipoff_ct']):raise ValueError('invalid capture chronology')
        identity=(eid,contract['period'],contract['market'],line)
        if identity in identities:raise ValueError('duplicate market contract')
        markets=main_markets.setdefault(eid,set())
        if contract['market'] in markets:raise ValueError('multiple main lines for event market')
        markets.add(contract['market'])
        identities.add(identity);grouped.setdefault(eid,event)
    if any(not {'SPREAD','TOTAL'}.issubset(markets) for markets in main_markets.values()):
        raise ValueError('incomplete main market coverage')
    if set(grouped)!=set(known) or len(grouped)!=expected_game_count:raise ValueError('event denominator mismatch')
    if any(type(manifest.get(k)) is not int or manifest[k]!=n for k,n in [('games',len(grouped)),('paired_markets',len(contracts)),('offered_sides',2*len(contracts))]):
        raise ValueError('manifest denominator mismatch')
    return dict(events=list(grouped.values()),contracts=contracts,manifest_sha256=manifest_sha256,
                pricing_authorized=False,settlement_rules_verified=False)
