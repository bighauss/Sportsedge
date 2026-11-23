"""Provider-free NHL empty-net rate challenger safeguards; research only."""
import unittest
import nhl_empty_net_challenger as C
import sportsedge_nhl_model as M


class EmptyNetShadow(unittest.TestCase):
    def test_production_weights_not_mutated(self):
        before = dict(M.W)
        r = C.compare(3.28, 2.98, -2.5)
        self.assertEqual(before, M.W)
        self.assertEqual(r["baseline_en_rates"]["lead1"], 0.13)
        self.assertEqual(r["baseline_en_rates"]["lead2"], 0.07)
        self.assertFalse(r["source_authenticated"])
        self.assertFalse(r["independent_holdout_verified"])
        self.assertEqual(r["approved_stake_u"], 0)

    def test_baseline_probability_exact_when_same_rates(self):
        r = C.compare(3.28, 2.98, -2.5,
                      en_p_lead1=M.W["en_p_lead1"],
                      en_p_lead2=M.W["en_p_lead2"])
        self.assertAlmostEqual(r["delta_p_win"], 0, places=10)
        self.assertAlmostEqual(r["baseline"]["p_push"], r["challenger"]["p_push"])

    def test_shadow_alt_line_moves_but_never_changes_main(self):
        base_weights = M.W.copy()
        alt = C.compare(3.28, 2.98, -2.5)
        main = C.compare(3.28, 2.98, -1.5)
        self.assertGreater(alt["challenger"]["p_win"], alt["baseline"]["p_win"])
        self.assertLess(abs(main["delta_p_win"]), 0.03)
        self.assertEqual(M.W, base_weights)

    def test_signed_integer_push_and_half_point(self):
        r = C.compare(3.1, 3.1, -2)
        self.assertGreater(r["baseline"]["p_push"], 0)
        self.assertGreater(r["challenger"]["p_push"], 0)
        r2 = C.compare(3.1, 3.1, -2.5)
        self.assertEqual(r2["baseline"]["p_push"], 0)
        self.assertEqual(r2["challenger"]["p_push"], 0)

    def test_probability_mass_normalized_and_nonnegative(self):
        for h, a in ((3.28, 2.98), (0.6, 4.0), (8.0, 7.5)):
            matrix = C.shadow_score_matrix(h, a)
            self.assertAlmostEqual(sum(sum(row) for row in matrix), 1, places=9)
            self.assertGreaterEqual(min(p for row in matrix for p in row), 0.0)

    def test_invalid_probabilities_refused(self):
        for p in (-.1, 1.01, float("nan"), float("inf"), True):
            with self.subTest(p=p):
                with self.assertRaises(ValueError):
                    C.compare(3.2, 2.9, -2.5, en_p_lead1=p)
                with self.assertRaises(ValueError):
                    C.compare(3.2, 2.9, -2.5, en_p_lead2=p)

    def test_invalid_expected_goals_and_spreads_refused(self):
        for v in (float("nan"), float("inf"), 0, -1, 100, True):
            with self.subTest(v=v):
                with self.assertRaises(ValueError):
                    C.compare(v, 3.0)
                with self.assertRaises(ValueError):
                    C.compare(3.0, v)
        for v in (float("nan"), float("inf"), 3.25, 50, True):
            with self.subTest(line=v):
                with self.assertRaises(ValueError):
                    C.compare(3.1, 3.2, v)

    def test_repeated_research_determinism_and_no_unknown_promotion(self):
        a = C.compare(3.12, 2.88)
        b = C.compare(3.12, 2.88)
        self.assertEqual(a, b)
        self.assertIn("UNVERIFIED", a["status"])
        self.assertEqual(a["official_counted"], 0)
        self.assertFalse(a["source_authenticated"])


if __name__ == "__main__":
    unittest.main()
