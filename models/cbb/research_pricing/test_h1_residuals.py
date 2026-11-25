"""Tests for chronological residual calibration safeguards."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_pricing.h1_residuals import fit_h1_residuals, withhold_team_total_if_missing, Hold

def _row(i, forecast="2026-11-20T12:00:00Z", tip="2026-11-20T18:00:00Z",
         result="2026-11-20T22:00:00Z", **kw):
    base = {
        "game_id": f"g{i}",
        "forecast_utc": forecast,
        "tipoff_utc": tip,
        "result_available_utc": result,
        "predicted_margin": 3.0,
        "actual_margin": 2.0 + (i % 5) - 2,
        "predicted_total": 60.0,
        "actual_total": 61.0 + (i % 7) - 3,
    }
    base.update(kw)
    return base

def test_quarantine_and_rejection_reasons():
    rows = [_row(i) for i in range(40)]
    rows.append(_row(0))  # duplicate of g0
    rows.append(_row(99, result="2026-11-26T00:00:00Z"))  # future
    fit = fit_h1_residuals(rows, cutoff_utc="2026-11-25T00:00:00Z", min_n=30)
    assert fit["admitted_n"] == 39  # g0 quarantined
    assert fit["rejected_n"] >= 3
    reasons = {r["reason"] for r in fit["rejected"]}
    assert "QUARANTINED_DUPLICATE" in reasons
    assert any("CHRONOLOGY" in r for r in reasons)

def test_insufficient_after_rejection():
    rows = [_row(i) for i in range(10)]
    try:
        fit_h1_residuals(rows, cutoff_utc="2026-11-25T00:00:00Z", min_n=30)
        assert False
    except Hold as e:
        assert "INSUFFICIENT" in str(e)

def test_team_total_withheld_when_missing():
    rows = [_row(i) for i in range(40)]
    fit = fit_h1_residuals(rows, cutoff_utc="2026-11-25T00:00:00Z")
    assert withhold_team_total_if_missing(fit["sds"], "home") is None
    assert withhold_team_total_if_missing(fit["sds"], "away") is None

def test_provenance_preserved():
    rows = [_row(i) for i in range(40)]
    fit = fit_h1_residuals(
        rows, cutoff_utc="2026-11-25T00:00:00Z",
        model_version="h1-research-v1", evidence_sha256="a"*64,
    )
    assert fit["model_version"] == "h1-research-v1"
    assert fit["evidence_sha256"] == "a"*64
    assert fit["status"] == "PAPER_0U_RESEARCH_CALIBRATION"

if __name__ == "__main__":
    test_quarantine_and_rejection_reasons()
    test_insufficient_after_rejection()
    test_team_total_withheld_when_missing()
    test_provenance_preserved()
    print("Chronological residual safeguards passed")
