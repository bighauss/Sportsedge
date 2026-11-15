"""End-to-end test on synthetic sample inputs. Run: python3 test_sportsedge_nba_model.py"""
import os, csv, tempfile
import sportsedge_nba_model as m

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = ["teams", "games", "injuries", "players", "positional_defense", "odds", "props"]

def test_all():
    # pricing sanity
    assert abs(m.am_to_dec(-110) - 1.9091) < 1e-3 and m.am_to_dec(150) == 2.5
    po, push = m.p_over(220, 18, 220.0)
    assert 0 < push < 0.05 and abs(po - (1 - po - push)) < 1e-9
    assert m.stars(0.07) == 5 and m.stars(0.001) == 1
    out = tempfile.mkdtemp()
    res = m.run_card({n: os.path.join(HERE, "sample", n + ".csv") for n in NAMES}, out)
    pr = res["projections"]
    g1 = pr["G1"]
    assert 200 < g1["total"] < 260 and abs(g1["home_pts"] + g1["away_pts"] - g1["total"]) < 1e-6
    assert "B2B" in g1["inputs"] and "altitude" in g1["inputs"] and "Aaron Gordon" in g1["inputs"]
    picks = res["picks"]
    assert picks, "expected some +EV picks"
    evs = [p["blend_ev"] for p in picks]
    assert evs == sorted(evs, reverse=True) and all(e > 0 for e in evs)
    for p in picks:
        if p["ou"] == "UNDER": assert p["line"] >= p["projection"]
        if p["ou"] == "OVER": assert p["line"] <= p["projection"]
        assert 1 <= p["stars"] <= 5
    rows = list(csv.DictReader(open(res["csv"])))
    assert len(rows) == len(picks)
    assert "SportsEdge NBA RUN IT card" in open(res["md"]).read()
    # minutes redistribution: Watson gains Gordon's minutes
    players = m.project_players(m.load_inputs({n: os.path.join(HERE, "sample", n + ".csv") for n in NAMES}), pr)
    assert players["Peyton Watson"]["min"] > 20 and players["Aaron Gordon"]["min"] == 0
    print(open(res["md"]).read())
    print(f"OK: {len(picks)} picks; markets: {sorted({p['market'] for p in picks})}")

if __name__ == "__main__":
    test_all()
