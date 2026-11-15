"""End-to-end test on synthetic samples. Network not used. Run: python3 test_cfb_model.py"""
import os, sys, csv, tempfile, socket
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
socket.socket = None  # hard network OFF
import sportsedge_cfb_model as m

def main():
    out = tempfile.mkdtemp()
    card, projs = m.run_card(os.path.join(HERE, "samples", "inputs.json"), out)
    assert len(projs) == 2
    p1, p2 = projs
    assert p1["home"] == "Alpha State" and p1["margin"] > 0, p1["margin"]
    assert any("travel" in n for n in p1["notes"]) and any("short week" in n for n in p1["notes"])
    assert any("QB OUT" in n for n in p1["notes"]) and "wind 18" in p1["weather"]
    assert "ignored" in p2["weather"] and any("altitude" in n for n in p2["notes"])
    assert any("DBs OUT" in n for n in p2["notes"])
    # pricing sanity
    assert abs(m.pgt(0, 0, 15.5) - 0.5) < 1e-9
    a, b = m.novig(-110, -110); assert abs(a - 0.5) < 1e-9
    assert abs(m.dec(-110) - 1.909090909) < 1e-6 and m.dec(150) == 2.5
    # card properties
    assert card, "empty card"
    evs = [r["ev_blend"] for r in card]; assert evs == sorted(evs, reverse=True)
    for r in card:
        assert r["ev_blend"] > 0 and 1 <= r["stars"] <= 5 and not m.contradicts(r)
        assert abs(r["p_blend"] - (0.3 * r["p_model"] + 0.7 * r["p_market"])) < 1e-9
    markets = {r["market"].split()[0] for r in card} | {r["market"] for r in card}
    print("markets on card:", sorted({r["market"] for r in card}))
    rows = list(csv.DictReader(open(os.path.join(out, "cfb_card.csv"))))
    assert len(rows) == len(card)
    md = open(os.path.join(out, "cfb_card.md")).read(); assert "Ranked card" in md and "Cross-check" in md
    # filter unit test
    assert m.contradicts({"direction": "under", "line": 50, "proj": 55})
    assert m.contradicts({"direction": "over", "line": 60, "proj": 55})
    assert not m.contradicts({"direction": "over", "line": 50, "proj": 55})
    # CSV dotted-column loader
    with open(os.path.join(out, "adv.csv"), "w") as f:
        f.write("team,offense.ppa,offense.havoc.total\nX,0.2,0.15\n")
    r = m.load(os.path.join(out, "adv.csv"))[0]; assert r["offense"]["havoc"]["total"] == 0.15
    # early-season prior: week 1 vs week 10 differs, week >=6 prior gone
    lm = m.league_means(m.load(os.path.join(HERE, "samples", "advanced.json")))
    adv = m.load(os.path.join(HERE, "samples", "advanced.json"))[0]
    assert m.regressed(adv, lm, "offense.ppa", 1, 0.1) != m.regressed(adv, lm, "offense.ppa", 10, 0.1)
    assert m.regressed(adv, lm, "offense.ppa", 6, 0.1) == m.regressed(adv, lm, "offense.ppa", 12, 0.1)
    print(f"PASS: {len(card)} plays, projections:",
          [(p['home'], round(p['pts_home'], 1), p['away'], round(p['pts_away'], 1)) for p in projs])
    print(md)

if __name__ == "__main__":
    main()
