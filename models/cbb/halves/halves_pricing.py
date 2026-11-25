"""Push-aware pricing of CBB half markets from halves_model distributions (PAPER/0u)."""
from __future__ import annotations
import math
try:
    from . import halves_model as HM
except ImportError:
    import halves_model as HM

MARKETS = ("SPREAD", "TOTAL", "TEAM_TOTAL_HOME", "TEAM_TOTAL_AWAY", "MONEYLINE")
TIE_RULES = ("TIE_PUSH", "TIE_LOSES", "THREE_WAY")

def american_to_decimal(american):
    a = HM._finite(american, "PRICE_INVALID")
    if a >= 100: return 1.0 + a / 100.0
    if a <= -100: return 1.0 + 100.0 / -a
    raise HM.HalvesHold("PRICE_INVALID")

def prob_to_american(p):
    if not 0.0 < p < 1.0: return None
    return -100.0 * p / (1.0 - p) if p >= 0.5 else 100.0 * (1.0 - p) / p

def _line(x):
    x = HM._finite(x, "LINE_INVALID")
    if abs(x * 2 - round(x * 2)) > 1e-9: raise HM.HalvesHold("LINE_NOT_HALF_POINT_GRID")
    return x

def outcome_probs(dist, market, side, line=None, tie_rule=None):
    pm = dist["pmf"]
    if market == "SPREAD":
        if side not in ("home", "away"): raise HM.HalvesHold("SIDE_INVALID")
        L = _line(line)
        thr = -L if side == "home" else L
        P = pm["margin"]
        gt, eq = P.prob_gt(thr), P.prob_eq(thr)
        lt = max(0.0, 1.0 - gt - eq)
        return (gt, eq, lt) if side == "home" else (lt, eq, gt)
    if market in ("TOTAL", "TEAM_TOTAL_HOME", "TEAM_TOTAL_AWAY"):
        if side not in ("over", "under"): raise HM.HalvesHold("SIDE_INVALID")
        L = _line(line)
        if L <= 0: raise HM.HalvesHold("LINE_INVALID")
        P = pm[{"TOTAL": "total", "TEAM_TOTAL_HOME": "home", "TEAM_TOTAL_AWAY": "away"}[market]]
        gt, eq = P.prob_gt(L), P.prob_eq(L)
        lt = max(0.0, 1.0 - gt - eq)
        return (gt, eq, lt) if side == "over" else (lt, eq, gt)
    if market == "MONEYLINE":
        if tie_rule not in TIE_RULES: raise HM.HalvesHold("TIE_RULE_REQUIRED")
        P = pm["margin"]
        ph, pt = P.prob_gt(0), P.pmf(0)
        pa = max(0.0, 1.0 - ph - pt)
        if side == "tie":
            if tie_rule != "THREE_WAY": raise HM.HalvesHold("TIE_SIDE_REQUIRES_THREE_WAY")
            return (pt, 0.0, 1.0 - pt)
        if side not in ("home", "away"): raise HM.HalvesHold("SIDE_INVALID")
        pw, pl = (ph, pa) if side == "home" else (pa, ph)
        if tie_rule == "TIE_PUSH": return (pw, pt, pl)
        return (pw, 0.0, pl + pt)
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
