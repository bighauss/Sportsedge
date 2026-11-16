"""Research-only CBB formatted-card audit with ORIGINAL engine push semantics.

The v5 engine emits conditional P(win | not push), but computes EV from
unconditional P(win) and P(loss). A pushed wager is NOT an EV arithmetic error.
Never certify sportsbook quote authenticity or rewrite a frozen card.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROW = re.compile(r'^\s*(\d+)\s*\|\s*(.*)$')
EXPECTED = re.compile(r'Card rows:\s*(\d+)')
DOUBTED = re.compile(r'^MODEL-DOUBTED\s*\((\d+)\)')
REPO_ROOT = Path(__file__).resolve().parents[2]


def _settlement_category(selection: str) -> str:
    """Conservative text-only classification; unknown push draw is NOT zero."""
    s = selection.strip().casefold()
    if s.startswith('1h ') and s.endswith(' ml'):
        return 'PUSH_AWARE_FIRST_HALF_ML'
    # CBB totals, team totals and spreads settle on integer points. Integer
    # lines can push; decimal quarters are more complex than binary settlement.
    if m := re.search(r'(?<![\w.])([+-]?\d+(?:\.\d+)?)$',s):
        line = Decimal(m[1])
        if line*2 != (line*2).to_integral_value():
            return 'NON_BINARY_ALTERNATE_SETTLEMENT_UNVERIFIED'
        if line == line.to_integral_value():
            return 'PUSH_AWARE_INTEGER_LINE'
    return 'BINARY_NO_EXACT_PUSH_FOR_DISCRETE_CBB_SCORE'


def _push_interval(binary_ev: Decimal, decimal_odds: Decimal,
                   reported_ev: Decimal, p_half: Decimal,
                   ev_half: Decimal):
    """Approximate interval from independently rounded DISPLAY values only.

    If a book settlement is non-binary/quarter or the zero crossing is near,
    do not infer a numeric push share. This is not Monte Carlo draw recovery.
    """
    min_b = binary_ev - decimal_odds*p_half
    max_b = binary_ev + decimal_odds*p_half
    min_e = reported_ev - ev_half
    max_e = reported_ev + ev_half
    if min_b <= 0 or min_e < 0 or max_b <= 0:
        return None
    lower = max(Decimal(0), 1 - max_e/min_b)
    upper = min(Decimal(1), 1 - min_e/max_b)
    if lower > upper or not (0 <= lower <= upper <= 1):
        return None
    return {'min':str(lower.quantize(Decimal('.000001'))),
            'max':str(upper.quantize(Decimal('.000001')))}


def _private_path(value):
    lexical = Path(os.path.abspath(os.fspath(value)))
    resolved = lexical.resolve()
    if (lexical == REPO_ROOT or REPO_ROOT in lexical.parents or
            resolved == REPO_ROOT or REPO_ROOT in resolved.parents):
        raise ValueError('PRIVATE_CARD_OR_REPORT_INSIDE_PUBLIC_CHECKOUT')
    if lexical.is_symlink() or any(p.is_symlink() for p in lexical.parents):
        raise ValueError('UNTRUSTED_PRIVATE_SYMLINK_PATH')
    return lexical


def _write_report(path: Path, value: dict) -> None:
    body=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            fd=-1
            f.write(body);f.flush();os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if fd>=0:
            os.close(fd)



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
            category = _settlement_category(selection)
            binary = category == 'BINARY_NO_EXACT_PUSH_FOR_DISCRETE_CBB_SCORE'
            inconsistent = abs(diff) > max_rounding_gap if binary else None
            inferred_push = (_push_interval(computed_ev,decimal_odds,ev_reported,
                                            p_half_round,ev_half_round)
                             if category.startswith('PUSH_AWARE') else None)
            rows.append({
                'line': line_number, 'section': section, 'rank': index,
                'game': game, 'selection': selection, 'price_american': cells[3],
                'display_model_pct': str(p), 'display_ev_pct': str(ev_reported),
                'computed_binary_ev_pct_from_display': str(computed_ev.quantize(Decimal('.001'))),
                'gap_percentage_points': str(diff.quantize(Decimal('.001'))),
                'rounding_tolerance_pp': str(max_rounding_gap.quantize(Decimal('.001'))),
                'ev_math_inconsistent_beyond_rounding': inconsistent,
                'settlement_review_category': category,
                'approx_display_implied_push_share_range': inferred_push,
                'reason': (category+'_ORIGINAL_PWIN_PLOSS_DRAWS_REQUIRED'
                           if category.startswith('PUSH_AWARE') else
                           category if not binary else
                           'EV_UNEXPLAINED_BY_DISPLAY_ROUNDING' if inconsistent else
                           'UNVERIFIED_ROUNDED_INPUTS'),
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
        'anomalies': [r for r in rows if r['ev_math_inconsistent_beyond_rounding'] is True],
        'push_aware_unresolved': [r for r in rows if r['settlement_review_category'].startswith('PUSH_AWARE')],
        'nonbinary_settlement_unresolved': [r for r in rows if r['settlement_review_category'] == 'NON_BINARY_ALTERNATE_SETTLEMENT_UNVERIFIED'],
        'parse_or_count_problems': problems,
        'rows': rows,
        'limitations': [
            'v5 emit() uses conditional model_p = pw/(pw+pl) and EV = pw*payout-pl, so displayed p is NOT unconditional when pushes exist.',
            'First-half ML and integer lines require original p_win/p_loss/p_push counts before EV can be verified.',
            'Any inferred push share is a rounding-bounded implication of text, NOT original model simulation evidence.',
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
    source=_private_path(args.card_text); target=_private_path(args.report)
    result=audit(source.read_text(encoding='utf-8'))
    _write_report(target,result)
    print(f"Card rows {result['card_count']}, model-doubted {result['model_doubted_count']}, "
          f"binary EV discrepancies {len(result['anomalies'])}, push-sensitive unresolved {len(result['push_aware_unresolved'])}; PAPER/0u")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
