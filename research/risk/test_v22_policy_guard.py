"""Synthetic v2.2 policy regressions. No historical prices or bets."""
import unittest

from v22_policy_guard import VERSION, CAP_GAME_U, assess


def row(**changes):
    fields = dict(
        rules_version=VERSION,
        source_receipt_verified=True,
        independent_model_verified=True,
        model_freeze_verified=True,
        independent_quote_chain_verified=True,
        ratings_half_present=True,
        market_family="ML",
        p_model="0.50",
        p_market_novig="0.45",
        price_american="+150",
    )
    fields.update(changes)
    return fields


class V22PolicyTest(unittest.TestCase):
    def test_adopted_risk_caps_no_game_cap(self):
        report = assess(row())
        self.assertIsNone(CAP_GAME_U)
        self.assertEqual(report["risk_caps_u"],
                         {"ct_day": "5", "theme": "3", "game": None})
        self.assertEqual(report["status"], "PAPER_0U")
        self.assertEqual(report["approved_stake_u"], 0)
        self.assertFalse(report["official"])

    def test_policy_mismatch_blocks(self):
        self.assertEqual(assess(row(rules_version="v2.1"))["status"], "BLOCK")

    def test_missing_ratings_shrinks_before_blend(self):
        report = assess(row(ratings_half_present=False))
        self.assertEqual(report["effective_model_probability"], "0.475")
        self.assertEqual(report["blended_probability"], "0.45750")
        self.assertEqual(report["confidence_ceiling"], "LOW")
        self.assertEqual(report["status"], "PAPER_0U")

    def test_gap_over_twelve_holds_even_after_shrink(self):
        report = assess(row(p_model="0.58", p_market_novig="0.45",
                            ratings_half_present=False))
        self.assertIn("GAP_HOLD_GREATER_THAN_12PP", report["flags"])
        self.assertEqual(report["status"], "BLOCK")
        self.assertEqual(report["approved_stake_u"], 0)

    def test_exact_twelve_not_above_twelve(self):
        report = assess(row(p_model="0.57", p_market_novig="0.45"))
        self.assertNotIn("GAP_HOLD_GREATER_THAN_12PP", report["flags"])

    def test_plus_200_cap_cannot_lift_by_self_attestation(self):
        report = assess(row(price_american="+200",
                            dog_ml_clv_count=1000,
                            dog_ml_clv_positive=True))
        self.assertEqual(report["long_dog_diagnostic_max_u"], "0.25")
        self.assertEqual(report["approved_stake_u"], 0)

    def test_thin_or_invalid_source_blocks(self):
        report = assess(row(independent_quote_chain_verified=False))
        self.assertEqual(report["status"], "BLOCK")

    def test_points_not_percentage_points(self):
        report = assess(row(projection_market_points_gap="3.1"))
        self.assertIn("PROJECTION_MARKET_POINTS_GAP_OVER_3", report["flags"])
        self.assertNotIn("GAP_HOLD_GREATER_THAN_12PP", report["flags"])

    def test_unverified_ratings_state_blocks(self):
        self.assertEqual(assess(row(ratings_half_present=None))["status"], "BLOCK")

    def test_nonfinite_model_probability_blocks(self):
        self.assertEqual(assess(row(p_model="nan"))["status"], "BLOCK")

    def test_non_dict(self):
        self.assertEqual(assess(None)["status"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
