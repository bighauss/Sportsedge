"""Research-only three-outcome scoring on matched rolling-origin rows.

The legacy binary scores condition on non-push outcomes. This companion
measures unconditional win/push/loss forecasts, without changing legacy
outputs, coefficients, selections or stakes. A market-only three-outcome
benchmark is not inferred from two-sided prices.
"""
import math
from statistics import mean

from . import harness as H


def score(prob, actual):
    """Multiclass Brier (sum across classes) and log loss, in W/P/L order."""
    if len(prob) != 3 or type(actual) is not int or actual not in (0, 1, 2):
        raise ValueError("INVALID_OUTCOME")
    if any(not math.isfinite(p) or p < 0 or p > 1 for p in prob):
        raise ValueError("INVALID_PROBABILITY")
    if not math.isclose(sum(prob), 1.0, rel_tol=0, abs_tol=1e-10):
        raise ValueError("PROBABILITIES_NOT_NORMALIZED")
    return (sum((p - (i == actual)) ** 2 for i, p in enumerate(prob)),
            -math.log(max(H.EPS, prob[actual])))


def matched_scores(rows, names, family):
    """Use identical events and include pushes; missing family holds all models."""
    names = tuple(names)
    if not names or len(set(names)) != len(names) or family not in H.FAMILIES:
        raise ValueError("INVALID_COHORT")
    seen = set()
    samples = {name: [] for name in names}
    held = 0
    for r in rows:
        key = (r["season"], r["event_id"])
        if key in seen:
            raise ValueError("DUPLICATE_EVENT")
        seen.add(key)
        if not all(family in r["p"].get(n, {}) for n in names):
            held += 1
            continue
        y = H.outcome(r, family)
        actual = 1 if y is None else (0 if y == 1 else 2)
        for name in names:
            win, push = r["p"][name][family]
            loss = 1.0 - win - push
            if -1e-12 <= loss < 0:
                loss = 0.0
            brier, logloss = score((win, push, loss), actual)
            samples[name].append((brier, logloss, push, actual == 1))
    result = []
    for name, vals in samples.items():
        n = len(vals)
        result.append({
            "model": name, "family": family, "n": n, "held_events": held,
            "observed_pushes": sum(v[3] for v in vals),
            "brier_3class_sum": mean(v[0] for v in vals) if n else None,
            "log_loss_3class_eps_clipped": mean(v[1] for v in vals) if n else None,
            "mean_predicted_push": mean(v[2] for v in vals) if n else None,
            "observed_push_frequency": mean(v[3] for v in vals) if n else None,
            "push_brier": mean((v[2]-v[3])**2 for v in vals) if n else None,
            "status": "RESEARCH_PAPER_0U_NON_COUNTED",
        })
    return result


def report(all_rows, ident, names):
    """Report identical forecast cohort and disjoint chronological subdivisions.

    Previously inspected years are retrospective, not fresh untouched evidence.
    The market supplies settlement thresholds only; no market-only W/P/L
    distribution is inferred. No selection or model tuning occurs here.
    """
    groups = {"ALL": ident}
    for split, seasons in H.SPLITS.items():
        groups[split.upper()] = [r for r in ident if r["season"] in seasons]
    for season in sorted({r["season"] for r in all_rows}):
        groups[str(season)] = [r for r in ident if r["season"] == season]
    output = []
    for group, cohort in groups.items():
        eligible = [r for r in all_rows
                    if group == "ALL"
                    or (group in ("TRAIN", "VALIDATION", "TEST")
                        and H.split_of(r["season"]).upper() == group)
                    or str(r["season"]) == group]
        for family in H.FAMILIES:
            for row in matched_scores(cohort, names, family):
                output.append({
                    "group": group,
                    "all_forecast_rows": len(eligible),
                    "identical_forecast_rows": len(cohort),
                    "outside_identical_cohort": len(eligible) - len(cohort),
                    **row,
                    "evaluation_state": "RETROSPECTIVE_NOT_UNTOUCHED",
                    "market_benchmark": "NOT_IDENTIFIED_FROM_TWO_SIDED_PRICES",
                })
    return output
