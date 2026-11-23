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
        for m in ("1H_ML", "Q1_ML", "Q4_ML"):
            wh, ph, _ = S.price(self.s, m, "home")
            wa, pa, _ = S.price(self.s, m, "away")
            self.assertGreater(ph, 0)
            self.assertAlmostEqual(wh + wa + ph, 1)
            self.assertEqual(ph, pa)

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
