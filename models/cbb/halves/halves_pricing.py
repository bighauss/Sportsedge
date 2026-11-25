"""Push-aware pricing of CBB half markets from ``halves_model`` distributions (PAPER/0u).

Public interface (import from the runner with ``models/cbb`` on sys.path)::

    from halves.halves_pricing import price_half_market, price_half_board_row
    dist = halves_model.project_period("H1", fg_home=74.2, fg_away=69.8, min_games=4)
    q = price_half_market(dist, market="SPREAD", side="home", line=-2.5, american=-110)

Markets and sides (lines are from the named side's perspective for SPREAD; the raw points
threshold for TOTAL / TEAM_TOTAL_*):
    SPREAD            side home|away   wins if side_margin + line > 0; push if == 0
    TOTAL             side over|under  vs line
    TEAM_TOTAL_HOME   side over|under  home team points in the period vs line
    TEAM_TOTAL_AWAY   side over|under  away team points in the period vs line
    MONEYLINE         side home|away|tie, requires ``tie_rule``:
                        "TIE_PUSH"   (two-way, a tied period refunds the stake)
                        "TIE_LOSES"  (two-way, a tied period loses)
                        "THREE_WAY"  (home/away/tie each a separate selection)
                      There is no default: the book's settlement rule must be stated.

Returned dict: p_win, p_push, p_loss (sum to 1), fair_american (push-aware: priced on
p_win / (p_win + p_loss)), ev_per_unit = p_win * (decimal - 1) - p_loss, plus label fields.
No EV cap, floor, or shrinkage is applied anywhere.
"""
from __future__ import annotations

import math

try:  # package import (runner) or flat import (tests run from this directory)
    from . import halves_model as HM
except ImportError:  # pragma: no cover
    import halves_model as HM

MARKETS = ("SPREAD", "TOTAL", "TEAM_TOTAL_HOME", "TEAM_TOTAL_AWAY", "MONEYLINE")
TIE_RULES = ("TIE_PUSH", "TIE_LOSES", "THREE_WAY")


def american_to_decimal(american):
    a = HM._finite(american, "PRICE_INVALID")
    if a >= 100:
        return 1.0 + a / 100.0
    if a <= -100:
        return 1.0 + 100.0 / -a
    raise HM.HalvesHold("PRICE_INVALID")


def prob_to_american(p):
    if not 0.0 < p < 1.0:
        return None
    return -100.0 * p / (1.0 - p) if p >= 0.5 else 100.0 * (1.0 - p) / p


def _line(x):
    x = HM._finite(x, "LINE_INVALID")
    if abs(x * 2 - round(x * 2)) > 1e-9:
        raise HM.HalvesHold("LINE_NOT_HALF_POINT_GRID")
    return x


def outcome_probs(dist, market, side, line=None, tie_rule=None):
    """(p_win, p_push, p_loss) for one selection."""
    pm = dist["pmf"]
    if market == "SPREAD":
        if side not in ("home", "away"):
            raise HM.HalvesHold("SIDE_INVALID")
        L = _line(line)
        # home margin m; home covers if m + L > 0 ; away (line L for away) covers if -m + L > 0
        thr = -L if side == "home" else L
        P = pm["margin"]
        gt, eq = P.prob_gt(thr), P.prob_eq(thr)
        lt = max(0.0, 1.0 - gt - eq)
        return (gt, eq, lt) if side == "home" else (lt, eq, gt)
    if market in ("TOTAL", "TEAM_TOTAL_HOME", "TEAM_TOTAL_AWAY"):
        if side not in ("over", "under"):
            raise HM.HalvesHold("SIDE_INVALID")
        L = _line(line)
        if L <= 0:
            raise HM.HalvesHold("LINE_INVALID")
        P = pm[{"TOTAL": "total", "TEAM_TOTAL_HOME": "home", "TEAM_TOTAL_AWAY": "away"}[market]]
        gt, eq = P.prob_gt(L), P.prob_eq(L)
        lt = max(0.0, 1.0 - gt - eq)
        return (gt, eq, lt) if side == "over" else (lt, eq, gt)
    if market == "MONEYLINE":
        if tie_rule not in TIE_RULES:
            raise HM.HalvesHold("TIE_RULE_REQUIRED")
        P = pm["margin"]
        ph, pt = P.prob_gt(0), P.pmf(0)
        pa = max(0.0, 1.0 - ph - pt)
        if side == "tie":
            if tie_rule != "THREE_WAY":
                raise HM.HalvesHold("TIE_SIDE_REQUIRES_THREE_WAY")
            return (pt, 0.0, 1.0 - pt)
        if side not in ("home", "away"):
            raise HM.HalvesHold("SIDE_INVALID")
        pw, pl = (ph, pa) if side == "home" else (pa, ph)
        if tie_rule == "TIE_PUSH":
            return (pw, pt, pl)
        return (pw, 0.0, pl + pt)  # TIE_LOSES and THREE_WAY: a tie loses the side bet
    raise HM.HalvesHold("MARKET_INVALID")


def price_half_market(dist, *, market, side, line=None, american=None, tie_rule=None):
    pw, pp, pl = outcome_probs(dist, market, side, line, tie_rule)
    decisive = pw + pl
    fair = prob_to_american(pw / decisive) if decisive > 0 else None
    out = {"period": dist["period"], "kind": dist["kind"], "market": market, "side": side,
           "line": line, "tie_rule": tie_rule,
           "p_win": pw, "p_push": pp, "p_loss": pl, "fair_american": fair,
           "label": HM.LABEL, "counting": HM.COUNTING, "approved_stake_u": 0,
           "model_version": dist["model_version"],
           "coefficients_sha256": dist["coefficients_sha256"]}
    if american is not None:
        dec = american_to_decimal(american)
        out["american"] = american
        out["break_even"] = 1.0 / dec
        out["ev_per_unit"] = pw * (dec - 1.0) - pl
    return out


def no_vig_two_way(american_a, american_b):
    """Multiplicative no-vig probabilities for a two-way quote (no push adjustment)."""
    qa, qb = 1 / american_to_decimal(american_a), 1 / american_to_decimal(american_b)
    return qa / (qa + qb), qb / (qa + qb)


def price_half_board_row(row, *, coefficients=None, tie_rule=None, fg_margin_sd=None,
                         fg_total_sd=None):
    """Convenience for a flat board row dict with keys:
    period, market, side, line, american, fg_home, fg_away and optional min_games, fg_poss,
    h1_home, h1_away, h1_poss (halftime periods only)."""
    dist = HM.project_period(row["period"], row["fg_home"], row["fg_away"],
                             coefficients=coefficients, min_games=row.get("min_games"),
                             fg_poss=row.get("fg_poss"), h1_home=row.get("h1_home"),
                             h1_away=row.get("h1_away"), h1_poss=row.get("h1_poss"),
                             fg_margin_sd=fg_margin_sd, fg_total_sd=fg_total_sd)
    return price_half_market(dist, market=row["market"], side=row["side"], line=row.get("line"),
                             american=row.get("american"),
                             tie_rule=row.get("tie_rule", tie_rule))
