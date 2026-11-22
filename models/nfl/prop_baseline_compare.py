"""Market-only baseline comparison for NFL RUN IT v3 prop probabilities. PAPER / 0u.

Question: does the v3 prop rule (market mean scaled by the model/market game-total
ratio) forecast props better than the market price alone, on identical rows?

Inputs: ledger rows from runit_ledger.build_ledger and a results map
{(game, selection): True | False | None} built from reviewed final player stats.
None (or absent) = pending/unverified; never graded as a miss.

Both forecasts are scored on the SAME rows: model = row["model_p"],
market = row["market_p"] (v3's one-sided implied/1.045 benchmark; a true
two-sided no-vig benchmark is not available for these props). Uncertainty on the
Brier difference uses a bootstrap clustered by GAME, because v3 prop edges in one
game share a single game-total signal and are not independent.
No formula in runit_ledger is changed here.
"""
from __future__ import annotations

import math
import random

EPS = 1e-6
COHORTS = ("priced", "on_card")


def _ll(p, y):
    p = min(1 - EPS, max(EPS, p))
    return -math.log(p if y else 1 - p)


def _scores(rows):
    n = len(rows)
    bm = sum((r["model_p"] - r["_y"]) ** 2 for r in rows) / n
    bk = sum((r["market_p"] - r["_y"]) ** 2 for r in rows) / n
    lm = sum(_ll(r["model_p"], r["_y"]) for r in rows) / n
    lk = sum(_ll(r["market_p"], r["_y"]) for r in rows) / n
    return dict(n=n, games=len({r["game"] for r in rows}), hit_rate=sum(r["_y"] for r in rows) / n,
                mean_model_p=sum(r["model_p"] for r in rows) / n,
                mean_market_p=sum(r["market_p"] for r in rows) / n,
                brier_model=bm, brier_market=bk, brier_diff=bm - bk,
                logloss_model=lm, logloss_market=lk, logloss_diff=lm - lk)


def _cluster_ci(rows, reps, seed):
    by = {}
    for r in rows:
        by.setdefault(r["game"], []).append(r)
    games = sorted(by)
    rng = random.Random(seed)
    diffs = []
    for _ in range(reps):
        s = [r for g in (rng.choice(games) for _ in games) for r in by[g]]
        diffs.append(_scores(s)["brier_diff"])
    diffs.sort()
    return diffs[int(0.025 * reps)], diffs[int(0.975 * reps) - 1]


def compare(ledger_rows, results, reps=2000, seed=7, min_games=2):
    """Returns {cohort: report}. brier_diff < 0 means the model beat the market."""
    props = [r for r in ledger_rows if r.get("kind") == "prop" and r.get("status") != "rejected_input"]
    out = {}
    for cohort in COHORTS:
        rows = props if cohort == "priced" else [r for r in props if r.get("qualifies")]
        census = dict(attempted=len(rows), graded=0, pending=0, invalid_prob=0)
        graded = []
        for r in rows:
            y = results.get((r["game"], r["selection"]))
            if not all(type(r.get(k)) in (int, float) and 0 <= r[k] <= 1 for k in ("model_p", "market_p")):
                census["invalid_prob"] += 1
            elif y is None:
                census["pending"] += 1
            elif type(y) is not bool:
                raise ValueError(f"result for {r['game']} {r['selection']} must be bool or None")
            else:
                census["graded"] += 1
                graded.append(dict(r, _y=y))
        assert sum(census[k] for k in ("graded", "pending", "invalid_prob")) == census["attempted"]
        rep = dict(census=census)
        if not graded:
            rep["status"] = "NO_GRADED_ROWS"
        else:
            rep.update(_scores(graded))
            if rep["games"] < min_games:
                rep["status"] = "INSUFFICIENT_GAMES_FOR_CI"
            else:
                lo, hi = _cluster_ci(graded, reps, seed)
                rep["brier_diff_ci95_game_cluster"] = (lo, hi)
                rep["status"] = ("MODEL_BETTER" if hi < 0 else "MARKET_BETTER" if lo > 0
                                 else "NO_SIGNIFICANT_DIFFERENCE")
        out[cohort] = rep
    return out
