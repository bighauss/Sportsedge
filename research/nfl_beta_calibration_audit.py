"""Prospective NFL beta calibration ledger, with no post-hoc pick selection.

Requires pregame frozen prediction records and later separate outcomes.
A result alone cannot establish that a pregame probability was recorded.
"""
import json
import math
from collections import defaultdict


def audit(predictions, outcomes, *, min_graded=100):
    if not isinstance(predictions, list) or not isinstance(outcomes, list):
        raise ValueError("INVALID_LEDGER")
    actual = {}
    for o in outcomes:
        k = o["prediction_id"]
        if k in actual or o.get("result") not in (0, 1):
            raise ValueError("DUPLICATE_OR_INVALID_OUTCOME")
        actual[k] = o["result"]
    seen = set()
    buckets = defaultdict(list)
    ungraded = 0
    for p in predictions:
        k = p["prediction_id"]
        if k in seen:
            raise ValueError("DUPLICATE_PREDICTION")
        seen.add(k)
        if p.get("status") != "PAPER_HOLD_0U" or p.get("stake_u") != 0:
            raise ValueError("NOT_PAPER")
        prob = p.get("beta_probability")
        if prob is None:
            ungraded += 1
            continue
        if isinstance(prob, bool) or not isinstance(prob, (float, int)) or not math.isfinite(prob) or not 0 <= prob <= 1:
            raise ValueError("INVALID_PROBABILITY")
        if not p.get("frozen_at_utc") or not p.get("kickoff_utc") or p["frozen_at_utc"] >= p["kickoff_utc"]:
            raise ValueError("NO_VERIFIABLE_PREGAME_FREEZE")
        if not p.get("receipt_sha256"):
            raise ValueError("NO_FROZEN_RECEIPT")
        if k not in actual:
            ungraded += 1
            continue
        buckets[p["kind"]].append((prob, actual[k]))
    summary = {}
    for kind, pairs in sorted(buckets.items()):
        n = len(pairs)
        brier = sum((p - y) ** 2 for p, y in pairs) / n
        base = sum(y for _, y in pairs) / n
        base_brier = sum((base - y) ** 2 for _, y in pairs) / n
        summary[kind] = dict(n=n, brier=round(brier, 6),
                             observed_hit_rate=round(base, 6),
                             baseline_brier=round(base_brier, 6),
                             validated=False,
                             reason=("INSUFFICIENT_PROSPECTIVE_SAMPLE" if n < min_graded
                                     else "NEEDS_CHRONOLOGICAL_HOLDOUT_AND_CLV"))
    return dict(status="AUDIT_ONLY_NO_PROMOTION", families=summary,
                missing_or_ungraded=ungraded, official_bets=0)
