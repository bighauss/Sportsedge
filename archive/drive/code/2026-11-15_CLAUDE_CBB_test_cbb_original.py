import os, sys, tempfile, socket
socket.socket = None  # network OFF
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sportsedge_cbb_model as m
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
out = tempfile.mkdtemp()
r = m.run_card({k: os.path.join(d, k + ".csv") for k in ("teams","players","games","injuries","odds","props")}, out)
for gid,(g,p) in r["projections"].items():
    assert 120 < p["total"] < 175 and abs(p["margin"]) < 30, p
    print(gid, g["away"], "@", g["home"], f"{p['home_pts']:.1f}-{p['away_pts']:.1f} poss {p['poss']:.1f}", p["notes"])
evs = [x["blend_ev"] for x in r["rows"]]; assert evs == sorted(evs, reverse=True) and all(e > 0 for e in evs)
assert all(1 <= x["stars"] <= 5 for x in r["rows"])
assert not any("Braden Huff" in x["bet"] for x in r["rows"]), "out player prop leaked"
for x in r["rows"]:
    if x["proj"] is not None:
        assert not m.contradicts(x["side"], x["line"], x["proj"]), x
assert abs(m.novig(-110,-110)-0.5) < 1e-9 and abs(m.am_to_dec(150)-2.5) < 1e-9
assert abs(m.model_prob({"margin":0,"total":140,"home_pts":70,"away_pts":70,"poss":67.5},"ml","home",0)-0.5)<1e-9
assert os.path.getsize(os.path.join(out,"cbb_card.csv")) > 0
print(open(os.path.join(out,"cbb_card.md")).read())
print("ALL TESTS PASSED")
