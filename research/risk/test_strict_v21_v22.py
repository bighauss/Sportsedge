"""Synthetic tests only. They do not certify real sportsbook price receipts."""
import unittest

from research.risk.strict_v21_v22 import POLICY_VERSION, SPORTS, diagnostic


def candidate(**overrides):
    row = dict(
        bet_id="B1", event_id="G1", theme="signal-T",
        risk_date_ct="2026-11-15", market="ML", sport="NFL",
        book="DK", price_american="+120", p_model=".60",
        p_market_novig=".55", bankroll="1000", dollars_per_u="10",
        confidence="HIGH", captured_utc="2026-11-15T17:10:00Z",
        game_start_utc="2026-11-15T18:00:00Z",
        source_receipt_verified=True, independent_model_verified=True,
        quote_is_fresh=True, injury_snapshot_locked=True,
        ratings_half_present=True, features_asof_verified=True,
    )
    row.update(overrides)
    return row


def size(**kwargs):
    return diagnostic(candidate(**kwargs))


class StrictRisk(unittest.TestCase):
    def test_never_authorizes_cash(self):
        r = size()
        self.assertEqual(r["approved_stake_u"], 0)
        self.assertEqual(r["status"], "PAPER_0U")
        self.assertEqual(r["policy_version"], POLICY_VERSION)
        self.assertGreater(float(r["diagnostic_u"]), 0)

    def test_all_seven_sports_research_only(self):
        self.assertEqual(SPORTS, set(("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA")))
        for sport in SPORTS:
            with self.subTest(sport=sport):
                r = size(sport=sport, goalie_confirmed=True)
                self.assertEqual(r["approved_stake_u"], 0)
                self.assertEqual(r["status"], "PAPER_0U")

    def test_missing_critical_asof_features_blocks_diagnostic(self):
        r = size(features_asof_verified=False)
        self.assertEqual(r["diagnostic_u"], 0)
        self.assertIn("V22_CRITICAL_ASOF_FEATURE_EVIDENCE_MISSING", r["flags"])

    def test_unrecorded_ratings_half_state_blocks(self):
        r = size(ratings_half_present=None)
        self.assertEqual(r["diagnostic_u"], 0)
        self.assertIn("V22_RATINGS_HALF_STATUS_UNVERIFIED", r["flags"])

    def test_explicit_half_only_shrink_before_blend(self):
        r = size(ratings_half_present=False, p_model=".65", p_market_novig=".55")
        self.assertEqual(r["blended_win_probability"], "0.565")
        self.assertIn("V22_MISSING_HALF_50_PERCENT_SHRINK_AND_LOW",
                      r["v22_applied_rules"])

    def test_missing_half_makes_low_confidence(self):
        full = size(p_model=".65", p_market_novig=".55")
        half = size(p_model=".65", p_market_novig=".55",
                    ratings_half_present=False)
        self.assertLess(float(half["diagnostic_u"]), float(full["diagnostic_u"]))

    def test_more_than_12_points_is_zero_even_if_shrunk(self):
        r = size(p_model=".80", p_market_novig=".55",
                 ratings_half_present=False)
        self.assertEqual(r["diagnostic_u"], 0)
        self.assertIn("V22_MODEL_MARKET_GAP_GT_12PTS_HOLD", r["flags"])

    def test_exactly_12_points_not_auto_hold(self):
        r = size(p_model=".67", p_market_novig=".55")
        self.assertNotIn("V22_MODEL_MARKET_GAP_GT_12PTS_HOLD", r["flags"])
        self.assertGreater(float(r["diagnostic_u"]), 0)

    def test_more_than_3_points_is_an_observation(self):
        r = size(p_model=".60", p_market_novig=".55")
        self.assertIn("V22_MODEL_MARKET_GAP_GT_3PTS_REVIEW",
                      r["v22_observations"])
        self.assertNotIn("V22_MODEL_MARKET_GAP_GT_12PTS_HOLD", r["flags"])

    def test_exactly_3_points_not_an_observation(self):
        r = size(p_model=".58", p_market_novig=".55")
        self.assertNotIn("V22_MODEL_MARKET_GAP_GT_3PTS_REVIEW",
                         r["v22_observations"])

    def test_dog_at_200_capped_to_quarter_unit(self):
        r = size(price_american="+200")
        self.assertEqual(r["diagnostic_u"], "0.25")
        self.assertEqual(r["approved_stake_u"], 0)

    def test_dog_at_199_not_price_capped(self):
        r = size(price_american="+199")
        self.assertGreater(float(r["diagnostic_u"]), .25)

    def test_fake_dog_clv_unlock_ignored(self):
        r = size(price_american="+350", dog_ml_clv_count=1000,
                 dog_ml_clv_positive=True, dog_ml_clv_certified=True)
        self.assertLessEqual(float(r["diagnostic_u"]), .25)

    def test_v21_game_cap_is_not_removed_by_v22(self):
        ledger = [dict(bet_id="X", event_id="G1",
                       theme="another", stake_u="1.90",
                       risk_date_ct="2026-11-15")]
        r = diagnostic(candidate(), ledger=ledger)
        self.assertEqual(r["diagnostic_u"], "0.10")

    def test_v21_day_cap_still_applies(self):
        ledger = [dict(bet_id="X", event_id="G2",
                       theme="another", stake_u="4.90",
                       risk_date_ct="2026-11-15")]
        r = diagnostic(candidate(), ledger=ledger)
        self.assertEqual(r["diagnostic_u"], "0.10")

    def test_v21_theme_cap_still_applies(self):
        ledger = [dict(bet_id="X", event_id="G2",
                       theme="signal-T", stake_u="2.90",
                       risk_date_ct="2026-11-14")]
        r = diagnostic(candidate(), ledger=ledger)
        self.assertEqual(r["diagnostic_u"], "0.10")

    def test_v21_negative_50_clv_halves(self):
        closes = [dict(eligible=True, comparable=True, sport="NFL", clv="-.01")
                  for _ in range(50)]
        base = size()
        penalized = diagnostic(candidate(), closing_observations=closes)
        self.assertAlmostEqual(float(penalized["diagnostic_u"]),
                               float(base["diagnostic_u"])/2)

    def test_missing_probability_fails_closed(self):
        r = size(p_model=None)
        self.assertEqual(r["diagnostic_u"], 0)
        self.assertIn("V22_MODEL_MARKET_PROBABILITY_UNVERIFIED", r["flags"])

    def test_invalid_price_fails_closed(self):
        r = size(price_american="+99")
        self.assertEqual(r["diagnostic_u"], 0)
        self.assertIn("V22_ML_PRICE_UNVERIFIED", r["flags"])

    def test_unknown_sport_fails_closed(self):
        r = size(sport="SOCCER")
        self.assertEqual(r["diagnostic_u"], 0)
        self.assertIn("V22_UNSUPPORTED_SPORT", r["flags"])

    def test_non_dict_fails_closed(self):
        r = diagnostic(None)
        self.assertEqual(r["approved_stake_u"], 0)
        self.assertEqual(r["diagnostic_u"], 0)


if __name__ == "__main__":
    unittest.main()
