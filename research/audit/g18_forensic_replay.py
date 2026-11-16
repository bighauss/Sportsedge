"""Read-only independent replay for SportsEdge Nov 9 CBB G-18 grading defect.

The historical bug dispatched generic TOTAL before TEAM_TOTAL, so a team total
could be compared with the two-team score. This tool reproduces *that rule* and
compares it with a corrected independent settlement reference. A historical
count is never considered reproduced unless the original pregame picks and
finals bytes are supplied; no source provider is authenticated by this tool.

Input: original picks.csv with columns game,pick,price, and a finals JSON map
from game strings ("Away @ Home") to away/home/away_1h/home_1h and source.
Every original row is retained, even invalid or ungraded. No ROI is reported:
all priced sides, including mirrored alternatives, are not qualified wagers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path


class InvalidRecord(ValueError):
    pass


def _reject_duplicate_json_keys(pairs):
    unique = {}
    for key, value in pairs:
        if key in unique:
            raise InvalidRecord('DUPLICATE_FINAL_JSON_KEY:' + key)
        unique[key] = value
    return unique


def _validate_american_price(price):
    # Retain bad rows, but never silently grade a malformed priced selection.
    if not isinstance(price, str) or not re.fullmatch(r'[+-]?[0-9]{3,6}', price.strip()):
        raise InvalidRecord('INVALID_OR_MISSING_AMERICAN_PRICE')
    value = int(price.strip())
    if not 100 <= abs(value) <= 100000:
        raise InvalidRecord('INVALID_OR_MISSING_AMERICAN_PRICE')
    return value



def _d(value: str) -> Decimal:
    try:
        n = Decimal(str(value))
    except InvalidOperation as e:
        raise InvalidRecord('INVALID_LINE') from e
    if not n.is_finite() or n < 0 or n > 10000:
        raise InvalidRecord('INVALID_LINE')
    return n


def _teams(game: str) -> tuple[str, str]:
    if not isinstance(game, str) or game.count(' @ ') != 1:
        raise InvalidRecord('BAD_GAME_IDENTITY')
    away, home = (x.strip() for x in game.split(' @ '))
    if not away or not home or away == home:
        raise InvalidRecord('BAD_GAME_IDENTITY')
    return away, home


def parse_selection(game: str, pick: str) -> tuple[str, str | None, str, Decimal | None]:
    """Parse original printed pick without guessing player/team identity."""
    away, home = _teams(game)
    if not isinstance(pick, str):
        raise InvalidRecord('MISSING_PICK')
    text = pick.strip()
    first_half = text.startswith('1H ')
    body = text[3:] if first_half else text
    prefix = '1H_' if first_half else ''
    if body in (f'{away} ML', f'{home} ML'):
        return prefix + 'ML', body[:-3], 'ML', None
    if (m := re.fullmatch(r'(?:(.+?) )?(Over|Under) (\d+(?:\.\d+)?)', body)):
        team, side, line = m.groups()
        if team is None:
            return prefix + 'TOTAL', None, side, _d(line)
        if team in (away, home):
            return prefix + 'TEAM_TOTAL', team, side, _d(line)
    # Signed spread line is relative to the printed team, not to the home team.
    if (m := re.fullmatch(r'(.+?) ([+-])(\d+(?:\.\d+)?)', body)):
        team, sign, number = m.groups()
        if team in (away, home):
            magnitude = _d(number)
            return prefix + 'SPREAD', team, 'SPREAD', magnitude if sign == '+' else -magnitude
    raise InvalidRecord('UNPARSED_MARKET_OR_TEAM')


def _score(value: object, field: str) -> Decimal:
    # College basketball points are nonnegative integers.
    if type(value) is not int or not 0 <= value <= 300:
        raise InvalidRecord('INVALID_SCORE:' + field)
    return Decimal(value)


def _grade(cmp: Decimal, side: str) -> str:
    if side == 'Under':
        cmp = -cmp
    return 'W' if cmp > 0 else ('L' if cmp < 0 else 'P')


def grade_one(game: str, pick: str, final: dict, *, historic_bug: bool) -> str:
    family, team, side, line = parse_selection(game, pick)
    if not isinstance(final, dict):
        raise InvalidRecord('INVALID_FINAL')
    away, home = _teams(game)
    first_half = family.startswith('1H_')
    field_a = 'away_1h' if first_half else 'away'
    field_h = 'home_1h' if first_half else 'home'
    if final.get(field_a) is None or final.get(field_h) is None:
        return 'NOT_GRADED'
    a = _score(final[field_a], field_a)
    h = _score(final[field_h], field_h)
    score = {away: a, home: h}
    opponent = {away: home, home: away}
    if family.endswith('ML'):
        return _grade(score[team] - score[opponent[team]], 'Over')
    if family.endswith('SPREAD'):
        assert line is not None
        return _grade(score[team] - score[opponent[team]] + line, 'Over')
    if historic_bug and family.endswith('TOTAL'):
        # Exact code-path defect: TEAM_TOTAL also ends with TOTAL.
        return _grade(a + h - line, side)
    if family.endswith('TEAM_TOTAL'):
        return _grade(score[team] - line, side)
    if family.endswith('TOTAL'):
        return _grade(a + h - line, side)
    raise InvalidRecord('UNKNOWN_FAMILY')


def replay(picks_bytes: bytes, finals_bytes: bytes, *, expected_picks_sha256: str | None = None,
           expected_finals_sha256: str | None = None) -> dict:
    picks_sha = hashlib.sha256(picks_bytes).hexdigest()
    finals_sha = hashlib.sha256(finals_bytes).hexdigest()
    if expected_picks_sha256 is not None and picks_sha != expected_picks_sha256:
        raise InvalidRecord('PICKS_DIGEST_MISMATCH')
    if expected_finals_sha256 is not None and finals_sha != expected_finals_sha256:
        raise InvalidRecord('FINALS_DIGEST_MISMATCH')
    try:
        text = picks_bytes.decode('utf-8-sig')
        finals = json.loads(finals_bytes.decode('utf-8'), object_pairs_hook=_reject_duplicate_json_keys)
    except InvalidRecord:
        raise
    except (UnicodeError, ValueError) as e:
        raise InvalidRecord('CORRUPT_SOURCE_FORMAT') from e
    if not isinstance(finals, dict):
        raise InvalidRecord('FINALS_MAP_REQUIRED')
    rd = csv.DictReader(io.StringIO(text, newline=''))
    if (not rd.fieldnames or len(rd.fieldnames) != len(set(rd.fieldnames)) or
            not {'game', 'pick', 'price'}.issubset(rd.fieldnames)):
        raise InvalidRecord('ORIGINAL_PICKS_SCHEMA_REQUIRED')
    records: list[dict] = []
    counts = Counter()
    for rownum, row in enumerate(rd, 2):
        item = {'csv_line': rownum, 'game': row.get('game'), 'pick': row.get('pick'),
                'price': row.get('price'), 'family': None, 'old': None, 'corrected': None,
                'changed': False, 'status': None}
        try:
            if None in row or not row.get('game') or not row.get('pick'):
                raise InvalidRecord('MALFORMED_ROW')
            _validate_american_price(row.get('price'))
            family, _, _, _ = parse_selection(row['game'], row['pick'])
            item['family'] = family
            if row['game'] not in finals:
                item['status'] = 'FINAL_NOT_SUPPLIED'
                counts['not_graded'] += 1
            else:
                old = grade_one(row['game'], row['pick'], finals[row['game']], historic_bug=True)
                new = grade_one(row['game'], row['pick'], finals[row['game']], historic_bug=False)
                item.update({'old': old, 'corrected': new, 'changed': old != new,
                             'status': 'GRADED_RESEARCH' if new != 'NOT_GRADED' else 'HALFTIME_NOT_SUPPLIED'})
                if new == 'NOT_GRADED':
                    counts['not_graded'] += 1
                else:
                    counts['graded'] += 1
                    counts['corrected_' + new] += 1
                    if 'TEAM_TOTAL' in family:
                        counts['team_total_graded'] += 1
                    if old != new:
                        counts['grade_flips'] += 1
                        if 'TEAM_TOTAL' not in family:
                            raise InvalidRecord('UNEXPECTED_NON_TEAM_TOTAL_FLIP')
        except (InvalidRecord, KeyError, TypeError) as e:
            item['status'] = 'UNRESOLVED:' + str(e)
            counts['unresolved'] += 1
            item['changed'] = False
        records.append(item)
    counts['total_rows'] = len(records)
    counts['team_total_rows'] = sum('TEAM_TOTAL' in str(r['family']) for r in records)
    return {
        'status': 'RESEARCH_ONLY_UNAUTHENTICATED_PAPER_0U',
        'picks_sha256': picks_sha, 'finals_sha256': finals_sha,
        'counts': dict(sorted(counts.items())),
        'row_audit': records,
        'proof_limits': [
            'A corrected grading comparison is not a verified historical bet or provider final.',
            'Neither source receipt nor historical file creation time is authenticated here.',
            'All original priced and mirrored rows are retained; no ROI or stake calculated.',
            'No actual November 9 496-row result can be claimed without those original bytes.'
        ]
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('original_picks_csv', type=Path)
    p.add_argument('finals_json', type=Path)
    p.add_argument('--expected-picks-sha256')
    p.add_argument('--expected-finals-sha256')
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args(argv)
    report = replay(args.original_picks_csv.read_bytes(), args.finals_json.read_bytes(),
                    expected_picks_sha256=args.expected_picks_sha256,
                    expected_finals_sha256=args.expected_finals_sha256)
    with args.report.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(f"G18 RESEARCH: {report['counts'].get('total_rows', 0)} priced rows, "
          f"{report['counts'].get('grade_flips', 0)} possible grading flips; PAPER/0u")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
