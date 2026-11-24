"""Research only: compare frozen margin forecasts against prior-only HCA/slope fit.

Input rows must be original pregame predictions joined to observed finals. This
module validates structure and chronology, NOT source authenticity or whether
a prediction itself was built from point-in-time inputs. No odds or stakes.
"""
from collections import Counter
from datetime import datetime
from math import isfinite
from statistics import mean

def utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    return datetime.fromisoformat(s[:-1] + "+00:00")

def number(x):
    if type(x) not in (int, float) or not isfinite(x):
        raise ValueError("FINITE_NUMBER_REQUIRED")
    return float(x)

def digest(s):
    if not isinstance(s, str) or len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError("SOURCE_DIGEST_REQUIRED")

def audit(records, min_train=50):
    if type(min_train) is not int or min_train < 3:
        raise ValueError("MIN_TRAIN_INVALID")
    rows = list(records)
    ids = Counter(r.get("event_id") for r in rows if isinstance(r, dict) and isinstance(r.get("event_id"), str))
    accepted, holds = [], []
    for i, r in enumerate(rows):
        try:
            eid = r["event_id"]
            if not isinstance(eid, str) or not eid or ids[eid] != 1:
                raise ValueError("DUPLICATE_OR_INVALID_EVENT")
            f, t, o = (utc(r[k]) for k in ("freeze_utc", "tipoff_utc", "final_observed_utc"))
            if not f < t < o:
                raise ValueError("INVALID_CHRONOLOGY")
            if type(r["neutral"]) is not bool:
                raise ValueError("UNKNOWN_NEUTRAL")
            digest(r["prediction_sha256"]); digest(r["final_sha256"])
            x, baseline, y = (number(r[k]) for k in ("neutral_margin", "baseline_margin", "actual_margin"))
            if max(abs(x), abs(baseline), abs(y)) > 150:
                raise ValueError("MARGIN_OUT_OF_RANGE")
            accepted.append(dict(index=i, event_id=eid, f=f, o=o, neutral=r["neutral"], x=x, baseline=baseline, y=y))
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            holds.append(dict(index=i, reason=str(e)))
    output = []
    for r in sorted(accepted, key=lambda v: (v["f"], v["event_id"])):
        # Same-freeze games cannot train one another. Only finals actually observed
        # before the target forecast freeze enter the fit.
        train = [v for v in accepted if not v["neutral"] and v["o"] < r["f"]]
        if len(train) < min_train:
            holds.append(dict(index=r["index"], reason="INSUFFICIENT_PRIOR_NONNEUTRAL"))
            continue
        xs, residuals = [v["x"] for v in train], [v["y"]-v["x"] for v in train]
        mx, mr = mean(xs), mean(residuals)
        sxx = sum((x-mx)**2 for x in xs)
        if sxx <= 1e-10:
            holds.append(dict(index=r["index"], reason="UNIDENTIFIED_MARGIN_SLOPE"))
            continue
        slope = sum((x-mx)*(e-mr) for x,e in zip(xs,residuals))/sxx
        intercept = mr-slope*mx
        hca = intercept if not r["neutral"] else 0.0
        output.append(dict(index=r["index"], event_id=r["event_id"], training_n=len(train),
                           hca=intercept, slope=slope, baseline=r["baseline"],
                           intercept_only=r["x"]+hca, intercept_slope=(1+slope)*r["x"]+hca,
                           actual=r["y"], neutral=r["neutral"]))
    metrics = {k: mean(abs(r[k]-r["actual"]) for r in output) if output else None
               for k in ("baseline","intercept_only","intercept_slope")}
    return dict(status="PAPER_0U_UNAUTHENTICATED_RESEARCH", input_rows=len(rows),
                compared_rows=len(output), holds=sorted(holds,key=lambda v:v["index"]),
                rows=output, paired_mae=metrics, official_counted=0, approved_stake_u=0)
