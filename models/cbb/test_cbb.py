"""End-to-end test on SYNTHETIC barttorvik-shaped samples (fake teams, players, odds).

Run: python3 test_cbb.py   (stdlib only, network off) -> prints card and ALL TESTS PASSED.
"""
import csv, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
socket.socket = None  # hard network OFF
import sportsedge_cbb_model as m

SAMPLES = os.path.join(HERE, "samples")


def w(name, rows):
    with open(os.path.join(SAMPLES, name + ".csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)


def team(name, g, oe, de, t, **kw):
    r = dict(team=name, games=g, adjoe=oe, adjde=de, adj_t=t, efg_o=52.0, efg_d=49.0, tov_o=17.0, tov_d=18.5,
             orb_o=30.0, orb_d=28.0, ftr_o=33.0, ftr_d=31.0, three_pa_rate=38.0, three_p_o=35.0, three_p_d=33.0,
             pre_adjoe=oe - 1, pre_adjde=de + 1, pre_adj_t=t, venue_hca="", altitude="")
    r.update(kw); return r


def make_samples():
    os.makedirs(SAMPLES, exist_ok=True)
    w("teams", [team("Alpha", 5, 116.0, 95.0, 70.0, venue_hca=3.5),
                team("Beta", 5, 106.0, 103.0, 66.0, three_p_o=39.0),
                team("BYU", 4, 112.0, 98.0, 68.5),
                team("Gamma", 4, 108.0, 101.0, 71.0)])
    w("players", [dict(player="Star Alpha", team="Alpha", mpg=33, usg=29, pts40=26.0, reb40=7.0, ast40=4.0, tpm40=2.5),
                  dict(player="Wing Alpha", team="Alpha", mpg=30, usg=22, pts40=18.0, reb40=6.0, ast40=3.0, tpm40=2.8),
                  dict(player="Star Beta", team="Beta", mpg=34, usg=28, pts40=24.0, reb40=5.0, ast40=6.0, tpm40=3.2),
                  dict(player="Guard Beta", team="Beta", mpg=31, usg=24, pts40=19.0, reb40=4.0, ast40=5.0, tpm40=2.9),
                  dict(player="Big BYU", team="BYU", mpg=29, usg=25, pts40=22.0, reb40=12.0, ast40=2.0, tpm40=0.4),
                  dict(player="Guard Gamma", team="Gamma", mpg=33, usg=27, pts40=23.0, reb40=4.5, ast40=5.5, tpm40=3.0)])
    w("games", [dict(game_id="C1", home="Alpha", away="Beta", neutral=0, away_tz_diff=2, away_b2b=0, home_b2b=0),
                dict(game_id="C2", home="BYU", away="Gamma", neutral=0, away_tz_diff=0, away_b2b=1, home_b2b=0)])
    w("injuries", [dict(team="Beta", player="Star Beta", status="out", role=""),
                   dict(team="Gamma", player="Guard Gamma", status="questionable", role="top2")])
    odds = []
    for gid, spread, total in (("C1", -11.5, 145.5), ("C2", -6.5, 141.5)):
        odds += [dict(game_id=gid, market="ml", side="home", line="", price_american=-600, opp_price_american=430),
                 dict(game_id=gid, market="ml", side="away", line="", price_american=430, opp_price_american=-600),
                 dict(game_id=gid, market="spread", side="home", line=spread, price_american=-105, opp_price_american=-105),
                 dict(game_id=gid, market="spread", side="away", line=-spread, price_american=-105, opp_price_american=-105),
                 dict(game_id=gid, market="total", side="over", line=total, price_american=-105, opp_price_american=-105),
                 dict(game_id=gid, market="total", side="under", line=total, price_american=-105, opp_price_american=-105),
                 dict(game_id=gid, market="team_total_home", side="over", line=round(total / 2 - spread / 2), price_american=-105, opp_price_american=-105),
                 dict(game_id=gid, market="team_total_home", side="under", line=round(total / 2 - spread / 2), price_american=-105, opp_price_american=-105),
                 dict(game_id=gid, market="h1_total", side="over", line=round(total * 0.47) + 0.5, price_american=-105, opp_price_american=-105),
                 dict(game_id=gid, market="h1_total", side="under", line=round(total * 0.47) + 0.5, price_american=-105, opp_price_american=-105)]
    w("odds", odds)
    w("props", [dict(game_id="C1", player="Star Alpha", stat="pts", line=19.5, over_price=-110, under_price=-110),
                dict(game_id="C1", player="Star Beta", stat="pts", line=18.5, over_price=-110, under_price=-110),
                dict(game_id="C2", player="Big BYU", stat="reb", line=8.5, over_price=-110, under_price=-110)])
    return {k: os.path.join(SAMPLES, k + ".csv") for k in ("teams", "players", "games", "injuries", "odds", "props")}


def main():
    inputs = make_samples()
    out = tempfile.mkdtemp()
    res = m.run_card(inputs, out_dir=out)
    rows, projs = res["rows"], res["projections"]
    g1, p1 = projs["C1"]; g2, p2 = projs["C2"]
    assert p1["margin"] > 0, p1                       # strong home team favored
    assert abs(p1["home_pts"] + p1["away_pts"] - p1["total"]) < 1e-9
    n1, n2 = " ".join(p1["notes"]), " ".join(p2["notes"])
    assert "HCA +3.5" in n1 and "away travel/b2b -0.75" in n1 and "Star Beta out" in n1, n1
    assert "altitude" in n2 and "Guard Gamma questionable" in n2, n2
    assert 100 < p1["total"] < 190 and 100 < p2["total"] < 190
    # Identity regression: identical names across teams must never bind by first match.
    twin = {
        "Alpha": [{"player": "Twin", "team": "Alpha", "player_id": "a-1"}],
        "Beta": [{"player": "Twin", "team": "Beta", "player_id": "b-1"}],
        "BYU": [{"player": "Outside", "team": "BYU", "player_id": "c-1"}],
    }
    game = {"home": "Alpha", "away": "Beta"}
    found, why = m.resolve_prop_player(game, {"player": "Twin"}, twin)
    assert found is None and why == "AMBIGUOUS_PROP_PLAYER"
    found, why = m.resolve_prop_player(game, {"player": "Twin", "team": "Alpha"}, twin)
    assert found["player_id"] == "a-1" and why is None
    found, why = m.resolve_prop_player(game, {"player": "Twin", "player_id": "b-1"}, twin)
    assert found["team"] == "Beta" and why is None
    found, why = m.resolve_prop_player(game, {"player": "Outside"}, twin)
    assert found is None and why == "PROP_PLAYER_NOT_ON_EVENT_ROSTER"
    found, why = m.resolve_prop_player(game, {"player": "Twin", "team": "BYU"}, twin)
    assert found is None and why == "PROP_TEAM_NOT_IN_EVENT"
    found, why = m.resolve_prop_player(game, {"player": "Twin", "player_id": "missing"}, twin)
    assert found is None and why == "PROP_PLAYER_NOT_ON_EVENT_ROSTER"
    # Same-name ambiguity is also quarantined by the card runner, not silently priced.
    with open(inputs["players"], newline="") as pf:
        existing = list(csv.DictReader(pf))
    dup = dict(existing[0]); dup["team"] = "Beta"
    w("players", existing + [dup])
    alt = m.run_card(inputs, out_dir=tempfile.mkdtemp())
    assert any("AMBIGUOUS_PROP_PLAYER:C1:Star Alpha" in x for x in alt["dropped"])
    assert not any(r["bet"].startswith("Star Alpha") for r in alt["rows"])
    # Restore source fixture for any following test runs.
    w("players", existing)

    # odds math
    assert abs(m.am_to_dec(-110) - 1.909090909) < 1e-6 and m.am_to_dec(150) == 2.5
    assert abs(m.novig(-110, -110) - 0.5) < 1e-9
    # card rules
    assert rows, "expected some +EV plays on the synthetic slate"
    evs = [r["blend_ev"] for r in rows]
    assert evs == sorted(evs, reverse=True) and all(e > 0 for e in evs)
    for r in rows:
        assert 1 <= r["stars"] <= 5
        assert abs(r["blend_p"] - (0.3 * r["model_p"] + 0.7 * r["market_p"])) < 1e-9
        assert not m.contradicts(r["side"], r["line"], r["proj"]), r
    assert not any(r["bet"].startswith("Star Beta") for r in rows), "OUT player must not get a prop"
    card = list(csv.DictReader(open(os.path.join(out, "cbb_card.csv"))))
    assert len(card) == len(rows)
    md = open(os.path.join(out, "cbb_card.md")).read()
    assert "SportsEdge CBB Run It Card" in md
    print(md)
    print("ALL TESTS PASSED: %d plays, %d dropped" % (len(rows), len(res["dropped"])))


if __name__ == "__main__":
    main()
