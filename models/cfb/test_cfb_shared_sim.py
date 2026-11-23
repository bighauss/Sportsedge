import statistics as st
import unittest

import cfb_shared_sim as S

PL = [dict(name="QB", team="home", stat="pass_yds", mean=260.0),
      dict(name="RB", team="away", stat="rush_yds", mean=85.0),
      dict(name="WR", team="home", stat="receptions", mean=6.0)]


class CfbSim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = S.simulate(31.0, 24.0, PL, n=20000, seed=5)

    def test_means_and_spread_scale(self):
        H, A = self.s["home"], self.s["away"]
        self.assertAlmostEqual(st.fmean(H) - st.fmean(A), 7.0, delta=1.0)
        self.assertAlmostEqual(st.fmean(H) + st.fmean(A), 55.0 + 1.0, delta=2.5)
        self.assertTrue(12 < st.pstdev([h - a for h, a in zip(H, A)]) < 20)

    def test_key_numbers_exist(self):
        m = [abs(h - a) for h, a in zip(self.s["home"], self.s["away"])]
        f = {k: m.count(k) / len(m) for k in (3, 4, 7)}
        self.assertGreater(f[3], f[4])
        self.assertGreater(f[7], f[4])

    def test_full_game_no_tie_period_ties_refunded(self):
        self.assertEqual(S.price(self.s, "ML", "home")[1], 0)
        w, p, _ = S.price(self.s, "1H_ML", "home")
        w2, _, _ = S.price(self.s, "1H_ML", "away")
        self.assertGreater(p, 0)
        self.assertAlmostEqual(w + w2 + p, 1)

    def test_spread_push_on_integer(self):
        self.assertGreater(S.price(self.s, "SPREAD", "home", -7)[1], 0.02)
        self.assertEqual(S.price(self.s, "SPREAD", "home", -6.5)[1], 0)

    def test_quarters_sum_to_regulation(self):
        for i in range(300):
            if self.s["ot"][i] == 0:
                self.assertEqual(sum(q[i] for q in self.s["hq"]), self.s["home"][i])

    def test_props_from_same_draws_correlate(self):
        qb = self.s["players"][("QB", "pass_yds")]
        self.assertAlmostEqual(st.fmean(qb), 260, delta=12)
        self.assertGreater(st.correlation(qb, self.s["home"]), 0.1)
        w, p, l = S.price(self.s, "PROP", "over:WR:receptions", 5.5)
        self.assertAlmostEqual(w + p + l, 1)

    def test_deterministic(self):
        a = S.simulate(28, 21, n=300, seed=2); b = S.simulate(28, 21, n=300, seed=2)
        self.assertEqual(a["home"], b["home"]); self.assertEqual(a["scenario_sha256"], b["scenario_sha256"])


if __name__ == "__main__":
    unittest.main()
