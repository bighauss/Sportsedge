#!/usr/bin/env python3
"""SportsEdge NFL: source-pinned ratings half + fail-closed roster-binding census.

RESEARCH ONLY / PAPER 0u. Does not edit the input screenshot capture, grade
slates, infer player identities from display names, validate a sportsbook offer,
or price bets. No bookmaker numbers may enter the team or player forecasts.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path

REQUIRED_CAPTURE = {'captured_ct','sport','game_time_ct','away','home','game_key',
                    'market','period','side','player','line','price_american'}
REQUIRED_RATINGS = {'team','off','def','gp','lg','hfa','asof','half_life','ridge'}
PLAYER_PREFIX = ('player_prop:',)
PLAYER_MARKETS = {'attd','first_td','td_2plus'}
CENSUS_FIELDS = ('source_csv_row','game_key','market','raw_player_label',
                 'selection_type','source_line','source_american_odds',
                 'candidate_gsis_id','candidate_dk_outcome_id','binding_status',
                 'reasons','approved_stake_u')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path, required):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rd = csv.DictReader(f, restkey='__extra__', restval=None)
        headers = rd.fieldnames or []
        if len(headers) != len(set(headers)) or not required.issubset(headers):
            raise ValueError('BAD_OR_DUPLICATE_COLUMNS')
        rows = list(rd)
    if not rows or any('__extra__' in r or None in r.values() for r in rows):
        raise ValueError('EMPTY_OR_RAGGED_SOURCE')
    return rows


def aware(value):
    t = datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return t


def finite(value):
    v = float(value)
    if not math.isfinite(v):
        raise ValueError('NONFINITE_NUMERIC')
    return v


def ratings(path, expected_sha):
    if not path or not expected_sha:
        return None, 'NO_PINNED_RATINGS_FILE'
    if len(expected_sha) != 64 or any(c not in '0123456789abcdef' for c in expected_sha.lower()):
        return None, 'RATINGS_PIN_INVALID'
    if not Path(path).is_file():
        return None, 'RATINGS_SOURCE_NOT_ACCESSIBLE'
    if sha256(path) != expected_sha.lower():
        return None, 'RATINGS_SHA256_MISMATCH'
    try:
        rows = read_csv(path, REQUIRED_RATINGS)
        values = {}
        common = None
        for r in rows:
            k = r['team'].strip().casefold()
            if not k or k in values:
                raise ValueError('DUPLICATE_OR_EMPTY_TEAM')
            fields = (finite(r['lg']), finite(r['hfa']), finite(r['ridge']),
                      finite(r['half_life']), date.fromisoformat(r['asof']))
            if common is None: common = fields
            if fields != common or not 0 <= fields[1] <= 12 or fields[0] <= 0 or fields[2] <= 0 or fields[3] <= 0:
                raise ValueError('INVALID_RATINGS_METADATA')
            gp = int(r['gp'])
            if gp < 1: raise ValueError('INVALID_GAME_COUNT')
            values[k] = (finite(r['off']), finite(r['def']))
        return (values, common), None
    except (OSError, UnicodeError, KeyError, ValueError, TypeError, csv.Error):
        return None, 'RATINGS_SCHEMA_OR_VALUES_INVALID'


def bridge(capture, ratings_file=None, ratings_sha=None, team_map=None, evidence=None):
    rows = read_csv(capture, REQUIRED_CAPTURE)
    snapshot = sha256(capture)
    rated, ratings_error = ratings(ratings_file, ratings_sha)
    team_map = team_map or {}
    evidence = evidence or {}
    groups = {}
    for i, r in enumerate(rows, 2):
        if r['sport'].strip().upper() != 'NFL':
            raise ValueError('NON_NFL_ROW')
        k = r['game_key'].strip()
        if not k: raise ValueError('MISSING_EVENT_KEY')
        pair = (r['home'],r['away'],r['game_time_ct'])
        if k in groups and groups[k]['pair'] != pair:
            raise ValueError('EVENT_IDENTITY_COLLISION')
        groups.setdefault(k, {'pair':pair,'rows':[]})['rows'].append((i,r))
    forecasts=[]
    for game, entry in sorted(groups.items()):
        home,away,start_s = entry['pair']
        reason = ratings_error
        hp=ap=None
        captures = [aware(r['captured_ct']) for _,r in entry['rows']]
        start = aware(start_s)
        if any(c >= start for c in captures):
            reason = 'SNAPSHOT_AFTER_EVENT_START'
        elif rated and not reason:
            R, meta = rated
            lg,hfa,_,_,asof = meta
            if asof >= min(captures).date():
                reason = 'RATINGS_ASOF_TOO_RECENT_FOR_DATE_ONLY_PIT'
            else:
                lookup = team_map.get(game, {})
                # Exact source team identifiers, never guesses/fuzzy text.
                hname = lookup.get('home', home).strip().casefold()
                aname = lookup.get('away', away).strip().casefold()
                if hname == aname or hname not in R or aname not in R:
                    reason = 'EXACT_TEAM_RATINGS_MAPPING_REQUIRED'
                else:
                    h,a = R[hname],R[aname]
                    hp=max(3.0,lg + h[0] - a[1] + hfa/2)
                    ap=max(3.0,lg + a[0] - h[1] - hfa/2)
                    reason='RATINGS_ONLY_NO_VERIFIED_PUBLISHER_OR_ROSTER_PIT'
        forecasts.append({'game_key':game,'home':home,'away':away,'start_ct':start_s,
                          'ratings_home_points':f'{hp:.3f}' if hp is not None else '',
                          'ratings_away_points':f'{ap:.3f}' if ap is not None else '',
                          'ratings_asof_date':rated[1][4].isoformat() if rated else '',
                          'ratings_source_sha256':ratings_sha or '',
                          'status':'PAPER_HOLD_0U','reason':reason or 'NO_RATINGS_SOURCE'})
    census=[]
    for game, entry in sorted(groups.items()):
        for rownum,r in entry['rows']:
            market=r['market']
            is_player=market.startswith(PLAYER_PREFIX) or market in PLAYER_MARKETS
            if not is_player: continue
            label=r['player'].strip()
            selection_type='TEAM_DST' if label.endswith(' D/ST') else 'PLAYER'
            is_trunc=('…' in label or '...' in label or r.get('raw_label_status')=='TRUNCATED_VISIBLE_LABEL')
            proof=evidence.get(str(rownum), {})
            issues=[]
            if is_trunc: issues.append('VISIBLE_LABEL_TRUNCATED')
            if not label: issues.append('NO_PLAYER_LABEL')
            if proof and proof.get('capture_sha256')!=snapshot:
                issues.append('PROOF_CAPTURE_SHA_MISMATCH')
            # A readable player name is not an authenticated outcome ID.
            if not proof.get('dk_outcome_id'): issues.append('DK_OUTCOME_ID_NOT_PROVEN')
            if selection_type=='PLAYER' and not proof.get('gsis_id'): issues.append('ROSTER_GSIS_ID_NOT_PROVEN')
            if not proof.get('team_id'): issues.append('ROSTER_TEAM_NOT_PROVEN')
            if not proof.get('provider_receipt_id'): issues.append('ORIGINAL_PROVIDER_RECEIPT_MISSING')
            if selection_type=='PLAYER' and not proof.get('roster_receipt_id'): issues.append('PIT_ROSTER_RECEIPT_MISSING')
            if proof:
                for field in ('provider_observed_utc','roster_observed_utc'):
                    try:
                        if aware(proof[field])>aware(r['captured_ct']):
                            issues.append('EVIDENCE_AFTER_SCREENSHOT_'+field.upper())
                    except (ValueError,KeyError,TypeError,AttributeError):
                        issues.append('EVIDENCE_TIME_INVALID_'+field.upper())
            if not issues:
                issues.append('EVIDENCE_CLAIM_NEEDS_INDEPENDENT_AUTHENTICATION')
            census.append({'source_csv_row':rownum,'game_key':game,'market':market,
                           'raw_player_label':label,'selection_type':selection_type,'source_line':r['line'],
                           'source_american_odds':r['price_american'],
                           'candidate_gsis_id':proof.get('gsis_id',''),
                           'candidate_dk_outcome_id':proof.get('dk_outcome_id',''),
                           'binding_status':'CANDIDATE_NOT_AUTHENTICATED' if len(issues)==1 and issues[0].startswith('EVIDENCE_CLAIM') else 'BLOCK_UNBOUND',
                           'reasons':'|'.join(issues),'approved_stake_u':0})
    counts = Counter(r['market'] for r in rows)
    report={'status':'PAPER_HOLD_0U','approved_stake_u':0,'source_capture_sha256':snapshot,
            'capture_rows':len(rows),'markets':dict(sorted(counts.items())),
            'game_count':len(groups),'games_with_numeric_ratings':sum(bool(x['ratings_home_points']) for x in forecasts),
            'participant_or_team_td_rows':len(census),'team_dst_quotes':sum(x['selection_type']=='TEAM_DST' for x in census),
            'person_player_prop_td_rows':sum(x['selection_type']=='PLAYER' for x in census),
            'participant_or_team_unbound':sum(x['binding_status']=='BLOCK_UNBOUND' for x in census),
            'ratings_source_status':ratings_error or 'HASH_CHECKED_LOCAL_BYTES_UNAUTHENTICATED_PUBLISHER',
            'caveats':['No provider-authenticated sportsbook quote','No certified player-to-DK outcome identity',
                       'No forward validation or independent bookmaker market fair probability',
                       'Do not mutate Claude immutable slate or grade using this audit']}
    return forecasts,census,report


def write_csv(path,rows,fieldnames=None):
    # An all-markets capture may validly contain zero player/TD inventory rows.
    # Emit a header-only census instead of crashing or inventing a player.
    columns=list(rows[0]) if rows else list(fieldnames or ())
    if not columns:
        raise ValueError('EMPTY_REPORT_SCHEMA')
    with open(path,'x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture',required=True)
    ap.add_argument('--ratings')
    ap.add_argument('--ratings-sha256')
    ap.add_argument('--team-map')
    ap.add_argument('--binding-evidence')
    ap.add_argument('--output-dir',required=True)
    args=ap.parse_args()
    with open(args.team_map,encoding='utf-8') if args.team_map else __import__('contextlib').nullcontext('{}') as f:
        mappings=json.loads(f.read() if args.team_map else '{}')
    with open(args.binding_evidence,encoding='utf-8') if args.binding_evidence else __import__('contextlib').nullcontext('{}') as f:
        proof=json.loads(f.read() if args.binding_evidence else '{}')
    a,b,report=bridge(args.capture,args.ratings,args.ratings_sha256,mappings,proof)
    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=False)
    write_csv(out/'ratings_half_PAPER_0U.csv',a)
    write_csv(out/'roster_binding_census_PAPER_0U.csv',b,CENSUS_FIELDS)
    (out/'bridge_audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__':
    main()
