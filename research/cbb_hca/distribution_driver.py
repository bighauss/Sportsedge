"""Prior-only residual distribution driver. Research only; no odds or stakes."""
from datetime import datetime
from statistics import mean
import math
from .cbb_distribution_audit import probabilities
from .paired_score_audit import bootstrap

def utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    return datetime.fromisoformat(s[:-1] + "+00:00")

def smooth(p, n):
    """Same explicit finite-probability policy for every distribution family."""
    if type(n) is not int or n < 1 or type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("SMOOTHING_INPUT_INVALID")
    return (p * n + 0.5) / (n + 1)

def calibration(ps, ys):
    if len(ps) < 10 or len(set(ys)) < 2:
        return dict(intercept=None, slope=None, converged=False, reason="INSUFFICIENT_VARIATION")
    xs = [math.log(p / (1 - p)) for p in ps]
    a, b, ok = 0.0, 1.0, False
    for _ in range(40):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in zip(xs, ys):
            q = 1 / (1 + math.exp(-max(-30, min(30, a + b * x))))
            w = q * (1 - q); d = y - q
            g0 += d; g1 += d * x; h00 += w; h01 += w * x; h11 += w * x * x
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da, db = (h11 * g0 - h01 * g1) / det, (-h01 * g0 + h00 * g1) / det
        a += da; b += db
        if max(abs(da), abs(db)) < 1e-8:
            ok = True; break
    return dict(intercept=a, slope=b, converged=ok, reason=None if ok else "NOT_CONVERGED")

def evaluate(records, *, min_train=30, use_mean_location=False):
    rows = []
    for r in records:
        if r.get("settlement") != "FG_INCL_OT":
            raise ValueError("ML_FG_INCL_OT_REQUIRED")
        rows.append(dict(r, f=utc(r["freeze_utc"]), o=utc(r["final_observed_utc"]), y=int(r["actual_margin"] > 0), residual=r["actual_margin"] - r["projected_margin"]))
    evaluated, holds = [], []
    for r in sorted(rows, key=lambda v: (v["f"], v["event_id"])):
        train = [v["residual"] for v in rows if v["o"] < r["f"]]
        if len(train) < min_train:
            holds.append(dict(event_id=r["event_id"], reason="INSUFFICIENT_PRIOR_FINALS")); continue
        try:
            raw = probabilities(train, r["projected_margin"], use_mean_location=use_mean_location)
        except ValueError as exc:
            holds.append(dict(event_id=r["event_id"], reason=str(exc))); continue
        scored = {k: smooth(raw[k], raw["training_n"]) for k in ("normal", "student_t", "empirical")}
        evaluated.append(dict(event_id=r["event_id"], y=r["y"], direction="HOME_FAVORITE" if r["projected_margin"] > 0 else "HOME_UNDERDOG" if r["projected_margin"] < 0 else "PICKEM", raw=raw, scored=scored, train_n=raw["training_n"]))
    summary = {}
    for fam in ("normal", "student_t", "empirical"):
        ps, ys = [r["scored"][fam] for r in evaluated], [r["y"] for r in evaluated]
        summary[fam] = dict(n=len(ps), brier=mean((p - y) ** 2 for p, y in zip(ps, ys)) if ps else None, log_loss=mean(-(y * math.log(p) + (1 - y) * math.log(1 - p)) for p, y in zip(ps, ys)) if ps else None, calibration=calibration(ps, ys), directions={d: dict(n=len(g), bias=mean(r["scored"][fam] - r["y"] for r in g)) for d in sorted({r["direction"] for r in evaluated}) if (g := [r for r in evaluated if r["direction"] == d])})
    return dict(status="PAPER_0U_PRIOR_ONLY_DISTRIBUTION_RESEARCH", probability_policy="COMMON_TRAIN_N_PLUS_HALF_SMOOTHING_NO_HIDDEN_CLIP", evaluated=len(evaluated), holds=holds, summary=summary, paired_brier_difference={fam: bootstrap({r["event_id"]: (r["scored"]["normal"] - r["y"]) ** 2 - (r["scored"][fam] - r["y"]) ** 2 for r in evaluated}) for fam in ("student_t", "empirical")}, approved_stake_u=0)
