"""Regression: selection-identity binding of v5 outcome mass to priced rows; hold when unavailable."""
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

TD = {"ATD": "Anytime TD", "TD2": "2+ TDs", "FTD": "First TD"}
_SAVED = {}


def setUpModule():
    _SAVED["sites"] = cm.CALLSITE_MODULES
    cm.CALLSITE_MODULES = {v5.__name__, __name__}


def tearDownModule():
    cm.CALLSITE_MODULES = _SAVED["sites"]


def board_row(market="TOTAL", line=44.0, player="", price_a=-110.0, price_b=105.0, sgp=""):
    return dict(sport="NFL", home="DET", away="CHI", market=market, line=line, player=player, sgp=sgp,
                price_a=price_a, price_b=price_b)


def priced(r, fn, *args):
    """Call fn from a frame whose local `r` is the board row, exactly as v5.run prices a row."""
    return fn(*args)


def v5_labels(r):
    if r["market"] in TD:
        return ("%s %s" % (r["player"], TD[r["market"]]), "%s No %s" % (r["player"], TD[r["market"]]))
    if r["player"]:
        name = r["market"].replace("_", " ").title()
        return ("%s Over %g %s" % (r["player"], r["line"], name), "%s Under %g %s" % (r["player"], r["line"], name))
    return v5.game_labels("NFL", r)


def out_row(r, side, w, l):
    a, b = (w, l) if side == 0 else (l, w)
    price = int(r["price_a"] if side == 0 else r["price_b"])
    return dict(sport="NFL", game="%s @ %s" % (r["away"], r["home"]), bet_type="%s|%d|%s" % (r["market"], side, r["sgp"]),
                player=r["player"], price=price, pick=v5_labels(r)[side], model_p=v5.cond(a, b),
                ev=a * v5.payout(price) - b)


def tiny_board():
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write("sport,home,away,market,line,price_a,price_b\nNFL,A,B,TOTAL,44,-110,-110\n")
    return p


D = np.array([1, 0, -1, 0, 2, -3, 0, 5])
E = np.array([1, 1, 0, -1, -1, -1, 0, 2])


class Binding(unittest.TestCase):
    def test_identical_masses_bind_by_selection_not_by_number(self):
        r1, r2 = board_row(line=44.0), board_row(line=45.0)
        with cm.capturing() as calls:
            w1, l1 = priced(r1, v5.wl, D)
            w2, l2 = priced(r2, v5.wl, D)
        rows = [out_row(r2, 1, w2, l2), out_row(r1, 0, w1, l1), out_row(r2, 0, w2, l2), out_row(r1, 1, w1, l1)]
        cm.attach(rows, calls)
        for r in rows:
            self.assertEqual((r["wpl_status"], r["wpl_binding"]), ("CAPTURED", "selection_identity"))
            self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=12)
        self.assertEqual((rows[1]["p_win"], rows[1]["p_push"], rows[1]["p_loss"]), (3 / 8, 3 / 8, 2 / 8))

    def test_row_order_is_irrelevant(self):
        r1, r2 = board_row(line=44.0), board_row(line=46.0)
        with cm.capturing() as calls:
            w1, l1 = priced(r1, v5.wl, D)
            w2, l2 = priced(r2, v5.wl, E)
        base = [out_row(r1, 0, w1, l1), out_row(r2, 0, w2, l2)]
        for order in ([0, 1], [1, 0]):
            rs = [dict(base[i]) for i in order]
            cm.attach(rs, calls)
            got = {r["pick"]: (r["p_win"], r["p_push"], r["p_loss"]) for r in rs}
            self.assertEqual(got["Over 44"], (3 / 8, 3 / 8, 2 / 8))
            self.assertEqual(got["Over 46"], (3 / 8, 2 / 8, 3 / 8))

    def test_prop_thresholds_with_identical_price_and_mass_bind_by_label(self):
        lo = board_row("PASS_TDS", 1.5, "J Goff", -110.0, -110.0)
        hi = board_row("PASS_TDS", 2.5, "J Goff", -110.0, -110.0)
        with cm.capturing() as calls:
            wa, la = priced(lo, v5.wl, D)
            wb, lb = priced(hi, v5.wl, D)
        rows = [out_row(hi, 0, wb, lb), out_row(lo, 0, wa, la), out_row(hi, 1, wb, lb), out_row(lo, 1, wa, la)]
        self.assertEqual(rows[0]["pick"], "J Goff Over 2.5 Pass Tds")
        cm.attach(rows, calls)
        self.assertEqual([r["wpl_status"] for r in rows], ["CAPTURED"] * 4)
        ghost = out_row(board_row("PASS_TDS", 3.5, "J Goff", -110.0, -110.0), 0, wa, la)
        cm.attach([ghost], calls)
        self.assertIn("no selection-bound", ghost["wpl_status"])

    def test_touchdown_markets_bind_by_v5_td_labels(self):
        for stat, name in TD.items():
            with self.subTest(stat=stat):
                br = board_row(stat, 0.5, "J Goff", 150.0, -190.0)
                with cm.capturing() as calls:
                    w, l = priced(br, v5.wl, D)
                rows = [out_row(br, 0, w, l), out_row(br, 1, w, l)]
                self.assertEqual((rows[0]["pick"], rows[1]["pick"]), ("J Goff " + name, "J Goff No " + name))
                cm.attach(rows, calls)
                self.assertEqual([r["wpl_status"] for r in rows], ["CAPTURED", "CAPTURED"])
                wrong = out_row(br, 0, w, l)
                wrong["pick"] = "J Goff Over 0.5 " + stat.title()
                cm.attach([wrong], calls)
                self.assertIsNone(wrong["p_win"])

    def test_same_threshold_with_two_masses_is_held(self):
        pr = board_row("PASS_TDS", 1.5, "J Goff", -110.0, -110.0)
        with cm.capturing() as calls:
            w, l = priced(pr, v5.wl, D)
            priced(pr, v5.wl, E)
        r = out_row(pr, 0, w, l)
        cm.attach([r], calls)
        self.assertIn("different outcome masses", r["wpl_status"])

    def test_wrong_label_for_a_priced_threshold_is_not_bound(self):
        pr = board_row("PASS_TDS", 1.5, "J Goff", -110.0, -110.0)
        with cm.capturing() as calls:
            w, l = priced(pr, v5.wl, D)
        r = out_row(pr, 0, w, l)
        r["pick"] = "J Goff Over 2.5 Pass Tds"
        cm.attach([r], calls)
        self.assertIsNone(r["p_win"])

    def test_lines_that_g_formatting_cannot_distinguish_are_held(self):
        a, b = board_row("REC_YDS", 200.50001, "A Wr"), board_row("REC_YDS", 200.50002, "A Wr")
        with cm.capturing() as calls:
            priced(a, v5.wl, D)
            priced(b, v5.wl, E)
        r = out_row(a, 0, 3 / 8, 2 / 8)
        cm.attach([r], calls)
        self.assertIsNone(r["p_win"])

    def test_row_for_a_selection_that_was_never_priced_is_unavailable(self):
        priced_row, ghost = board_row(line=44.0), board_row(line=47.0)
        with cm.capturing() as calls:
            w, l = priced(priced_row, v5.wl, D)
        r = out_row(ghost, 0, w, l)
        cm.attach([r], calls)
        self.assertIn("no selection-bound", r["wpl_status"])

    def test_missing_identity_is_unavailable_even_if_numbers_match(self):
        with cm.capturing() as calls:
            w, l = v5.wl(D)
        r = out_row(board_row(), 0, w, l)
        cm.attach([r], calls)
        self.assertIsNone(r["p_win"])

    def test_numeric_mismatch_on_bound_identity_is_unavailable(self):
        br = board_row()
        with cm.capturing() as calls:
            w, l = priced(br, v5.wl, D)
        r = out_row(br, 0, w, l)
        r["ev"] += 1e-6
        cm.attach([r], calls)
        self.assertIn("does not reproduce", r["wpl_status"])

    def test_duplicate_identical_pricing_of_one_identity_is_fine(self):
        br = board_row()
        with cm.capturing() as calls:
            w, l = priced(br, v5.wl, D)
            priced(br, v5.wl, D)
        r = out_row(br, 0, w, l)
        cm.attach([r], calls)
        self.assertEqual(r["wpl_status"], "CAPTURED")

    def test_fitting_calls_inside_anchor_are_excluded_and_anchor_is_restored(self):
        saved, br = v5.anchor, board_row()
        v5.anchor = lambda *a, **k: priced(br, v5.wl, np.array([1, -1]))
        try:
            with cm.capturing() as calls:
                v5.anchor()
                priced(br, v5.wl, D)
        finally:
            v5.anchor = saved
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["counts"], (3, 3, 2, 8))
        self.assertIs(v5.anchor, saved)

    def test_fitting_lambda_outside_anchor_gets_no_identity(self):
        fit = board_row("REC_YDS", 59.5, "A Wr")
        probe = lambda x: v5.stat_probs(("c", 1.0), x, fit["line"], 1)  # noqa: E731  same shape as v5's bisect
        with cm.capturing() as calls:
            probe(5.0)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]["ident"])
        r = out_row(fit, 0, calls[0]["w"], calls[0]["l"])
        cm.attach([r], calls)
        self.assertIsNone(r["p_win"])

    def test_nan_outcomes_give_unavailable_not_a_probability(self):
        br = board_row()
        with cm.capturing() as calls:
            w, l = priced(br, v5.wl, np.array([1.0, float("nan"), -1.0]))
        r = out_row(br, 0, w, l)
        cm.attach([r], calls)
        self.assertIsNone(r["p_push"])

    def test_invalid_row_fields_fail_closed(self):
        with cm.capturing() as calls:
            priced(board_row(), v5.wl, D)
        for r in (dict(model_p=0.5, ev=0.0, price=True, bet_type="TOTAL|0|"), dict(model_p=0.5, ev=0.0, price=-110),
                  dict(model_p=0.5, ev=0.0, price=-110, bet_type="TOTAL|2|")):
            cm.attach([r], calls)
            self.assertIsNone(r["p_win"])

    def test_count_prop_push_mass_integer_and_half_lines(self):
        ri_b = board_row("PASS_TDS", 5.0, "J Goff", 110.0, -130.0)
        rh_b = board_row("PASS_TDS", 4.5, "J Goff", 110.0, -130.0)
        with cm.capturing() as calls:
            iw, il = priced(ri_b, v5.stat_probs, ("c", 1.0), 5.0, 5.0, 1)
            hw, hl = priced(rh_b, v5.stat_probs, ("c", 1.0), 5.0, 4.5, 1)
        ri, rh = out_row(ri_b, 0, iw, il), out_row(rh_b, 0, hw, hl)
        cm.attach([ri, rh], calls)
        self.assertEqual((ri["wpl_status"], rh["wpl_status"]), ("CAPTURED", "CAPTURED"))
        self.assertGreater(ri["p_push"], 0.1)
        self.assertEqual(rh["p_push"], 0.0)
        self.assertEqual(ri["wpl_source"], "prop_exact_distribution")

    def test_yardage_props_push_uses_same_draws_and_binds_by_label(self):
        for stat in ("PASS_YDS", "REC_YDS", "RUSH_YDS"):
            with self.subTest(stat=stat):
                br = board_row(stat, 59.5, "A Player", -110.0, -110.0)
                with cm.capturing() as calls:
                    w, l = priced(br, v5.stat_probs, ("y", 0.28), 70.0, 59.5, 3)
                r = out_row(br, 0, w, l)
                cm.attach([r], calls)
                self.assertEqual(r["wpl_status"], "CAPTURED")
                self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=12)

    def test_integer_yardage_line_has_positive_push(self):
        br = board_row("REC_YDS", 60.0, "A Player", -110.0, -110.0)
        with cm.capturing() as calls:
            w, l = priced(br, v5.stat_probs, ("y", 0.28), 60.0, 60.0, 3)
        r = out_row(br, 0, w, l)
        cm.attach([r], calls)
        self.assertEqual(r["wpl_status"], "CAPTURED")
        self.assertGreater(r["p_push"], 0.0)

    def test_td_closed_form_source(self):
        br = board_row("ATD", 0.5, "J Goff", 150.0, -190.0)
        with cm.capturing() as calls:
            w, l = priced(br, v5.td_probs, dict(htd=np.array([1, 2, 0]), atd=np.array([1, 1, 1])), "ATD", 0.3, True)
        r = out_row(br, 0, w, l)
        cm.attach([r], calls)
        self.assertEqual((r["wpl_source"], r["p_push"]), ("td_closed_form", 0.0))

class QuoteIdentity(unittest.TestCase):
    def raw(self, **kw):
        r = board_row()
        r.update(event_id="event1", kickoff_utc="2026-11-26T20:00:00Z",
                 captured_utc="2026-11-26T19:00:00Z", book="DK", source="DK")
        r.update(kw)
        return r

    def test_selection_stable_quote_changes_on_either_price_or_capture(self):
        a = self.raw()
        sid, qid, status = cm.raw_identity(a, 0)
        self.assertEqual(status, "SOURCE_FIELDS_PRESENT")
        for change in (dict(price_a=-115.0), dict(price_b=100.0),
                       dict(captured_utc="2026-11-26T19:01:00Z"), dict(book="OTHER")):
            with self.subTest(change=change):
                s, q, _ = cm.raw_identity(dict(a, **change), 0)
                self.assertEqual(s, sid)
                self.assertNotEqual(q, qid)
        for change in (dict(event_id="rematch"), dict(line=45.0)):
            self.assertNotEqual(cm.raw_identity(dict(a, **change), 0)[0], sid)
        self.assertNotEqual(cm.raw_identity(a, 1)[0], sid)

    def test_source_bound_ids_independent_of_output_order(self):
        a, b = self.raw(line=44.0), self.raw(line=45.0)
        with cm.capturing() as calls:
            w1, l1 = priced(a, v5.wl, D)
            w2, l2 = priced(b, v5.wl, E)
        rows = [out_row(a, 0, w1, l1), out_row(b, 0, w2, l2)]
        got = []
        for seq in (rows, list(reversed(rows))):
            rr = cm.attach([dict(x) for x in seq], calls)
            for x in rr:
                x["held"] = ""
            run_nfl.assign_quote_ids(rr)
            got.append({x["pick"]: (x["quote_id"], x["selection_id"]) for x in rr})
        self.assertEqual(got[0], got[1])
        self.assertEqual(len({q for q, _ in got[0].values()}), 2)

    def test_distinct_reciprocal_quotes_same_output_label_held(self):
        a = self.raw()
        b = self.raw(price_b=125.0)
        with cm.capturing() as calls:
            w, l = priced(a, v5.wl, D)
            priced(b, v5.wl, D)
        o = out_row(a, 0, w, l)
        cm.attach([o], calls)
        self.assertEqual(o["quote_identity_status"], "AMBIGUOUS")
        self.assertIsNone(o["raw_quote_id"])
        self.assertIn("distinct source quotes", o["wpl_status"])

    def test_identical_quote_copies_all_held_and_retained(self):
        a = self.raw()
        with cm.capturing() as calls:
            w, l = priced(a, v5.wl, D)
            priced(a, v5.wl, D)
        rows = cm.attach([out_row(a, 0, w, l), out_row(a, 0, w, l)], calls)
        for o in rows:
            o["held"] = ""
        run_nfl.assign_quote_ids(rows)
        self.assertEqual(rows[0]["quote_id"], rows[1]["quote_id"])
        self.assertNotEqual(rows[0]["row_id"], rows[1]["row_id"])
        self.assertTrue(all(o["quote_identity_status"] == "DUPLICATE" for o in rows))
        self.assertTrue(all("all copies held" in o["held"] for o in rows))
        self.assertTrue(all(not o["selected_for_card"] for o in rows))

    def test_missing_source_fields_and_player_id_are_not_authentication(self):
        self.assertEqual(cm.raw_identity(board_row(), 0)[2], "SOURCE_FIELDS_INCOMPLETE")
        a = self.raw(player="P", team="DET")
        self.assertEqual(cm.raw_identity(a, 0)[2], "SOURCE_FIELDS_INCOMPLETE")
        self.assertEqual(cm.raw_identity(dict(a, player_id="p1"), 0)[2], "SOURCE_FIELDS_PRESENT")



class Guard(unittest.TestCase):
    def base(self, **kw):
        pay = 100.0 / 110.0
        o = dict(sport="NFL", price=-110, status="BLENDED", blend_p=0.5, p_win=0.45, p_push=0.1, p_loss=0.45,
                 wpl_status="CAPTURED", held="", ev=0.0, model_ev=0.45 * pay - 0.45)
        o.update(kw)
        return o

    def test_unavailable_rows_are_held(self):
        g = cm.priced_guard(lambda o, gaps: dict(o), self.base(wpl_status="UNAVAILABLE: no selection-bound simulator call"), {})
        self.assertIn("simulator W/P/L unavailable", g["held"])

    def test_captured_push_drives_blended_ev_and_clears_breakeven_hold(self):
        o = self.base(held="push share not recoverable at break-even (hold)")
        g = cm.priced_guard(lambda o_, gaps: dict(o_), o, {})
        self.assertEqual(g["held"], "")
        self.assertAlmostEqual(g["ev"], 0.9 * (0.5 * 100 / 110 - 0.5), places=12)

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
