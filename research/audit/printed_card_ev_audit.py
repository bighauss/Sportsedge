"""Audit arithmetic on a SportsEdge human-readable paper card, not original odds.

Detect EV that cannot arise from one-decimal rounded displayed win chance
and American price, retaining appendix MODEL-DOUBTED entries separately.
Card text cannot authenticate a quote, prove no-vig fair odds, or grade bets.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROW = re.compile(r'^\s*(\d+)\s*\|\s*(.*)$')
EXPECTED = re.compile(r'Card rows:\s*(\d+)')
DOUBTED = re.compile(r'^MODEL-DOUBTED\s*\((\d+)\)')


def _pct(s: str) -> tuple[Decimal, Decimal]:
    text = s.strip()
    if not text.endswith('%'):
        raise ValueError('PERCENT_SIGN_MISSING')
    body = text[:-1].strip()
    try:
        value = Decimal(body)
    except InvalidOperation as ex:
        raise ValueError('INVALID_PERCENT') from ex
    if not value.is_finite():
        raise ValueError('NONFINITE_PERCENT')
    digits = len(body.rpartition('.')[2]) if '.' in body else 0
    if digits > 8:
        raise ValueError('PERCENT_PRECISION_UNBOUNDED')
    unit = Decimal('1').scaleb(-digits)
    return value, unit / 2


def _decimal_odds(odds: str) -> Decimal:
    value = odds.strip().replace('−', '-').replace('＋', '+')
    if not re.fullmatch(r'[+-]?\d+', value):
        raise ValueError('INVALID_AMERICAN_PRICE')
    x = int(value)
    if abs(x) < 100 or abs(x) > 100000:
        raise ValueError('INVALID_AMERICAN_PRICE')
    return Decimal(1) + (Decimal(x) / 100 if x > 0 else Decimal(100) / abs(x))


def audit(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise ValueError('EMPTY_CARD')
    section = 'CARD'
    rows = []
    problems = []
    expected_card = None
    expected_doubted = None
    for line_number, line in enumerate(text.splitlines(), 1):
        if (m := EXPECTED.search(line)):
            expected_card = int(m.group(1))
        if (m := DOUBTED.match(line)):
            section = 'MODEL_DOUBTED'
            expected_doubted = int(m.group(1))
            continue
        if not ROW.match(line):
            continue
        cells = [c.strip() for c in line.split('|')]
        if len(cells) != 10:
            problems.append({'line': line_number, 'reason': 'INVALID_TABLE_COLUMN_COUNT'})
            continue
        try:
            index = int(cells[0]); game = cells[1]; selection = cells[2]
            if not (game.startswith('CBB ') and selection):
                raise ValueError('INVALID_GAME_OR_SELECTION')
            decimal_odds = _decimal_odds(cells[3])
            p, p_half_round = _pct(cells[4])
            ev_reported, ev_half_round = _pct(cells[7])
            if not (0 < p < 100):
                raise ValueError('INVALID_MODEL_PROBABILITY')
            computed_ev = p * decimal_odds - 100  # probability and EV in percentage points
            diff = computed_ev - ev_reported
            max_rounding_gap = decimal_odds * p_half_round + ev_half_round
            inconsistent = abs(diff) > max_rounding_gap
            rows.append({
                'line': line_number, 'section': section, 'rank': index,
                'game': game, 'selection': selection, 'price_american': cells[3],
                'display_model_pct': str(p), 'display_ev_pct': str(ev_reported),
                'computed_binary_ev_pct_from_display': str(computed_ev.quantize(Decimal('.001'))),
                'gap_percentage_points': str(diff.quantize(Decimal('.001'))),
                'rounding_tolerance_pp': str(max_rounding_gap.quantize(Decimal('.001'))),
                'ev_math_inconsistent_beyond_rounding': inconsistent,
                'reason': 'UNVERIFIED_ROUNDED_INPUTS' if not inconsistent else 'EV_UNEXPLAINED_BY_DISPLAY_ROUNDING',
            })
        except (ValueError, InvalidOperation) as ex:
            problems.append({'line': line_number, 'reason': str(ex)})
    card = [r for r in rows if r['section'] == 'CARD']
    doubted = [r for r in rows if r['section'] == 'MODEL_DOUBTED']
    if expected_card is not None and expected_card != len(card):
        problems.append({'line': None, 'reason': 'CARD_COUNT_MISMATCH', 'expected': expected_card, 'parsed': len(card)})
    if expected_doubted is not None and expected_doubted != len(doubted):
        problems.append({'line': None, 'reason': 'DOUBTED_COUNT_MISMATCH', 'expected': expected_doubted, 'parsed': len(doubted)})
    if [r['rank'] for r in card] != list(range(1, len(card)+1)):
        problems.append({'line': None, 'reason': 'CARD_RANKS_NOT_CONTIGUOUS'})
    if doubted and [r['rank'] for r in doubted] != list(range(1, len(doubted)+1)):
        problems.append({'line': None, 'reason': 'DOUBTED_RANKS_NOT_CONTIGUOUS'})
    return {
        'status': 'FORMATTED_RESEARCH_ONLY_NO_BOOK_PROVENANCE_PAPER_0U',
        'source_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'card_count': len(card), 'model_doubted_count': len(doubted),
        'table_rows_total': len(rows),
        'anomalies': [r for r in rows if r['ev_math_inconsistent_beyond_rounding']],
        'parse_or_count_problems': problems,
        'rows': rows,
        'limitations': [
            'Single displayed probability and American price imply binary only EV, not push-aware EV.',
            'Bookmaker receipts, source clock, full-precision unrounded p and grading were not supplied.',
            'MODEL_DOUBTED appendix rows are not main card selections.',
            'This audit establishes neither authenticated quote availability nor historical ROI.'
        ]
    }


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('card_text',type=Path)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args(argv)
    result=audit(args.card_text.read_text(encoding='utf-8'))
    with args.report.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,sort_keys=True)
        f.write('\n')
    print(f"Card rows {result['card_count']}, model-doubted {result['model_doubted_count']}, "
          f"EV-display anomalies {len(result['anomalies'])}; PAPER/0u")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
