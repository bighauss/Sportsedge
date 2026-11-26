"""Regression: capture exact v5 outcome mass and attach W/P/L without touching frozen v5."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl_capture as cap_mod  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402


def row(w, l, price, side, market="TOTAL"):
    a, b = (w, l) if side == 0 else (l, w)
    return dict(model_p=v5.cond(a, b), ev=a * v5.payout(price) - b, price=price,
                bet_type="%s|%d|" % (market, side))


class Capture(unittest.TestCase):
    def test_wl_push_captured_from_same_array(self):
        d = np.array([1, 0, -1, 0, 2, -3, 0, 5])
        with cap_mod.capturing() as cap:
            w, l = v5.wl(d)
        self.assertEqual((w, l), (3 / 8, 2 / 8))
        self.assertEqual(cap.items[(w, l)], {(3 / 8, "simulator_counts")})

    def test_originals_restored_even_on_error(self):
        orig = (v5.wl, v5.stat_probs, v5.td_probs)
        with self.assertRaises(RuntimeError):
            with cap_mod.capturing():
                raise RuntimeError("boom")
        self.assertEqual((v5.wl, v5.stat_probs, v5.td_probs), orig)

    def test_attach_both_sides_exact_push(self):
        d = np.array([1, 0, -1, 0, 2, -3, 0, 5])
        with cap_mod.capturing() as cap:
            w, l = v5.wl(d)
        rows = cap_mod.attach([row(w, l, -110, 0), row(w, l, 105, 1)], cap)
        for r, (pw, pl) in zip(rows, ((3 / 8, 2 / 8), (2 / 8, 3 / 8))):
            self.assertEqual(r["wpl_status"], "CAPTURED")
            self.assertEqual((r["p_win"], r["p_loss"], r["p_push"]), (pw, pl, 3 / 8))
            self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0)

    def test_unmatched_row_is_unavailable_not_guessed(self):
        with cap_mod.capturing() as cap:
            v5.wl(np.array([1, -1, 0]))
        r = row(0.123, 0.456, -110, 0)
        cap_mod.attach([r], cap)
        self.assertIsNone(r["p_push"])
        self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_conflicting_push_for_same_win_loss_is_ambiguous(self):
        with cap_mod.capturing() as cap:
            v5.wl(np.array([1, -1, 0, 0]))
            cap.add(0.25, 0.25, 0.4, "simulator_counts")
        w, l = 0.25, 0.25
        r = row(w, l, -110, 0)
        cap_mod.attach([r], cap)
        self.assertIsNone(r["p_push"])

    def test_invalid_row_fields_fail_closed(self):
        with cap_mod.capturing() as cap:
            v5.wl(np.array([1, -1, 0]))
        for r in (dict(model_p=0.5, ev=0.0, price=True, bet_type="TOTAL|0|"), dict(model_p=0.5, ev=0.0, price=-110),
                  dict(model_p=0.5, ev=0.0, price=-110, bet_type="TOTAL|2|")):
            cap_mod.attach([r], cap)
            self.assertIsNone(r["p_win"])

    def test_td_and_stat_paths_labelled_separately(self):
        with cap_mod.capturing() as cap:
            tw, tl = v5.td_probs(dict(htd=np.array([1, 2, 0]), atd=np.array([1, 1, 1])), "ATD", 0.3, True)
            sw, sl = v5.stat_probs(("c", 1.0), 5.0, 4.5, 1)
        self.assertEqual({m[1] for m in cap.items[(tw, tl)]}, {"td_closed_form"})
        self.assertEqual({m[1] for m in cap.items[(sw, sl)]}, {"analytic_distribution"})
        r = row(sw, sl, 110, 0, "PASS_TDS")
        cap_mod.attach([r], cap)
        self.assertEqual(r["wpl_source"], "analytic_distribution")
        self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0)

    def test_install_is_idempotent_and_wraps_run(self):
        saved = v5.run
        calls = []
        v5.run = lambda path: calls.append(path) or []
        try:
            cap_mod.install()
            first = v5.run
            cap_mod.install()
            self.assertIs(v5.run, first)
            self.assertEqual(v5.run("board.csv"), [])
            self.assertEqual(calls, ["board.csv"])
        finally:
            v5.run = saved


if __name__ == "__main__":
    unittest.main()
