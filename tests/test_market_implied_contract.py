import math
from dataclasses import replace
import pytest
from research.market_implied.devig import BookQuote, consensus, devig, _bisect, METHODS, ev_per_unit


def quote(**kw):
    return replace(BookQuote("External", [-110,-110], event_id="event-1", market="spread",
        period="game", line=-3.5, outcomes=("home","away"), capture_utc="2026-11-24T01:00:00Z",
        start_utc="2026-11-24T02:00:00Z", rules="two-way-refund", sport="NFL"), **kw)


def run(qs):
    return consensus(qs, as_of="2026-11-24T01:01:00Z", max_age_seconds=120)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("bad", [float("nan"),float("inf"),float("-inf"),True])
def test_nonfinite_odds_rejected(method,bad):
    assert devig([bad,-110],method).status == "INVALID"


@pytest.mark.parametrize("change", [dict(event_id="other"),dict(player_id="other"),dict(market="total"),
    dict(period="1h"),dict(line=-2.5),dict(outcomes=("away","home")),dict(rules="other"),
    dict(sport="NBA"),dict(start_utc="2026-11-24T03:00:00Z"),dict(prices=[-110,-110,200]),
    dict(capture_utc="2026-11-24T00:00:00Z"),dict(capture_utc="2026-11-24T01:00:00"),
    dict(capture_utc="2026-11-24T01:02:00Z"),dict(weight=0),dict(weight=-1),dict(weight=float("nan")),
    dict(weight=float("inf")),dict(outcomes=("home","home"))])
def test_contract_and_freshness_defects(change):
    assert run([quote(),quote(book="Other",**change)]).status == "INVALID"


def test_metadata_required():
    assert run([BookQuote("External",[-110,-110])]).status == "INVALID"


def test_no_bracket_or_convergence():
    with pytest.raises(ValueError): _bisect(lambda x:x*x+1,-1,1)
    with pytest.raises(ValueError): _bisect(lambda x:x*x-2,0,2,it=1)
    assert _bisect(lambda x:x,0,1) == 0


def test_valid_and_dk_exclusion():
    result=run([quote(),quote(book="DraftKings",prices=[-200,170])])
    assert result.status == "OK" and result.fair == pytest.approx([.5,.5])
    assert consensus([quote(book="DraftKings")],exclude=()).status == "NO_PRICE"


@pytest.mark.parametrize("method", METHODS)
def test_valid_numeric_vectors(method):
    for prices,fmt in [([-110,-110],"american"),([-300,240],"american"),([2.6,3.3,2.9],"decimal")]:
        result=devig(prices,method,fmt)
        assert result.status == "OK" and sum(result.fair) == pytest.approx(1)


def test_push_invalid_and_fair_ev():
    with pytest.raises(ValueError): ev_per_unit(.6,2,.5)
    with pytest.raises(ValueError): ev_per_unit(.5,2,-.1)
    assert ev_per_unit(.47,2,.06) == pytest.approx(0)
