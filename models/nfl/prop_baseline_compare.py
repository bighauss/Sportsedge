"""Conservative NFL v3 prop-probability baseline diagnostic (research/0u).

Tests whether v3's market-derived prop probabilities beat the market-only
benchmark ON IDENTICAL GRADED SOURCE ROWS. No original sportsbook quote, final
player-stat identity, or historical prediction is authenticated here.

The market benchmark is v3's one-sided implied/1.045, not a verified two-sided
no-vig price. Entire-game signals share dependence: bootstrap by game.
Duplicated outcome identities, pending results, PUSH and VOID are not scored.
No model promotion or live betting stake may be derived from this report.
"""
from __future__ import annotations

from collections import Counter
import math
import random

EPS = 1e-6
COHORTS = ("priced", "on_card")
MIN_GAMES = 20
MIN_GRADED_ROWS = 100
BLOCKED_STATUSES = frozenset(("rejected_input", "duplicate_offer",
                              "game_not_on_slate"))


def _ll(p, y):
    p = min(1 - EPS, max(EPS, p))
    return -math.log(p if y else 1 - p)


def _scores(rows):
    n = len(rows)
    model_brier = sum((r["model_p"] - r["_y"]) ** 2 for r in rows) / n
    market_brier = sum((r["market_p"] - r["_y"]) ** 2 for r in rows) / n
    lm = sum(_ll(r["model_p"], r["_y"]) for r in rows) / n
    lk = sum(_ll(r["market_p"], r["_y"]) for r in rows) / n
    return {
        "n": n, "games": len({r["game"] for r in rows}),
        "hit_rate": sum(r["_y"] for r in rows) / n,
        "mean_model_p": sum(r["model_p"] for r in rows) / n,
        "mean_market_p": sum(r["market_p"] for r in rows) / n,
        "brier_model": model_brier, "brier_market": market_brier,
        "brier_diff": model_brier - market_brier,
        "logloss_model": lm, "logloss_market": lk,
        "logloss_diff": lm - lk,
    }


def _cluster_ci(rows, reps, seed):
    by_game = {}
    for row in rows:
        by_game.setdefault(row["game"], []).append(row)
    games = sorted(by_game)
    if len(games) < 2 or reps < 200:
        raise ValueError("CLUSTER_CI_REQUIRES_MULTIPLE_GAMES_AND_200_BOOTSTRAPS")
    rng = random.Random(seed)
    diffs = []
    for _ in range(reps):
        selected = [r for g in (rng.choice(games) for _ in games)
                    for r in by_game[g]]
        diffs.append(_scores(selected)["brier_diff"])
    diffs.sort()
    return diffs[int(0.025 * reps)], diffs[int(0.975 * reps) - 1]


def _eligible(r):
    status = r.get("status")
    return (status not in BLOCKED_STATUSES and
            not (isinstance(status, str) and (
                status.startswith("unsupported_market:") or
                status.startswith("missing_input:"))))


def compare(ledger_rows, results, reps=2000, seed=7,
            min_games=MIN_GAMES, min_rows=MIN_GRADED_ROWS):
    """Calculate game-clustered model-minus-market scores without lost rows.

    `results` is keyed by (game, selection), with boolean results, None,
    or explicit PUSH / VOID. This identity is intentionally fail-closed:
    if more than one source row shares the key, all collided rows are counted
    as AMBIGUOUS and none is scored. Better provider IDs need a new contract.
    """
    if not isinstance(ledger_rows, list) or not isinstance(results, dict):
        raise TypeError("LEDGER_LIST_AND_RESULT_MAP_REQUIRED")
    if (type(reps) is not int or type(min_games) is not int or
            type(min_rows) is not int or reps < 200 or not 2 <= min_games <= 10000 or
            not 1 <= min_rows <= 1000000):
        raise ValueError("INVALID_SAMPLE_OR_BOOTSTRAP_CONTRACT")
    props = [r for r in ledger_rows if r.get("kind") == "prop"]
    out = {}
    for cohort in COHORTS:
        rows = props if cohort == "priced" else [
            r for r in props if r.get("qualifies") is True
        ]
        census = dict(attempted=len(rows), graded=0, pending=0, invalid_prob=0,
                      blocked=0, ambiguous_identity=0, push=0, void=0)
        keys = Counter(
            (r.get("game"), r.get("selection")) for r in rows
            if isinstance(r.get("game"), str) and
            isinstance(r.get("selection"), str)
        )
        graded = []
        for r in rows:
            key = (r.get("game"), r.get("selection"))
            if not _eligible(r):
                census["blocked"] += 1
            elif (not isinstance(key[0], str) or not key[0] or
                  not isinstance(key[1], str) or not key[1] or
                  keys[key] != 1):
                census["ambiguous_identity"] += 1
            elif not all(type(r.get(k)) in (int, float) and
                         math.isfinite(r[k]) and 0 <= r[k] <= 1
                         for k in ("model_p", "market_p")):
                census["invalid_prob"] += 1
            else:
                y = results.get(key)
                if y is None:
                    census["pending"] += 1
                elif y == "PUSH" and type(y) is str:
                    census["push"] += 1
                elif y == "VOID" and type(y) is str:
                    census["void"] += 1
                elif type(y) is not bool:
                    raise ValueError("RESULT_MUST_BE_BOOL_PUSH_VOID_OR_NONE")
                else:
                    census["graded"] += 1
                    graded.append(dict(r, _y=y))
        assert sum(census.values()) - census["attempted"] == census["attempted"]
        rep = {
            "census": census, "model_validated": False,
            "source_authenticated": False, "calibration_verified": False,
            "market_benchmark": "v3_one_sided_implied_divided_by_1.045",
            "official_counted": 0, "approved_stake_u": 0,
        }
        if not graded:
            rep["status"] = "NO_GRADED_ROWS"
        else:
            rep.update(_scores(graded))
            if rep["games"] < min_games or rep["n"] < min_rows:
                rep["status"] = "INSUFFICIENT_GAMES_OR_ROWS_FOR_CI"
            else:
                lo, hi = _cluster_ci(graded, reps, seed)
                rep["brier_diff_ci95_game_cluster"] = (lo, hi)
                rep["status"] = (
                    "MODEL_BETTER_RESEARCH_ONLY" if hi < 0 else
                    "MARKET_BETTER_RESEARCH_ONLY" if lo > 0 else
                    "NO_SIGNIFICANT_DIFFERENCE"
                )
        out[cohort] = rep
    return out
