"""Optional export of sanitized SportsEdge aggregate diagnostics.

Read a pre-existing private quality_gate report; never upload source rows or
raw quotes. Local exports only unless --langfuse with explicit opt-in.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from optional_sinks import (ExportBlocked, metrics_only, private_path,
                            write_mlflow_local, write_whylogs_local,
                            trace_langfuse_aggregate)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True, help="PRIVATE quality_gate JSON report")
    p.add_argument("--whylogs-bin", help="PRIVATE local output file, requires whylogs/pandas")
    p.add_argument("--mlflow-dir", help="PRIVATE local store directory, requires mlflow")
    p.add_argument("--langfuse", action="store_true",
                   help="explicitly opt into aggregate-only remote tracing")
    args = p.parse_args(argv)
    if not (args.whylogs_bin or args.mlflow_dir or args.langfuse):
        p.error("AT_LEAST_ONE_OPT_IN_SINK_REQUIRED")
    source = private_path(args.report)
    report = json.loads(source.read_text(encoding="utf-8"))
    metrics_only(report)
    if args.whylogs_bin:
        print(write_whylogs_local(report, args.whylogs_bin))
    if args.mlflow_dir:
        print(write_mlflow_local(report, args.mlflow_dir))
    if args.langfuse:
        print(trace_langfuse_aggregate(report, explicit_consent=True))


if __name__ == "__main__":
    main()
