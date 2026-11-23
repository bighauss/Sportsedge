"""Tests for engine/run_nfl.py (NFL owner guards). python -m unittest engine/test_run_nfl.py"""
import csv, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_nfl  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

COLS = ["sport", "home", "away", "home_proj", "away_proj", "player", "team", "proj",
        "market", "line", "price_a", "price_b"]


def board(rows):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "board.csv")
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


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_nfl.N_FIT = 20000          # speed; production uses 100k
        os.chdir(tempfile.mkdtemp())

    def gaps(self, rows):
        return run_nfl.projection_gaps(run_nfl.load_nfl_lines(board(rows)))

    def test_spread_gap_sign_and_hold(self):
        r = run_nfl.build(board(game(30, 14)))       # proj home -16 vs book ~-3.5
        sg, tg = r["gaps"]["AWY @ HOM"]
        self.assertGreater(sg, 6)
        self.assertLess(abs(tg), 6)
        spreads = [o for o in r["out"] if o["bet_type"].startswith("SPREAD|")]
        self.assertTrue(spreads and all(o["held"] for o in spreads))
        totals = [o for o in r["out"] if o["bet_type"].startswith("TOTAL|")]
        self.assertTrue(totals and not any(o["held"] for o in totals))
        self.assertFalse(any(o["held"] for o in r["out"] if o["bet_type"].startswith("ML|")))
        self.assertFalse(any(o["held"] for o in r["card"]))

    def test_away_side_gap_negative(self):
        sg, _ = self.gaps(game(14, 30))[ "AWY @ HOM"]
        self.assertLess(sg, -6)

    def test_boundary(self):
        gp = {"G": (6.0, -6.0)}
        for mk in ("SPREAD", "TOTAL"):
            o = dict(sport="NFL", game="G", player="", bet_type=f"{mk}|0|", model_p=0.6,
                     market_p=0.5, ev=0.1, price=-110)
            self.assertEqual(run_nfl.guard(o, gp)["held"], "")          # exactly 6 is not held
        o = dict(sport="NFL", game="G", player="", bet_type="1H_SPREAD|0|", model_p=0.6,
                 market_p=0.5, ev=0.1, price=-110)
        self.assertTrue(run_nfl.guard(o, {"G": (6.01, 0)})["held"])      # periods held too

    def test_blend_math_and_push(self):
        # model w=0.55 l=0.40 push=0.05 at -110; market 0.5
        w, l = 0.55, 0.40
        ev = w * v5.payout(-110) - l
        o = dict(sport="NFL", game="G", player="", bet_type="SPREAD|0|", model_p=w / (w + l),
                 market_p=0.5, ev=ev, price=-110)
        g = run_nfl.guard(o, {})
        p = 0.3 * (w / (w + l)) + 0.7 * 0.5
        self.assertAlmostEqual(g["blend_p"], p, 9)
        self.assertAlmostEqual(g["ev"], 0.95 * (p * v5.payout(-110) - (1 - p)), 9)
        self.assertAlmostEqual(g["model_ev"], ev, 12)

    def test_one_sided_not_blended(self):
        o = dict(sport="NFL", game="G", player="X", bet_type="REC_YDS|0|", model_p=0.4,
                 market_p=None, ev=0.2, price=200)
        g = run_nfl.guard(o, {})
        self.assertEqual(g["blend_p"], 0.4)
        self.assertEqual(g["ev"], 0.2)

    def test_props_never_held(self):
        o = dict(sport="NFL", game="G", player="X", bet_type="REC_YDS|0|", model_p=0.6,
                 market_p=0.5, ev=0.1, price=-110)
        self.assertEqual(run_nfl.guard(o, {"G": (20, 20)})["held"], "")

    def test_extreme_disagreement_stays_visible(self):
        r = run_nfl.build(board(game(38, 10)))
        self.assertTrue(r["held"])
        self.assertTrue(all("pts off book spread" in o["held"] for o in r["held"]
                            if o["bet_type"].startswith("SPREAD|")))

    def test_non_nfl_untouched(self):
        o = dict(sport="CBB", game="G", player="", bet_type="SPREAD|0|", model_p=0.7,
                 market_p=0.5, ev=0.3, price=-110)
        g = run_nfl.guard(dict(o), {"G": (20, 20)})
        self.assertEqual((g["ev"], g["held"]), (0.3, ""))


if __name__ == "__main__":
    unittest.main()
