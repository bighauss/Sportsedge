"""Regression: explicit win/push/loss (direct simulator counts + guarded EV diagnostic)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl  # noqa: E402


def ev_of(mp, price, s):
    pay = price / 100.0 if price > 0 else 100.0 / -price
    return s * (mp * pay - (1 - mp))


def sim():
    return dict(h=np.array([27, 24, 20, 23, 30]), a=np.array([20, 24, 23, 20, 27]))


class DirectSimulator(unittest.TestCase):
    def test_spread_counts_and_sides_mirror(self):
        a = nfl_wpl.direct_wpl(sim(), "NFL", "SPREAD", -3, 0)
        b = nfl_wpl.direct_wpl(sim(), "NFL", "SPREAD", -3, 1)
        self.assertEqual((a["p_win"], a["p_push"], a["p_loss"]), (0.2, 0.4, 0.4))
        self.assertEqual((b["p_win"], b["p_push"], b["p_loss"]), (0.4, 0.4, 0.2))
        self.assertEqual(a["wpl_status"], "SIMULATED")
        self.assertEqual(a["n_sims"], 5)

    def test_total_push_mass(self):
        o = nfl_wpl.direct_wpl(sim(), "NFL", "TOTAL", 47, 0)
        u = nfl_wpl.direct_wpl(sim(), "NFL", "TOTAL", 47, 1)
        self.assertEqual((o["p_win"], o["p_push"], o["p_loss"]), (0.4, 0.2, 0.4))
        self.assertEqual(o["p_push"], u["p_push"])
        self.assertEqual(o["p_win"], u["p_loss"])

    def test_half_point_line_has_no_push(self):
        self.assertEqual(nfl_wpl.direct_wpl(sim(), "NFL", "SPREAD", -3.5, 0)["p_push"], 0.0)

    def test_fail_closed(self):
        for kw in (dict(market="BOGUS", line=1, side=0), dict(market="TOTAL", line=float("nan"), side=0),
                   dict(market="TOTAL", line="x", side=0), dict(market="TOTAL", line=47, side=2),
                   dict(market="TOTAL", line=47, side=True)):
            with self.subTest(kw=kw):
                r = nfl_wpl.direct_wpl(sim(), "NFL", **kw)
                self.assertIsNone(r["p_win"])
                self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_nonfinite_outcomes_rejected(self):
        S = dict(h=np.array([27.0, float("nan")]), a=np.array([20.0, 21.0]))
        self.assertIsNone(nfl_wpl.direct_wpl(S, "NFL", "TOTAL", 47, 0)["p_win"])


class OddsValidation(unittest.TestCase):
    def test_invalid_odds_rejected(self):
        for bad in (None, 0, 50, -50, 99, -99, float("nan"), float("inf"), "abc", True, [], ""):
            with self.subTest(bad=bad):
                self.assertIsNone(nfl_wpl.valid_american(bad))
                r = nfl_wpl.wpl(0.55, bad, 0.05)
                self.assertIsNone(r["p_win"])
                self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_valid_odds_accepted(self):
        for ok in (-110, 100, -100, 105, "+150", 2500):
            self.assertIsNotNone(nfl_wpl.valid_american(ok))


class EvDiagnostic(unittest.TestCase):
    def test_round_trip_and_sum_to_one(self):
        for mp in (0.2, 0.45, 0.6, 0.8):
            for price in (-110, 105, 250, -300):
                for s in (1.0, 0.93, 0.85):
                    r = nfl_wpl.wpl(mp, price, ev_of(mp, price, s))
                    if r["p_win"] is None:
                        continue
                    self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=9)
                    self.assertAlmostEqual(r["p_push"], 1 - s, places=6)

    def test_nan_and_missing_ev_fail_closed(self):
        for ev in (float("nan"), float("inf"), None, "x", 5.0):
            self.assertIsNone(nfl_wpl.wpl(0.55, -110, ev)["p_win"])

    def test_invalid_model_p(self):
        for mp in (None, float("nan"), -0.1, 1.2, "x"):
            self.assertIsNone(nfl_wpl.wpl(mp, -110, 0.05)["p_win"])

    def test_break_even_unavailable(self):
        mp = 1 / (1 + 100.0 / 110.0)
        self.assertIsNone(nfl_wpl.wpl(mp, -110, 0.0)["p_push"])

    def test_annotate_never_falls_back_to_blended_ev(self):
        o = nfl_wpl.annotate(dict(model_p=0.55, price=-110, ev=0.05))
        self.assertIsNone(o["p_win"])
        self.assertIn("model_ev absent", o["wpl_status"])
        o2 = nfl_wpl.annotate(dict(model_p=0.55, price=-110, ev=-0.5, model_ev=ev_of(0.55, -110, 0.9)))
        self.assertAlmostEqual(o2["p_push"], 0.1, places=6)


if __name__ == "__main__":
    unittest.main()
