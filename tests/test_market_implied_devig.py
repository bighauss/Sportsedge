import math
import pytest
from research.market_implied.devig import (
    METHODS, american_to_decimal, decimal_to_american, devig, devig_all,
    consensus, BookQuote, implied_team_scores, implied_margin_sd,
    ev_per_unit, fair_win_given_push,
)

def test_odds_roundtrip():
    for a in (-250, -110, 100, 150, 2500):
        assert decimal_to_american(american_to_decimal(a)) == pytest.approx(a)
    with pytest.raises(ValueError): american_to_decimal(50)

@pytest.mark.parametrize("m", METHODS)
def test_symmetric_two_way_is_50_50(m):
    r=devig([-110,-110],m)
    assert r.status == "OK"
    assert r.fair == pytest.approx([.5,.5])

@pytest.mark.parametrize("m", METHODS)
def test_sums_to_one_and_keeps_order(m):
    r=devig([-300,240],m)
    assert sum(r.fair) == pytest.approx(1)
    assert r.fair[0] > r.fair[1]
    assert r.fair[0] < 300/400

def test_favorite_longshot_ordering():
    mult=devig([-1000,650],"multiplicative").fair[1]
    assert devig([-1000,650],"power").fair[1] < mult
    assert devig([-1000,650],"shin").fair[1] < mult

def test_multiway_with_draw():
    r=devig([2.6,3.3,2.9],"shin",fmt="decimal")
    assert r.status == "OK" and len(r.fair) == 3
    assert sum(r.fair) == pytest.approx(1)

def test_missing_side_fails_closed():
    r=devig([-110,None]); assert r.status == "NO_PRICE" and r.fair is None

def test_stale_negative_overround_rejected():
    assert devig([150,150]).status == "INVALID"

def test_additive_extreme_longshot_fails_closed():
    r=devig([-20000,5000,6000,8000],"additive")
    assert r.status in ("OK","INVALID")
    if r.status == "OK": assert min(r.fair)>0

def test_consensus_excludes_draftkings_and_copies():
    meta=dict(event_id="e",market="ml",period="game",outcomes=("home","away"),
              capture_utc="2026-11-24T01:00:00Z",start_utc="2026-11-24T02:00:00Z",rules="two-way",sport="NFL")
    q=[BookQuote("DraftKings",[-200,170],**meta),BookQuote("Pinnacle",[-150,140],weight=2,**meta),
       BookQuote("SkinBook",[-150,130],copies="Pinnacle",**meta)]
    r=consensus(q,as_of="2026-11-24T01:01:00Z",max_age_seconds=120)
    assert r.reason == "books=1"
    assert r.fair == pytest.approx(devig([-150,140]).fair)

def test_consensus_no_independent_book():
    assert consensus([BookQuote("draftkings",[-110,-110])]).status == "NO_PRICE"

def test_no_artificial_ev_against_own_book():
    fair=devig([-110,-110]).fair[0]
    assert ev_per_unit(fair,american_to_decimal(-110))<0

def test_team_scores_and_sd():
    assert implied_team_scores(-3.5,47.5) == (25.5,22)
    assert 10 < implied_margin_sd(-3.5,.62) < 14
    with pytest.raises(ValueError): implied_margin_sd(-3.5,.40)

def test_push_fair_odds():
    d=fair_win_given_push(.47,.06)
    assert ev_per_unit(.47,d,.06) == pytest.approx(0)
