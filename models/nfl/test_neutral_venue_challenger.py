"""Synthetic NFL neutral-site regressions; no private games or official bets."""
import unittest

from neutral_venue_challenger import (
    UnknownVenue, project_without_unearned_hfa, paired_margin_errors,
)


def row(event_id, neutral, forecast_home, forecast_away, final_home, final_away):
    return dict(
        event_id=event_id, neutral=neutral, forecast_home=forecast_home,
        forecast_away=forecast_away, final_home=final_home,
        final_away=final_away,
    )


class NeutralVenueChallengerTests(unittest.TestCase):
    def test_known_normal_venue_is_byte_for_byte_score_equivalent(self):
        self.assertEqual(
            project_without_unearned_hfa(
                27.3, 20.2, neutral=False, home_field_margin_points=1.6),
            (27.3, 20.2),
        )

    def test_known_neutral_removes_exact_full_margin_advantage(self):
        h, a = project_without_unearned_hfa(
            27.3, 20.2, neutral=True, home_field_margin_points=1.6)
        self.assertAlmostEqual(h, 26.5)
        self.assertAlmostEqual(a, 21.0)
        self.assertAlmostEqual((h-a), (27.3-20.2)-1.6)
        self.assertAlmostEqual((h+a), 27.3+20.2)

    def test_no_inferred_venue_from_string_or_missing_value(self):
        for flag in ("true", "false", 0, 1, None, [], {}):
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(UnknownVenue, "NEUTRAL_VENUE_BOOL_REQUIRED"):
                    project_without_unearned_hfa(
                        20, 20, neutral=flag, home_field_margin_points=1.6)

    def test_invalid_hfa_and_nonfinite_score_blocked(self):
        for value in (-1, 20.1, float("nan"), float("inf"), True):
            with self.subTest(hfa=value):
                with self.assertRaises(ValueError):
                    project_without_unearned_hfa(
                        20, 20, neutral=True,
                        home_field_margin_points=value)
        for score in (float("nan"), float("-inf"), -1, True):
            with self.subTest(score=score):
                with self.assertRaises(ValueError):
                    project_without_unearned_hfa(
                        score, 20, neutral=False,
                        home_field_margin_points=1.6)

    def test_no_negative_home_score_after_neutral_correction(self):
        with self.assertRaisesRegex(ValueError, "NEUTRAL_CORRECTION_CAUSES_NEGATIVE_HOME_SCORE"):
            project_without_unearned_hfa(
                0.3, 2, neutral=True, home_field_margin_points=1.6)

    def test_paired_errors_with_normal_and_neutral(self):
        sample = [
            row("neutral", True, 21, 17, 20, 18),
            row("normal", False, 27, 24, 26, 24),
        ]
        result = paired_margin_errors(sample, home_field_margin_points=2)
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["n_neutral"], 1)
        self.assertAlmostEqual(result["original_margin_mae"], 1.5)
        self.assertAlmostEqual(result["challenger_margin_mae"], 0.5)
        self.assertEqual(result["approved_stake_u"], 0)
        self.assertFalse(result["future_holdout_verified"])

    def test_unknown_venue_blocks_paired_report(self):
        with self.assertRaises(UnknownVenue):
            paired_margin_errors(
                [row("g", None, 21, 17, 21, 17)],
                home_field_margin_points=1.6)

    def test_duplicate_event_id_refused(self):
        game=row("g", True, 21, 17, 21, 17)
        with self.assertRaisesRegex(ValueError, "MISSING_OR_DUPLICATED_EVENT_ID"):
            paired_margin_errors([game, game], home_field_margin_points=1.6)

    def test_no_synthetic_or_missing_final_accepted_as_outcome(self):
        game=row("g", True, 21, 17, 21, float("nan"))
        with self.assertRaisesRegex(ValueError, "FINITE_NONNEGATIVE_FINAL_REQUIRED"):
            paired_margin_errors([game], home_field_margin_points=1.6)

    def test_empty_cohort_refused_not_reported_as_zero_mae(self):
        with self.assertRaisesRegex(ValueError, "NONEMPTY_PAIRED_ROWS_REQUIRED"):
            paired_margin_errors([], home_field_margin_points=1.6)


if __name__=="__main__":
    unittest.main()
