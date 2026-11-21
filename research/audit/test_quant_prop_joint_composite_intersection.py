"""Composite/composite stat-overlap regressions for research-only player-prop audit.

Synthetic records only. Does not establish correlation, validate a sports model,
or authorize any sportsbook pricing. No changes to historical source rows.
"""
import unittest

from test_quant_prop_joint_structural_guards import assess, row
from prop_joint_correlation import STAT_COMPONENTS, classify


class QuantCompositeIntersection(unittest.TestCase):
    def test_shared_component_pairs_are_structural_in_both_input_orders(self):
        # The earlier direct-component check covered PTS vs PRA, but not
        # PR vs PA even though both outcomes directly contain PTS.
        cases = (
            ("PR", "PA", "PTS"),
            ("PR", "RA", "REB"),
            ("PA", "RA", "AST"),
            ("PRA", "PTS_REB_AST", "PTS"),
            ("PR", "PRA", "PTS"),
            ("RUSH_REC_YDS", "REC_YDS", "REC_YDS"),
            ("PRA", "REB", "REB"),
        )
        for first, second, shared in cases:
            with self.subTest(first=first, second=second, shared=shared):
                self.assertIn(shared, STAT_COMPONENTS.get(first, {first}))
                self.assertIn(shared, STAT_COMPONENTS.get(second, {second}))
                for flipped in (False, True):
                    a = row("A", stat=first, line="20.5", result="WIN")
                    b = row("B", stat=second, line="30.5", result="LOSS")
                    report, pairs, exclusions = assess(
                        [b, a] if flipped else [a, b]
                    )
                    self.assertEqual(report["pair_rows"], 1)
                    self.assertEqual(len(exclusions), 0)
                    self.assertEqual(pairs[0]["kind"], "STRUCTURAL_LOGIC_ONLY")
                    self.assertIn("SAME_PLAYER_COMPOSITE_OVERLAP", pairs[0]["relation"])

    def test_disjoint_atomic_or_composite_stats_remain_empirical_candidates(self):
        # Nonoverlapping same-player results can have stochastic correlation,
        # but do not share a literal stat component under known mappings.
        cases = (
            ("PTS", "AST"),
            ("PR", "AST"),
            ("PA", "REB"),
            ("RUSH_REC_YDS", "PASS_YDS"),
        )
        for first, second in cases:
            with self.subTest(first=first, second=second):
                a = row("A", stat=first, line="20.5", result="WIN")
                b = row("B", stat=second, line="30.5", result="LOSS")
                report, pairs, excluded = assess([a, b])
                self.assertEqual(report["pair_rows"], 1)
                self.assertEqual(len(excluded), 0)
                self.assertEqual(pairs[0]["kind"], "EMPIRICAL_CANDIDATE")
                self.assertIn("SAME_PLAYER_DIFFERENT_STATS", pairs[0]["relation"])

    def test_direct_classifier_remains_order_invariant_for_composite_pairs(self):
        a = dict(player_id="PLAYER", stat="PR", side="OVER", period="FG",
                 line_num=20.5, team_id="TEAM")
        b = dict(player_id="PLAYER", stat="PA", side="OVER", period="FG",
                 line_num=30.5, team_id="TEAM")
        self.assertEqual(classify(a, b), "SAME_PLAYER_COMPOSITE_OVERLAP")
        self.assertEqual(classify(b, a), "SAME_PLAYER_COMPOSITE_OVERLAP")


if __name__ == "__main__":
    unittest.main()
