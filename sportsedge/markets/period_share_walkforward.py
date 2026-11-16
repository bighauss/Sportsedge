"""Source-preserving out-of-sample audit of train-only regulation period shares.

Synthetic/PRIVATE research only. Uses the actual existing period fitter anew
at each chronological holdout start. Only finals captured strictly before the
current group of events may enter that fold's training. No market odds, model
weights, wager selection, stake approval or source attestation is provided.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import math
from pathlib import Path

from .period_share_fit import (
    FIT_VERSION, PERIODS, _clock, _duplicate_keys, _nonfinite,
    _private_path, fit_period_shares, MAX_SIZE,
)

SCHEMA = "SPORTSEDGE_PERIOD_SHARE_WALKFORWARD_R1"


def audit(raw: bytes, *, sport: str, evaluation_asof_utc: str,
          minimum_training: int = 50, minimum_dates: int = 7,
          holdout_per_fold: int = 20, minimum_folds: int = 3) -> dict:
    """Evaluate fixed empirical period proportions vs a uniform baseline.

    Every complete same-start cohort is held out together. Future results are
    unavailable for training even if their events started earlier. An invalid
    original record prevents ALL scored folds, never first-copy-wins.
    """
    if sport not in PERIODS:
        raise ValueError("UNKNOWN_PERIOD_SHARE_SPORT")
    if (type(minimum_training) is not int or minimum_training < 50 or
            type(minimum_dates) is not int or minimum_dates < 7 or
            type(holdout_per_fold) is not int or holdout_per_fold < 10 or
            type(minimum_folds) is not int or minimum_folds < 3):
        raise ValueError("WEAK_OR_NONPREREGISTERED_FOLD_POLICY")
    asof = _clock(evaluation_asof_utc, "EVALUATION_ASOF")
    if asof > datetime.now(timezone.utc):
        raise ValueError("EVALUATION_ASOF_IN_FUTURE")
    if type(raw) is not bytes or not raw or len(raw) > MAX_SIZE:
        raise ValueError("ORIGINAL_PERIOD_LEDGER_MISSING_OR_TOO_LARGE")

    # Validate EVERY original byte/row before computing any test statistic.
    # Aggregate shares returned by this full-ledger check are deliberately
    # NEVER used as a holdout prediction; they contain evaluation outcomes.
    census = fit_period_shares(raw, sport=sport,
                               fit_asof_utc=evaluation_asof_utc,
                               minimum_training=minimum_training,
                               minimum_dates=minimum_dates)
    base = {
        "schema": SCHEMA, "sport": sport, "evaluation_asof_utc": evaluation_asof_utc,
        "original_file_sha256": "sha256:" + sha256(raw).hexdigest(),
        "input_rows": census["total_rows"],
        "blocked_rows": census["blocked_rows"],
        "blocked_reasons": census["blocked_reasons"],
        "fit_failures": census["fit_failures"],
        "fitted_using_full_ledger": False,
        "source_authenticated": False, "period_holdout_calibrated": False,
        "official": False, "approved_stake_u": 0,
        "warnings": [
            "All source publication/capture clocks and hash strings are still operator claims.",
            "This evaluates TRAIN-ONLY temporal scoring proportions; not model score predictions, calibrated joint tails, bookmaker EV or CLV.",
            "The uniform baseline is NOT a sportsbook no-vig benchmark. No model promotion or change to original cards.",
        ],
    }
    if census["status"] != "TRAIN_ONLY_PERIOD_SHARES_RESEARCH_UNCALIBRATED":
        return {**base, "status": "BLOCK_INVALID_OR_INSUFFICIENT_ORIGINAL_LEDGER",
                "completed_folds": 0, "folds": [], "scored_holdout_games": 0}

    # The fitter already validated UTF-8, exact JSON keys, every identity,
    # regulation totals, no duplicates, and dates. Keep literal original
    # JSONL row bytes for each subsequent train-only refit.
    lines = raw.decode("utf-8").splitlines(keepends=True)
    parsed = [json.loads(line, object_pairs_hook=_duplicate_keys,
                         parse_constant=_nonfinite) for line in lines]
    dataset = []
    for line, record in zip(lines, parsed):
        start = _clock(record["game_start_utc"], "GAME_START")
        captured = _clock(record["final_captured_utc"], "FINAL_CAPTURED")
        scores = [sum(record["periods"][key]) for key in PERIODS[sport]]
        dataset.append((start, captured, line, scores))
    grouped = defaultdict(list)
    for item in dataset:
        grouped[item[0]].append(item)
    times = sorted(grouped)
    folds = []
    cursor = 0
    seed_games = 0
    short_tail = 0

    while cursor < len(times):
        cutoff = times[cursor]
        train = [r for r in dataset if r[0] < cutoff and r[1] < cutoff]
        dates = {r[0].date() for r in train}
        if len(train) < minimum_training or len(dates) < minimum_dates:
            seed_games += len(grouped[cutoff])
            cursor += 1
            continue

        held = []
        next_cursor = cursor
        while next_cursor < len(times) and len(held) < holdout_per_fold:
            held.extend(grouped[times[next_cursor]])
            next_cursor += 1
        if len(held) < holdout_per_fold:
            short_tail = len(held)
            break

        # Training here is a literal subset of previously saved source bytes.
        # This is a rolling PREQUENTIAL update: outcomes from previous test
        # folds can be used only after they become available, not retroactively.
        training_bytes = b"".join(
            (line if line.endswith("\n") else line + "\n").encode("utf-8")
            for _, _, line, _ in train
        )
        fitted = fit_period_shares(
            training_bytes, sport=sport,
            fit_asof_utc=cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            minimum_training=minimum_training, minimum_dates=minimum_dates)
        if fitted["status"] != "TRAIN_ONLY_PERIOD_SHARES_RESEARCH_UNCALIBRATED":
            raise ValueError("TRAIN_ONLY_FOLD_RECOMPUTATION_FAILED")
        p = fitted["period_shares"]
        points = [sum(row[3][j] for row in held) for j in range(len(p))]
        total = sum(points)
        zero_games = sum(sum(row[3]) == 0 for row in held)
        logloss = (-sum(count*math.log(prob) for count, prob in zip(points,p))/total
                   if total else None)
        uniform_logloss = math.log(len(p)) if total else None
        folds.append({
            "fold_index": len(folds),
            "train_n": len(train), "holdout_n": len(held),
            "training_distinct_dates": len(dates),
            "train_latest_final_captured_utc":
                max(r[1] for r in train).isoformat(),
            "holdout_start_utc": cutoff.isoformat(),
            "holdout_last_start_utc": held[-1][0].isoformat(),
            "train_original_subset_sha256": fitted["source_file_sha256"],
            "period_fit_model_sha256": fitted["period_fit_model_sha256"],
            "trained_period_shares": p,
            "heldout_regulation_points": total,
            "zero_score_holdout_games": zero_games,
            "model_logloss_per_scoring_point": logloss,
            "uniform_logloss_per_scoring_point": uniform_logloss,
            "model_minus_uniform_logloss": (
                logloss-uniform_logloss if total else None),
            "training_only_prior_available_finals": True,
        })
        cursor = next_cursor

    completed = len(folds)
    all_points = sum(f["heldout_regulation_points"] for f in folds)
    delta = (sum(f["model_minus_uniform_logloss"]*f["heldout_regulation_points"]
                 for f in folds if f["heldout_regulation_points"])
             / all_points if all_points else None)
    status = ("RESEARCH_WALKFORWARD_DESCRIPTIVE_NOT_CERTIFIED"
              if completed >= minimum_folds and all_points
              else "INSUFFICIENT_CHRONOLOGICAL_HOLDOUTS")
    return {**base, "status": status, "completed_folds": completed,
            "minimum_folds": minimum_folds,
            "holdout_per_fold_requested": holdout_per_fold,
            "seed_games_before_first_eligible_fold": seed_games,
            "short_tail_games_not_scored": short_tail,
            "scored_holdout_games": sum(f["holdout_n"] for f in folds),
            "total_heldout_scoring_points": all_points,
            "weighted_model_minus_uniform_logloss": delta,
            "folds": folds}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sport", required=True, choices=sorted(PERIODS))
    parser.add_argument("--evaluation-asof-utc", required=True)
    args = parser.parse_args(argv)
    src, target = _private_path(args.input), _private_path(args.out)
    if not src.is_file():
        parser.error("PRIVATE_LEDGER_NOT_FOUND")
    report = audit(src.read_bytes(), sport=args.sport,
                   evaluation_asof_utc=args.evaluation_asof_utc)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True, allow_nan=False)
        fh.write("\n")
    print(report["status"], "folds", report["completed_folds"],
          "official", False, "stake_u", 0)


if __name__ == "__main__":
    main()
