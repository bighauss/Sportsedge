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


def period_sim():
    H = np.array([[7, 7, 3, 10], [3, 7, 7, 7]])
    A = np.array([[0, 7, 7, 3], [7, 3, 7, 7]])
    return dict(h=H.sum(1), a=A.sum(1), H=H, A=A)


class DirectSimulator(unittest.TestCase):
    def test_spread_counts_and_sides_mirror(self):
        a = nfl_wpl.direct_wpl(sim(), "NFL", "SPREAD", -3, 0)
        b = nfl_wpl.direct_wpl(sim(), "NFL", "SPREAD", -3, 1)
        self.assertEqual((a["p_win"], a["p_push"], a["p_loss"]), (0.2, 0.4, 0.4))
        self.assertEqual((b["p_win"], b["p_push"], b["p_loss"]), (0.4, 0.4, 0.2))
        self.assertEqual((a["wpl_status"], a["n_sims"]), ("SIMULATED", 5))

    def test_total_push_mass(self):
        o = nfl_wpl.direct_wpl(sim(), "NFL", "TOTAL", 47, 0)
        u = nfl_wpl.direct_wpl(sim(), "NFL", "TOTAL", 47, 1)
        self.assertEqual((o["p_win"], o["p_push"], o["p_loss"]), (0.4, 0.2, 0.4))
        self.assertEqual((o["p_push"], o["p_win"]), (u["p_push"], u["p_loss"]))

    def test_half_point_line_has_no_push(self):
        self.assertEqual(nfl_wpl.direct_wpl(sim(), "NFL", "SPREAD", -3.5, 0)["p_push"], 0.0)

    def test_moneyline_needs_no_line(self):
        r = nfl_wpl.direct_wpl(sim(), "NFL", "ML", None, 0)
        self.assertEqual(r["wpl_status"], "SIMULATED")
        self.assertEqual((r["p_win"], r["p_push"], r["p_loss"]), (0.6, 0.2, 0.2))

    def test_line_required_for_spread_and_total(self):
        for m in ("SPREAD", "TOTAL", "HOME_TT"):
            self.assertIsNone(nfl_wpl.direct_wpl(sim(), "NFL", m, None, 0)["p_win"])

    def test_period_market_uses_period_matrix(self):
        r = nfl_wpl.direct_wpl(period_sim(), "NFL", "1H_SPREAD", -7, 0)
        self.assertEqual(r["wpl_status"], "SIMULATED")
        self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0)
        S = dict(h=np.array([1, 2]), a=np.array([1, 2]))
        self.assertIsNone(nfl_wpl.direct_wpl(S, "NFL", "1H_SPREAD", -7, 0)["p_win"])

    def test_fail_closed_inputs(self):
        cases = [dict(market="BOGUS", line=1, side=0), dict(market="TOTAL", line=float("nan"), side=0),
                 dict(market="TOTAL", line="x", side=0), dict(market="TOTAL", line=True, side=0),
                 dict(market="TOTAL", line=47, side=2), dict(market="TOTAL", line=47, side=True),
                 dict(market="TOTAL", line=47, side=np.bool_(True)), dict(market="TOTAL", line=47, side=0.0),
                 dict(market="BTTS", line=0, side=0), dict(market=None, line=47, side=0)]
        for kw in cases:
            with self.subTest(kw=kw):
                r = nfl_wpl.direct_wpl(sim(), "NFL", **kw)
                self.assertIsNone(r["p_win"])
                self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_non_nfl_sport_rejected(self):
        self.assertIsNone(nfl_wpl.direct_wpl(sim(), "CFB", "TOTAL", 47, 0)["p_win"])

    def test_malformed_simulation_objects(self):
        bad = [None, [], {}, dict(h=np.array([27, 24, 20]), a=np.array([20])),
               dict(h=np.array([[1, 2]]), a=np.array([[1, 2]])), dict(h=np.array([]), a=np.array([])),
               dict(h=np.array([27.0, float("nan")]), a=np.array([20.0, 21.0])),
               dict(h=np.array(["a"]), a=np.array(["b"]))]
        for S in bad:
            with self.subTest(S=repr(S)[:40]):
                r = nfl_wpl.direct_wpl(S, "NFL", "TOTAL", 47, 0)
                self.assertIsNone(r["p_win"])
                self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_count_conservation(self):
        rng = np.random.default_rng(1)
        S = dict(h=rng.integers(0, 45, 5000), a=rng.integers(0, 45, 5000))
        for line in (-3, -3.5, 0, 7, 44, 44.5):
            for side in (0, 1):
                r = nfl_wpl.direct_wpl(S, "NFL", "SPREAD", line, side)
                self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=12)
                self.assertEqual(round(r["p_win"] * 5000) + round(r["p_push"] * 5000) + round(r["p_loss"] * 5000), 5000)


class OddsValidation(unittest.TestCase):
    def test_invalid_odds_rejected(self):
        for bad in (None, 0, 50, -50, 99, -99, 110.5, -110.5, float("nan"), float("inf"), "abc", "+150",
                    True, np.bool_(True), [], ""):
            with self.subTest(bad=bad):
                self.assertIsNone(nfl_wpl.valid_american(bad))
                r = nfl_wpl.wpl(0.55, bad, 0.05)
                self.assertIsNone(r["p_win"])
                self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_valid_odds_accepted(self):
        for ok in (-110, 100, -100, 105, 110.0, 2500, np.int64(-120)):
            self.assertIsNotNone(nfl_wpl.valid_american(ok))


class EvDiagnostic(unittest.TestCase):
    def test_round_trip_and_sum_to_one(self):
        derived = 0
        for mp in (0.2, 0.45, 0.6, 0.8):
            for price in (-110, 105, 250, -300):
                for s in (1.0, 0.93, 0.85):
                    r = nfl_wpl.wpl(mp, price, ev_of(mp, price, s))
                    self.assertEqual(r["wpl_status"], "DERIVED_FROM_EV", (mp, price, s))
                    derived += 1
                    self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=9)
                    self.assertAlmostEqual(r["p_push"], 1 - s, places=6)
        self.assertEqual(derived, 48)

    def test_nan_and_missing_ev_fail_closed(self):
        for ev in (float("nan"), float("inf"), None, "x", True, 5.0):
            self.assertIsNone(nfl_wpl.wpl(0.55, -110, ev)["p_win"])

    def test_invalid_model_p(self):
        for mp in (None, float("nan"), -0.1, 1.2, "x", True, np.bool_(True), False):
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
