"""Regression: explicit win/push/loss mass derived from v5 push-aware EV."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402


def ev_of(mp, price, s):
    return s * (mp * v5.payout(price) - (1 - mp))


class WinPushLoss(unittest.TestCase):
    def test_round_trip_and_sum_to_one(self):
        for mp in (0.2, 0.45, 0.6, 0.8):
            for price in (-110, 105, 250, -300):
                for s in (1.0, 0.93, 0.85):
                    if abs(mp * v5.payout(price) - (1 - mp)) < 1e-3:
                        continue
                    r = nfl_wpl.wpl(mp, price, ev_of(mp, price, s))
                    self.assertEqual(r["wpl_status"], "DERIVED")
                    self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=9)
                    self.assertAlmostEqual(r["p_push"], 1 - s, places=6)
                    self.assertAlmostEqual(r["p_win"], s * mp, places=6)

    def test_break_even_is_unavailable_not_guessed(self):
        mp = 1 / (1 + v5.payout(-110))
        r = nfl_wpl.wpl(mp, -110, 0.0)
        self.assertIsNone(r["p_push"])
        self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_invalid_inputs_fail_closed(self):
        self.assertIsNone(nfl_wpl.wpl(None, -110, 0.1)["p_win"])
        self.assertIsNone(nfl_wpl.wpl(1.2, -110, 0.1)["p_win"])
        self.assertIsNone(nfl_wpl.wpl(0.6, -110, 5.0)["p_win"])

    def test_annotate_uses_pre_blend_model_ev(self):
        o = dict(model_p=0.55, price=-110, model_ev=ev_of(0.55, -110, 0.9), ev=-0.5)
        nfl_wpl.annotate(o)
        self.assertAlmostEqual(o["p_push"], 0.1, places=6)


if __name__ == "__main__":
    unittest.main()
