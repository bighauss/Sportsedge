"""CBB display regression tests: no false confidence/real-unit release."""
import copy
import unittest
from cbb_confidence_gate import CardConfidenceError, decorate_research_card


H = "a" * 64


def fixture():
    return {"release": "PAPER_0U",
            "source": {"model_sha256": H, "feature_sha256": "b" * 64,
                       "frozen_utc": "2026-11-18T23:00:00Z"},
            "plays": [{"bet_id": "nov18:weber-utah:1h-tt-under",
                       "event_id": "weber-utah", "market": "1H_TEAM_TOTAL",
                       "side": "UNDER", "status": "PAPER_0U",
                       "model_p": 0.738, "price_american": -115,
                       "opposite_american": -105,
                       "raw_ev": 0.3796, "stars": 5,
                       "captured_utc": "2026-11-19T00:40:00Z",
                       "tipoff_utc": "2026-11-19T02:00:00Z"}]}


class CardTests(unittest.TestCase):
    def test_high_ev_stars_suppressed_without_rewriting_original(self):
        d = fixture()
        original = copy.deepcopy(d)
        out = decorate_research_card(d)
        self.assertEqual(d, original)
        self.assertIsNone(out["plays"][0]["stars"])
        self.assertEqual(out["plays"][0]["legacy_raw_ev_stars"], 5)
        self.assertEqual(out["plays"][0]["confidence_label"], "UNVALIDATED")
        self.assertEqual(out["rating_policy"], "SUPPRESS_UNVALIDATED_CBB_STARS")
        self.assertEqual(out["official_counted"], 0)
        self.assertEqual(out["plays"][0]["approved_stake_u"], 0)

    def test_ev_checked_without_adopting_wrong_30_70_stack(self):
        out = decorate_research_card(fixture())["plays"][0]
        self.assertAlmostEqual(out["raw_ev_recomputed"],
                               .738 * (1 + 100 / 115) - 1, places=5)
        self.assertIsNotNone(out["market_p_simple_novig_diagnostic"])
        self.assertNotIn("blended_ev", out)

    def test_missing_opposing_book_price_not_reconstructed(self):
        d = fixture()
        d["plays"][0].pop("opposite_american")
        out = decorate_research_card(d)["plays"][0]
        self.assertIsNone(out["market_p_simple_novig_diagnostic"])
        self.assertIn("OPPOSING_QUOTE_NOT_SUPPLIED", out["reasons"])
        d["plays"][0]["market_p"] = .5
        with self.assertRaisesRegex(CardConfidenceError, "MARKET_PROB"):
            decorate_research_card(d)

    def test_forged_real_status_rejected(self):
        d = fixture()
        d["release"] = "OFFICIAL"
        with self.assertRaisesRegex(CardConfidenceError, "PAPER_0U"):
            decorate_research_card(d)
        d = fixture()
        d["plays"][0]["status"] = "OFFICIAL"
        with self.assertRaisesRegex(CardConfidenceError, "PLAY_PAPER"):
            decorate_research_card(d)

    def test_post_tip_and_late_features_rejected(self):
        d = fixture()
        d["plays"][0]["captured_utc"] = "2026-11-19T02:01:00Z"
        with self.assertRaisesRegex(CardConfidenceError, "PREGAME"):
            decorate_research_card(d)
        d = fixture()
        d["source"]["frozen_utc"] = "2026-11-19T01:00:00Z"
        with self.assertRaisesRegex(CardConfidenceError, "FEATURE_AFTER"):
            decorate_research_card(d)

    def test_invalid_sha_ev_and_identity_rejected(self):
        d = fixture()
        d["source"]["model_sha256"] = "bad"
        with self.assertRaisesRegex(CardConfidenceError, "MODEL_SHA"):
            decorate_research_card(d)
        d = fixture()
        d["plays"][0]["raw_ev"] = .8
        with self.assertRaisesRegex(CardConfidenceError, "EV_ARITHMETIC"):
            decorate_research_card(d)
        d = fixture()
        d["plays"][0]["bet_id"] = ""
        with self.assertRaisesRegex(CardConfidenceError, "BET_ID"):
            decorate_research_card(d)

    def test_duplicate_selection_rejected(self):
        d = fixture()
        d["plays"].append(copy.deepcopy(d["plays"][0]))
        with self.assertRaisesRegex(CardConfidenceError, "DUPLICATE_SELECTION"):
            decorate_research_card(d)


if __name__ == "__main__":
    unittest.main()
