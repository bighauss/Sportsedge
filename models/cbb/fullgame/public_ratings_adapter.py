"""Non-destructive AdjustedFit public ratings adapter (PAPER / 0u, NON_COUNTED).

Replaces iterative k-core low-game-count filtering (which cascades to an empty sample
on sparse early-season graphs) with single-pass prior-season Division I membership
filtering (`d1_set`) and Gauss-Seidel ridge regression (`fullgame.ratings.AdjustedFit`)
anchored to a prior-season carryover.

HCA is estimated by the fit from verified-venue evidence (never hardcoded). The returned
diagnostics state this so integrators do not add a home-court term a second time.
Fail-closed rules: unknown Division I membership is dropped (never assumed true), games
missing required fields are dropped, games after the admission cutoff are excluded, and
output efficiencies outside the native parser contract (60-160) raise.

Admission vs recency: ``as_of_date`` is the recency-weighting reference date. Timestamp
eligibility is separate: pass ``admit_through`` (inclusive date) when the caller has already
enforced an exact timestamp cutoff; otherwise games on or after ``as_of_date`` are excluded.
"""
from __future__ import annotations

from datetime import date
import json
import math

from . import ratings as R

DEFAULT_PARAMS = {
    "lam": 4.0,
    "lam_pace": 4.0,
    "half_life": 40.0,
    "hca_lam": 400.0,
    "carry": 0.85,
    "carry_pace": 0.70,
}
REQUIRED_FIELDS = ("game_id", "date", "home", "away", "site")
EFFICIENCY_MIN, EFFICIENCY_MAX = 60.0, 160.0


def _as_date(value):
    return date.fromisoformat(value[:10]) if isinstance(value, str) else value


def filter_d1_single_pass(games, d1_set=None, as_of=None, admit_through=None):
    """Single-pass admission. No iterative k-core pruning; every drop is counted by reason."""
    usable = []
    census = {"dropped_non_d1": 0, "dropped_unknown_d1": 0, "dropped_missing_poss": 0,
              "dropped_missing_fields": 0, "dropped_bad_date": 0, "dropped_future": 0}
    through = _as_date(admit_through) if admit_through is not None else None
    for g in games:
        if any(g.get(k) in (None, "") for k in REQUIRED_FIELDS):
            census["dropped_missing_fields"] += 1
            continue
        if g.get("possessions") is None or g.get("home") == g.get("away"):
            census["dropped_missing_poss"] += 1
            continue
        if as_of is not None or through is not None:
            try:
                day = date.fromisoformat(str(g["date"])[:10])
            except ValueError:
                census["dropped_bad_date"] += 1
                continue
            if through is not None:
                if day > through:
                    census["dropped_future"] += 1
                    continue
            elif day >= as_of:
                census["dropped_future"] += 1
                continue
        if d1_set is not None:
            if not (str(g["home"]) in d1_set and str(g["away"]) in d1_set):
                census["dropped_non_d1"] += 1
                continue
        else:
            flags = (g.get("home_d1"), g.get("away_d1"))
            if any(f is None for f in flags):
                census["dropped_unknown_d1"] += 1
                continue
            if not all(f is True for f in flags):
                census["dropped_non_d1"] += 1
                continue
        usable.append(g)
    return usable, {"usable": len(usable), **census, "iterative_pruning_disabled": True}


def fit_public_adjusted_ratings(games, *, season, as_of_date, d1_set=None, prev_final=None,
                                hca_prior=0.0, params=None, admit_through=None):
    """Fit ridge-regularized schedule-adjusted ratings without iterative k-core collapse.

    Returns (json_bytes, diagnostics). Teams in `d1_set` or `prev_final` with zero current-season
    games still receive regularized carryover ratings rather than being dropped. The caller must
    supply prev_final built only from seasons that ended before as_of_date.
    """
    cfg = {**DEFAULT_PARAMS, **(params or {})}
    cutoff = _as_date(as_of_date)
    usable, census = filter_d1_single_pass(
        games, d1_set=d1_set, as_of=None if admit_through is not None else cutoff,
        admit_through=admit_through)
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
    if usable:
        fit.fit(usable, cutoff)
    team_ids = sorted(set(fit.o) | set(prior) | (set(d1_set) if d1_set is not None else set()))
    rows, out_of_contract = [], []
    for tid in team_ids:
        o, d, q = fit.team(tid)
        ortg = fit.mu + o
        drtg = fit.mu + d
        for value in (ortg, drtg):
            if not math.isfinite(value) or not EFFICIENCY_MIN <= value <= EFFICIENCY_MAX:
                out_of_contract.append(str(tid))
                break
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
    if out_of_contract:
        raise ValueError("RATINGS_OUT_OF_CONTRACT: efficiency outside 60-160 for teams "
                         + ",".join(sorted(set(out_of_contract))[:20]))
    diag = {
        **census,
        "season": int(season),
        "as_of_date": cutoff.isoformat(),
        "rated_teams": len(rows),
        "teams_with_current_games": len(fit.o),
        "hca_per100": round(fit.h, 4),
        "hca_basis": "ESTIMATED_IN_FIT_FROM_VERIFIED_VENUE_GAMES_DO_NOT_ADD_AGAIN",
        "league_ortg": round(fit.mu, 4),
        "league_pace": round(fit.pi, 4),
        "label": "PAPER_0U",
        "counted": "NON_COUNTED",
    }
    return json.dumps(rows, sort_keys=True).encode("utf-8"), diag
