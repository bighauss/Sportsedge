"""Run all SportsEdge point-in-time research synthetic test suites in normal CI.

This file is intentionally called by the existing NFL DFS tests.yml step, so
CI execution does not depend on GitHub Workflows write permissions. An absent
test file is an error; never silently skip an entire research guard lane.
"""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys

RESEARCH_SUITES = (
    "models/test_audit_disagreement_calibration.py",
    "models/test_ledger_grades_to_audit_csv.py",
    "models/nfl_dfs/test_usage_share_features.py",
    "models/nfl_dfs/test_market_walkforward.py",
    "ledger/test_close_snapshot_archive.py",
    "models/nba/test_minutes_candidate.py",
    "models/nba/test_anchor_evaluator.py",
    "models/common/test_research_guardrails.py",
    "sportsedge/validation/test_paper_ledger.py",
    "research/risk/test_portfolio_stress_audit.py",
)


def run_all_research_tests() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative in RESEARCH_SUITES:
        path = root / relative
        if not path.is_file():
            raise RuntimeError("Missing mandatory research test: " + relative)
        print("RESEARCH CI: " + relative, flush=True)
        if relative.startswith("sportsedge/validation/"):
            subprocess.run([sys.executable, "-m", "unittest", "-v",
                            "sportsedge.validation.test_paper_ledger"],
                           cwd=str(root), check=True)
        else:
            subprocess.run([sys.executable, str(path)], cwd=str(path.parent), check=True)


if __name__ == "__main__":
    run_all_research_tests()
