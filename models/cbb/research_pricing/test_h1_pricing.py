"""Regression tests for the research first-half pricing interface."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_pricing.h1_pricing import (
    american_to_decimal, break_even, ev, price_h1_spread, price_h1_total,
    nine_blends, Hold, BLEND_WEIGHTS,
)

def test_american_decimal_and_breakeven():
    assert abs(american_to_decimal(100) - 2.0) < 1e-9
    assert abs(american_to_decimal(-110) - (1 + 100/110)) < 1e-9
    assert abs(break_even(-110) - (110/210)) < 1e-9
    try:
        american_to_decimal(0)
        assert False
    except Hold:
        pass

def test_ev_formula():
    # Even money, 55% win: EV = 0.55 * 1 - 0.45 = 0.10
    assert abs(ev(0.55, 0.45, 100) - 0.10) < 1e-9
    # -110, 52.4% win should be near zero
    p = 110/210
    assert abs(ev(p, 1-p, -110)) < 1e-9

def test_probability_normalization():
    row = price_h1_spread(
        game_id="g1", home_team="A", away_team="B",
        expected_home=35.0, expected_away=32.0, sd_margin=8.0,
        line=-3.5, american=-110, side="home", capture_utc="2026-11-25T12:00:00Z",
    )
    assert abs(row["p_win"] + row["p_loss"] + row["p_push"] - 1.0) < 1e-9
    assert row["approved_stake_u"] == 0
    assert row["status"] == "PAPER_0U_RESEARCH"

def test_nine_weights_present():
    row = price_h1_total(
        game_id="g1", expected_home=35.0, expected_away=32.0, sd_total=10.0,
        line=67.5, american=-105, side="over", capture_utc="2026-11-25T12:00:00Z",
        p_market=0.52,
    )
    blends = row["nine_blends"]
    assert len(blends) == 9
    assert blends[0]["model_weight"] == 0.0
    assert blends[-1]["model_weight"] == 1.0
    assert all(abs(b["model_weight"] + b["market_weight"] - 1.0) < 1e-9 for b in blends)

def test_neutral_identity_preserved_by_caller():
    # Module does not apply HCA; caller must pass already-adjusted expectations.
    # Neutral game: expected scores supplied without campus adjustment must be used as-is.
    row = price_h1_spread(
        game_id="n1", home_team="X", away_team="Y",
        expected_home=34.0, expected_away=34.0, sd_margin=8.0,
        line=0.0, american=-110, side="home", capture_utc="2026-11-25T12:00:00Z",
    )
    assert abs(row["expected_margin"]) < 1e-9

def test_invalid_side_rejected():
    try:
        price_h1_spread(
            game_id="g1", home_team="A", away_team="B",
            expected_home=35.0, expected_away=32.0, sd_margin=8.0,
            line=-3.5, american=-110, side="neither", capture_utc="2026-11-25T12:00:00Z",
        )
        assert False
    except Hold as e:
        assert "INVALID_SIDE" in str(e)

if __name__ == "__main__":
    test_american_decimal_and_breakeven()
    test_ev_formula()
    test_probability_normalization()
    test_nine_weights_present()
    test_neutral_identity_preserved_by_caller()
    test_invalid_side_rejected()
    print("All H1 pricing interface tests passed")
