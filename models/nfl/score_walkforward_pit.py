#!/usr/bin/env python3
"""Point-in-time NFL score-conversion walk-forward research (PAPER / 0u).

Consumes immutable *pregame* NFL team EPA feature snapshots, not today's
retrospective nflverse ratings. Learns point conversion on earlier completed
games only. Does not price odds, simulate spreads or release approved plays.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite, sqrt
from pathlib import Path

from epa_ridge_pit import solve, utc

# Restrict research inputs/results to outside the PUBLIC GitHub checkout.
# Resolving the path also detects symlinks and ../ traversal into the repo.
REPO_ROOT = Path(__file__).resolve().parents[2]


def private_evidence_path(path):
    resolved = Path(path).expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError("PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO")
    return resolved

FEATURE_COLUMNS = frozenset((
    "game_id", "home_team", "away_team", "kickoff_utc",
    "forecast_asof_utc", "source_observed_utc", "epa_ratings_sha256",
    "home_off_pass", "home_def_allow_pass", "home_off_rush",
    "home_def_allow_rush", "away_off_pass", "away_def_allow_pass",
    "away_off_rush", "away_def_allow_rush",
))
RESULT_COLUMNS = frozenset((
    "game_id", "home_score", "away_score", "final_utc",
    "result_available_utc",
))
EPA_COLUMNS = tuple(sorted(c for c in FEATURE_COLUMNS
                           if c.startswith(("home_", "away_"))
                           and c.endswith(("_pass", "_rush"))))


def _numeric(value, field):
    try:
        x = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("BAD_NUMERIC:" + field) from exc
    if not isfinite(x):
        raise ValueError("NONFINITE_NUMERIC:" + field)
    return x


def _read_csv(path, columns):
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, restkey="__overflow__", restval=None)
        fields = reader.fieldnames or []
        if set(fields) != columns or len(fields) != len(set(fields)):
            raise ValueError("UNEXPECTED_CSV_COLUMNS")
        rows = list(reader)
    if not rows or any("__overflow__" in row or
                       any(v is None for v in row.values()) for row in rows):
        raise ValueError("EMPTY_OR_RAGGED_CSV")
    return rows


def _validate_features(features):
    seen = set()
    verified = []
    for raw in features:
        if not isinstance(raw, dict) or set(raw) != FEATURE_COLUMNS:
            raise ValueError("FEATURE_SCHEMA_VIOLATION")
        game_id = raw["game_id"].strip()
        home, away = raw["home_team"].strip(), raw["away_team"].strip()
        if not game_id or game_id in seen:
            raise ValueError("DUPLICATE_OR_EMPTY_GAME_ID")
        seen.add(game_id)
        if not home or not away or home == away:
            raise ValueError("INVALID_TEAM_MAPPING")
        kickoff = utc(raw["kickoff_utc"])
        asof = utc(raw["forecast_asof_utc"])
        observed = utc(raw["source_observed_utc"])
        if not observed <= asof < kickoff:
            raise ValueError("PREGAME_FEATURES_OR_SOURCE_CUTOFF_VIOLATION:" + game_id)
        fingerprint = raw["epa_ratings_sha256"]
        if not isinstance(fingerprint, str) or len(fingerprint) != 71 or (
            not fingerprint.startswith("sha256:")
        ) or any(c not in "0123456789abcdef" for c in fingerprint[7:]):
            raise ValueError("INVALID_EPA_RATINGS_FINGERPRINT")
        row = dict(raw)
        row.update({"game_id": game_id, "home_team": home, "away_team": away,
                    "kickoff_time": kickoff, "forecast_time": asof})
        for column in EPA_COLUMNS:
            row[column] = _numeric(raw[column], column)
        verified.append(row)
    if not verified:
        raise ValueError("NO_PREGAME_FEATURES")
    return sorted(verified, key=lambda row: (
        row["forecast_time"], row["kickoff_time"], row["game_id"]))


def _validate_results(results, features):
    by_id = {r["game_id"]: r for r in features}
    seen = set()
    checked = {}
    for raw in results:
        if not isinstance(raw, dict) or set(raw) != RESULT_COLUMNS:
            raise ValueError("RESULT_SCHEMA_VIOLATION")
        game_id = raw["game_id"].strip()
        if game_id in seen or game_id not in by_id:
            raise ValueError("RESULT_DUPLICATE_OR_UNKNOWN_EVENT")
        seen.add(game_id)
        final = utc(raw["final_utc"])
        available = utc(raw["result_available_utc"])
        if not by_id[game_id]["kickoff_time"] < final <= available:
            raise ValueError("RESULT_CHRONOLOGY_VIOLATION:" + game_id)
        try:
            hs, as_ = int(raw["home_score"]), int(raw["away_score"])
        except (TypeError, ValueError) as exc:
            raise ValueError("RESULT_SCORE_NOT_INTEGER") from exc
        if (str(hs) != str(raw["home_score"]).strip() or
            str(as_) != str(raw["away_score"]).strip() or
            hs < 0 or as_ < 0):
            raise ValueError("RESULT_SCORE_INVALID")
        checked[game_id] = {
            "home_score": hs, "away_score": as_, "available": available,
        }
    return checked


def _design(row, which):
    """Off + opponent defense-allowed EPA; team home effect fitted, not fixed."""
    if which == "home":
        return [1.0, row["home_off_pass"], row["away_def_allow_pass"],
                row["home_off_rush"], row["away_def_allow_rush"], 1.0]
    return [1.0, row["away_off_pass"], row["home_def_allow_pass"],
            row["away_off_rush"], row["home_def_allow_rush"], 0.0]


def _fit(eligible, outcomes, ridge):
    matrix = [[0.0] * 6 for _ in range(6)]
    target = [0.0] * 6
    for row in eligible:
        game = outcomes[row["game_id"]]
        for side, score in (("home", game["home_score"]),
                            ("away", game["away_score"])):
            x = _design(row, side)
            for i in range(6):
                target[i] += x[i] * score
                for j in range(6):
                    matrix[i][j] += x[i] * x[j]
    for i in range(1, 6):
        matrix[i][i] += ridge
    return solve(matrix, target)


def _dot(x, y):
    return sum(a * b for a, b in zip(x, y))


def walkforward(features, results, *, ridge=25.0, min_train_games=32):
    """Train strictly on outcomes AVAILABLE before each candidate's freeze."""
    ridge = _numeric(ridge, "RIDGE")
    if ridge <= 0:
        raise ValueError("RIDGE_MUST_BE_POSITIVE")
    if (isinstance(min_train_games, bool) or
        not isinstance(min_train_games, int) or min_train_games < 2):
        raise ValueError("INVALID_MINIMUM_TRAIN_GAMES")
    rows = _validate_features(features)
    outcomes = _validate_results(results, rows)
    predictions = []
    evaluated = []
    withheld = 0
    for candidate in rows:
        past = [r for r in rows if (
            r["kickoff_time"] < candidate["forecast_time"] and
            r["game_id"] in outcomes and
            outcomes[r["game_id"]]["available"] <= candidate["forecast_time"]
        )]
        # No scores/odds of this event can influence its own coefficients.
        if len(past) < min_train_games:
            predictions.append({
                "game_id": candidate["game_id"],
                "forecast_asof_utc": candidate["forecast_time"].isoformat(),
                "status": "PAPER_HOLD_0U",
                "reason": "INSUFFICIENT_PRIOR_AVAILABLE_RESULT_HISTORY",
                "training_games": len(past),
                "projected_home_score": None,
                "projected_away_score": None,
                "approved_stake_u": 0,
            })
            withheld += 1
            continue
        coefficients = _fit(past, outcomes, ridge)
        projected_home = max(0.0, _dot(coefficients, _design(candidate, "home")))
        projected_away = max(0.0, _dot(coefficients, _design(candidate, "away")))
        fingerprint = sha256(
            "\n".join(sorted(r["game_id"] for r in past)).encode()).hexdigest()
        prediction = {
            "game_id": candidate["game_id"],
            "forecast_asof_utc": candidate["forecast_time"].isoformat(),
            "training_games": len(past),
            "training_event_ids_sha256": "sha256:" + fingerprint,
            "feature_source_sha256": candidate["epa_ratings_sha256"],
            "projected_home_score": round(projected_home, 3),
            "projected_away_score": round(projected_away, 3),
            "projected_margin_home": round(projected_home - projected_away, 3),
            "projected_total": round(projected_home + projected_away, 3),
            "status": "PAPER_HOLD_0U",
            "reason": "NO_AUTHENTICATED_PIT_OR_FORWARD_MARKET_ACCEPTANCE",
            "win_probability": None,
            "cover_probability": None,
            "over_probability": None,
            "expected_value": None,
            "approved_stake_u": 0,
        }
        predictions.append(prediction)
        if candidate["game_id"] in outcomes:
            actual = outcomes[candidate["game_id"]]
            mean_home = sum(outcomes[r["game_id"]]["home_score"]
                            for r in past) / len(past)
            mean_away = sum(outcomes[r["game_id"]]["away_score"]
                            for r in past) / len(past)
            # Both sides counted; never cherry-pick the better team/period.
            evaluated.extend((
                (projected_home - actual["home_score"],
                 mean_home - actual["home_score"]),
                (projected_away - actual["away_score"],
                 mean_away - actual["away_score"]),
            ))
    metrics = {
        "fully_walkforward_evaluated_games": len(evaluated) // 2,
        "model_score_mae": (
            round(sum(abs(m) for m, _ in evaluated) / len(evaluated), 5)
            if evaluated else None),
        "baseline_home_away_average_mae": (
            round(sum(abs(b) for _, b in evaluated) / len(evaluated), 5)
            if evaluated else None),
        "model_score_rmse": (
            round(sqrt(sum(m*m for m, _ in evaluated) / len(evaluated)), 5)
            if evaluated else None),
        "baseline_home_away_average_rmse": (
            round(sqrt(sum(b*b for _, b in evaluated) / len(evaluated)), 5)
            if evaluated else None),
    }
    return {
        "status": "PAPER_HOLD_0U",
        "approved_stake_u": 0,
        "feature_authentication": "CALLER_ASSERTED_ASOF_CANNOT_PROVE_SOURCE_PUBLICATION_TIME",
        "market_only_baseline": "NOT_AVAILABLE_NO_VERIFIED_BOTH_SIDED_QUOTES",
        "game_count": len(rows),
        "result_count": len(outcomes),
        "withheld_insufficient_history": withheld,
        "fit_parameters": {
            "ridge": ridge,
            "min_train_games": min_train_games,
            "training_policy": "result_available_utc <= forecast_asof_utc AND earlier kickoff",
        },
        "score_metrics": metrics,
        "predictions": predictions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-train-games", type=int, default=32)
    parser.add_argument("--ridge", type=float, default=25.0)
    args = parser.parse_args()
    # Check EVERY input and output before opening a file or computing scores.
    feature_path = private_evidence_path(args.features)
    result_path = private_evidence_path(args.results)
    output_path = private_evidence_path(args.out)
    score = walkforward(
        _read_csv(feature_path, FEATURE_COLUMNS),
        _read_csv(result_path, RESULT_COLUMNS),
        ridge=args.ridge, min_train_games=args.min_train_games,
    )
    score["input_sha256"] = {
        "features": "sha256:" + sha256(feature_path.read_bytes()).hexdigest(),
        "results": "sha256:" + sha256(result_path.read_bytes()).hexdigest(),
    }
    with output_path.open("x", encoding="utf-8") as fh:
        json.dump(score, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({
        "status": score["status"], "game_count": score["game_count"],
        "scored_games": score["score_metrics"]["fully_walkforward_evaluated_games"],
        "out": args.out,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
