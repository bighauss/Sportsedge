"""Regression tests for the repaired first-half pricing interface."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_pricing.h1_pricing import (
    american_to_decimal, break_even, ev, price_h1_spread, price_h1_total,
    price_h1_moneyline, price_h1_team_total, Hold,
)

def test_american_and_ev():
    assert abs(american_to_decimal(100) - 2.0) < 1e-9
    assert abs(ev(0.55, 0.45, 100) - 0.10) < 1e-9
    p = 110 / 210
    assert abs(ev(p, 1 - p, -110)) < 1e-9

def test_away_spread_sign():
    # Home is expected to win by 5. Home -3.5 should be a favorite cover.
    # Away +3.5 should be the opposite side.
    home = price_h1_spread(
        game_id="g1", home_team="A", away_team="B",
        expected_home=40.0, expected_away=35.0, sd_margin=8.0,
        line=-3.5, american=-110, side="home", capture_utc="2026-11-25T12:00:00Z",
    )
    away = price_h1_spread(
        game_id="g1", home_team="A", away_team="B",
        expected_home=40.0, expected_away=35.0, sd_margin=8.0,
        line=-3.5, american=-110, side="away", capture_utc="2026-11-25T12:00:00Z",
    )
    assert home["p_win"] > 0.5
    assert away["p_win"] < 0.5
    assert abs(home["p_win"] + away["p_win"] + home["p_push"] - 1.0) < 1e-6

def test_integer_push_nonzero():
    row = price_h1_spread(
        game_id="g1", home_team="A", away_team="B",
        expected_home=35.0, expected_away=35.0, sd_margin=8.0,
        line=0.0, american=-110, side="home", capture_utc="2026-11-25T12:00:00Z",
    )
    assert row["p_push"] > 0.0
    assert abs(row["p_win"] + row["p_loss"] + row["p_push"] - 1.0) < 1e-6

def test_nine_blends_include_ev():
    row = price_h1_total(
        game_id="g1", expected_home=35.0, expected_away=32.0, sd_total=10.0,
        line=67.5, american=-105, side="over", capture_utc="2026-11-25T12:00:00Z",
        p_market=0.52,
    )
    blends = row["nine_blends"]
    assert len(blends) == 9
    assert all("blended_ev" in b for b in blends)
    assert blends[-1]["blended_ev"] is not None

def test_fair_odds_account_for_push():
    row = price_h1_spread(
        game_id="g1", home_team="A", away_team="B",
        expected_home=35.0, expected_away=35.0, sd_margin=8.0,
        line=0.0, american=-110, side="home", capture_utc="2026-11-25T12:00:00Z",
    )
    # Conditional fair decimal (push refunds) should be lower than the naive 1/p_win
    assert row["fair_decimal"] is not None
    assert row["fair_decimal"] < 1.0 / row["p_win"]
    # And equal to 1 / (p_win / (p_win + p_loss))
    p_cond = row["p_win"] / (row["p_win"] + row["p_loss"])
    assert abs(row["fair_decimal"] - 1.0 / p_cond) < 1e-9

def test_moneyline_and_team_total_exist():
    ml = price_h1_moneyline(
        game_id="g1", home_team="A", away_team="B",
        expected_home=36.0, expected_away=33.0, sd_margin=8.0,
        american=-150, side="home", capture_utc="2026-11-25T12:00:00Z",
    )
    tt = price_h1_team_total(
        game_id="g1", team="A", expected=36.0, sd=7.0,
        line=35.5, american=-110, side="over", capture_utc="2026-11-25T12:00:00Z",
    )
    assert ml["market"] == "H1_MONEYLINE"
    assert tt["market"] == "H1_TEAM_TOTAL"
    assert abs(ml["p_win"] + ml["p_loss"] + ml["p_push"] - 1.0) < 1e-6

def test_timestamp_validation():
    try:
        price_h1_spread(
            game_id="g1", home_team="A", away_team="B",
            expected_home=35.0, expected_away=32.0, sd_margin=8.0,
            line=-3.5, american=-110, side="home", capture_utc="not-a-timestamp",
        )
        assert False
    except Hold as e:
        assert "TIMESTAMP" in str(e)

if __name__ == "__main__":
    test_american_and_ev()
    test_away_spread_sign()
    test_integer_push_nonzero()
    test_nine_blends_include_ev()
    test_fair_odds_account_for_push()
    test_moneyline_and_team_total_exist()
    test_timestamp_validation()
    print("All repaired H1 pricing tests passed")
