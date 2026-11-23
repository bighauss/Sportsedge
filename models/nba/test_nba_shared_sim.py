import statistics as st
import unittest

import nba_shared_sim as S

PLAYERS = [dict(name="Star", team="home", pts=27.0, reb=6.0, ast=7.0, fg3=3.0),
           dict(name="Big", team="away", pts=14.0, reb=11.0, ast=2.0, fg3=0.4)]


class SharedSim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = S.simulate(115.0, 110.0, PLAYERS, n=20000, seed=11)

    def test_means_and_sds_match_analytic_scale(self):
        H, A = self.s["home"], self.s["away"]
        self.assertAlmostEqual(st.fmean(H) - st.fmean(A), 5.0, delta=0.5)
        self.assertAlmostEqual(st.fmean(H) + st.fmean(A), 225.0, delta=1.5)
        self.assertTrue(10.5 < st.pstdev([h - a for h, a in zip(H, A)]) < 14.5)
        self.assertTrue(15.5 < st.pstdev([h + a for h, a in zip(H, A)]) < 20.5)

    def test_full_game_never_ties_ml_sums_to_one(self):
        w, p, l = S.price(self.s, "ML", "home")
        w2, _, _ = S.price(self.s, "ML", "away")
        self.assertEqual(p, 0)
        self.assertAlmostEqual(w + w2, 1)

    def test_period_ml_tie_refunded_and_consistent(self):
        for m in ("1H_ML", "Q1_ML"):
            wh, ph, _ = S.price(self.s, m, "home", tie_rule="push")
            wa, pa, _ = S.price(self.s, m, "away", tie_rule="push")
            self.assertGreater(ph, 0)
            self.assertAlmostEqual(wh + wa + ph, 1)
            self.assertEqual(ph, pa)
        wh, ph, _ = S.price(self.s, "Q4_ML", "home", tie_rule="push", ot_rule="exclude")
        self.assertGreater(ph, 0)

    def test_period_ml_tie_rule_required_and_three_way_lose(self):
        with self.assertRaises(ValueError):
            S.price(self.s, "1H_ML", "home")
        wp, pp, lp = S.price(self.s, "1H_ML", "home", tie_rule="push")
        wl, pl, ll = S.price(self.s, "1H_ML", "home", tie_rule="lose")
        self.assertEqual(wp, wl)
        self.assertEqual(pl, 0)
        self.assertAlmostEqual(ll, lp + pp)
        self.assertLess(S.ev(wl, pl, -110), S.ev(wp, pp, -110))

    def test_second_half_ot_rule_required_and_applied(self):
        for m in ("2H_TOTAL", "2H_ML", "Q4_SPREAD"):
            with self.assertRaises(ValueError):
                S.price(self.s, m, "over" if "TOTAL" in m else "home", line=110.5, tie_rule="push")
        ex = S.price(self.s, "2H_TOTAL", "over", 112.5, ot_rule="exclude")[0]
        inc = S.price(self.s, "2H_TOTAL", "over", 112.5, ot_rule="include")[0]
        self.assertGreater(inc, ex)  # OT only adds points
        w, p, l = S.price(self.s, "2H_ML", "home", tie_rule="push", ot_rule="include")
        self.assertAlmostEqual(w + p + l, 1)

    def test_invalid_selections_rejected(self):
        bad = [("ML", "Home", None), ("ML", "over", None), ("SPREAD", "draw", -3.5),
               ("TOTAL", "home", 220.5), ("TOTAL", "Over", 220.5), ("SPREAD", "home", None),
               ("PROP_PTS", "over:Nobody", 20.5), ("PROP_PTS", "yes:Star", 20.5),
               ("PROP_PTS", "Star", 20.5), ("PROP_BLK", "over:Star", 1.5), ("FOO", "home", None),
               ("PROP_PTS", "over:Star", None)]
        for m, sel, line in bad:
            with self.assertRaises(ValueError, msg=(m, sel)):
                S.price(self.s, m, sel, line)

    def test_threes_never_exceed_points(self):
        for name, p in self.s["players"].items():
            self.assertTrue(all(3 * t <= pt for t, pt in zip(p["fg3"], p["pts"])), name)
        self.assertAlmostEqual(st.fmean(self.s["players"]["Star"]["fg3"]), 3.0, delta=0.1)
        with self.assertRaises(ValueError):
            S.simulate(110, 105, [dict(name="X", team="home", pts=5, fg3=2)], n=10)
        with self.assertRaises(ValueError):
            S.simulate(110, 105, [dict(name="X", team="Home", pts=5, fg3=1)], n=10)

    def test_integer_spread_push_and_half_point_none(self):
        self.assertGreater(S.price(self.s, "SPREAD", "home", -5)[1], 0)
        self.assertEqual(S.price(self.s, "SPREAD", "home", -5.5)[1], 0)

    def test_quarters_sum_to_regulation_and_halves_consistent(self):
        reg = [sum(q[i] for q in self.s["hq"]) for i in range(100)]
        for i in range(100):
            if self.s["ot"][i] == 0:
                self.assertEqual(reg[i], self.s["home"][i])
        o1, _, _ = S.price(self.s, "1H_TOTAL", "over", 0.5)
        self.assertGreater(o1, 0.99)

    def test_props_from_same_draws_and_pra_is_sum(self):
        p = self.s["players"]["Star"]
        self.assertAlmostEqual(st.fmean(p["pts"]), 27.0, delta=0.6)
        self.assertEqual(p["pra"][:50], [a + b + c for a, b, c in zip(p["pts"][:50], p["reb"][:50], p["ast"][:50])])
        w, pu, l = S.price(self.s, "PROP_PRA", "over:Star", 39.5)
        self.assertAlmostEqual(w + pu + l, 1)
        self.assertEqual(pu, 0)

    def test_star_points_correlate_with_team_points(self):
        p = self.s["players"]["Star"]["pts"]
        self.assertGreater(st.correlation(p, self.s["home"]), 0.15)

    def test_deterministic_seed_and_hash(self):
        a = S.simulate(115, 110, PLAYERS, n=500, seed=3)
        b = S.simulate(115, 110, PLAYERS, n=500, seed=3)
        self.assertEqual(a["home"], b["home"])
        self.assertEqual(a["scenario_sha256"], b["scenario_sha256"])

    def test_ev_push_refund(self):
        self.assertAlmostEqual(S.ev(0.5, 0.05, -110), 0.004545, 5)


if __name__ == "__main__":
    unittest.main()
