"""Tests for engine/run_nfl.py (NFL owner guards). python -m unittest engine/test_run_nfl.py"""
import csv, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_nfl  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

COLS = ["sport", "home", "away", "home_proj", "away_proj", "player", "team", "proj",
        "market", "line", "price_a", "price_b"]


def board(rows):
    p = os.path.join(tempfile.mkdtemp(), "board.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})
    return p


def game(hp, ap, spread=-3.5, total=44.5, extra=()):
    base = dict(sport="NFL", home="HOM", away="AWY", home_proj=hp, away_proj=ap)
    return [dict(base, market="SPREAD", line=spread, price_a=-110, price_b=-110),
            dict(base, market="TOTAL", line=total, price_a=-110, price_b=-110),
            dict(base, market="ML", price_a=-180, price_b=150)] + [dict(base, **e) for e in extra]


def row(**kw):
    o = dict(sport="NFL", game="G", player="", pick="HOM -3.5", bet_type="SPREAD|0|", model_p=0.55,
             market_p=0.5, ev=0.05, price=-110)
    o.update(kw)
    return o


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(tempfile.mkdtemp())
        cls.prod = run_nfl.build(board(game(30, 14, extra=[
            dict(market="1H_SPREAD", line=-2.5, price_a=-110, price_b=-110),
            dict(market="1Q_SPREAD", line=-0.5, price_a=-110, price_b=-110),
            dict(player="WR1", team="HOM", market="REC_YDS", line=59.5, price_a=200, proj=70),
        ])))                                         # production N_FIT (100k)

    def test_spread_gap_sign_and_hold(self):
        g = self.prod["gaps"]
        self.assertGreater(g[("AWY @ HOM", "SPREAD", -3.5)], 6)
        self.assertLess(abs(g[("AWY @ HOM", "TOTAL", 44.5)]), 6)
        out = self.prod["out"]
        self.assertTrue(all(o["held"] for o in out if o["bet_type"].startswith("SPREAD|")))
        self.assertFalse(any("pts off" in o["held"] for o in out if o["bet_type"].startswith("TOTAL|")))
        self.assertFalse(any("pts off" in o["held"] for o in out if o["bet_type"].startswith("ML|")))
        self.assertFalse(any(o["held"] for o in self.prod["card"]))

    def test_away_side_gap_negative(self):
        g = run_nfl.projection_gaps(run_nfl.load_nfl_lines(board(game(14, 30))))
        self.assertLess(g[("AWY @ HOM", "SPREAD", -3.5)], -6)

    def test_only_moved_period_quote_changes(self):
        """Full-game board fixed; move only the 1Q spread. Only the 1Q gap/hold may change."""
        proj = (24, 20)                                   # close to the book: nothing held
        q = lambda ln: dict(market="1Q_SPREAD", line=ln, price_a=-110, price_b=-110)
        base = run_nfl.build(board(game(*proj, spread=-3.5, total=44.5, extra=[q(-0.5)])))
        moved = run_nfl.build(board(game(*proj, spread=-3.5, total=44.5, extra=[q(-9.5)])))
        k = ("AWY @ HOM", "SPREAD", -3.5), ("AWY @ HOM", "TOTAL", 44.5)
        for kk in k:
            self.assertAlmostEqual(base["gaps"][kk], moved["gaps"][kk], 6)
        g0, g1 = base["gaps"][("AWY @ HOM", "1Q_SPREAD", -0.5)], moved["gaps"][("AWY @ HOM", "1Q_SPREAD", -9.5)]
        self.assertLess(abs(g0), 6)
        self.assertLess(g1, -6)                           # book says home -9.5 in 1Q, model ~-1
        hq = lambda r: [o["held"] for o in r["out"] if o["bet_type"].startswith("1Q_SPREAD|")]
        self.assertFalse(any("pts off" in h for h in hq(base)))
        self.assertTrue(all("1Q projection" in h for h in hq(moved)))
        full = lambda r: [o["held"] for o in r["out"] if o["bet_type"].split("|")[0] in ("SPREAD", "TOTAL")]
        self.assertEqual(full(base), full(moved))

    def test_boundary(self):
        gp = {("G", "SPREAD", -3.5): 6.0, ("G", "TOTAL", 44.5): -6.0, ("G", "1H_SPREAD", -2.5): 6.01}
        sp = lambda **k: row(pick=k.pop("pick"), **k)
        self.assertEqual(run_nfl.guard(sp(pick="HOM -3.5"), gp)["held"], "")
        self.assertEqual(run_nfl.guard(sp(pick="AWY +3.5", bet_type="SPREAD|1|"), gp)["held"], "")
        self.assertEqual(run_nfl.guard(sp(pick="Under 44.5", bet_type="TOTAL|1|"), gp)["held"], "")
        self.assertIn("1H projection", run_nfl.guard(sp(pick="1H AWY +2.5", bet_type="1H_SPREAD|1|"), gp)["held"])
        self.assertEqual(run_nfl.guard(sp(pick="2H HOM -2.5", bet_type="2H_SPREAD|0|"), gp)["held"], "")

    def test_blend_math_and_push(self):
        w, l = 0.55, 0.40
        ev = w * v5.payout(-110) - l
        g = run_nfl.guard(row(model_p=w / (w + l), ev=ev), {})
        p = 0.3 * (w / (w + l)) + 0.7 * 0.5
        self.assertAlmostEqual(g["blend_p"], p, 9)
        self.assertAlmostEqual(g["ev"], 0.95 * (p * v5.payout(-110) - (1 - p)), 9)
        self.assertAlmostEqual(g["model_ev"], ev, 12)

    def test_model_only_never_on_blended_card(self):
        g = run_nfl.guard(row(player="X", bet_type="REC_YDS|0|", model_p=0.4, market_p=None,
                              ev=0.2, price=200), {})
        self.assertEqual((g["status"], g["blend_p"], g["ev"]), ("MODEL_ONLY", 0.4, 0.2))
        self.assertFalse(any(o["status"] == "MODEL_ONLY" for o in self.prod["card"]))
        self.assertTrue(any("WR1" in o["pick"] for o in self.prod["model_only"]))

    def test_prob_guard_separate_from_points(self):
        self.assertIn("prob guard", run_nfl.guard(row(model_p=0.80, market_p=0.50), {})["held"])
        self.assertIn("prob guard", run_nfl.guard(row(model_p=0.30, market_p=0.50), {})["held"])
        self.assertIn("prob guard", run_nfl.guard(row(bet_type="ML|0|", model_p=0.10, market_p=0.06), {})["held"])
        self.assertEqual(run_nfl.guard(row(model_p=0.60, market_p=0.50), {})["held"], "")

    def test_extreme_disagreement_not_hidden_by_blend(self):
        r = run_nfl.build(board(game(38, 10)))
        sp = [o for o in r["out"] if o["bet_type"].startswith("SPREAD|")]
        self.assertTrue(sp and all(o["held"] for o in sp))
        self.assertFalse(any(o["bet_type"].startswith("SPREAD|") for o in r["card"]))

    def test_every_held_row_listed(self):
        self.assertEqual(len(self.prod["held"]), sum(1 for o in self.prod["out"] if o["held"]))

    def test_props_never_point_held(self):
        g = run_nfl.guard(row(player="X", pick="X Over 59.5 Rec Yds", bet_type="REC_YDS|0|"), {})
        self.assertEqual(g["held"], "")

    def test_n_fit_restored_and_production_value(self):
        self.assertEqual(run_nfl.N_FIT, 100000)
        self.assertEqual(v5.N_FIT, 20000)

    def test_non_nfl_untouched(self):
        g = run_nfl.guard(row(sport="CBB", model_p=0.7, ev=0.3, pick="HOM -3.5"), {("G", "SPREAD", -3.5): 20})
        self.assertEqual((g["ev"], g["held"]), (0.3, ""))


if __name__ == "__main__":
    unittest.main()
