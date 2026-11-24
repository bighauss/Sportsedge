"""Tests for engine/run_nfl.py (NFL owner guards). python -m unittest engine/test_run_nfl.py"""
import csv, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_nfl  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

COLS = ["sport", "home", "away", "home_proj", "away_proj", "player", "team", "proj",
        "market", "line", "price_a", "price_b"]


def board(rows):
    p = os.path.join(tempfile.mkdtemp(), "board.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})
    return p


def game(hp, ap, spread=-3.5, total=44.5, extra=()):
    base = dict(sport="NFL", home="HOM", away="AWY", home_proj=hp, away_proj=ap)
    return [dict(base, market="SPREAD", line=spread, price_a=-110, price_b=-110),
            dict(base, market="TOTAL", line=total, price_a=-110, price_b=-110),
            dict(base, market="ML", price_a=-180, price_b=150)] + [dict(base, **e) for e in extra]


def G(game, mk, ln, side=0, price=-110):
    return (game, mk, float(ln), side, price)


def gp(r, mk, ln, side=0, price=-110):
    return r["gaps"][G("AWY @ HOM", mk, ln, side, price)]


def row(**kw):
    o = dict(sport="NFL", game="G", player="", pick="HOM -3.5", bet_type="SPREAD|0|", model_p=0.55,
             market_p=0.5, ev=0.05, price=-110)
    o.update(kw)
    return o


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(tempfile.mkdtemp())
        cls.prod = run_nfl.build(board(game(30, 14, extra=[
            dict(market="1H_SPREAD", line=-2.5, price_a=-110, price_b=-110),
            dict(market="1Q_SPREAD", line=-0.5, price_a=-110, price_b=-110),
            dict(player="WR1", team="HOM", market="REC_YDS", line=59.5, price_a=200, proj=70),
        ])))                                         # production N_FIT (100k)

    def test_spread_gap_sign_and_hold(self):
        self.assertGreater(gp(self.prod, "SPREAD", -3.5), 6)
        self.assertLess(abs(gp(self.prod, "TOTAL", 44.5)), 6)
        out = self.prod["out"]
        self.assertTrue(all(o["held"] for o in out if o["bet_type"].startswith("SPREAD|")))
        self.assertFalse(any("pts off" in o["held"] for o in out if o["bet_type"].startswith("TOTAL|")))
        self.assertFalse(any("pts off" in o["held"] for o in out if o["bet_type"].startswith("ML|")))
        self.assertFalse(any(o["held"] for o in self.prod["card"]))

    def test_away_side_gap_negative(self):
        g = run_nfl.projection_gaps(run_nfl.load_nfl_lines(board(game(14, 30))))
        self.assertLess(g[G("AWY @ HOM", "SPREAD", -3.5)], -6)

    def test_only_moved_period_quote_changes(self):
        """Full-game board fixed; move only the 1Q spread. Only the 1Q gap/hold may change."""
        proj = (24, 20)                                   # close to the book: nothing held
        q = lambda ln: dict(market="1Q_SPREAD", line=ln, price_a=-110, price_b=-110)
        base = run_nfl.build(board(game(*proj, spread=-3.5, total=44.5, extra=[q(-0.5)])))
        moved = run_nfl.build(board(game(*proj, spread=-3.5, total=44.5, extra=[q(-9.5)])))
        for mk, ln in (("SPREAD", -3.5), ("TOTAL", 44.5)):
            self.assertAlmostEqual(gp(base, mk, ln), gp(moved, mk, ln), 6)
        g0, g1 = gp(base, "1Q_SPREAD", -0.5), gp(moved, "1Q_SPREAD", -9.5)
        self.assertLess(abs(g0), 6)
        self.assertLess(g1, -6)                           # book says home -9.5 in 1Q, model ~-1
        hq = lambda r: [o["held"] for o in r["out"] if o["bet_type"].startswith("1Q_SPREAD|")]
        self.assertFalse(any("pts off" in h for h in hq(base)))
        self.assertTrue(all("1Q projection" in h for h in hq(moved)))
        full = lambda r: [o["held"] for o in r["out"] if o["bet_type"].split("|")[0] in ("SPREAD", "TOTAL")]
        self.assertEqual(full(base), full(moved))

    def test_boundary(self):
        g = {G("G", "SPREAD", -3.5, 0): 6.0, G("G", "SPREAD", -3.5, 1): 6.0, G("G", "TOTAL", 44.5, 1): -6.0,
             G("G", "1H_SPREAD", -2.5, 1): 6.01}
        sp = lambda **k: row(pick=k.pop("pick"), **k)
        self.assertEqual(run_nfl.guard(sp(pick="HOM -3.5"), g)["held"], "")
        self.assertEqual(run_nfl.guard(sp(pick="AWY +3.5", bet_type="SPREAD|1|"), g)["held"], "")
        self.assertEqual(run_nfl.guard(sp(pick="Under 44.5", bet_type="TOTAL|1|"), g)["held"], "")
        self.assertIn("1H projection", run_nfl.guard(sp(pick="1H AWY +2.5", bet_type="1H_SPREAD|1|"), g)["held"])
        self.assertEqual(run_nfl.guard(sp(pick="2H HOM -2.5", bet_type="2H_SPREAD|0|"), g)["held"], "")

    def test_duplicate_quotes_keyed_by_price(self):
        r = run_nfl.projection_gaps(run_nfl.load_nfl_lines(board(game(24, 20, extra=[
            dict(market="SPREAD", line=-3.5, price_a=-130, price_b=110)]))))
        self.assertNotAlmostEqual(r[G("AWY @ HOM", "SPREAD", -3.5, 0, -110)],
                                  r[G("AWY @ HOM", "SPREAD", -3.5, 0, -130)], 2)

    def test_conflicting_identical_quote_is_held(self):
        g = {G("G", "SPREAD", -3.5, 0): None}
        self.assertIn("duplicate quote", run_nfl.guard(row(), g)["held"])

    def test_break_even_push_not_assumed_zero(self):
        pay = v5.payout(-110)
        mp = 1 / (1 + pay)                              # exactly break-even conditional
        g = run_nfl.guard(row(model_p=mp, market_p=0.6, ev=0.0), {})
        self.assertIn("push share", g["held"])
        self.assertEqual(g["ev"], 0.0)

    def test_every_row_zero_stake_and_create_only(self):
        self.assertTrue(all(o["approved_stake_u"] == 0 for o in self.prod["out"]))
        p = board(game(24, 20))
        cwd = os.getcwd()
        os.chdir(os.path.dirname(p))
        try:
            run_nfl.main(p)
            run_nfl.main(p)
            self.assertEqual(len([f for f in os.listdir(".") if f.startswith("picks_nfl_")]), 2)
        finally:
            os.chdir(cwd)

    def test_selected_for_card_matches_card_exactly(self):
        out, card = self.prod["out"], self.prod["card"]
        sel = {o["row_id"] for o in out if o["selected_for_card"]}
        self.assertEqual(sel, {c["row_id"] for c in card})
        self.assertEqual(len(sel), len(card))
        excluded = {o["row_id"] for o in self.prod["held"]} | {o["row_id"] for o in self.prod["model_only"]} \
            | {o["row_id"] for o in self.prod["doubted"]}
        self.assertFalse(sel & excluded)
        self.assertTrue(all(not o["selected_for_card"] for o in out if o["held"] or o["status"] == "MODEL_ONLY"))
        self.assertTrue(all(o["approved_stake_u"] == 0 for o in out))
        self.assertTrue(all(isinstance(o["selected_for_card"], bool) for o in out))
        # best_per_group returns COPIES; the card objects must carry the same
        # marker and identity as the exported originals, not stale False.
        self.assertTrue(all(c["selected_for_card"] is True for c in card))
        for c in card:
            original = out[c["row_id"]]
            self.assertEqual((c["quote_id"], c["selected_for_card"]),
                             (original["quote_id"], original["selected_for_card"]))
        self.assertTrue(all(not c["selected_for_card"] for c in
                            self.prod["doubted"] + self.prod["model_only"]))

    def test_exported_csv_and_returned_card_same_selected_ids(self):
        """Compare real main() CSV export with returned build() rows and card."""
        from unittest.mock import patch
        import contextlib
        import io
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with patch.object(run_nfl, "build", return_value=self.prod):
                    with contextlib.redirect_stdout(io.StringIO()):
                        run_nfl.main("unused-board.csv")
                exports = [x for x in os.listdir(tmp) if x.startswith("picks_nfl_")]
                self.assertEqual(len(exports), 1)
                with open(exports[0], newline="") as f:
                    saved = list(csv.DictReader(f))
            finally:
                os.chdir(cwd)
        marked_csv = {(int(r["row_id"]), r["quote_id"]) for r in saved
                      if r["selected_for_card"] == "True"}
        marked_out = {(r["row_id"], r["quote_id"]) for r in self.prod["out"]
                      if r["selected_for_card"]}
        marked_card = {(c["row_id"], c["quote_id"]) for c in self.prod["card"]}
        self.assertEqual(marked_csv, marked_out)
        self.assertEqual(marked_csv, marked_card)
        self.assertTrue(all(c["selected_for_card"] is True for c in self.prod["card"]))
        self.assertTrue(all(float(r["approved_stake_u"]) == 0 for r in saved))
        self.assertEqual(len({r["quote_id"] for r in saved}), len(saved))

    def test_duplicate_looking_quotes_distinct_ids(self):
        r = run_nfl.build(board(game(24, 20, extra=[dict(market="SPREAD", line=-3.5, price_a=-110, price_b=-110)])))
        sp = [o for o in r["out"] if o["bet_type"] == "SPREAD|0|"]
        self.assertEqual(len(sp), 2)
        self.assertEqual(sp[0]["pick"], sp[1]["pick"])
        self.assertNotEqual(sp[0]["quote_id"], sp[1]["quote_id"])
        self.assertEqual(len({o["quote_id"] for o in r["out"]}), len(r["out"]))
        self.assertLessEqual(sum(o["selected_for_card"] for o in sp), 1)

    def test_marker_does_not_change_selection(self):
        p = board(game(30, 14, extra=[dict(market="1Q_SPREAD", line=-0.5, price_a=-110, price_b=-110)]))
        a = run_nfl.build(p)
        strip = lambda rows: [{k: v for k, v in o.items() if k not in ("row_id", "quote_id", "selected_for_card")}
                              for o in rows]
        # recompute card from the guarded rows without the marker and compare
        ok = [o for o in strip(a["out"]) if not o["held"] and o["ev"] >= v5.EV_FLOOR and o["status"] != "MODEL_ONLY"]
        card2 = [o for o in run_nfl.best_per_group(ok) if o["ev"] < v5.DOUBT_EV]
        self.assertEqual([(o["pick"], o["price"], o["ev"], o["blend_p"]) for o in card2],
                         [(o["pick"], o["price"], o["ev"], o["blend_p"]) for o in a["card"]])

    def test_blend_math_and_push(self):
        w, l = 0.55, 0.40
        ev = w * v5.payout(-110) - l
        g = run_nfl.guard(row(model_p=w / (w + l), ev=ev), {})
        p = 0.3 * (w / (w + l)) + 0.7 * 0.5
        self.assertAlmostEqual(g["blend_p"], p, 9)
        self.assertAlmostEqual(g["ev"], 0.95 * (p * v5.payout(-110) - (1 - p)), 9)
        self.assertAlmostEqual(g["model_ev"], ev, 12)

    def test_push_share_identity_on_real_v5_rows(self):
        """BLEND_W = 1.0 must reproduce v5's push-aware EV exactly on every BLENDED row,
        including integer lines (3, 7, 44) where the simulator produces pushes."""
        old = run_nfl.BLEND_W
        run_nfl.BLEND_W = 1.0
        try:
            r = run_nfl.build(board(game(24, 20, spread=-3, total=44, extra=[
                dict(market="SPREAD", line=-7, price_a=105, price_b=-125),
                dict(market="1H_SPREAD", line=-3, price_a=-110, price_b=-110),
            ])))
        finally:
            run_nfl.BLEND_W = old
        blended = [o for o in r["out"] if o["status"] == "BLENDED" and "push share" not in o["held"]]
        self.assertTrue(blended)
        pushy = 0
        for o in blended:
            self.assertAlmostEqual(o["ev"], o["model_ev"], 9, msg=o["pick"])
            self.assertAlmostEqual(o["blend_p"], o["model_p"], 12)
            den = o["model_p"] * v5.payout(o["price"]) - (1 - o["model_p"])
            if abs(den) > 1e-6 and o["model_ev"] / den < 0.999:
                pushy += 1
        self.assertGreater(pushy, 0, "fixture must include rows with a nonzero push share")
        self.assertTrue(all(o["approved_stake_u"] == 0 for o in r["out"]))

    def test_model_only_never_on_blended_card(self):
        g = run_nfl.guard(row(player="X", bet_type="REC_YDS|0|", model_p=0.4, market_p=None,
                              ev=0.2, price=200), {})
        self.assertEqual((g["status"], g["blend_p"], g["ev"]), ("MODEL_ONLY", 0.4, 0.2))
        self.assertFalse(any(o["status"] == "MODEL_ONLY" for o in self.prod["card"]))
        self.assertTrue(any("WR1" in o["pick"] for o in self.prod["model_only"]))

    def test_prob_guard_separate_from_points(self):
        self.assertIn("prob guard", run_nfl.guard(row(model_p=0.80, market_p=0.50), {})["held"])
        self.assertIn("prob guard", run_nfl.guard(row(model_p=0.30, market_p=0.50), {})["held"])
        self.assertIn("prob guard", run_nfl.guard(row(bet_type="ML|0|", model_p=0.10, market_p=0.06), {})["held"])
        self.assertEqual(run_nfl.guard(row(model_p=0.60, market_p=0.50), {})["held"], "")

    def test_extreme_disagreement_not_hidden_by_blend(self):
        r = run_nfl.build(board(game(38, 10)))
        sp = [o for o in r["out"] if o["bet_type"].startswith("SPREAD|")]
        self.assertTrue(sp and all(o["held"] for o in sp))
        self.assertFalse(any(o["bet_type"].startswith("SPREAD|") for o in r["card"]))

    def test_every_held_row_listed(self):
        self.assertEqual(len(self.prod["held"]), sum(1 for o in self.prod["out"] if o["held"]))

    def test_props_never_point_held(self):
        g = run_nfl.guard(row(player="X", pick="X Over 59.5 Rec Yds", bet_type="REC_YDS|0|"), {})
        self.assertEqual(g["held"], "")

    def test_n_fit_restored_and_production_value(self):
        self.assertEqual(run_nfl.N_FIT, 100000)
        self.assertEqual(v5.N_FIT, 20000)

    def test_non_nfl_untouched(self):
        g = run_nfl.guard(row(sport="CBB", model_p=0.7, ev=0.3, pick="HOM -3.5"), {G("G", "SPREAD", -3.5): 20})
        self.assertEqual((g["ev"], g["held"]), (0.3, ""))


if __name__ == "__main__":
    unittest.main()
