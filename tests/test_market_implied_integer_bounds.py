"""Synthetic partition and quote checks; not historical odds or returns."""
from dataclasses import replace
from itertools import product

import pytest
from research.market_implied.devig import BookQuote
from research.market_implied.ladder import integer_count_bounds


def quotes():
    base = BookQuote("external", (1.25, 5), event_id="fixture", sport="CBB",
                     market="prop_points", player_id="fixture-player", period="FG",
                     rules="FG_INCL_OT_DNP_VOID", line=2.5, outcomes=("over", "under"),
                     capture_utc="2026-01-01T01:00:00Z", start_utc="2026-01-01T03:00:00Z",
                     fmt="decimal")
    return [base, replace(base, line=5.5, prices=(1/.3, 1/.7))]


def run(rows, k):
    return integer_count_bounds(rows, k, as_of="2026-01-01T01:01:00Z",
                                max_age_seconds=120, method="multiplicative")


@pytest.mark.parametrize("k", [0, 2, 3, 4, 5, 6, 7, 900])
def test_sharp_bounds_agree_with_extreme_distributions(k):
    # The last representative above k covers the otherwise unbounded tail.
    states = product(range(3), range(3, 6), {6, max(6, k), max(6, k+1)})
    triples = [[sum(m for n, m in zip(ns, (.2, .5, .3)) if op(n, k))
                for op in (int.__gt__, int.__eq__, int.__lt__)] for ns in states]
    result = run(quotes(), k)
    for i, key in enumerate(("over", "push", "under")):
        values = [row[i] for row in triples]
        assert result["bounds"][key] == pytest.approx((min(values), max(values)))
    assert result["approved_stake_u"] == 0


def test_adjacent_half_lines_identify_atom_and_target_never_enters():
    a, b = quotes()
    rows = [replace(a, line=4.5), b]
    result = run(rows, 5)
    for key, mass in zip(("over", "push", "under"), (.3, .5, .2)):
        assert result["bounds"][key] == pytest.approx([mass]*2)
    assert result == run(rows + [replace(a, book="Draft Kings"),
                                 replace(b, book="draftkings6_best"),
                                 replace(b, book="skin", copies="external")], 5)


@pytest.mark.parametrize("k", [True, -1, 3.5, float("nan")])
def test_bad_target(k):
    with pytest.raises(ValueError, match="INTEGER"):
        run(quotes(), k)


def test_not_all_integer_measurements_are_nonnegative_counts():
    with pytest.raises(ValueError, match="COUNT_MARKET"):
        run([replace(q, market="prop_rush_yards") for q in quotes()], 1)
    a, b = quotes()
    with pytest.raises(ValueError, match="MIXED_LADDER"):
        run([a, replace(b, player_id="different")], 3)


def test_weights_must_be_stable_across_rungs():
    a, b = quotes()
    with pytest.raises(ValueError, match="CHANGING_BOOK_WEIGHT"):
        run([a, b, replace(a, book="B"), replace(b, book="B", weight=3)], 4)


@pytest.mark.parametrize("sport,market", [("CFB","prop_receptions"), ("NFL","prop_receptions"),
    ("MLB","prop_total_bases"), ("NBA","prop_points"), ("CBB","prop_rebounds"),
    ("NHL","prop_shots_on_goal"), ("PGA","prop_birdies")])
def test_explicit_count_contracts_only(sport, market):
    rows = [replace(q, sport=sport, market=market, rules="fixture-rules") for q in quotes()]
    assert run(rows, 4)["bounds"]["push"] == pytest.approx([0, .5])
