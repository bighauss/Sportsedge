"""Market-implied probability engine (RESEARCH ONLY, PAPER / 0u).

Never feeds production v5. Converts sportsbook prices to fair (no-vig)
probabilities, builds a multi-book consensus that can exclude the execution
book (DraftKings), and reverse-engineers team scores from spread + total.

Methods: multiplicative, additive, power, Shin (Shin 1993; Strumbelj 2014).
Missing opposing prices fail closed with status NO_PRICE: a one-sided raw
implied probability is never returned as fair.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Dict, List, Optional, Sequence

METHODS = ("multiplicative", "additive", "power", "shin")


# ---------- odds conversion ----------
def american_to_decimal(a: float) -> float:
    if a == 0 or -100 < a < 100:
        raise ValueError(f"invalid American odds {a}")
    return 1 + (a / 100 if a > 0 else 100 / -a)


def decimal_to_american(d: float) -> float:
    if d <= 1:
        raise ValueError(f"invalid decimal odds {d}")
    return (d - 1) * 100 if d >= 2 else -100 / (d - 1)


def implied(dec: float) -> float:
    return 1.0 / dec


def overround(decs: Sequence[float]) -> float:
    return sum(implied(d) for d in decs) - 1.0


# ---------- de-vig methods ----------
def _multiplicative(q: List[float]) -> List[float]:
    s = sum(q)
    return [x / s for x in q]


def _additive(q: List[float]) -> List[float]:
    m = (sum(q) - 1) / len(q)
    p = [x - m for x in q]
    if min(p) <= 0:  # additive breaks on extreme longshots -> fail closed
        raise ValueError("additive method produced non-positive probability")
    return p


def _bisect(f, lo, hi, it=200):
    flo = f(lo)
    for _ in range(it):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def _power(q: List[float]) -> List[float]:
    # find k with sum(q_i^k) = 1 ; k>1 when overround>0
    k = _bisect(lambda k: sum(x ** k for x in q) - 1, 1e-6, 50)
    return [x ** k for x in q]


def _shin(q: List[float]) -> List[float]:
    s = sum(q)
    if s <= 1:
        return _multiplicative(q)

    def probs(z):
        return [
            (math.sqrt(z * z + 4 * (1 - z) * x * x / s) - z) / (2 * (1 - z))
            for x in q
        ]

    z = _bisect(lambda z: sum(probs(z)) - 1, 0.0, 0.999)
    p = probs(z)
    t = sum(p)
    return [x / t for x in p]


_FN = {"multiplicative": _multiplicative, "additive": _additive,
       "power": _power, "shin": _shin}


@dataclass
class FairResult:
    status: str                      # OK | NO_PRICE | INVALID
    method: str
    fair: Optional[List[float]] = None
    overround: Optional[float] = None
    reason: str = ""


def devig(prices: Sequence[Optional[float]], method: str = "power",
          fmt: str = "american") -> FairResult:
    """prices: every outcome of ONE market (2-way or multiway, incl. draw).
    Any missing side -> NO_PRICE (never fabricate the opposing price)."""
    if method not in _FN:
        raise ValueError(method)
    if len(prices) < 2 or any(p is None for p in prices):
        return FairResult("NO_PRICE", method, reason="missing opposing price")
    try:
        decs = [american_to_decimal(p) if fmt == "american" else float(p)
                for p in prices]
        if any(d <= 1 for d in decs):
            raise ValueError("decimal odds must exceed 1")
        q = [implied(d) for d in decs]
        orr = sum(q) - 1
        if orr < -0.02:
            return FairResult("INVALID", method, overround=orr,
                              reason="negative overround (stale/mixed quotes)")
        return FairResult("OK", method, _FN[method](q), orr)
    except ValueError as e:
        return FairResult("INVALID", method, reason=str(e))


def devig_all(prices, fmt="american") -> Dict[str, FairResult]:
    return {m: devig(prices, m, fmt) for m in METHODS}


# ---------- push-aware fair odds ----------
def fair_win_given_push(p_win: float, p_push: float) -> float:
    """Fair decimal odds for a bet that refunds on push."""
    if not 0 < p_win < 1 - p_push:
        raise ValueError("bad probabilities")
    return 1 + (1 - p_win - p_push) / p_win


def ev_per_unit(p_win: float, dec_offered: float, p_push: float = 0.0) -> float:
    p_lose = 1 - p_win - p_push
    return p_win * (dec_offered - 1) - p_lose


# ---------- consensus ----------
@dataclass
class BookQuote:
    book: str
    prices: Sequence[Optional[float]]
    weight: float = 1.0
    copies: Optional[str] = None  # book this one copies -> not independent


def consensus(quotes: Sequence[BookQuote], method="power",
              exclude: Sequence[str] = ("draftkings",)) -> FairResult:
    """Weighted log-odds consensus of independent books' fair probs.
    Excludes the execution book and books flagged as copies."""
    ex = {b.lower() for b in exclude}
    used = [qt for qt in quotes
            if qt.book.lower() not in ex and qt.copies is None]
    fairs = []
    for qt in used:
        r = devig(qt.prices, method)
        if r.status == "OK":
            fairs.append((qt.weight, r.fair))
    if not fairs:
        return FairResult("NO_PRICE", method, reason="no independent book")
    n = len(fairs[0][1])
    w = sum(x for x, _ in fairs)
    logs = [sum(wt * math.log(f[i]) for wt, f in fairs) / w for i in range(n)]
    e = [math.exp(v) for v in logs]
    s = sum(e)
    return FairResult("OK", f"consensus/{method}", [x / s for x in e],
                      reason=f"books={len(fairs)}")


# ---------- reverse-engineer game projection ----------
def implied_team_scores(spread_home: float, total: float):
    """spread_home is the home line (e.g. -3.5 => home favored by 3.5)."""
    margin = -spread_home
    return (total + margin) / 2, (total - margin) / 2


def implied_margin_sd(spread_home: float, p_home_fair_ml: float) -> float:
    """Solve the normal margin SD that reconciles spread with fair ML.
    Rough for discrete sports (NFL key numbers) - flag, don't trust blindly."""
    mu = -spread_home
    if mu == 0 or not 0 < p_home_fair_ml < 1:
        raise ValueError("unidentifiable: pick'em or bad prob")
    z = NormalDist().inv_cdf(p_home_fair_ml)
    if z == 0 or (mu > 0) != (z > 0):
        raise ValueError("inconsistent: spread and ML disagree on favorite")
    return mu / z
