"""P4 — Fair odds, no-vig, EV, Kelly, line shopping, alt lines (Theo 8-13, 20; Rusty #4).

Pure functions, standard library only. Every EV produced here is a CANDIDATE
until it passes the P1 gates (see gates.py).
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def american_to_decimal(odds: float) -> float:
    if odds == 0 or -100 < odds < 100:
        raise ValueError(f"invalid American odds: {odds}")
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def decimal_to_american(dec: float) -> float:
    if dec <= 1:
        raise ValueError(f"invalid decimal odds: {dec}")
    return (dec - 1) * 100 if dec >= 2 else -100 / (dec - 1)


def decimal_to_fractional(dec: float, max_den: int = 100) -> str:
    from fractions import Fraction
    f = Fraction(dec - 1).limit_denominator(max_den)
    return f"{f.numerator}/{f.denominator}"


def implied_prob(odds: float) -> float:
    return 1 / american_to_decimal(odds)


def prob_to_american(p: float) -> float:
    if not 0 < p < 1:
        raise ValueError(f"probability out of range: {p}")
    return decimal_to_american(1 / p)


def overround(odds_list: Sequence[float]) -> float:
    """Total implied probability minus 1 (the vig/margin)."""
    return sum(implied_prob(o) for o in odds_list) - 1


def no_vig(odds_list: Sequence[float], method: str = "multiplicative") -> list[float]:
    """Fair probabilities. methods: multiplicative, additive, power, shin."""
    raw = [implied_prob(o) for o in odds_list]
    total = sum(raw)
    n = len(raw)
    if method == "multiplicative":
        return [r / total for r in raw]
    if method == "additive":
        return [r - (total - 1) / n for r in raw]
    if method == "power":
        lo, hi = 0.5, 10.0
        for _ in range(100):
            k = (lo + hi) / 2
            s = sum(r ** k for r in raw)
            lo, hi = (k, hi) if s > 1 else (lo, k)
        return [r ** k for r in raw]
    if method == "shin":
        lo, hi = 0.0, 0.4
        def probs(z):
            return [(math.sqrt(z * z + 4 * (1 - z) * r * r / total) - z) / (2 * (1 - z)) for r in raw]
        for _ in range(100):
            z = (lo + hi) / 2
            s = sum(probs(z))
            lo, hi = (z, hi) if s > 1 else (lo, z)
        return probs(z)
    raise ValueError(method)


def ev_per_unit(p_win: float, odds: float, p_push: float = 0.0, commission: float = 0.0) -> float:
    """Expected profit per 1 unit risked. Push returns stake. Commission on net winnings."""
    dec = american_to_decimal(odds)
    win_profit = (dec - 1) * (1 - commission)
    p_loss = 1 - p_win - p_push
    return p_win * win_profit - p_loss


def breakeven_prob(odds: float, p_push: float = 0.0) -> float:
    dec = american_to_decimal(odds)
    return (1 - p_push) / dec


def min_odds_for_ev(p_win: float) -> float:
    return prob_to_american(p_win)


def kelly_fraction(p_win: float, odds: float, fraction: float = 1.0, p_push: float = 0.0) -> float:
    """Kelly stake as fraction of bankroll (never negative). Recommendation only."""
    b = american_to_decimal(odds) - 1
    q = 1 - p_win - p_push
    f = (b * p_win - q) / b
    return max(0.0, f * fraction)


def line_shopping(prices: dict[str, float], bets_per_year: int = 500, stake: float = 100) -> dict:
    best_book = max(prices, key=lambda k: american_to_decimal(prices[k]))
    worst_book = min(prices, key=lambda k: american_to_decimal(prices[k]))
    b, w = prices[best_book], prices[worst_book]
    ip_diff = implied_prob(w) - implied_prob(b)
    per_win = (american_to_decimal(b) - american_to_decimal(w)) * stake
    # at breakeven-ish win rate of worst line
    p = implied_prob(w)
    return {
        "best_book": best_book, "best": b, "worst_book": worst_book, "worst": w,
        "implied_prob_diff": ip_diff,
        "extra_profit_per_win": per_win,
        "annual_impact": per_win * p * bets_per_year,
    }


def odds_report(odds: float, my_prob: float, bankroll: float | None = None) -> dict:
    dec = american_to_decimal(odds)
    out = {
        "american": odds, "decimal": round(dec, 4), "fractional": decimal_to_fractional(dec),
        "implied_prob": implied_prob(odds), "my_prob": my_prob,
        "edge": my_prob - implied_prob(odds),
        "ev_per_100": 100 * ev_per_unit(my_prob, odds),
        "breakeven_prob": breakeven_prob(odds),
        "fair_odds": prob_to_american(my_prob),
    }
    if bankroll:
        out.update({k: bankroll * kelly_fraction(my_prob, odds, f)
                    for k, f in (("kelly_full", 1), ("kelly_half", .5), ("kelly_quarter", .25))})
    return out


def alt_line_value(main_line: float, main_odds: float, alts: Iterable[tuple[float, float]],
                   margin_pmf: dict[int, float], fav: bool = True) -> list[dict]:
    """Price each alt spread against an empirical margin distribution.

    margin_pmf: {favorite_margin: probability} from HISTORY (no invented key-number
    weights). Line given as favorite spread (e.g. -3.5). Returns cover prob + EV.
    """
    def cover(line):
        need = -line
        p_win = sum(p for m, p in margin_pmf.items() if m > need)
        p_push = sum(p for m, p in margin_pmf.items() if m == need)
        return p_win, p_push
    rows = []
    for line, odds in [(main_line, main_odds), *alts]:
        pw, pp = cover(line)
        rows.append({"line": line, "odds": odds, "p_cover": pw, "p_push": pp,
                     "ev_per_unit": ev_per_unit(pw, odds, pp)})
    return sorted(rows, key=lambda r: -r["ev_per_unit"])


def parlay(legs: Sequence[tuple[float, float]], offered_odds: float) -> dict:
    """legs: (true_prob, leg_odds). Assumes independence — flag via correlation.py."""
    p = math.prod(l[0] for l in legs)
    return {"true_prob": p, "fair_odds": prob_to_american(p), "offered": offered_odds,
            "ev_per_10": 10 * ev_per_unit(p, offered_odds),
            "weakest_leg": min(range(len(legs)), key=lambda i: legs[i][0] - implied_prob(legs[i][1])),
            "independence_assumed": True}
