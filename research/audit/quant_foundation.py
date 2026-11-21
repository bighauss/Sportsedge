"""Read-only, standard-library SportsEdge PIT audit, EV and paper performance.

Input contract is compatible with research/audit/pregame_edge_audit.py.
No betting eligibility or prediction-model changes are authorized by this file.
"""
from __future__ import annotations

import argparse
import csv
import io
import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from fractions import Fraction

SPORTS = frozenset(('NFL', 'CFB', 'CBB', 'NBA', 'MLB', 'NHL'))
REQUIRED = ('sport', 'event_id', 'period', 'market', 'side', 'price_american',
            'p_model', 'model_asof_utc', 'captured_utc', 'game_start_utc',
            'quote_sha256', 'model_sha256')
TIME_FIELDS = ('model_asof_utc', 'captured_utc', 'game_start_utc',
               'feature_available_utc', 'source_published_utc')


def when(value: str) -> dt.datetime:
    if not value or not value.strip():
        raise ValueError('MISSING_TIME')
    stamp = dt.datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    if stamp.utcoffset() is None:
        raise ValueError('NAIVE_TIME')
    return stamp.astimezone(dt.timezone.utc)


def american(odds: str | int) -> tuple[float, float]:
    """Return gross decimal odds and implied probability (not no-vig fair)."""
    try:
        value = int(str(odds).strip().replace('−', '-').replace('＋', '+'))
    except (TypeError, ValueError) as exc:
        raise ValueError('INVALID_AMERICAN_ODDS') from exc
    if -100 < value < 100 or abs(value) > 100000:
        raise ValueError('INVALID_AMERICAN_ODDS')
    decimal = 1.0 + (value / 100 if value > 0 else 100 / abs(value))
    return decimal, 1.0 / decimal



def odds_in_format(odds: str | int | float, fmt: str) -> tuple[float, float]:
    """Explicit odds-format conversion; no auto-detection or format guessing."""
    f = fmt.strip().casefold()
    if f == 'american':
        return american(odds)
    if f == 'decimal':
        value = float(odds)
        if not math.isfinite(value) or value <= 1 or value > 1e7:
            raise ValueError('INVALID_DECIMAL_ODDS')
        return value, 1.0/value
    if f == 'fractional':
        try:
            value = Fraction(str(odds).strip())
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError('INVALID_FRACTIONAL_ODDS') from exc
        if value <= 0 or float(value) > 1e7:
            raise ValueError('INVALID_FRACTIONAL_ODDS')
        decimal = float(value) + 1.0
        return decimal, 1.0/decimal
    raise ValueError('UNKNOWN_ODDS_FORMAT')


def settlement_ev(probabilities: dict[str, float], odds: str | int | float,
                  *, odds_format: str = 'american', fee_on_profit: float = 0.0) -> float:
    """W/L/P/HW/HL expected return per $1, for explicitly supported settlements.

    Half wins and losses are paid/charged at half stake. This is NOT an
    implementation of all sport-specific dead-heat or void book policies.
    """
    if not math.isfinite(fee_on_profit) or not 0 <= fee_on_profit <= 1:
        raise ValueError('INVALID_FEE')
    if not probabilities or set(probabilities)-{'W','L','P','HW','HL'}:
        raise ValueError('UNSUPPORTED_SETTLEMENT_OUTCOME')
    vals = list(probabilities.values())
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or
           not math.isfinite(v) or v < 0 for v in vals):
        raise ValueError('INVALID_SETTLEMENT_PROBABILITY')
    if abs(sum(vals)-1) > 1e-8:
        raise ValueError('SETTLEMENT_PROBABILITIES_NOT_NORMALIZED')
    profit = (odds_in_format(odds,odds_format)[0]-1.0)*(1.0-fee_on_profit)
    payout = {'W': profit,'L': -1.0,'P': 0.0,'HW': profit/2,'HL': -0.5}
    return sum(probabilities.get(key,0.0)*value for key,value in payout.items())


def quarter_line_probabilities(draws: list[float], line: float, side: str) -> dict:
    """Derive quarter-line W/L/P/HW/HL via two half-stake components.

    For example Over 2.25 = half Over 2.0 + half Over 2.5.
    Requires genuine projected samples; never manufactures a distribution.
    """
    if (not draws or side.casefold() not in ('over','under') or
            not math.isfinite(line) or any(not math.isfinite(x) for x in draws)):
        raise ValueError('INVALID_QUARTER_LINE_INPUT')
    if any(not float(x).is_integer() for x in draws):
        raise ValueError('QUARTER_SPLIT_REQUIRES_INTEGER_OUTCOMES')
    if round(line*4) != line*4 or round(line*4) % 2 != 1:
        raise ValueError('NOT_QUARTER_LINE')
    low = math.floor(line*2)/2
    high = low + 0.5
    outcomes = {'W': 0,'L': 0,'P': 0,'HW': 0,'HL': 0}
    for draw in draws:
        one = (1 if draw > low else 0 if draw == low else -1) if side.casefold() == 'over' else (-1 if draw > low else 0 if draw == low else 1)
        two = (1 if draw > high else 0 if draw == high else -1) if side.casefold() == 'over' else (-1 if draw > high else 0 if draw == high else 1)
        score = one+two
        outcome = {2:'W',1:'HW',0:'P',-1:'HL',-2:'L'}[score]
        outcomes[outcome]+=1
    return {key:value/len(draws) for key,value in outcomes.items()}


def devig_two_way(odds_a: str | int, odds_b: str | int, *,
                  format_a: str = 'american', format_b: str = 'american') -> dict:
    """Proportional no-vig estimate for a matched two-way market only."""
    a = odds_in_format(odds_a, format_a)[1]
    b = odds_in_format(odds_b, format_b)[1]
    return {'overround': a + b - 1.0,
            'no_vig_a': a / (a + b), 'no_vig_b': b / (a + b)}


def ev_per_dollar(p_win: float, p_push: float, odds: str | int | float,
                  *, fee_on_profit: float = 0.0, odds_format: str = 'american') -> float:
    """P(win)*net_profit - P(loss), flat $1 risk; returned fees only on wins."""
    if (not all(math.isfinite(v) for v in (p_win, p_push, fee_on_profit))
            or min(p_win, p_push, fee_on_profit) < 0
            or p_win + p_push > 1 + 1e-12 or fee_on_profit > 1):
        raise ValueError('INVALID_PROBABILITIES_OR_FEE')
    profit = (odds_in_format(odds, odds_format)[0] - 1.0) * (1.0 - fee_on_profit)
    return p_win * profit - (1.0 - p_win - p_push)


def probabilities_from_samples(draws: list[float], line: float,
                               side: str) -> dict:
    """Discrete empirical distribution; exact equality is a push, never a win."""
    if not draws or side.lower() not in ('over', 'under'):
        raise ValueError('MISSING_SAMPLES_OR_SIDE')
    if not math.isfinite(line) or any(not math.isfinite(v) for v in draws):
        raise ValueError('INVALID_SAMPLES')
    win = sum((v > line if side.lower() == 'over' else v < line) for v in draws)
    push = sum(v == line for v in draws)
    n = len(draws)
    return {'mean': mean(draws), 'median': median(draws),
            'p_win': win / n, 'p_push': push / n,
            'p_loss': (n - win - push) / n, 'n': n}


def player_prop_baseline(logs: list[dict], *, player_id: str,
                         asof_utc: str, projected_minutes: float,
                         line: float, side: str,
                         opportunity_multiplier: float = 1.0,
                         efficiency_multiplier: float = 1.0) -> dict:
    """Lag-only empirical baseline; no fitted uncertainty claim.

    Every log: player_id, game_start_utc, data_available_utc,
               actual_stat, played_minutes, opportunities.
    Requires user-supplied projected minutes; multipliers 1 are neutral.
    """
    freeze = when(asof_utc)
    if (not player_id or projected_minutes <= 0 or
            not all(math.isfinite(x) and x > 0 for x in
                    (projected_minutes, opportunity_multiplier, efficiency_multiplier))):
        raise ValueError('INVALID_PROP_INPUT')
    past = []
    for row in logs:
        if row.get('player_id') != player_id:
            continue
        # Unknown point-in-time provenance is NOT inferred from game date.
        start, published = when(row['game_start_utc']), when(row['data_available_utc'])
        if start >= freeze or published >= freeze:
            continue
        mins, opp, stat = (float(row[name]) for name in
                           ('played_minutes', 'opportunities', 'actual_stat'))
        if not all(math.isfinite(x) for x in (mins, opp, stat)) or mins <= 0 or opp <= 0 or stat < 0:
            raise ValueError('INVALID_PAST_LOG')
        past.append((mins, opp, stat))
    if len(past) < 3:
        raise ValueError('INSUFFICIENT_PIT_LOGS')
    volume_rate = sum(opp for mins, opp, stat in past) / sum(mins for mins, opp, stat in past)
    efficiency = sum(stat for mins, opp, stat in past) / sum(opp for mins, opp, stat in past)
    projected_opportunities = projected_minutes * volume_rate * opportunity_multiplier
    baseline_mean = projected_opportunities * efficiency * efficiency_multiplier
    # Paired within-game rates retain observed opportunity/efficiency covariation.
    draws = [projected_minutes * (opp / mins) * (stat / opp)
             * opportunity_multiplier * efficiency_multiplier for mins, opp, stat in past]
    probabilities = probabilities_from_samples(draws, line, side)
    return {'status': 'UNCALIBRATED_RESEARCH', 'player_id': player_id,
            'n_past_games': len(past), 'projected_opportunities': projected_opportunities,
            'baseline_mean': baseline_mean, 'empirical': probabilities,
            'draws': draws, 'asof_utc': freeze.isoformat()}


def audit_rows(raw_rows: list[dict]) -> dict:
    """Every original input row is retained; every transformation is logged."""
    issues, corrections, cleaned, seen = [], [], [], set()
    id_to_names, name_to_ids = defaultdict(set), defaultdict(set)
    event_start, event_teams = defaultdict(set), defaultdict(set)
    stat_values = defaultdict(list)
    def issue(number, code, field=''):
        issues.append({'row': number, 'code': code, 'field': field})
    for number, original in enumerate(raw_rows, 2):
        row = dict(original)
        for field, old in list(row.items()):
            if old is None:
                continue
            new = old.strip() if isinstance(old, str) else old
            if field == 'price_american' and isinstance(new, str):
                new = new.replace('−', '-').replace('＋', '+')
            if old != new:
                row[field] = new
                corrections.append({'row': number, 'field': field,
                                    'from': old, 'to': new})
        cleaned.append(row)
        for field in REQUIRED:
            if not row.get(field) and not (field == 'price_american' and row.get(field) == 0):
                issue(number, 'MISSING_REQUIRED', field)
        if not row.get('line') and str(row.get('market', '')).strip().lower() not in ('ml', 'moneyline', 'money_line'):
            issue(number, 'MISSING_LINE', 'line')
        if row.get('sport') not in SPORTS:
            issue(number, 'UNKNOWN_SPORT', 'sport')
        if 'prop' in str(row.get('market', '')).lower() and not row.get('player_id'):
            issue(number, 'UNBOUND_PLAYER_ID', 'player_id')
        times = {}
        for field in TIME_FIELDS:
            if row.get(field):
                try:
                    times[field] = when(str(row[field]))
                except (TypeError, ValueError):
                    issue(number, 'INVALID_TIME', field)
        if 'game_start_utc' in times:
            for field in ('captured_utc', 'model_asof_utc'):
                if field in times and times[field] >= times['game_start_utc']:
                    issue(number, 'AFTER_KICKOFF', field)
        if 'model_asof_utc' in times:
            for field in ('feature_available_utc', 'source_published_utc'):
                if field not in times:
                    issue(number, 'PIT_PROVENANCE_NOT_SUPPLIED', field)
                elif times[field] > times['model_asof_utc']:
                    issue(number, 'FUTURE_INPUT_LEAK', field)
        if all(x in times for x in ('captured_utc', 'game_start_utc')) and times['captured_utc'] >= times['game_start_utc']:
            issue(number, 'NOT_PREGAME', 'captured_utc')
        for field in ('quote_sha256', 'model_sha256'):
            value = str(row.get(field, ''))
            if len(value) != 64 or any(c not in 'abcdefABCDEF0123456789' for c in value):
                issue(number, 'UNVERIFIABLE_HASH_FORMAT', field)
        try:
            american(row.get('price_american'))
        except ValueError:
            issue(number, 'INVALID_ODDS', 'price_american')
        try:
            p = float(row.get('p_model'))
            if not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError
        except (ValueError, TypeError):
            issue(number, 'INVALID_MODEL_PROBABILITY', 'p_model')
        forbidden = ('feature_final_', 'feature_closing_', 'feature_postgame_')
        for field in row:
            if any(field.lower().startswith(prefix) for prefix in forbidden) and row.get(field):
                issue(number, 'POTENTIAL_TARGET_LEAKAGE', field)
        key = tuple(row.get(k, '') for k in ('sport', 'event_id', 'game_start_utc',
                     'book', 'period', 'market', 'side', 'line', 'player_id', 'captured_utc'))
        if key in seen:
            issue(number, 'DUPLICATE_QUOTE_IDENTITY')
        seen.add(key)
        if row.get('event_id') and row.get('sport') and 'game_start_utc' in times:
            eid = (row['sport'], row['event_id'])
            event_start[eid].add(times['game_start_utc'].isoformat())
            if row.get('home_id') and row.get('away_id'):
                event_teams[eid].add((row['home_id'],row['away_id']))
        for field in ('actual_stat','projected_mean','projected_minutes','played_minutes'):
            if row.get(field) in (None,''):
                continue
            try:
                val = float(row[field])
                if not math.isfinite(val):
                    raise ValueError
                if field in ('projected_minutes','played_minutes') and val < 0:
                    issue(number,'NEGATIVE_PLAYING_TIME',field)
                stat_values[(row.get('sport'),row.get('market'),field)].append((number,val))
            except (TypeError,ValueError):
                issue(number,'NONFINITE_OR_INVALID_STAT',field)
        pid, name = row.get('player_id', ''), row.get('player', '')
        if pid and name:
            id_to_names[pid].add(name.casefold())
            name_to_ids[name.casefold()].add(pid)
    for event, dates in event_start.items():
        if len(dates)>1:
            issue(0,'EVENT_ID_KICKOFF_CONFLICT:'+':'.join(event))
    for event, teams in event_teams.items():
        if len(teams)>1:
            issue(0,'EVENT_ID_TEAM_MAPPING_CONFLICT:'+':'.join(event))
    for (sport,market,field), pairs in stat_values.items():
        if len(pairs)<20:
            continue
        center=median(v for _,v in pairs)
        mad=median(abs(v-center) for _,v in pairs)
        if mad>0:
            for rownum,value in pairs:
                if abs(value-center)>10*mad:
                    issue(rownum,'ROBUST_STAT_OUTLIER_REVIEW',field)
    for key, names in id_to_names.items():
        if len(names) > 1:
            issue(0, 'PLAYER_ID_NAME_CONFLICT:' + key)
    for name, ids in name_to_ids.items():
        if len(ids) > 1:
            issue(0, 'PLAYER_NAME_ID_CONFLICT:' + name)
    return {'status': 'PAPER_0U_AUDIT_ONLY', 'total_rows': len(raw_rows),
            'retained_rows': len(cleaned), 'corrections': corrections,
            'issues': issues, 'cleaned_rows': cleaned}


def paper_ledger(rows: list[dict]) -> dict:
    """Use the same STRICT frozen-decision replay as the other paper CLI.

    Do not maintain a permissive second accounting path: mirrored sides,
    duplicate selections and source/clock failures must all fail closed.
    This is a structural research report, never a verified wager ledger.
    """
    from quant_evidence import replay  # Lazy import avoids module import cycles.

    report = replay(rows)
    overall = report['overall']
    return {
        'status': 'PAPER_RESEARCH_NOT_CERTIFIED',
        'qualified_graded_n': report['eligible'],
        'wins': overall['wins'], 'losses': overall['losses'],
        'pushes': overall['pushes'],
        'win_rate_decided': overall['win_rate'],
        'net_units': overall['net_units'], 'roi_flat_1u': overall['roi'],
        'max_drawdown_units': report['max_drawdown_units'],
        'by_market': [
            {'sport': item['sport'], 'market': item['market'],
             'n': item['n'], 'units': item['net_units'], 'roi': item['roi']}
            for item in report['by_market']
        ],
        'unverifiable': [
            {'row': item['row'], 'code': item['reason'],
             'selection_id': item.get('selection_id')}
            for item in report['rejected_qualified_or_invalid']
        ],
        'unqualified_n': report['unqualified'],
        'mirror_quarantined_rows': report['mirror_quarantined_rows'],
        'duplicate_decision_groups': report['duplicate_decision_groups'],
        'total_quarantined_rows': report['total_quarantined_rows'],
        'accounting_contract': report['status'],
        'warning': 'Identical conservative decision admission as quant_evidence.replay; no certified historical ROI or source authentication.',
    }



def parse_source_csv(raw: bytes) -> list[dict]:
    """Parse a complete original CSV without silently overwriting duplicate
    headers, ignoring blank records, or coercing ragged fields.

    Invalid sources stay untouched; do not emit a misleading normalized copy.
    Both the audit and paper ledger must consume the same safe row parser.
    """
    if type(raw) is not bytes or not raw:
        raise ValueError('EMPTY_OR_NONBYTES_CSV')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('INVALID_UTF8_CSV') from exc
    # A blank physical line inside a quoted CSV field is valid source data.
    # Parse *logical* records so genuine empty records cannot disappear while
    # embedded line breaks keep the exact original field and row denominator.
    try:
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = next(reader, None)
        if not header or any(not isinstance(h, str) or not h.strip()
                             for h in header):
            raise ValueError('CSV_HEADER_MISSING_OR_BLANK')
        normalized = [h.strip().casefold() for h in header]
        if len(set(normalized)) != len(header):
            raise ValueError('CSV_DUPLICATE_NORMALIZED_HEADER')
        if any(h != h.strip() for h in header):
            raise ValueError('CSV_UNNORMALIZED_HEADER')
        rows = []
        for cells in reader:
            if not cells or all(not value.strip() for value in cells):
                raise ValueError('BLANK_CSV_RECORD')
            if len(cells) > len(header):
                raise ValueError('CSV_EXTRA_FIELD_NOT_IN_HEADER')
            if len(cells) < len(header):
                raise ValueError('CSV_MISSING_FIELD_IN_RECORD')
            rows.append(dict(zip(header, cells)))
    except csv.Error as exc:
        raise ValueError('MALFORMED_CSV') from exc
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('audit', 'ledger'))
    parser.add_argument('csv_file')
    parser.add_argument('--report', required=True, help='Create-only JSON, never overwrites')
    parser.add_argument('--cleaned', help='Create-only corrected CSV; audit mode only')
    args = parser.parse_args(argv)
    raw = Path(args.csv_file).read_bytes()
    rows = parse_source_csv(raw)
    report = audit_rows(rows) if args.mode == 'audit' else paper_ledger(rows)
    report['source_sha256'] = hashlib.sha256(raw).hexdigest()
    if args.mode == 'audit' and args.cleaned and rows:
        with Path(args.cleaned).open('x', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(report.pop('cleaned_rows'))
    elif args.cleaned and args.mode == 'ledger':
        parser.error('--cleaned is only valid for audit mode')
    report.pop('cleaned_rows', None)
    with Path(args.report).open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str, allow_nan=False)
        f.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
