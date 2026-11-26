"""Regression: order-independent, verified binding of v5 outcome mass to priced rows; hold when unavailable."""
import csv
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl_capture as cm  # noqa: E402
import run_nfl  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402


def row(w, l, price, side, market="TOTAL"):
    a, b = (w, l) if side == 0 else (l, w)
    return dict(model_p=v5.cond(a, b), ev=a * v5.payout(price) - b, price=price,
                bet_type="%s|%d|" % (market, side), sport="NFL")


def tiny_board():
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write("sport,home,away,market,line,price_a,price_b\nNFL,A,B,TOTAL,44,-110,-110\n")
    return p


D = np.array([1, 0, -1, 0, 2, -3, 0, 5])
E = np.array([1, 1, 0, -1, -1, -1, 0, 2])


class Capture(unittest.TestCase):
    def test_binding_is_independent_of_row_order(self):
        with cm.capturing() as calls:
            wd, ld = v5.wl(D)
            we, le = v5.wl(E)
        self.assertEqual(calls[0]["counts"], (3, 3, 2, 8))
        rows = [row(wd, ld, -110, 0), row(wd, ld, 105, 1), row(we, le, -110, 0), row(we, le, 105, 1)]
        expect = [(3 / 8, 3 / 8, 2 / 8), (2 / 8, 3 / 8, 3 / 8), (3 / 8, 2 / 8, 3 / 8), (3 / 8, 2 / 8, 3 / 8)]
        for order in (list(range(4)), [3, 2, 1, 0], [2, 0, 3, 1]):
            rs = [dict(rows[i]) for i in order]
            cm.attach(rs, calls)
            for i, r in zip(order, rs):
                self.assertEqual(r["wpl_status"], "CAPTURED", (order, i))
                self.assertEqual((r["p_win"], r["p_push"], r["p_loss"]), expect[i])
                self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=12)
                self.assertGreaterEqual(min(r["p_win"], r["p_push"], r["p_loss"]), 0.0)

    def test_identical_calls_share_identical_mass(self):
        with cm.capturing() as calls:
            w1, l1 = v5.wl(D)
            w2, l2 = v5.wl(D)
        r = row(w1, l1, -110, 0)
        cm.attach([r], calls)
        self.assertEqual((r["wpl_status"], r["wpl_n_calls"], r["p_push"]), ("CAPTURED", 2, 3 / 8))

    def test_fitting_calls_inside_anchor_are_excluded(self):
        saved = v5.anchor
        v5.anchor = lambda *a, **k: v5.wl(np.array([1, -1]))
        try:
            with cm.capturing() as calls:
                v5.anchor()
                v5.wl(D)
        finally:
            v5.anchor = saved
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["counts"], (3, 3, 2, 8))

    def test_nan_outcomes_give_unavailable_not_a_probability(self):
        with cm.capturing() as calls:
            w, l = v5.wl(np.array([1.0, float("nan"), -1.0]))
        r = row(w, l, -110, 0)
        cm.attach([r], calls)
        self.assertIsNone(r["p_push"])
        self.assertTrue(r["wpl_status"].startswith("UNAVAILABLE"))

    def test_unmatched_row_is_unavailable(self):
        with cm.capturing() as calls:
            v5.wl(D)
        r = row(0.123, 0.456, -110, 0)
        cm.attach([r], calls)
        self.assertIsNone(r["p_win"])

    def test_conflicting_push_for_same_win_loss_is_unavailable(self):
        with cm.capturing() as calls:
            w, l = v5.wl(np.array([1, -1, 0, 0]))
        calls.append(dict(kind="wl", src="x", w=w, l=l, push=0.4, counts=None))
        r = row(w, l, -110, 0)
        cm.attach([r], calls)
        self.assertIsNone(r["p_push"])

    def test_invalid_row_fields_fail_closed(self):
        with cm.capturing() as calls:
            v5.wl(D)
        for r in (dict(model_p=0.5, ev=0.0, price=True, bet_type="TOTAL|0|"), dict(model_p=0.5, ev=0.0, price=-110),
                  dict(model_p=0.5, ev=0.0, price=-110, bet_type="TOTAL|2|")):
            cm.attach([r], calls)
            self.assertIsNone(r["p_win"])

    def test_count_prop_push_mass_integer_and_half_lines(self):
        with cm.capturing() as calls:
            iw, il = v5.stat_probs(("c", 1.0), 5.0, 5.0, 1)
            hw, hl = v5.stat_probs(("c", 1.0), 5.0, 4.5, 1)
        ri, rh = row(iw, il, 110, 0, "PASS_TDS"), row(hw, hl, 110, 0, "PASS_TDS")
        cm.attach([ri, rh], calls)
        self.assertEqual((ri["wpl_status"], rh["wpl_status"]), ("CAPTURED", "CAPTURED"))
        self.assertGreater(ri["p_push"], 0.1)
        self.assertEqual(rh["p_push"], 0.0)
        self.assertEqual(ri["wpl_source"], "prop_exact_distribution")

    def test_yardage_prop_push_uses_same_draws(self):
        with cm.capturing() as calls:
            w, l = v5.stat_probs(("y", 0.28), 250.0, 250.0, 3)
        r = row(w, l, -110, 0, "PASS_YDS")
        cm.attach([r], calls)
        self.assertEqual(r["wpl_status"], "CAPTURED")
        self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=12)

    def test_td_path_separate_source(self):
        with cm.capturing() as calls:
            w, l = v5.td_probs(dict(htd=np.array([1, 2, 0]), atd=np.array([1, 1, 1])), "ATD", 0.3, True)
        r = row(w, l, 150, 0, "ATD")
        cm.attach([r], calls)
        self.assertEqual((r["wpl_source"], r["p_push"]), ("td_closed_form", 0.0))


class Guard(unittest.TestCase):
    def base(self, **kw):
        pay = 100.0 / 110.0
        o = dict(sport="NFL", price=-110, status="BLENDED", blend_p=0.5, p_win=0.45, p_push=0.1, p_loss=0.45,
                 wpl_status="CAPTURED", held="", ev=0.0, model_ev=0.45 * pay - 0.45)
        o.update(kw)
        return o

    def test_unavailable_rows_are_held(self):
        g = cm.priced_guard(lambda o, gaps: dict(o), self.base(wpl_status="UNAVAILABLE: no matching simulator call"), {})
        self.assertIn("simulator W/P/L unavailable", g["held"])

    def test_captured_push_drives_blended_ev_and_clears_breakeven_hold(self):
        o = self.base(held="push share not recoverable at break-even (hold)")
        g = cm.priced_guard(lambda o_, gaps: dict(o_), o, {})
        pay = 100.0 / 110.0
        self.assertEqual(g["held"], "")
        self.assertAlmostEqual(g["ev"], 0.9 * (0.5 * pay - 0.5), places=12)

    def test_disagreement_with_v5_ev_is_held(self):
        g = cm.priced_guard(lambda o, gaps: dict(o), self.base(model_ev=0.2), {})
        self.assertIn("disagrees with v5 EV", g["held"])

    def test_non_nfl_untouched(self):
        g = cm.priced_guard(lambda o, gaps: dict(o), dict(sport="CBB", held=""), {})
        self.assertEqual(g["held"], "")


class Board(unittest.TestCase):
    def write(self, rows):
        p = os.path.join(tempfile.mkdtemp(), "b.csv")
        with open(p, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sport", "home", "away", "market", "line", "price_a", "price_b"])
            w.writerows(rows)
        return p

    def test_invalid_odds_rejected_before_v5_truncation(self):
        for bad in ("110.5", "50", "0", "-99", "abc"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    cm.validate_board(self.write([["NFL", "A", "B", "TOTAL", "44", bad, "-110"]]))

    def test_valid_and_non_nfl_rows_pass(self):
        cm.validate_board(self.write([["NFL", "A", "B", "TOTAL", "44", "-110", "+100"],
                                      ["CBB", "A", "B", "TOTAL", "44", "50", "x"]]))


class Install(unittest.TestCase):
    def test_restores_all_names_even_on_error(self):
        before = (v5.run, run_nfl.guard, v5.wl, v5.stat_probs, v5.td_probs, v5.anchor)
        with self.assertRaises(RuntimeError):
            with cm.installed():
                self.assertIsNot(v5.run, before[0])
                self.assertIsNot(run_nfl.guard, before[1])
                raise RuntimeError("boom")
        self.assertEqual((v5.run, run_nfl.guard, v5.wl, v5.stat_probs, v5.td_probs, v5.anchor), before)

    def test_v5_failure_inside_capture_restores_v5_functions(self):
        before = (v5.wl, v5.stat_probs, v5.td_probs, v5.anchor)
        orig_run = v5.run
        v5.run = lambda path: (_ for _ in ()).throw(RuntimeError("v5 failed"))
        try:
            with cm.installed():
                with self.assertRaises(RuntimeError):
                    v5.run(tiny_board())
        finally:
            v5.run = orig_run
        self.assertEqual((v5.wl, v5.stat_probs, v5.td_probs, v5.anchor), before)

    def test_invalid_odds_stop_the_run_before_v5(self):
        p = os.path.join(tempfile.mkdtemp(), "b.csv")
        with open(p, "w", newline="") as f:
            f.write("sport,home,away,market,line,price_a,price_b\nNFL,A,B,TOTAL,44,110.5,-110\n")
        with cm.installed():
            with self.assertRaises(ValueError):
                v5.run(p)


if __name__ == "__main__":
    unittest.main()
