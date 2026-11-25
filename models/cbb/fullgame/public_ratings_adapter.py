"""Non-destructive AdjustedFit public ratings adapter (PAPER / 0u, NON_COUNTED).

Replaces iterative k-core low-game-count filtering (which cascades to an empty sample
on sparse early-season graphs) with single-pass prior-season Division I membership
filtering (`d1_set`) and Gauss-Seidel ridge regression (`fullgame.ratings.AdjustedFit`)
anchored to a prior-season carryover.

HCA is estimated strictly from verified-venue prior evidence (never hardcoded to a
predetermined range). Does not touch frozen production models or DEFAULT_CONFIG.
"""
from __future__ import annotations

from datetime import date
import json

from . import ratings as R

DEFAULT_PARAMS = {
    "lam": 4.0,
    "lam_pace": 4.0,
    "half_life": 40.0,
    "hca_lam": 400.0,
    "carry": 0.85,
    "carry_pace": 0.70,
}


def filter_d1_single_pass(games, d1_set=None):
    """Exclude non-D1 and missing-possession rows in a single pass (no iterative k-core pruning)."""
    usable, dropped_non_d1, dropped_missing_poss = [], 0, 0
    for g in games:
        if g.get("possessions") is None or g.get("home") == g.get("away"):
            dropped_missing_poss += 1
            continue
        if d1_set is not None:
            in_d1 = str(g["home"]) in d1_set and str(g["away"]) in d1_set
        else:
            in_d1 = bool(g.get("home_d1", True)) and bool(g.get("away_d1", True))
        if not in_d1:
            dropped_non_d1 += 1
            continue
        usable.append(g)
    return usable, {"usable": len(usable), "dropped_non_d1": dropped_non_d1,
                    "dropped_missing_poss": dropped_missing_poss, "iterative_pruning_disabled": True}


def fit_public_adjusted_ratings(games, *, season, as_of_date, d1_set=None, prev_final=None,
                                hca_prior=0.0, params=None):
    """Fit ridge-regularized schedule-adjusted ratings without iterative k-core collapse.

    Returns (json_bytes, diagnostics). Teams in `d1_set` or `prev_final` with zero current-season
    games still receive regularized carryover ratings rather than being dropped.
    """
    cfg = {**DEFAULT_PARAMS, **(params or {})}
    usable, census = filter_d1_single_pass(games, d1_set=d1_set)
    prior, new_team = ({}, (0.0, 0.0, 0.0))
    mu0, pi0 = 103.0, 68.0
    if prev_final is not None:
        prior, new_team = R.make_prior(prev_final, cfg["carry"], cfg["carry_pace"])
        mu0, pi0 = prev_final[1], prev_final[2]
    if not usable and not prior:
        raise ValueError("RATINGS_INSUFFICIENT_SAMPLE: no usable D1 games and no prior state")
    fit = R.AdjustedFit(
        lam=cfg["lam"],
        lam_pace=cfg["lam_pace"],
        half_life=cfg["half_life"],
        prior=prior,
        hca_prior=hca_prior,
        hca_lam=cfg["hca_lam"] if prev_final is not None else 0.0,
        mu0=mu0,
        pi0=pi0,
    )
    fit.default_prior = new_team
    cutoff = date.fromisoformat(as_of_date[:10]) if isinstance(as_of_date, str) else as_of_date
    if usable:
        fit.fit(usable, cutoff)
    team_ids = sorted(set(fit.o) | set(prior) | (set(d1_set) if d1_set is not None else set()))
    rows = []
    for tid in team_ids:
        o, d, q = fit.team(tid)
        ortg = fit.mu + o
        drtg = fit.mu + d
        rows.append({
            "teamId": int(tid) if str(tid).isdigit() else tid,
            "team": str(tid),
            "season": int(season),
            "offensiveRating": round(ortg, 4),
            "defensiveRating": round(drtg, 4),
            "netRating": round(ortg - drtg, 4),
            "pace": round(fit.pi + q, 4),
            "n_games": int(fit.n.get(tid, 0)),
            "rating_basis": "ADJUSTED_FIT_RIDGE_CARRYOVER_NO_ITERATIVE_FILTER",
        })
    diag = {
        **census,
        "season": int(season),
        "as_of_date": cutoff.isoformat(),
        "rated_teams": len(rows),
        "teams_with_current_games": len(fit.o),
        "hca_per100": round(fit.h, 4),
        "league_ortg": round(fit.mu, 4),
        "league_pace": round(fit.pi, 4),
        "label": "PAPER_0U",
        "counted": "NON_COUNTED",
    }
    return json.dumps(rows, sort_keys=True).encode("utf-8"), diag
