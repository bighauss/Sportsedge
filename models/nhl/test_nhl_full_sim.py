import statistics as st
import unittest

import nhl_full_sim as S

SK = [dict(name="Sniper", team="home", shot_share=0.14, goal_share=0.18, assist_share=0.10),
      dict(name="D-man", team="away", shot_share=0.08, goal_share=0.05, assist_share=0.12)]


class NhlFullSim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = S.simulate(3.3, 3.0, 31.0, 29.0, SK, n=20000, seed=9)

    def test_scale_and_ot_rate(self):
        H, A = self.s["home"], self.s["away"]
        self.assertAlmostEqual(st.fmean(H) + st.fmean(A), 6.3 + 0.35, delta=0.4)
        ot = sum(o or s for o, s in zip(self.s["ot"], self.s["so"])) / len(H)
        self.assertTrue(0.15 < ot < 0.28, ot)

    def test_ml_two_way_and_three_way(self):
        w, p, _ = S.price(self.s, "ML", "home"); w2, _, _ = S.price(self.s, "ML", "away")
        self.assertEqual(p, 0); self.assertAlmostEqual(w + w2, 1)
        h3 = S.price(self.s, "ML3", "home")[0]; a3 = S.price(self.s, "ML3", "away")[0]; d3 = S.price(self.s, "ML3", "draw")[0]
        self.assertAlmostEqual(h3 + a3 + d3, 1)
        self.assertGreater(d3, 0.15)

    def test_margin_shape_three_exceeds_two_goal(self):
        m = [abs(h - a) for h, a in zip(self.s["home"], self.s["away"])]
        self.assertGreater(m.count(1), m.count(2))

    def test_period_markets(self):
        w, t, l = S.price(self.s, "P1_ML2", "home")
        self.assertGreater(t, 0.2); self.assertAlmostEqual(w + t + l, 1)
        self.assertAlmostEqual(S.price(self.s, "P1_TOTAL", "over", 1.5)[0] + S.price(self.s, "P1_TOTAL", "under", 1.5)[0], 1)

    def test_puck_line_and_total_integer_push(self):
        self.assertGreater(S.price(self.s, "TOTAL", "over", 6)[1], 0.05)
        self.assertEqual(S.price(self.s, "PL", "home", -1.5)[1], 0)

    def test_skater_props_from_same_draws(self):
        sn = self.s["skaters"]["Sniper"]
        self.assertTrue(all(g <= h for g, h in zip(sn["goals"], self.s["home"])))
        self.assertEqual(sn["points"][:40], [a + b for a, b in zip(sn["goals"][:40], sn["assists"][:40])])
        self.assertGreater(st.correlation(sn["sog"], self.s["home"]) if st.pstdev(sn["sog"]) else 1, 0.0)
        w, p, l = S.price(self.s, "PROP_SOG", "over:Sniper", 3.5)
        self.assertAlmostEqual(w + p + l, 1)

    def test_deterministic(self):
        a = S.simulate(3, 3, n=200, seed=1); b = S.simulate(3, 3, n=200, seed=1)
        self.assertEqual(a["home"], b["home"]); self.assertEqual(a["scenario_sha256"], b["scenario_sha256"])


if __name__ == "__main__":
    unittest.main()
