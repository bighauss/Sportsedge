"""Additional synthetic cross-snapshot and non-overblocking settlement tests.

No historical data: invented rows verify algebraic consistency only.
"""
import unittest
from test_quant_prop_joint_structural_guards import row, assess


class QuantSettlementBoundsAcrossSnapshots(unittest.TestCase):
    def test_cross_snapshot_nested_lines_conflict_without_same_market_result_flip(self):
        early = [
            row("pts-over20", stat="PTS", line="20.5", result="WIN"),
            row("ast-over5", stat="AST", line="5.5", result="LOSS"),
        ]
        later = [
            row("pts-over10", stat="PTS", line="10.5", result="LOSS"),
            row("ast-over5", stat="AST", line="5.5", result="LOSS"),
        ]
        for leg in later:
            leg["snapshot_id"] = "snapshot-2"
            leg["asof_utc"] = "2026-11-20T20:00:00Z"
        report, pairs, excluded = assess(early + later)
        self.assertEqual(report["pair_rows"], 0)
        self.assertEqual(
            report["exclusion_counts"]["PLAYER_FINAL_SETTLEMENT_CONTRADICTION"], 4
        )

    def test_impossible_under_ladder_quarantines_affected_snapshot(self):
        report, pairs, excluded = assess([
            row("low", line="10.5", side="UNDER", result="WIN"),
            row("high", line="20.5", side="UNDER", result="LOSS"),
        ])
        self.assertEqual(report["pair_rows"], 0)
        self.assertGreaterEqual(len(excluded), 2)

    def test_consistent_over_ladder_is_not_quarantined(self):
        report, pairs, excluded = assess([
            row("high", line="20.5", side="OVER", result="LOSS"),
            row("low", line="10.5", side="OVER", result="WIN"),
        ])
        self.assertEqual(report["pair_rows"], 1)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(excluded), 0)

    def test_opposite_same_half_point_consistent_labels_are_retained(self):
        report, pairs, excluded = assess([
            row("over", line="20.5", side="OVER", result="WIN"),
            row("under", line="20.5", side="UNDER", result="LOSS"),
        ])
        self.assertEqual(report["pair_rows"], 1)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(excluded), 0)


if __name__ == "__main__":
    unittest.main()
