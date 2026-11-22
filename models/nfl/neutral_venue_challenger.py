"""NFL venue-adjusted score challenger. Research only, never model promotion.

The original private v3 ratings replay uses a home-field term even for
explicitly neutral games when projecting; its fit discounts the term at
neutral sites. This pure helper removes only a caller-provided HALF of the
FULL score-difference home-field term on each team. It does not infer a venue,
supply a bookmaker price or modify the original frozen v3 model.

One independent, point-in-time venue source must resolve neutral as a bool.
A later corrected venue flag must never be backdated as an input receipt.
"""
from __future__ import annotations

from math import isfinite


class UnknownVenue(ValueError):
    """Research input lacks an explicit Boolean venue determination."""


def project_without_unearned_hfa(
    projected_home: float,
    projected_away: float,
    *,
    neutral: bool,
    home_field_margin_points: float,
) -> tuple[float, float]:
    """Remove the full HFA **margin** advantage at confirmed neutral venues.

    Preconditions:
    - `projected_home` and `projected_away` already include the original
      symmetric HFA (+margin/2 home, -margin/2 away).
    - neutral is a genuine boolean from an independently reviewed pregame venue.
    - no model constant or inferred probability is introduced here.

    On non-neutral venues this is an exact no-op. On neutral venues:
    H' = H - HFA/2 and A' = A + HFA/2, preserving the predicted game total.
    """
    if type(neutral) is not bool:
        raise UnknownVenue("NEUTRAL_VENUE_BOOL_REQUIRED")
    if any(type(x) not in (int, float) or not isfinite(x)
           for x in (projected_home, projected_away, home_field_margin_points)):
        raise ValueError("FINITE_NUMERIC_SCORES_AND_HFA_REQUIRED")
    if projected_home < 0 or projected_away < 0:
        raise ValueError("NEGATIVE_PROJECTED_SCORE")
    if home_field_margin_points < 0 or home_field_margin_points > 20:
        raise ValueError("HOME_FIELD_MARGIN_OUT_OF_RESEARCH_BOUNDS")
    if not neutral:
        return float(projected_home), float(projected_away)
    half = home_field_margin_points / 2
    home, away = projected_home - half, projected_away + half
    if home < 0:
        raise ValueError("NEUTRAL_CORRECTION_CAUSES_NEGATIVE_HOME_SCORE")
    return float(home), float(away)


def paired_margin_errors(
    original_forecasts: list[dict],
    *,
    home_field_margin_points: float,
) -> dict:
    """Paired development MAE, retaining all candidate games and missingness.

    Caller must construct each row from an eligible pregame forecast and a
    later *observed* final, not a retrospective reconstructed pregame snapshot.
    No quote/bet/execution metrics or statistical significance is asserted.
    """
    if type(original_forecasts) is not list:
        raise ValueError("FORECAST_ROWS_REQUIRED")
    if not original_forecasts:
        raise ValueError("NONEMPTY_PAIRED_ROWS_REQUIRED")
    seen = set()
    paired = []
    for row in original_forecasts:
        if type(row) is not dict or set(row) != {
            "event_id", "neutral", "forecast_home", "forecast_away",
            "final_home", "final_away",
        }:
            raise ValueError("FORECAST_ROW_SCHEMA_INVALID")
        eid = row["event_id"]
        if type(eid) is not str or not eid or eid in seen:
            raise ValueError("MISSING_OR_DUPLICATED_EVENT_ID")
        seen.add(eid)
        home, away = project_without_unearned_hfa(
            row["forecast_home"], row["forecast_away"],
            neutral=row["neutral"],
            home_field_margin_points=home_field_margin_points,
        )
        if (type(row["final_home"]) not in (int, float)
                or type(row["final_away"]) not in (int, float)
                or not isfinite(row["final_home"])
                or not isfinite(row["final_away"])
                or row["final_home"] < 0 or row["final_away"] < 0):
            raise ValueError("FINITE_NONNEGATIVE_FINAL_REQUIRED")
        actual = row["final_home"] - row["final_away"]
        original = row["forecast_home"] - row["forecast_away"]
        corrected = home - away
        paired.append({
            "event_id": eid, "neutral": row["neutral"],
            "original_margin_abs": abs(original - actual),
            "challenger_margin_abs": abs(corrected - actual),
        })
    before = sum(r["original_margin_abs"] for r in paired) / len(paired)
    after = sum(r["challenger_margin_abs"] for r in paired) / len(paired)
    return {
        "state": "RESEARCH_DEVELOPMENT_ONLY",
        "n": len(paired),
        "n_neutral": sum(r["neutral"] for r in paired),
        "original_margin_mae": before,
        "challenger_margin_mae": after,
        "delta_mae_challenger_minus_original": after - before,
        "private_originals_authenticated": False,
        "future_holdout_verified": False,
        "official_counted": 0,
        "approved_stake_u": 0,
    }
