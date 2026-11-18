"""Synthetic / reported-grade arithmetic only; no external source authenticity."""
import unittest
from grade_reconciliation import reconcile, profit_per_unit


def row(i, odds, outcome, stake="1", event="NE-DET"):
    return {"bet_id": str(i), "event_id": event,
            "price_american": str(odds), "stake_u": stake, "outcome": outcome}


class GradeReconciliationTest(unittest.TestCase):
    def test_reported_nov15_ne_det_discrepancy(self):
        # Published result/price ledger, not a verified original wager ledger.
        rows = [row(1, 100, "L"), row(2, 124, "L"), row(3, -110, "L"),
                row(4, -112, "L"), row(5, -105, "W"), row(6, -126, "W"),
                row(7, -127, "L"), row(8, -114, "L"), row(9, -107, "W")]
        report = reconcile(rows, "-4.32")
        self.assertEqual(report["summary"]["actual_staked_decisions"], 9)
        self.assertEqual(report["summary"]["wins"], 3)
        self.assertEqual(report["summary"]["losses"], 6)
        self.assertFalse(report["reported_comparison"]["matches_within_0_01u"])
        self.assertTrue(-3.34 < float(report["summary"]["net_units"]) < -3.31)

    def test_push_zero_and_american_odds(self):
        self.assertEqual(profit_per_unit("+200"), 2)
        self.assertAlmostEqual(float(profit_per_unit("-110")), 100 / 110)
        x = reconcile([row("a", -110, "P")])
        self.assertEqual(x["summary"]["net_units"], "0")

    def test_duplicate_decisions_all_quarantined(self):
        x = reconcile([row("a", -110, "W"), row("a", -110, "L")])
        self.assertEqual(len(x["blocked"]), 2)
        self.assertEqual(x["summary"]["actual_staked_decisions"], 0)

    def test_no_silent_flat_unit_for_missing_stake(self):
        x = reconcile([row("a", -110, "W", "")])
        self.assertEqual(len(x["blocked"]), 1)
        self.assertEqual(x["summary"]["risk_units"], "0")

    def test_paper_rows_not_staked(self):
        x = reconcile([row("a", 200, "W", "0")])
        self.assertEqual(x["summary"]["paper_0u_rows"], 1)
        self.assertEqual(x["summary"]["net_units"], "0")
        self.assertEqual(x["summary"]["actual_staked_decisions"], 0)

    def test_pending_excluded(self):
        x = reconcile([row("a", -110, "PENDING")])
        self.assertEqual(len(x["pending"]), 1)
        self.assertEqual(x["summary"]["net_units"], "0")

    def test_bad_prices_and_outcomes_rejected(self):
        x = reconcile([row("a", -20, "W"), row("b", 100, "BOGUS")])
        self.assertEqual(len(x["blocked"]), 2)


if __name__ == "__main__":
    unittest.main()
