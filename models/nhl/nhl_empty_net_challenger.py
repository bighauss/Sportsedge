"""NHL empty-net-rate shadow scenario research. NO model default changes; PAPER/0u.

The 0.11/0.32 rates are exploratory private-final refit candidates, NOT
source-authenticated, independently calibrated, or authorized live prices.
Never mutate sportsedge_nhl_model.W or produce official stakes.
"""
from __future__ import annotations
import math
import sportsedge_nhl_model as base

VERSION = "NHL_EN_MARGIN_SHADOW_R1"
EXPERIMENTAL_LEAD1 = 0.11
EXPERIMENTAL_LEAD2 = 0.32


def _finite(x, label):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError("INVALID_" + label)
    return float(x)


def _rates(p1, p2):
    a, b = _finite(p1, "EN_RATE"), _finite(p2, "EN_RATE")
    if not 0 <= a <= 1 or not 0 <= b <= 1:
        raise ValueError("EN_RATE_OUT_OF_RANGE")
    return a, b


def shadow_score_matrix(home_goals, away_goals, *,
                        en_p_lead1=EXPERIMENTAL_LEAD1,
                        en_p_lead2=EXPERIMENTAL_LEAD2):
    """Return optional research final-regulation score matrix, baseline W unchanged."""
    h, a = _finite(home_goals, "EXPECTED_GOALS"), _finite(away_goals, "EXPECTED_GOALS")
    if not 0 < h <= 15 or not 0 < a <= 15:
        raise ValueError("EXPECTED_GOALS_OUT_OF_RANGE")
    p1, p2 = _rates(en_p_lead1, en_p_lead2)
    original = base.score_matrix(h, a, empty_net=False)
    n = len(original) - 1
    output = [[0.0] * (n + 2) for _ in range(n + 2)]
    for i, row in enumerate(original):
        for j, p in enumerate(row):
            gap = i - j
            en = p1 if abs(gap) == 1 else p2 if abs(gap) == 2 else 0.0
            output[i][j] += p * (1.0 - en)
            if en:
                if gap > 0:
                    output[i + 1][j] += p * en
                else:
                    output[i][j + 1] += p * en
    return output


def _cover(matrix, home_spread):
    spread = _finite(home_spread, "HOME_SPREAD")
    if not -15 <= spread <= 15 or abs(spread * 2 - round(spread * 2)) > 1e-9:
        raise ValueError("UNSUPPORTED_PUCK_LINE")
    win = push = 0.0
    for h, row in enumerate(matrix):
        for a, prob in enumerate(row):
            diff = h - a + spread
            if diff > 1e-9:
                win += prob
            elif abs(diff) <= 1e-9:
                push += prob
    return {"p_win": win, "p_push": push, "p_loss": max(0.0, 1.0 - win - push)}


def compare(home_goals, away_goals, home_spread=-2.5, *,
            en_p_lead1=EXPERIMENTAL_LEAD1,
            en_p_lead2=EXPERIMENTAL_LEAD2):
    """Same underlying lambdas, active baseline vs isolated EN margin challenger."""
    h, a = _finite(home_goals, "EXPECTED_GOALS"), _finite(away_goals, "EXPECTED_GOALS")
    _rates(en_p_lead1, en_p_lead2)
    if not 0 < h <= 15 or not 0 < a <= 15:
        raise ValueError("EXPECTED_GOALS_OUT_OF_RANGE")
    old = base.score_matrix(h, a, empty_net=True)
    new = shadow_score_matrix(h, a, en_p_lead1=en_p_lead1, en_p_lead2=en_p_lead2)
    p_old, p_new = _cover(old, home_spread), _cover(new, home_spread)
    return {
        "schema": VERSION, "status": "PAPER_0U_SHADOW_UNVERIFIED",
        "home_spread": home_spread, "baseline": p_old, "challenger": p_new,
        "delta_p_win": p_new["p_win"] - p_old["p_win"],
        "baseline_en_rates": {
            "lead1": base.W["en_p_lead1"], "lead2": base.W["en_p_lead2"]},
        "challenger_en_rates": {"lead1": float(en_p_lead1), "lead2": float(en_p_lead2)},
        "source_authenticated": False, "independent_holdout_verified": False,
        "official_counted": 0, "approved_stake_u": 0,
    }
