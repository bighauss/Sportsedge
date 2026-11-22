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



class MalformedInputTests(unittest.TestCase):
    """Bad offers become retained rejection rows; valid offers keep pricing."""

    BAD = [
        ("zero odds", prop("Zero", 200, 0), "invalid_odds:odds"),
        ("small odds", prop("Small", 200, 50), "invalid_odds:odds"),
        ("string odds", prop("Str", 200, "-110"), "invalid_odds:odds"),
        ("bool odds", prop("Bool", 200, True), "invalid_odds:odds"),
        ("nan odds", prop("NaN", 200, float("nan")), "invalid_odds:odds"),
        ("empty game", dict(file="8.03.30", game=[], player="E", line=200, odds=-110), "invalid_input:game"),
        ("one-team game", dict(file="8.03.30", game=["AAA Alphas"], player="O", line=200, odds=-110), "invalid_input:game"),
        ("non-list game", dict(file="8.03.30", game="AAA@BBB", player="S", line=200, odds=-110), "invalid_input:game"),
        ("unknown team", prop("U", 200, -110, game=("ZZZ Zebras", "BBB Bravos")), "unknown_team"),
        ("negative line", prop("Neg", -5, -110), "invalid_input:line"),
        ("inf line", prop("Inf", float("inf"), -110), "invalid_input:line"),
        ("fractional TD line", prop("Frac", 1.5, -110, file="8.03.53"), "invalid_input:line"),
        ("blank player", prop("  ", 200, -110), "invalid_input:player"),
        ("not a dict", ["junk"], "invalid_input:not_a_mapping"),
    ]

    def test_each_bad_prop_rejected_and_batch_survives(self):
        props = [prop("Good QB", 240, -105)] + [b[1] for b in self.BAD]
        rows, s = L.build_ledger([GAME], props, PROJ, ABBR)
        self.assertEqual(len(rows), 12 + len(props))
        good = [r for r in rows if r["selection"].startswith("Good QB")]
        self.assertEqual(len(good), 1)
        self.assertNotEqual(good[0]["status"], "rejected_input")
        by_index = {r.get("input_index"): r for r in rows if r["status"] == "rejected_input"}
        for i, (label, _, reason) in enumerate(self.BAD, start=1):
            self.assertIn(i, by_index, label)
            self.assertEqual(by_index[i]["reject_reason"], reason, label)

    def test_bad_game_quotes_rejected_others_priced(self):
        good2 = dict(GAME, away="CCC", home="DDD")
        bads = [dict(GAME, away="EEE", home="FFF", ml_h=0),
                dict(GAME, away="GGG", home="HHH", total="44.5"),
                dict(GAME, away="III", home="III"),
                "junk"]
        projs = dict(PROJ, **{"CCC@DDD": (20.0, 21.0), "EEE@FFF": (20, 20),
                              "GGG@HHH": (20, 20), "III@III": (20, 20)})
        rows, s = L.build_ledger([GAME, good2] + bads, [], projs, ABBR)
        self.assertEqual(len(rows), 24 + len(bads))
        reasons = [r["reject_reason"] for r in rows if r["status"] == "rejected_input"]
        self.assertEqual(reasons, ["invalid_odds:ml_h", "invalid_input:total",
                                   "invalid_input:teams", "invalid_input:not_a_mapping"])

    def test_bad_projection_rejected(self):
        rows, s = L.build_ledger([GAME], [prop("P", 200, -110)],
                                 {"AAA@BBB": (float("nan"), 20)}, ABBR)
        self.assertEqual(rows[0]["reject_reason"], "invalid_input:projection")
        self.assertEqual(rows[1]["reject_reason"], "game_not_on_slate")
        self.assertEqual(len(rows), 2)


class LegacyRoundingBoundaryTests(unittest.TestCase):
    """Frozen v3 compared totals against the 1-decimal note."""
    PROJ = {"AAA@BBB": (22.27, 22.27)}          # T = 44.54 vs line 44.5

    def _totals(self, legacy):
        rows, s = L.build_ledger([GAME], [], self.PROJ, ABBR, legacy_note_rounding=legacy)
        return {r["selection"]: r for r in rows if r["market"] == "Total"}, s

    def test_legacy_filters_both_sides_at_boundary(self):
        t, s = self._totals(True)
        self.assertEqual(s["filter_basis"], "v3_note_1dp")
        self.assertEqual(t["Over 44.5"]["status"], "filtered_contradicts_projection")
        self.assertEqual(t["Under 44.5"]["status"], "filtered_contradicts_projection")

    def test_full_precision_is_a_different_version(self):
        t, s = self._totals(False)
        self.assertEqual(s["filter_basis"], "full_precision")
        self.assertNotEqual(t["Over 44.5"]["status"], "filtered_contradicts_projection")
        self.assertEqual(t["Under 44.5"]["status"], "filtered_contradicts_projection")

    def test_default_is_legacy(self):
        rows, s = L.build_ledger([GAME], [], self.PROJ, ABBR)
        self.assertEqual(s["filter_basis"], "v3_note_1dp")


if __name__ == "__main__":
    unittest.main()
