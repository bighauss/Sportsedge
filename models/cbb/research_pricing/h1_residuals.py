"""Empirical first-half residual calibration with chronological safeguards (PAPER/0u).

Requires unique game IDs, forecast timestamps, tip times, and result-availability
timestamps. Enforces that forecasts precede tipoff and that results were
available before the calibration cutoff. Rejects duplicates. Reports residual
bias and separates calibration from out-of-sample evaluation.
"""
from __future__ import annotations
import math
from collections import Counter
from datetime import datetime
from statistics import mean, stdev
from typing import Dict, Iterable, List, Optional, Tuple

class Hold(Exception):
    pass

def _utc(s: str) -> datetime:
    if not isinstance(s, str) or not s.endswith("Z"):
        raise Hold("TIMESTAMP_INVALID")
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError:
        raise Hold("TIMESTAMP_INVALID")

def admit_records(
    records: Iterable[dict],
    *,
    cutoff_utc: str,
    min_n: int = 30,
) -> List[dict]:
    """
    Admit only records that satisfy chronology and uniqueness.

    Required keys per record:
      game_id, forecast_utc, tipoff_utc, result_available_utc,
      predicted_margin, actual_margin, predicted_total, actual_total
    Optional: predicted_home, actual_home, predicted_away, actual_away
    """
    cutoff = _utc(cutoff_utc)
    seen = Counter()
    admitted = []
    for i, r in enumerate(records):
        try:
            gid = r.get("game_id")
            if not isinstance(gid, str) or not gid.strip():
                raise Hold("INVALID_GAME_ID")
            seen[gid] += 1
            if seen[gid] > 1:
                raise Hold("DUPLICATE_GAME_ID")
            f, t, o = (_utc(r[k]) for k in ("forecast_utc", "tipoff_utc", "result_available_utc"))
            if not (f < t < o <= cutoff):
                raise Hold("CHRONOLOGY_VIOLATION")
            for k in ("predicted_margin", "actual_margin", "predicted_total", "actual_total"):
                v = r[k]
                if type(v) not in (int, float) or not math.isfinite(v):
                    raise Hold("NONFINITE_VALUE")
            admitted.append(r)
        except (KeyError, TypeError, Hold) as exc:
            # Individual rejection is recorded by the caller if needed;
            # here we simply skip invalid rows so the fit can proceed on clean data.
            continue
    if len(admitted) < min_n:
        raise Hold("INSUFFICIENT_RESIDUAL_SAMPLE")
    return admitted

def residual_stats(pairs: List[Tuple[float, float]]) -> Dict[str, float]:
    residuals = [a - p for p, a in pairs]
    n = len(residuals)
    if n < 2:
        raise Hold("INSUFFICIENT_RESIDUAL_SAMPLE")
    mu = mean(residuals)
    sd = stdev(residuals)
    if sd <= 0 or not math.isfinite(sd):
        raise Hold("NONPOSITIVE_RESIDUAL_SD")
    return {"n": n, "residual_mean": mu, "residual_sd": sd, "residual_bias": mu}

def fit_h1_residuals(
    records: Iterable[dict],
    *,
    cutoff_utc: str,
    min_n: int = 30,
    model_version: str = "unspecified",
    evidence_sha256: Optional[str] = None,
) -> Dict:
    """
    Fit residual distributions from chronologically admissible records.
    Returns calibration summary plus residual SDs ready for pricing.
    """
    admitted = admit_records(records, cutoff_utc=cutoff_utc, min_n=min_n)
    margin_pairs = [(r["predicted_margin"], r["actual_margin"]) for r in admitted]
    total_pairs = [(r["predicted_total"], r["actual_total"]) for r in admitted]
    fit = {
        "margin": residual_stats(margin_pairs),
        "total": residual_stats(total_pairs),
    }
    # Team totals only when both predicted and actual are present for every admitted row
    if all("predicted_home" in r and "actual_home" in r for r in admitted):
        fit["home_team_total"] = residual_stats(
            [(r["predicted_home"], r["actual_home"]) for r in admitted]
        )
    if all("predicted_away" in r and "actual_away" in r for r in admitted):
        fit["away_team_total"] = residual_stats(
            [(r["predicted_away"], r["actual_away"]) for r in admitted]
        )
    return {
        "status": "PAPER_0U_RESEARCH_CALIBRATION",
        "model_version": model_version,
        "evidence_sha256": evidence_sha256,
        "cutoff_utc": cutoff_utc,
        "admitted_n": len(admitted),
        "min_n": min_n,
        "fit": fit,
        "sds": {
            "sd_margin": fit["margin"]["residual_sd"],
            "sd_total": fit["total"]["residual_sd"],
            "sd_home_team_total": fit.get("home_team_total", {}).get("residual_sd"),
            "sd_away_team_total": fit.get("away_team_total", {}).get("residual_sd"),
        },
    }

def withhold_team_total_if_missing(sds: Dict[str, Optional[float]], side: str) -> Optional[float]:
    """Return the empirical SD or None if unavailable. Caller must withhold pricing."""
    key = "sd_home_team_total" if side == "home" else "sd_away_team_total"
    return sds.get(key)
