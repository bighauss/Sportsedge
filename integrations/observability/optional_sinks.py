"""Opt-in adapters for aggregate-only research telemetry.

Only allowlisted numeric counters are exported; no prompts, quotes, player IDs,
raw traces, source URLs, credential strings or private event details. No network
calls by default. Third-party packages are intentionally OPTIONAL.
"""
from __future__ import annotations

import os
from pathlib import Path

KEYS = {
    "input_rows": "input_rows",
    "clock_consistent_rows": "clock_consistent_rows",
    "blocked_rows": "blocked_rows",
}
METRICS = {
    "n_decided", "n_clv_matched", "n_clv_unmatched",
    "brier_descriptive_not_forward_certified",
    "log_loss_descriptive_not_forward_certified",
    "clv_prob_gain_same_selection",
}


class ExportBlocked(ValueError):
    pass


def metrics_only(report):
    if not isinstance(report, dict) or report.get("schema") != "SPORTSEDGE_OBSERVABILITY_V1":
        raise ExportBlocked("INVALID_REPORT_SCHEMA")
    if (report.get("official") is not False or report.get("stake_u") != 0
            or report.get("source_authenticated") is not False):
        raise ExportBlocked("ADMISSION_CANNOT_BE_AUTHENTICATED_BY_MONITOR")
    metric_data = report.get("metrics")
    if not isinstance(metric_data, dict):
        raise ExportBlocked("MISSING_METRICS")
    result = {}
    for key in KEYS:
        v = report.get(key)
        if type(v) is not int or v < 0:
            raise ExportBlocked("INVALID_COUNT:" + key)
        result[key] = v
    if result["clock_consistent_rows"] + result["blocked_rows"] != result["input_rows"]:
        raise ExportBlocked("ROW_CENSUS_MISMATCH")
    for key in METRICS:
        value = metric_data.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExportBlocked("INVALID_METRIC:" + key)
        import math
        if not math.isfinite(value):
            raise ExportBlocked("INVALID_METRIC:" + key)
        result[key] = float(value)
    for key in ("n_decided", "n_clv_matched", "n_clv_unmatched"):
        if key in result:
            v = result[key]
            if int(v) != v or v < 0 or v > result["clock_consistent_rows"]:
                raise ExportBlocked("METRIC_COUNT_OUTSIDE_VALID_ROW_CENSUS:" + key)
    if "n_clv_matched" in result and "n_clv_unmatched" in result:
        if result["n_clv_matched"] + result["n_clv_unmatched"] != result["clock_consistent_rows"]:
            raise ExportBlocked("CLOSING_COVERAGE_COUNT_MISMATCH")
    return result


def private_path(value):
    p = Path(value).resolve()
    root = Path(__file__).resolve().parents[2]
    if p == root or root in p.parents:
        raise ExportBlocked("TELEMETRY_OUTPUT_MUST_BE_OUTSIDE_PUBLIC_REPO")
    return p


def write_whylogs_local(report, output_file):
    """Opt-in local binary profile using whylogs + pandas, no cloud writer."""
    data = metrics_only(report)
    dest = private_path(output_file)
    if dest.exists():
        raise ExportBlocked("OUTPUT_EXISTS_CREATE_ONLY")
    try:
        import pandas as pd
        import whylogs as why
    except ImportError as exc:
        raise ExportBlocked("INSTALL_OPTIONAL_WHYLOGS_AND_PANDAS") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    # No why.init() -- it can select cloud/anonymous upload based on environment.
    profile = why.log(pd.DataFrame([data]))
    outcome = profile.writer("local").write(dest=str(dest))
    if not dest.is_file() or dest.stat().st_size == 0:
        raise ExportBlocked("WHYLOGS_LOCAL_WRITE_FAILED")
    return {"status": "LOCAL_ONLY", "metrics": len(data)}


def write_mlflow_local(report, store_dir):
    """Local-only MLflow experiment, no remote URI or raw artifacts."""
    data = metrics_only(report)
    root = private_path(store_dir)
    try:
        import mlflow
    except ImportError as exc:
        raise ExportBlocked("INSTALL_OPTIONAL_MLFLOW") from exc
    root.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(root.as_uri())
    mlflow.set_experiment("SportsEdge_Research_Quality")
    with mlflow.start_run():
        mlflow.log_params({"certification": "PAPER_0U",
                           "source_attestation": "not_authenticated",
                           "measure": "descriptive_not_forward_validated"})
        mlflow.log_metrics(data)
    return {"status": "LOCAL_ONLY", "metrics": len(data)}


def trace_langfuse_aggregate(report, *, explicit_consent=False):
    """Remote opt-in ONLY. No inputs/outputs or row-level metadata ever sent."""
    data = metrics_only(report)
    if explicit_consent is not True:
        raise ExportBlocked("REMOTE_TELEMETRY_REQUIRES_EXPLICIT_CONSENT")
    if os.environ.get("SPORTSEDGE_ENABLE_LANGFUSE") != "1":
        raise ExportBlocked("LANGFUSE_DISABLED")
    if not all(os.environ.get(key) for key in
               ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")):
        raise ExportBlocked("LANGFUSE_KEYS_NOT_CONFIGURED")
    try:
        from langfuse import get_client
    except ImportError as exc:
        raise ExportBlocked("INSTALL_OPTIONAL_LANGFUSE") from exc
    client = get_client()
    with client.start_as_current_observation(
            name="sportsedge_research_quality_aggregate", as_type="span") as observation:
        observation.update(metadata={"certification": "PAPER_0U", **data})
    client.flush()
    return {"status": "AGGREGATE_ONLY_REMOTE_OPT_IN", "metrics": len(data)}
