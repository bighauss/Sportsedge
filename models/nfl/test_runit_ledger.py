"""Synthetic tests for runit_ledger. All quotes below are invented fixtures."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import runit_ledger as L  # noqa: E402

ABBR = {"Alphas": "AAA", "Bravos": "BBB", "Cats": "CCC", "Dogs": "DDD"}
GAME = dict(away="AAA", home="BBB", spread=-3.5, sp_a=-110, sp_h=-110, total=44.5,
            o=-110, u=-110, ml_a=150, ml_h=-170, h1_spread=-1.5, h1_a=-110, h1_h=-110,
            h1_total=22.5, h1_o=-110, h1_u=-110, h1_ml_a=130, h1_ml_h=-150)
PROJ = {"AAA@BBB": (24.0, 25.0)}   # model total 49 vs market 44.5 -> scales props up


def prop(player, line, odds, file="8.03.30", game=("AAA Alphas", "BBB Bravos")):
    return dict(file=file, game=list(game), player=player, line=line, odds=odds)


PROPS = [
    prop("Qual QB", 240, -105),                      # mean scaled up -> qualifies
    prop("Neg QB", 240, -400),                       # heavy fav: blended EV <= 0
    prop("Over QB", 400, 300),                       # mean far below line -> filtered
    prop("Qual QB", 240, -105),                      # exact duplicate
    dict(file="8.03.30", game=["AAA Alphas", "BBB Bravos"], player="NoOdds", line=200, odds=None),
    prop("Ghost", 50, -110, game=("CCC Cats", "DDD Dogs")),   # game not on slate
    prop("Weird", 1, -110, file="9.99.99"),          # unsupported market
]


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.s = L.build_ledger([GAME], PROPS, PROJ, ABBR)

    def find(self, sel_prefix):
        return [r for r in self.rows if r["selection"].startswith(sel_prefix)]

    def test_denominator_reconciles(self):
        self.assertEqual(self.s["attempted_rows"], 12 + len(PROPS))
        self.assertEqual(len(self.rows), 12 + len(PROPS))
        self.assertEqual(sum(self.s["status_counts"].values()), len(self.rows))

    def test_every_input_appears(self):
        for p in PROPS:
            self.assertTrue(self.find(f"{p['player']} "), p["player"])

    def test_qualifying(self):
        q = [r for r in self.find("Qual QB") if r["status"] == "on_card"]
        self.assertEqual(len(q), 1)
        self.assertTrue(q[0]["qualifies"])
        self.assertGreater(q[0]["blended_ev"], 0)

    def test_negative_blended_ev_retained(self):
        (r,) = self.find("Neg QB")
        self.assertFalse(r["qualifies"])
        self.assertLessEqual(r["blended_ev"], 0)
        self.assertIn(r["status"], ("negative_ev", "nonpositive_blended_ev", "below_2pct"))

    def test_above_projection_retained_with_reason(self):
        (r,) = self.find("Over QB")
        self.assertEqual(r["status"], "filtered_contradicts_projection")
        self.assertIn("below line", r["reject_reason"])
        self.assertIsInstance(r["model_p"], float)      # full precision kept

    def test_duplicate_rejected_not_dropped(self):
        dup = [r for r in self.find("Qual QB") if r["reject_reason"] == "duplicate_offer"]
        self.assertEqual(len(dup), 1)

    def test_missing_and_unknown_inputs(self):
        reasons = {r["reject_reason"] for r in self.rows if r["status"] == "rejected_input"}
        self.assertIn("missing_input:odds", reasons)
        self.assertIn("game_not_on_slate", reasons)
        self.assertIn("unsupported_market:9.99.99", reasons)

    def test_contradicting_totals_retained(self):
        under = [r for r in self.rows if r["selection"] == "Under 44.5"]
        self.assertEqual(under[0]["status"], "filtered_contradicts_projection")

    def test_qualifies_and_on_image_are_separate(self):
        for r in self.rows:
            if r["on_image"]:
                self.assertTrue(r["qualifies"])
        self.assertLessEqual(self.s["on_image"], self.s["qualifies"])

    def test_image_prop_cap(self):
        props = [prop(f"P{i}", 200, 100) for i in range(6)]
        rows, s = L.build_ledger([GAME], props, PROJ, ABBR)
        shown = [r for r in rows if r["on_image"] and r["kind"] == "prop"]
        self.assertLessEqual(len(shown), L.IMAGE_MAX_PROPS_PER_GAME)

    def test_missing_game_field(self):
        bad = dict(GAME, away="CCC", home="DDD", total=None)
        rows, s = L.build_ledger([GAME, bad], [], dict(PROJ, **{"CCC@DDD": (20, 20)}), ABBR)
        self.assertEqual(len(rows), 13)
        self.assertEqual(rows[-1]["reject_reason"], "missing_input:total")


if __name__ == "__main__":
    unittest.main()
