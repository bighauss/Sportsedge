"""Chronological score forecast residual audit with pre-holdout final availability.

This is research only, NEVER a promotion to an official wagering market. A
game's kickoff time alone cannot establish when its final score was knowable.
Historical result publication AND local capture must precede a fold cutoff
before that game can be included in training. Original clock assertions still
require independent attestation for any future live/official Gate C decision.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import statistics

from .allmarkets_research import _hash, _time


@dataclass(frozen=True)
class FrozenGame:
    event_id: str
    sport: str
    start_at_utc: datetime
    features_asof_utc: datetime
    fitted_until_utc: datetime
    projection_home: float
    projection_away: float
    final_home: int
    final_away: int
    forecast_sha256: str
    # These are REQUIRED for usable score audit. Defaults exist solely so
    # callers using the old constructor get an explicit Gate C failure
    # instead of silently treating a start time as result availability.
    final_published_utc: datetime | None = None
    final_captured_utc: datetime | None = None

    def __post_init__(self):
        for t in (self.start_at_utc, self.features_asof_utc, self.fitted_until_utc):
            _time(t)
        _hash(self.forecast_sha256)
        if not isinstance(self.event_id, str) or not self.event_id.strip() or (
            not isinstance(self.sport, str) or not self.sport.strip()
        ):
            raise ValueError("CHRONOLOGICAL_GAME_IDENTITY_MISSING")
        if not (self.fitted_until_utc < self.features_asof_utc < self.start_at_utc):
            raise ValueError("FUTURE_LEAK_OR_SAME_GAME_TRAINING")
        if any(type(x) not in (int, float) or not math.isfinite(x) or
               x < 0 for x in (self.projection_home, self.projection_away)):
            raise ValueError("INVALID_PREDICTIVE_SCORE")
        if any(type(x) is not int or x < 0 or x > 500 for x in
               (self.final_home, self.final_away)):
            raise ValueError("INVALID_FINAL_SCORE")
        if self.final_published_utc is None or self.final_captured_utc is None:
            raise ValueError("ORIGINAL_FINAL_AVAILABILITY_REQUIRED")
        _time(self.final_published_utc)
        _time(self.final_captured_utc)
        if not (self.start_at_utc < self.final_published_utc <=
                self.final_captured_utc <= datetime.now(timezone.utc)):
            raise ValueError("ORIGINAL_FINAL_CHRONOLOGY_INVALID")


def _residuals(games: list[FrozenGame]) -> tuple[list[float], list[float]]:
    return (
        [(g.final_home-g.final_away) -
         (g.projection_home-g.projection_away) for g in games],
        [(g.final_home+g.final_away) -
         (g.projection_home+g.projection_away) for g in games],
    )


def walk_forward_score_audit(
    games: list[FrozenGame],
    *,
    minimum_training: int = 50,
    holdout_per_fold: int = 25,
    minimum_folds: int = 3,
) -> dict:
    """Recompute train-only residual widths and score later start cohorts.

    Never train using a final captured at or after the first holdout start.
    Every event with an identical start belongs to the same holdout cohort,
    even when that makes a fold larger than the requested size. Earlier
    holdout finals may join later training only after their capture time.
    """
    if (type(minimum_training) is not int or minimum_training < 30 or
            type(holdout_per_fold) is not int or holdout_per_fold < 10 or
            type(minimum_folds) is not int or minimum_folds < 3):
        raise ValueError("WEAK_OR_NONPREREGISTERED_FOLD_POLICY")
    if not isinstance(games, list) or any(
        not isinstance(g, FrozenGame) for g in games
    ):
        raise ValueError("FROZEN_GAME_RECORDS_REQUIRED")

    base = {
        "input_games": len(games),
        "official_counted": 0,
        "approved_stake_u": 0,
        "independent_source_attested": False,
    }
    if not games:
        return {**base, "status": "INSUFFICIENT_CHRONOLOGICAL_OBSERVATIONS",
                "completed_folds": 0, "folds": []}

    ordered = sorted(games, key=lambda g: (g.start_at_utc, g.event_id))
    identities = {(g.sport.strip().casefold(), g.event_id.strip().casefold())
                  for g in ordered}
    if len(identities) != len(ordered) or len({g.sport for g in ordered}) != 1:
        raise ValueError("DUPLICATE_EVENTS_OR_MIXED_SPORT")

    if len(ordered) < minimum_training + holdout_per_fold:
        return {**base, "status": "INSUFFICIENT_CHRONOLOGICAL_OBSERVATIONS",
                "completed_folds": 0, "folds": []}

    starts: dict[datetime, list[FrozenGame]] = defaultdict(list)
    for g in ordered:
        starts[g.start_at_utc].append(g)
    timestamps = sorted(starts)
    folds: list[dict] = []
    cursor = 0
    seed_unscored = 0
    short_tail_unscored = 0

    while cursor < len(timestamps):
        cutoff = timestamps[cursor]
        training = [g for g in ordered
                    if g.start_at_utc < cutoff and g.final_captured_utc < cutoff]
        if len(training) < minimum_training:
            seed_unscored += len(starts[cutoff])
            cursor += 1
            continue

        holdout: list[FrozenGame] = []
        after = cursor
        while after < len(timestamps) and len(holdout) < holdout_per_fold:
            holdout.extend(starts[timestamps[after]])
            after += 1
        if len(holdout) < holdout_per_fold:
            short_tail_unscored += len(holdout)
            break

        # Intentionally fit using only observations that really existed
        # by the FIRST holdout start. Model point forecasts are already
        # frozen independently before their own event start.
        margin_errors, total_errors = _residuals(training)
        sd_margin = statistics.stdev(margin_errors)
        sd_total = statistics.stdev(total_errors)
        if not (math.isfinite(sd_margin) and math.isfinite(sd_total) and
                0.1 <= sd_margin <= 150 and 0.1 <= sd_total <= 150):
            raise ValueError("DEGENERATE_TRAINING_RESIDUALS")

        errors_margin, errors_total = _residuals(holdout)
        logs, briers = [], []
        for g in holdout:
            margin = g.projection_home - g.projection_away
            prob = (1 + math.erf(margin / (sd_margin*math.sqrt(2)))) / 2
            outcome = (1 if g.final_home > g.final_away
                       else 0 if g.final_home < g.final_away else 0.5)
            prob = min(max(prob, 1e-10), 1-1e-10)
            briers.append((prob-outcome)**2)
            if outcome in (0, 1):
                logs.append(-(outcome*math.log(prob) +
                              (1-outcome)*math.log(1-prob)))

        folds.append({
            "fold_index": len(folds),
            "training_n": len(training),
            "holdout_n": len(holdout),
            "train_latest_final_captured_utc":
                max(g.final_captured_utc for g in training).isoformat(),
            "training_ends_before_utc": cutoff.isoformat(),
            "evaluation_starts_utc": cutoff.isoformat(),
            "evaluation_ends_utc": holdout[-1].start_at_utc.isoformat(),
            "train_sd_margin": sd_margin, "train_sd_total": sd_total,
            "holdout_mae_margin": statistics.mean(abs(x) for x in errors_margin),
            "holdout_mae_total": statistics.mean(abs(x) for x in errors_total),
            "holdout_brier_ml": statistics.mean(briers),
            "holdout_logloss_ml": statistics.mean(logs) if logs else None,
            "train_data_source_hashes": len({
                g.forecast_sha256 for g in training}),
        })
        cursor = after

    return {
        **base,
        "status": ("RESEARCH_HOLDOUT_REVIEW" if len(folds) >= minimum_folds
                   else "INSUFFICIENT_CHRONOLOGICAL_FOLDS"),
        "sport": ordered[0].sport,
        "completed_folds": len(folds),
        "seed_unscored_games": seed_unscored,
        "short_tail_unscored_games": short_tail_unscored,
        "holdout_scored_games": sum(f["holdout_n"] for f in folds),
        "folds": folds,
        "reasons": [
            "NO_INDEPENDENT_SOURCE_ATTESTATION_FROM_THIS_MODULE",
            "ORIGINAL_FINAL_PUBLISH_AND_CAPTURE_CLOCKS_SELF_REPORTED",
            "SCORE_FORECAST_ERROR_IS_NOT_BETTING_EDGE",
            "NEED_AUTHENTICATED_DK_TAKE_AND_CLOSE_QUOTES",
            "NO_AUTOMATIC_HYPERPARAMETER_ADOPTION",
        ],
    }
