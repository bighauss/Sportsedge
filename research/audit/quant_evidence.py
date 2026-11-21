"""Read-only, point-in-time SportsEdge eight-prompt audit companion.

Consumes *already frozen* prediction and outcome records. This NEVER trains,
retrains, calibrates, authenticates a sportsbook, promotes wagers, or revises
an historical result. Genuine walk-forward training requires versioned releases
and a separately pre-registered fold/training pipeline.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import random
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from pathlib import Path
from statistics import mean

from quant_foundation import SPORTS, american, when, devig_two_way

HEX = frozenset('0123456789abcdef')
VALID_OUTCOMES = frozenset(('W', 'L', 'P'))


def digest_ok(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(x in HEX for x in value)


def _valid_probability(value: object, name: str) -> float:
    v = float(value)
    if not math.isfinite(v) or not 0 < v < 1:
        raise ValueError('INVALID_' + name.upper())
    return v


def _asof_check(row: dict) -> None:
    required = ('sport', 'event_id', 'market', 'period', 'side', 'book',
                'model_asof_utc', 'captured_utc', 'game_start_utc',
                'feature_available_utc', 'source_published_utc',
                'fitted_until_utc', 'settled_utc',
                'model_sha256', 'quote_sha256', 'price_american',
                'qualification_rule_sha256', 'qualified')
    missing = [key for key in required if not str(row.get(key, '')).strip()]
    if missing:
        raise ValueError('MISSING_REQUIRED:' + ','.join(missing))
    if row['sport'] not in SPORTS or not row['event_id']:
        raise ValueError('INVALID_SPORT_EVENT')
    market_lower = str(row['market']).casefold()
    if (any(word in market_lower for word in
            ('spread', 'total', 'yard', 'point', 'shot', 'save', 'rebound', 'assist', 'alt'))
            and row.get('line') in ('', None)):
        raise ValueError('MARKET_LINE_MISSING')
    if any(not digest_ok(row.get(f)) for f in
           ('model_sha256', 'quote_sha256', 'qualification_rule_sha256')):
        raise ValueError('INVALID_DIGEST_FORMAT')
    start, freeze, captured = (when(row[k]) for k in
                               ('game_start_utc', 'model_asof_utc', 'captured_utc'))
    if not (freeze < start and captured < start):
        raise ValueError('POST_KICKOFF_PREDICTION_OR_PRICE')
    if when(row['feature_available_utc']) > freeze or when(row['source_published_utc']) > freeze:
        raise ValueError('PIT_FEATURE_NOT_RELEASED')
    if when(row['fitted_until_utc']) >= freeze:
        raise ValueError('TRAINING_NOT_EARLIER_THAN_FORECAST')
    if when(row['settled_utc']) <= start:
        raise ValueError('IMPOSSIBLE_SETTLEMENT_TIME')
    american(row['price_american'])
    if str(row.get('qualified')).lower() not in ('0', '1', 'true', 'false'):
        raise ValueError('UNLOCKED_SELECTION_STATUS')
    market_id = _market_id(str(row['market']))
    if ('prop' in market_id or market_id in ('attd', 'firsttd', 'td2plus',
                                             'firstbasket', 'homerun')) and not str(row.get('player_id') or '').strip():
        raise ValueError('UNBOUND_PROP_ID')
    if market_id == 'teamtotal' and not str(row.get('team_id') or '').strip():
        raise ValueError('UNBOUND_TEAM_TOTAL_ID')
    if not row.get('book'):
        raise ValueError('UNBOUND_BOOK')



def _canonical_line(line: object) -> str:
    if line is None or str(line).strip() == '':
        return ''
    try:
        value = Decimal(str(line).strip())
        if not value.is_finite():
            raise ValueError('INVALID_MARKET_LINE')
        return format(value.normalize(), 'f')
    except InvalidOperation as exc:
        raise ValueError('INVALID_MARKET_LINE') from exc


def _market_id(market: str) -> str:
    s = market.casefold().replace(' ', '').replace('_', '').replace('-', '')
    return {'moneyline':'ml', 'moneylinefullgame':'ml', 'totals':'total',
            'spreads':'spread'}.get(s, s)


def _book_id(book: str) -> str:
    """Normalize common spelling variants without changing upstream prices."""
    name = ' '.join(book.casefold().split())
    return {'dk': 'draftkings', 'draft kings': 'draftkings',
            'fd': 'fanduel', 'fan duel': 'fanduel'}.get(name, name)


def _selection_fingerprint(row: dict) -> tuple:
    """Keep participant/stat identity: different teams can have identical TT lines."""
    market = _market_id(str(row['market']))
    line = _canonical_line(row.get('line'))
    if market == 'ml' and line in ('', '0'):
        line = ''
    return (row['sport'], row['event_id'], when(row['game_start_utc']).isoformat(),
            _book_id(row['book']), str(row['period']).strip().casefold(),
            market, str(row['side']).strip().casefold(), line,
            str(row.get('player_id', '')).strip(),
            when(row['captured_utc']).isoformat(),
            str(row.get('team_id') or '').strip().casefold(),
            str(row.get('stat') or '').strip().casefold())


def _decision_key(fingerprint: tuple) -> tuple:
    """One paper decision across quote snapshots: same outcome and line, not a new bet.

    A later quote can change the price but cannot produce a second independently
    executed wager without a separate transaction ledger and source proof.
    """
    return fingerprint[:9] + fingerprint[10:]


def _mirror_key(fingerprint: tuple) -> tuple:
    """Opposite selections from one quote instant must not both inflate ROI.

    Totals/props compare the same threshold; spread home/away compare equal
    *magnitude* because they commonly have opposite signed handicap lines.
    Team and stat are part of the identity, preventing false prop/TT matches.
    """
    sport, event, start, book, period, market, side, line, player, capture, team, stat = fingerprint
    if side not in ('home', 'away', 'over', 'under', 'yes', 'no'):
        return None
    if market in ('spread', 'puckline', 'runline') and side in ('home', 'away'):
        if line == '':
            return None
        line = format(abs(Decimal(line)).normalize(), 'f')
    return (sport, event, start, book, period, market, line, player, capture, team, stat)


def _is_opposed(sides: set[str]) -> bool:
    return any(pair <= sides for pair in (
        {'home', 'away'}, {'over', 'under'}, {'yes', 'no'}))


def _validate_market_pair(row: dict) -> float:
    required = ('paired_quote_sha256', 'paired_captured_utc', 'paired_event_id',
                'paired_book', 'paired_period', 'paired_market', 'paired_side',
                'paired_line', 'paired_price_american')
    if any(k not in row for k in required):
        raise ValueError('MARKET_BASELINE_PAIR_NOT_ATTESTED')
    if not digest_ok(row['paired_quote_sha256']):
        raise ValueError('MARKET_BASELINE_PAIR_NOT_ATTESTED')
    if (row['paired_event_id'] != row['event_id'] or
        _book_id(row['paired_book']) != _book_id(row['book']) or
        row['paired_period'].strip().casefold() != row['period'].strip().casefold() or
        _market_id(row['paired_market']) != _market_id(row['market'])):
        raise ValueError('MISMATCHED_MARKET_PAIR_IDENTITY')
    opposite = {'over': 'under', 'under': 'over', 'home':'away', 'away':'home',
                'yes':'no', 'no':'yes'}
    side = str(row['side']).strip().casefold()
    if side not in opposite or row['paired_side'].strip().casefold() != opposite[side]:
        raise ValueError('MISMATCHED_OPPOSING_SIDE')
    market_id = _market_id(row['market'])
    # A same-line UNDER for a different player or different team total is NOT
    # an opposing quote. Requiring exact subject IDs prevents fabricated fair
    # baselines from unrelated offers sharing a threshold and event.
    if ('prop' in market_id or market_id in ('attd', 'firsttd', 'td2plus',
                                             'firstbasket', 'homerun')):
        fields = ('player_id', 'stat')
    elif market_id == 'teamtotal':
        fields = ('team_id', 'stat')
    else:
        fields = ()
    for field in fields:
        actual = str(row.get(field) or '').strip().casefold()
        paired = str(row.get('paired_' + field) or '').strip().casefold()
        if field in ('team_id','player_id') and not actual:
            raise ValueError('UNBOUND_SUBJECT_FOR_MARKET_BASELINE:' + field)
        if (actual or paired) and (not paired or actual != paired):
            raise ValueError('MISMATCHED_MARKET_PAIR_SUBJECT:' + field)
    orig = _canonical_line(row.get('line'))
    pair = _canonical_line(row.get('paired_line'))
    if _market_id(row['market']) in ('spread','puckline','runline','rl'):
        if not orig or not pair or Decimal(orig) + Decimal(pair) != 0:
            raise ValueError('MISMATCHED_SPREAD_LINE')
    elif orig != pair:
        raise ValueError('MISMATCHED_MARKET_PAIR_LINE')
    paired_time = when(row['paired_captured_utc'])
    captured_time = when(row['captured_utc'])
    if paired_time >= when(row['game_start_utc']) or abs((paired_time - captured_time).total_seconds()) > 300:
        raise ValueError('STALE_OR_LATE_OPPOSING_QUOTE')
    supplied = _valid_probability(row['market_p_no_vig'], 'market_probability')
    computed = devig_two_way(row['price_american'],row['paired_price_american'])['no_vig_a']
    if abs(supplied - computed) > 1e-6:
        raise ValueError('NO_VIG_BASELINE_MATH_MISMATCH')
    return computed

def _wilson(wins: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.95996398454
    p = wins / total
    den = 1 + z*z/total
    mid = (p + z*z/(2*total))/den
    rad = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/den
    return [round(max(0, mid-rad), 6), round(min(1, mid+rad), 6)]


def _percentile(sorted_values: list[float], fraction: float) -> float:
    k = (len(sorted_values)-1)*fraction
    lo = math.floor(k)
    hi = math.ceil(k)
    return sorted_values[lo] + (sorted_values[hi]-sorted_values[lo])*(k-lo)


def _cluster_ci(pairs: list[tuple[str, float]], *, reps: int = 400, seed: int = 46) -> list[float] | None:
    """Resample events, NOT correlated individual picks. Descriptive only."""
    grouped: dict[str, list[float]] = defaultdict(list)
    for event, value in pairs:
        grouped[event].append(value)
    events = sorted(grouped)
    if len(events) < 2 or reps < 20:
        return None
    rng = random.Random(seed)
    sims = []
    for _ in range(reps):
        draw = [rng.choice(events) for _ in events]
        nums = [v for event in draw for v in grouped[event]]
        sims.append(mean(nums))
    sims.sort()
    return [round(_percentile(sims, .025), 6), round(_percentile(sims, .975), 6)]


def _summary(records: list[dict]) -> dict:
    n = len(records)
    if not n:
        return {'n': 0, 'events': 0, 'wins': 0, 'losses': 0, 'pushes': 0, 'roi': None, 'net_units': 0.0,
                'brier': None, 'log_loss': None, 'market_brier': None,
                'model_brier_on_market_matched_rows': None,
                'paired_brier_delta_model_minus_market': None,
                'paired_brier_event_cluster95': None,
                'market_baseline_matched_n': 0,
                'win_rate': None, 'win_wilson95': None, 'roi_event_cluster95': None,
                'small_sample': True}
    events = len({r['event_id'] for r in records})
    decided = [r for r in records if r['outcome'] != 'P']
    model_brier = mean((r['p']-int(r['outcome'] == 'W'))**2 for r in decided) if decided else None
    model_logloss = mean(-math.log(r['p'] if r['outcome'] == 'W' else (1-r['p'])) for r in decided) if decided else None
    market = [r for r in decided if r.get('q') is not None]
    market_brier = (mean((r['q']-int(r['outcome'] == 'W'))**2 for r in market) if market else None)
    # An all-decided-rows model Brier is NOT comparable to market Brier
    # computed only where the exact same-line original two-way quote exists.
    # Score both probabilities on the identical matched decided rows.
    model_matched_brier = (
        mean((r['p']-int(r['outcome'] == 'W'))**2 for r in market)
        if market else None)
    paired_differences = [
        (r['p']-int(r['outcome'] == 'W'))**2
        - (r['q']-int(r['outcome'] == 'W'))**2 for r in market
    ]
    paired_brier_delta = mean(paired_differences) if market else None
    paired_brier_ci = _cluster_ci([
        (str(row['sport']) + ':' + str(row['event_id']), delta)
        for row, delta in zip(market, paired_differences)
    ])
    unit_total = sum(r['unit'] for r in records)
    n_w = sum(r['outcome'] == 'W' for r in decided)
    return {'n': n, 'decided_n': len(decided), 'events': events,
            'wins': n_w, 'losses': len(decided)-n_w, 'pushes': n-len(decided),
            'net_units': round(unit_total, 6), 'roi': round(unit_total/n, 6),
            'roi_event_cluster95': _cluster_ci([(r['event_id'], r['unit']) for r in records]),
            'win_rate': round(n_w/len(decided), 6) if decided else None,
            'win_wilson95': _wilson(n_w, len(decided)),
            'brier': round(model_brier, 6) if model_brier is not None else None,
            'log_loss': round(model_logloss, 6) if model_logloss is not None else None,
            'market_brier': round(market_brier, 6) if market_brier is not None else None,
            'model_brier_on_market_matched_rows': (
                round(model_matched_brier, 6) if model_matched_brier is not None else None),
            'paired_brier_delta_model_minus_market': (
                round(paired_brier_delta, 6) if paired_brier_delta is not None else None),
            'paired_brier_event_cluster95': paired_brier_ci,
            'market_baseline_matched_n': len(market),
            'small_sample': events < 30}


def replay(rows: list[dict]) -> dict:
    """Score explicit frozen, qualified rows. Nonqualifiers still counted in census.

    A hash with correct syntax is NOT proof of source authorship, so outputs
    are never labeled verified sportsbook returns.
    """
    rejected = []
    accepted = []
    unqualified = 0
    all_ids: dict[str, list[dict]] = defaultdict(list)
    fingerprints: dict[tuple, list[dict]] = defaultdict(list)
    decisions: dict[tuple, list[dict]] = defaultdict(list)
    mirror_checks: dict[tuple, list[dict]] = defaultdict(list)
    for n, row in enumerate(rows, 2):
        try:
            _asof_check(row)
            if str(row['qualified']).lower() in ('0', 'false'):
                unqualified += 1
                continue
            selection_id = str(row.get('selection_id') or '').strip()
            if not selection_id:
                raise ValueError('MISSING_SELECTION_ID')
            fingerprint = _selection_fingerprint(row)
            if row.get('outcome') not in VALID_OUTCOMES:
                raise ValueError('NOT_SETTLED_WIN_LOSS_PUSH')
            if not row.get('result_source'):
                raise ValueError('UNVERIFIED_RESULT_SOURCE')
            p = _valid_probability(row.get('p_model'), 'model_probability')
            q = None
            if row.get('market_p_no_vig') not in (None, ''):
                q = _validate_market_pair(row)
            outcome = row['outcome']
            profit = american(row['price_american'])[0] - 1
            unit = {'W': profit, 'L': -1.0, 'P': 0.0}[outcome]
            record = {'event_id': row['event_id'], 'sport': row['sport'],
                      'market': row['market'], 'side': row['side'],
                      'selection_id': selection_id, 'game_start_utc': when(row['game_start_utc']),
                      'outcome': outcome, 'p': p, 'q': q, 'unit': unit,
                      '_original_csv_line': n}
            accepted.append(record)
            all_ids[selection_id].append(record)
            fingerprints[fingerprint].append(record)
            decisions[_decision_key(fingerprint)].append(record)
            mirror_key = _mirror_key(fingerprint)
            if mirror_key is not None:
                mirror_checks[mirror_key].append(record)
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({'row': n, 'selection_id': row.get('selection_id'), 'reason': str(exc)})

    # Fail CLOSED. Simultaneous opposite sides are mirrored board offers, not
    # independent wagers. Repeated identical selections across captures are
    # also not multiple paper decisions; quarantine ALL of their occurrences.
    mirror_groups = [group for group in mirror_checks.values()
                     if _is_opposed({r['side'].strip().casefold() for r in group})]
    quarantines: dict[int, str] = {}
    for group in mirror_groups:
        for r in group:
            quarantines[r['_original_csv_line']] = 'MIRRORED_QUALIFIED_PAIR_QUARANTINED'
    duplicate_group_keys: set[frozenset[int]] = set()
    for groupings, reason in (
        (all_ids, 'DUPLICATE_SELECTION_ID_QUARANTINED'),
        (fingerprints, 'DUPLICATE_CANONICAL_QUALIFIED_BET_QUARANTINED'),
        (decisions, 'REPEATED_QUALIFIED_DECISION_QUARANTINED'),
    ):
        for group in groupings.values():
            if len(group) > 1:
                duplicate_group_keys.add(frozenset(r['_original_csv_line'] for r in group))
                for r in group:
                    quarantines.setdefault(r['_original_csv_line'], reason)
    for r in accepted:
        n = r['_original_csv_line']
        if n in quarantines:
            rejected.append({'row': n, 'selection_id': r['selection_id'],
                             'reason': quarantines[n]})
    accepted = [r for r in accepted if r['_original_csv_line'] not in quarantines]
    accepted.sort(key=lambda r: (r['game_start_utc'], r['selection_id']))
    ledger = []
    balance = peak = max_drawdown = 0.0
    for r in accepted:
        balance += r['unit']
        peak = max(peak, balance)
        max_drawdown = max(max_drawdown, peak-balance)
        ledger.append({'selection_id': r['selection_id'], 'event_id': r['event_id'],
                       'units': round(r['unit'], 6), 'cumulative_units': round(balance, 6)})
    by_market: dict[tuple[str, str], list[dict]] = defaultdict(list)
    cal: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in accepted:
        by_market[(r['sport'], r['market'])].append(r)
        if r['outcome'] != 'P':
            bucket = min(19, int(r['p']*20))
            cal[(r['sport'], r['market'], f'{bucket*5:02d}-{(bucket+1)*5:02d}%')].append(r)
    return {
        'status': 'REPLAY_PAPER_0U_NOT_EXECUTION_AUTHENTICATED',
        'input_rows': len(rows), 'unqualified': unqualified,
        'rejected_qualified_or_invalid': rejected, 'eligible': len(accepted),
        'possible_opposite_side_selection_groups': len(mirror_groups),
        'mirror_quarantined_rows': len({r['_original_csv_line'] for group in mirror_groups for r in group}),
        'duplicate_decision_groups': len(duplicate_group_keys),
        'total_quarantined_rows': len(quarantines),
        'overall': _summary(accepted),
        'max_drawdown_units': round(max_drawdown, 6),
        'by_market': [{'sport': sport, 'market': market, **_summary(group)}
                      for (sport, market), group in sorted(by_market.items())],
        'calibration_5pp': [{'sport': sport, 'market': market, 'prob_bucket': bucket,
                            'predicted_mean': round(mean(r['p'] for r in group), 6),
                            'observed_win_rate': round(mean(r['outcome'] == 'W' for r in group), 6),
                            **_summary(group)} for (sport, market, bucket), group in sorted(cal.items())],
        'ledger': ledger,
        'warning': 'Mirrored sides and repeated paper decisions (including across price snapshots) are quarantined from ROI/calibration. This is not walk-forward TRAINING or authenticated execution; hashes cannot certify sportsbook availability.',
    }


def bias_analysis(rows: list[dict]) -> dict:
    """Signed error (actual - projection) in independent scored numeric markets."""
    valid = []
    rejected = []
    for n, r in enumerate(rows, 2):
        try:
            event = r['event_id']
            if not event or r.get('sport') not in SPORTS:
                raise ValueError('INVALID_EVENT_OR_SPORT')
            if when(r['model_asof_utc']) >= when(r['game_start_utc']):
                raise ValueError('POST_KICKOFF_PROJECTION')
            if when(r['feature_available_utc']) > when(r['model_asof_utc']):
                raise ValueError('FUTURE_FEATURE')
            if not (digest_ok(r.get('model_sha256')) and r.get('result_source')):
                raise ValueError('UNCERTIFIED_MODEL_OR_RESULT')
            actual = float(r['actual_value']); predicted = float(r['projected_mean'])
            if not math.isfinite(actual) or not math.isfinite(predicted):
                raise ValueError('NONFINITE_VALUE')
            valid.append((r, actual-predicted))
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({'row': n, 'reason': str(exc)})
    groups: dict[tuple[str, str], list[tuple[dict, float]]] = defaultdict(list)
    dimensions = ('sport', 'market', 'player_id', 'team_id', 'opponent_id', 'side')
    for r, error in valid:
        for d in dimensions:
            if r.get(d):
                groups[(d, str(r[d]))].append((r, error))
    report = []
    for (d, value), group in sorted(groups.items()):
        event_count = len({r['event_id'] for r, e in group})
        errors = [e for r, e in group]
        report.append({'dimension': d, 'value': value, 'n': len(errors),
                       'distinct_events': event_count, 'mean_error_actual_minus_model': round(mean(errors), 6),
                       'mae': round(mean(abs(x) for x in errors), 6),
                       'mean_error_cluster95': _cluster_ci([(r['event_id'], e) for r, e in group]),
                       'small_sample': event_count < 30})
    return {'status': 'PAPER_ERROR_DIAGNOSTIC_NO_MODEL_CHANGE', 'rows': len(rows),
            'accepted': len(valid), 'rejected': rejected, 'groups': report}


def paired_ablation(rows: list[dict]) -> dict:
    """Score separately frozen baseline vs feature candidate; NEVER fit here."""
    clean, excluded, seen = [], [], set()
    for n, row in enumerate(rows, 2):
        try:
            key = (row['event_id'], row['market'], row['selection'])
            if key in seen:
                raise ValueError('DUPLICATE_EVAL_KEY')
            seen.add(key)
            if (when(row['feature_available_utc']) > when(row['forecast_asof_utc'])
                    or when(row['forecast_asof_utc']) >= when(row['game_start_utc'])):
                raise ValueError('PIT_VIOLATION')
            if not all(digest_ok(row.get(x)) for x in ('baseline_model_sha256', 'candidate_model_sha256')):
                raise ValueError('UNPINNED_MODELS')
            y = float(row['outcome'])
            if y not in (0., 1.):
                raise ValueError('BINARY_DECIDED_ONLY')
            pb = _valid_probability(row['baseline_probability'], 'baseline')
            pc = _valid_probability(row['candidate_probability'], 'candidate')
            clean.append((row['event_id'], (pb-y)**2, (pc-y)**2))
        except (ValueError, KeyError, TypeError) as exc:
            excluded.append({'row': n, 'reason': str(exc)})
    delta = [(event, baseline-candidate) for event, baseline, candidate in clean]
    return {'status': 'ABLATION_SHADOW_ONLY_NO_ADOPTION', 'n': len(clean),
            'events': len({x[0] for x in clean}), 'excluded': excluded,
            'baseline_brier': round(mean(v for _,v,_ in clean),6) if clean else None,
            'candidate_brier': round(mean(v for _,_,v in clean),6) if clean else None,
            'delta_brier_positive_is_candidate_better': round(mean(v for _,v in delta),6) if delta else None,
            'delta_event_cluster95': _cluster_ci(delta),
            'small_sample': len({x[0] for x in clean}) < 30,
            'warning': 'Only compare preregistered feature additions on a genuinely untouched date block; this script cannot establish training or release authenticity.'}


def market_census(rows: list[dict]) -> dict:
    """Every supplied offer row remains visible even if pricing is absent."""
    out = []
    for i,r in enumerate(rows, 2):
        key = {k:r.get(k,'') for k in ('sport','event_id','period','market','player_id','line')}
        missing = [k for k in ('sport','event_id','period','market') if not r.get(k)]
        if missing:
            status = 'INVALID_INVENTORY_ROW'
        elif str(r.get('offered','')).lower() in ('0','false'):
            status = 'NOT_OFFERED'
        elif str(r.get('offered','')).lower() not in ('1','true'):
            status = 'OFFER_STATUS_UNKNOWN'
        elif str(r.get('captured','')).lower() not in ('1','true'):
            status = 'NOT_CAPTURED'
        elif str(r.get('modeled','')).lower() not in ('1','true'):
            status = 'NO_MODEL'
        elif str(r.get('provenance','')).lower() not in ('1','true'):
            status = 'NO_PROVENANCE'
        else:
            status = 'PAPER_UNTIL_FORWARD_ACCEPTANCE'
        out.append({'row':i, **key, 'status': status})
    counts = {status:sum(v['status']==status for v in out) for status in sorted({x['status'] for x in out})}
    return {'status':'PAPER_MARKET_CENSUS', 'provided_inventory_n':len(out),
            'status_counts': counts, 'rows':out,
            'warning':'Only evaluates supplied offers; cannot infer sportsbook market availability.'}


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['replay','bias','ablation','census'])
    p.add_argument('csv_file')
    p.add_argument('--report',required=True,help='Create-only output JSON')
    args=p.parse_args(argv)
    raw=Path(args.csv_file).read_bytes()
    rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    f={'replay':replay,'bias':bias_analysis,'ablation':paired_ablation,'census':market_census}[args.mode]
    report=f(rows)
    report['source_sha256']=hashlib.sha256(raw).hexdigest()
    with Path(args.report).open('x',encoding='utf-8') as fp:
        json.dump(report,fp,indent=2,sort_keys=True,allow_nan=False)
        fp.write('\n')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
