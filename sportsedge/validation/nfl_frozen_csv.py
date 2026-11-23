"""Retrospective paper grading of the original NFL v3 all-candidates export."""
import csv
from collections import Counter
from io import StringIO
import re

from sportsedge.markets.allmarkets_research import Market
from sportsedge.validation import espn_final_evidence as espn, paper_grade_batch as batch, paper_ledger as ledger

SCHEMA = 'sportsedge-nfl-v3-frozen-csv-v1'
HEADER = 'game,market,selection,odds,model_p,raw_ev,blended_ev,note,status'.split(',')
STATUSES = {'on_card', 'deduped_same_signal', 'negative_ev', 'below_2pct',
            'filtered_contradicts_projection', 'held_outlier_ev_gt_25pct'}
GAME_MARKETS = {'Spread': 'SPREAD', 'Moneyline': 'ML', 'Total': 'TOTAL',
                '1H Spread': 'SPREAD', '1H ML': 'ML', '1H Total': 'TOTAL'}
PROPS = {'Rec Yds', 'Receptions', 'Rush Yds', 'Rush+Rec Yds', 'Pass TDs', 'Pass Yds'}


def _market(row, event_id):
    away, home = row['game'].split('@')
    half = row['market'].startswith('1H ')
    kind = GAME_MARKETS[row['market']]
    prefix = '1H ' if half else ''
    number = r'([+-]?[0-9]+(?:\.[0-9]+)?)'
    if kind == 'TOTAL':
        match = re.fullmatch(prefix + '(Over|Under) ' + number, row['selection'])
    else:
        suffix = 'ML' if kind == 'ML' else number
        match = re.fullmatch('([A-Z]+) ' + prefix + suffix, row['selection'])
    if not match:
        raise ledger.Blocked('INVALID_CSV_SELECTION')
    side = match[1].upper() if kind == 'TOTAL' else {home: 'HOME', away: 'AWAY'}[match[1]]
    return Market('NFL', event_id, kind, '1H' if half else 'FG', side,
                  line='' if kind == 'ML' else match[2], settlement='POSTED_RULES')


def _final(root, game, spec, kickoff, asof):
    if spec.get('espn_original') is None:
        return None
    raw, captured, _ = ledger.source_bytes(root, spec['espn_original'])
    if not kickoff < captured <= asof:
        raise ledger.Blocked('INVALID_FINAL_CAPTURE_TIME')
    final = espn.inspect(raw, event_id=spec['event_id'], sport='NFL',
                         home_espn_id=spec['home_id'], away_espn_id=spec['away_id'],
                         captured_utc=captured.isoformat(), kickoff_utc=kickoff.isoformat())
    comp, = ledger.strict_json(raw)['header']['competitions']
    sides = {part['homeAway']: part['team']['abbreviation'] for part in comp['competitors']}
    # ESPN abbreviates Washington WSH. The frozen v3 exporter uses WAS.
    codes = [({'WSH': 'WAS'}.get(sides[k], sides[k])) for k in ('away', 'home')]
    if '@'.join(codes) != game:
        raise ledger.Blocked('FROZEN_TEAM_CODES_MISMATCH')
    return final['candidate']


def grade(root, plan, asof):
    if set(plan) != {'schema', 'csv', 'games'} or not isinstance(plan['games'], dict):
        raise ledger.Blocked('INVALID_CSV_MANIFEST')
    raw, observed, digest = ledger.source_bytes(root, plan['csv'])
    if observed > asof:
        raise ledger.Blocked('FUTURE_CSV_CAPTURE')
    reader = csv.DictReader(StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
    if reader.fieldnames != HEADER:
        raise ledger.Blocked('INVALID_FROZEN_CSV_HEADER')
    statuses, identities, details, admitted, finals = Counter(), Counter(), [], [], {}
    ids = Counter(spec.get('event_id') for spec in plan['games'].values() if isinstance(spec, dict))
    try:
        for index, row in enumerate(reader, 1):
            if None in row or None in row.values() or row['status'] not in STATUSES:
                raise ledger.Blocked('INVALID_FROZEN_CSV_ROW')
            statuses[row['status']] += 1
            if row['status'] != 'on_card':
                continue
            detail = {'csv_row': index, 'status': 'PICK_EVIDENCE_BLOCKED'}
            details.append(detail)
            try:
                game = row['game']
                spec = plan['games'][game]
                kickoff = ledger.time_utc(spec['kickoff_utc'])
                if (not observed < kickoff or spec['ids_reviewed'] is not True
                        or ids[spec['event_id']] != 1 or spec['home_id'] == spec['away_id']
                        or not all(isinstance(spec[k], str) and espn.ID_RE.fullmatch(spec[k])
                                   for k in ('event_id', 'home_id', 'away_id'))):
                    continue
                if row['market'] in PROPS:
                    detail['status'] = 'PLAYER_ID_BLOCKED'
                    continue
                market = _market(row, spec['event_id'])
                identities[market.identity()] += 1
                admitted.append((game, spec, kickoff, market, detail))
            except batch.BAD_INPUT:
                continue
    except csv.Error as exc:
        raise ledger.Blocked('INVALID_FROZEN_CSV') from exc
    if not statuses:
        raise ledger.Blocked('EMPTY_FROZEN_CSV')
    for game, spec, kickoff, market, detail in admitted:
        if identities[market.identity()] != 1:
            detail['status'] = 'DUPLICATE_MARKET_BLOCKED'
            continue
        try:
            if game not in finals:
                finals[game] = _final(root, game, spec, kickoff, asof)
            final = finals[game]
            detail['status'] = ledger._settle_final(final, market) if final is not None else 'PENDING_FINAL'
        except batch.BAD_INPUT:
            detail['status'] = 'FINAL_OR_SETTLEMENT_BLOCKED'
    return dict(csv_sha256=digest, candidate_rows=sum(statuses.values()), candidate_statuses=dict(statuses),
                manifest_entries=len(details), results=dict(Counter(d['status'] for d in details)),
                official_counted=0, approved_stake_u=0), details
