"""Tests for empirical H1 residual calibration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_pricing.h1_residuals import residual_sd, fit_h1_residuals, sds_for_pricing, Hold

def test_residual_sd_basic():
    pairs = [(30.0, 32.0), (28.0, 27.0), (35.0, 36.0)] * 15  # n=45
    r = residual_sd(pairs)
    assert r["n"] == 45
    assert r["residual_sd"] > 0

def test_insufficient_sample_rejected():
    try:
        residual_sd([(1.0, 2.0)] * 10, min_n=30)
        assert False
    except Hold as e:
        assert "INSUFFICIENT" in str(e)

def test_fit_returns_pricing_sds():
    margin = [(5.0, 3.0), (2.0, 4.0), (0.0, -1.0)] * 20
    total = [(60.0, 62.0), (55.0, 53.0), (70.0, 71.0)] * 20
    fit = fit_h1_residuals(margin, total)
    sds = sds_for_pricing(fit)
    assert sds["sd_margin"] > 0
    assert sds["sd_total"] > 0
    assert sds["sd_home_team_total"] is None

if __name__ == "__main__":
    test_residual_sd_basic()
    test_insufficient_sample_rejected()
    test_fit_returns_pricing_sds()
    print("H1 residual tests passed")
