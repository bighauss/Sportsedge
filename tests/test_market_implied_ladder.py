from dataclasses import replace
import pytest
from research.market_implied.devig import BookQuote
from research.market_implied.ladder import infer_count_ladder

def quote(line,over,under,**kw):
    return replace(BookQuote("External",[over,under],event_id="event-1",player_id="player-1",
      market="prop_points",period="FG",line=line,outcomes=("over","under"),
      capture_utc="2026-11-24T01:00:00Z",start_utc="2026-11-24T02:00:00Z",
      rules="FG_INCL_OT_DNP_VOID",sport="CBB",fmt="decimal"),**kw)
def run(qs):
    return infer_count_ladder(qs,as_of="2026-11-24T01:01:00Z",max_age_seconds=120,method="multiplicative")
def pair():
    return [quote(4.5,1.25,5),quote(7.5,2.5,1/.6)]
def test_interval_mass_and_unidentified_mean():
    r=run(pair())
    assert [i["mass"] for i in r["interval_masses"]]==pytest.approx([.2,.4,.4])
    assert r["lower_median_bounds"]==[5,7]
    assert r["mean_lower_bound"]==pytest.approx(5.2)
    assert r["mean_estimate"] is None and not r["full_pmf_identified"]
def test_dk_alias_excluded():
    assert run(pair()+[quote(4.5,2,2,book="DK")])==run(pair())
@pytest.mark.parametrize("change,reason",[
    (dict(line=7),"NONNEGATIVE_HALF_LINE"),
    (dict(line=float("nan")),"NONNEGATIVE_HALF_LINE"),
    (dict(outcomes=("under","over")),"TWO_SIDED"),
    (dict(prices=[2]),"TWO_SIDED"),
    (dict(player_id=None),"PLAYER_ID"),
    (dict(player_id="other"),"MIXED_LADDER"),
    (dict(rules="other"),"MIXED_LADDER"),
    (dict(book="Other"),"CHANGING_BOOK"),
    (dict(capture_utc="2026-11-24T00:58:59Z"),"SNAPSHOT_SKEW")])
def test_bad_contract(change,reason):
    a,b=pair()
    with pytest.raises(ValueError,match=reason):run([a,replace(b,**change)])
def test_nonmonotone_and_duplicate():
    a,b=pair()
    with pytest.raises(ValueError,match="NONMONOTONIC"):run([a,replace(b,prices=[1/.9,10])])
    with pytest.raises(ValueError,match="DUPLICATE"):run([a,b,a])
def test_target_only():
    with pytest.raises(ValueError,match="NO_EXTERNAL"):run([replace(q,book="Draft Kings") for q in pair()])
