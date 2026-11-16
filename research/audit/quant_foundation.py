"""Read-only, standard-library SportsEdge PIT audit, EV and paper performance.

Input contract is compatible with research/audit/pregame_edge_audit.py.
No betting eligibility or prediction-model changes are authorized by this file.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

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


def devig_two_way(odds_a: str | int, odds_b: str | int) -> dict:
    """Proportional no-vig estimate for a matched two-way market only."""
    a = american(odds_a)[1]
    b = american(odds_b)[1]
    return {'overround': a + b - 1.0,
            'no_vig_a': a / (a + b), 'no_vig_b': b / (a + b)}


def ev_per_dollar(p_win: float, p_push: float, odds: str | int,
                  *, fee_on_profit: float = 0.0) -> float:
    """P(win)*net_profit - P(loss), flat $1 risk; returned fees only on wins."""
    if (not all(math.isfinite(v) for v in (p_win, p_push, fee_on_profit))
            or min(p_win, p_push, fee_on_profit) < 0
            or p_win + p_push > 1 + 1e-12 or fee_on_profit > 1):
        raise ValueError('INVALID_PROBABILITIES_OR_FEE')
    profit = (american(odds)[0] - 1.0) * (1.0 - fee_on_profit)
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
        pid, name = row.get('player_id', ''), row.get('player', '')
        if pid and name:
            id_to_names[pid].add(name.casefold())
            name_to_ids[name.casefold()].add(pid)
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
    """Only explicitly qualified and completely graded entries count in ROI."""
    issues, eligible, seen = [], [], set()
    for i, row in enumerate(rows, 2):
        qualified = str(row.get('qualified', '')).strip().lower()
        if qualified not in ('1', 'true', '0', 'false'):
            issues.append({'row': i, 'code': 'QUALIFICATION_UNKNOWN'}); continue
        if qualified in ('0', 'false'):
            continue
        key = str(row.get('selection_id', '')).strip()
        if not key or key in seen:
            issues.append({'row': i, 'code': 'SELECTION_ID_MISSING_OR_DUPLICATED'}); continue
        seen.add(key)
        if not row.get('qualification_rule_sha256'):
            issues.append({'row': i, 'code': 'UNFROZEN_QUALIFICATION_RULE'}); continue
        try:
            freeze, start, captured = (when(row[f]) for f in
                                    ('model_asof_utc', 'game_start_utc', 'captured_utc'))
            if freeze >= start or captured >= start:
                raise ValueError('NOT_PREGAME')
            american(row['price_american'])
            for digest_field in ('quote_sha256', 'model_sha256', 'qualification_rule_sha256'):
                digest = str(row.get(digest_field, ''))
                if len(digest) != 64 or any(c not in '0123456789abcdefABCDEF' for c in digest):
                    raise ValueError('INVALID_' + digest_field.upper())
            for source_field in ('feature_available_utc', 'source_published_utc'):
                if when(row[source_field]) > freeze:
                    raise ValueError('FUTURE_' + source_field.upper())
            if row.get('sport') not in SPORTS or not row.get('event_id') or not row.get('book'):
                raise ValueError('UNBOUND_EVENT_OR_BOOK')
            if 'prop' in str(row.get('market', '')).lower() and not row.get('player_id'):
                raise ValueError('UNBOUND_PROP_PLAYER')
            if row.get('outcome') not in ('W', 'L', 'P'):
                raise ValueError('RESULT_UNVERIFIABLE')
            if not row.get('result_source'):
                raise ValueError('MISSING_RESULT_PROVENANCE')
            unit = {'W': american(row['price_american'])[0] - 1,
                    'L': -1.0, 'P': 0.0}[row['outcome']]
            eligible.append({'id': key, 'sport': row.get('sport', ''),
                             'market': row.get('market', ''), 'unit': unit,
                             'outcome': row['outcome'], 'start': start})
        except (KeyError, ValueError, TypeError) as exc:
            issues.append({'row': i, 'code': 'EXCLUDED_NOT_VERIFIED:' + str(exc)})
    eligible.sort(key=lambda x: (x['start'], x['id']))
    balance = peak = drawdown = 0.0
    by_market = defaultdict(lambda: {'n': 0, 'units': 0.0})
    for item in eligible:
        balance += item['unit']
        peak = max(peak, balance)
        drawdown = max(drawdown, peak - balance)
        agg = by_market[(item['sport'], item['market'])]
        agg['n'] += 1
        agg['units'] += item['unit']
    n = len(eligible)
    wins = sum(x['outcome'] == 'W' for x in eligible)
    losses = sum(x['outcome'] == 'L' for x in eligible)
    return {'status': 'PAPER_RESEARCH_NOT_CERTIFIED', 'qualified_graded_n': n,
            'wins': wins, 'losses': losses, 'pushes': n-wins-losses,
            'win_rate_decided': wins/(wins+losses) if wins+losses else None,
            'net_units': balance, 'roi_flat_1u': balance/n if n else None,
            'max_drawdown_units': drawdown,
            'by_market': [{'sport': s, 'market': m, **v,
                           'roi': v['units']/v['n']} for (s, m), v in sorted(by_market.items())],
            'unverifiable': issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('audit', 'ledger'))
    parser.add_argument('csv_file')
    parser.add_argument('--report', required=True, help='Create-only JSON, never overwrites')
    parser.add_argument('--cleaned', help='Create-only corrected CSV; audit mode only')
    args = parser.parse_args(argv)
    raw = Path(args.csv_file).read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
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
