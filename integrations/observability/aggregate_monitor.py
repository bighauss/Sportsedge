"""Compare sanitized observability aggregates across independently stored runs.

This is an alert *candidate*, not a model drift claim or betting release gate.
No sensitive input records or automated changes to stake/model weights.
"""
from __future__ import annotations

import json
from pathlib import Path

from optional_sinks import metrics_only, private_path, ExportBlocked


def compare_reports(baseline, current, *, min_rows=30,
                    max_block_increase=0.05, max_clv_coverage_drop=0.10,
                    max_brier_increase=0.03):
    a, b = metrics_only(baseline), metrics_only(current)
    if type(min_rows) is not int or min_rows < 30:
        raise ExportBlocked("MIN_ROWS_MUST_BE_AT_LEAST_30")
    for val in (max_block_increase, max_clv_coverage_drop, max_brier_increase):
        if isinstance(val, bool) or not isinstance(val, (int,float)) or not 0 <= val <= 1:
            raise ExportBlocked("INVALID_THRESHOLD")
    alerts = []
    samples = min(a["input_rows"], b["input_rows"])
    if samples < min_rows:
        status = "INSUFFICIENT_SAMPLE_NO_DRIFT_CLAIM"
    else:
        prior_block = a["blocked_rows"] / a["input_rows"]
        now_block = b["blocked_rows"] / b["input_rows"]
        if now_block - prior_block > max_block_increase:
            alerts.append("BLOCKED_ROW_RATE_INCREASE")
        if min(a["clock_consistent_rows"], b["clock_consistent_rows"]) >= min_rows:
            prior_coverage = a.get("n_clv_matched", 0) / a["clock_consistent_rows"]
            now_coverage = b.get("n_clv_matched", 0) / b["clock_consistent_rows"]
            if prior_coverage - now_coverage > max_clv_coverage_drop:
                alerts.append("MATCHED_CLOSE_COVERAGE_DROP")
        if min(a.get("n_decided", 0), b.get("n_decided", 0)) >= min_rows:
            p = a.get("brier_descriptive_not_forward_certified")
            n = b.get("brier_descriptive_not_forward_certified")
            if p is not None and n is not None and n - p > max_brier_increase:
                alerts.append("DESCRIPTIVE_BRIER_WORSENING_UNCONFIRMED")
        status = "REVIEW_ALERTS" if alerts else "NO_THRESHOLD_ALERT"
    return {
        "schema": "SPORTSEDGE_OBSERVABILITY_COMPARE_V1",
        "status": status, "alerts": alerts, "min_rows": min_rows,
        "baseline_rows": a["input_rows"], "current_rows": b["input_rows"],
        "source_authenticated": False, "forward_validated": False,
        "official": False, "stake_u": 0,
        "warning": "Aggregate-only descriptive thresholds; composition shifts, PIT authenticity and forward calibration NOT established.",
    }


def run_cli(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", required=True)
    p.add_argument("--current", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    previous = json.loads(private_path(args.baseline).read_text(encoding="utf-8"))
    current = json.loads(private_path(args.current).read_text(encoding="utf-8"))
    report = compare_reports(previous, current)
    dest = private_path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(report["status"], report["alerts"])


if __name__ == "__main__":
    run_cli()
