import copy
import pytest
from research.market_implied.walkforward import walk_forward, MARKET_WEIGHTS


def rows():
    return [dict(sport="NFL",event_id=f"e{i}",quote_id=f"q{i}",market="spread",horizon="1h",
             capture_utc=f"2026-11-{i:02}T10:00:00Z",start_utc=f"2026-11-{i:02}T11:00:00Z",
             result_available_utc=f"2026-11-{i:02}T15:00:00Z",prob_definition="conditional_no_push",
             result="W",market_p=.8,independent_p=.2,current_p=.5) for i in range(1,6)]


def test_full_chronology_and_nine_candidates():
    r=walk_forward(rows(),min_events=2)
    assert len(MARKET_WEIGHTS)==9
    assert [x["status"] for x in r["forecasts"]][:2]==["INSUFFICIENT_TRAINING"]*2
    assert all(x["market_weight"]==1 for x in r["forecasts"][2:])
    assert len(r["metrics"])==13
    assert {x["n"] for x in r["metrics"]}=={3}
    assert all(x["small_sample"] and not x["promotion_authorized"] for x in r["metrics"])


def test_future_labels_do_not_change_frozen_forecasts():
    base=rows(); a=walk_forward(base,min_events=2)
    base[-1]["result"]="L"
    b=walk_forward(base,min_events=2)
    assert a["forecasts"]==b["forecasts"]


def test_delayed_results_not_training():
    base=rows(); base[0]["result_available_utc"]="2026-12-01T00:00:00Z"
    r=walk_forward(base,min_events=2)
    assert r["forecasts"][2]["status"]=="INSUFFICIENT_TRAINING"


def test_duplicate_and_naive_rejected():
    base=rows()
    with pytest.raises(ValueError): walk_forward(base+[base[0]],min_events=2)
    base[0]["capture_utc"]="2026-11-01T10:00:00"
    with pytest.raises(ValueError): walk_forward(base,min_events=2)


def test_missing_push_deadheat_are_reported_not_binary_scored():
    base=rows(); base[-1]["result"]="DH"; base[-2]["result"]="P"; base[-3]["current_p"]=None
    r=walk_forward(base,min_events=2)
    assert not r["metrics"]
    assert {x["result"] for x in r["coverage"]}=={"W","P","DH"}


@pytest.mark.parametrize("sport",["NFL","CFB","CBB","NBA","MLB","NHL","PGA"])
def test_seven_sport_probability_schema(sport):
    base=rows()
    for r in base:r["sport"]=sport
    assert len(walk_forward(base,min_events=2)["metrics"])==13
