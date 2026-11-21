"""Research-only tests: legacy market validation labels cannot promote wagers.

No actual wager or private spreadsheet is included in this synthetic suite.
"""
import unittest
from sportsedge_stage2_readonly_audit import audit_ledger, audit_other


class Stage2LegacyStatusTests(unittest.TestCase):
    def test_historical_oos_claims_are_not_independent_approval(self):
        rows = [
            {
                "Market": "Example market",
                "Status": "VALIDATED",
                "Validation": "Historical OOS",
                "Live_Output_Ready": "FALSE",
                "Execution_Gate": "Fresh independent source/price required",
            }
            for _ in range(10)
        ]
        rows += [
            {"Market": "Caution", "Status": "CAUTION", "Validation": "Historical OOS",
             "Live_Output_Ready": "FALSE", "Execution_Gate": "Extra uncertainty"},
            *[
                {"Market": "Blocked", "Status": "BLOCKED", "Validation": "Historical OOS failure",
                 "Live_Output_Ready": "FALSE", "Execution_Gate": "Never execute"}
                for _ in range(5)
            ],
            *[
                {"Market": "Unbuilt", "Status": "UNBUILT", "Validation": "Not yet validated",
                 "Live_Output_Ready": "FALSE", "Execution_Gate": "No execution"}
                for _ in range(4)
            ],
        ]
        got = audit_other("MARKET_STATUS", rows)
        self.assertEqual(got["rows"], 20)
        self.assertEqual(got["validated_historical_claims"], 10)
        self.assertEqual(got["validated_but_live_not_ready_rows"], 10)
        self.assertEqual(got["live_output_ready_false_rows"], 20)
        self.assertEqual(got["historical_oos_claimed_rows"], 16)
        self.assertEqual(got["status_claims"]["BLOCKED"], 5)
        self.assertEqual(got["status_claims"]["UNBUILT"], 4)
        self.assertEqual(got["independently_reproduced_historical_validation_rows"], 0)
        self.assertEqual(got["authenticated_official_ready_rows"], 0)
        self.assertEqual(got["approved_stake_u"], 0)

    def test_even_true_self_declared_live_ready_does_not_authenticate(self):
        rows = [{
            "Market": "Fictitious",
            "Status": "VALIDATED",
            "Validation": "Historical OOS",
            "Live_Output_Ready": "TRUE",
            "Execution_Gate": "claimed ready",
        }]
        got = audit_other("MARKET_STATUS", rows)
        self.assertEqual(got["validated_but_live_not_ready_rows"], 0)
        self.assertEqual(got["live_output_ready_true_rows"], 1)
        self.assertEqual(got["authenticated_official_ready_rows"], 0)
        self.assertEqual(got["approved_stake_u"], 0)

    def test_ambiguous_live_flags_are_not_successfully_ready(self):
        rows = [
            {"Market": "A", "Status": "VALIDATED", "Validation": "Historical OOS",
             "Live_Output_Ready": "", "Execution_Gate": "X"},
            {"Market": "B", "Status": "BLOCKED", "Validation": "Historical OOS failure",
             "Live_Output_Ready": "maybe", "Execution_Gate": "X"},
            {"Market": "C", "Status": "UNBUILT", "Validation": "Not yet validated",
             "Live_Output_Ready": "TRUE", "Execution_Gate": "none"},
        ]
        got = audit_other("MARKET_STATUS", rows)
        self.assertEqual(got["ambiguous_live_output_ready_rows"], 2)
        self.assertEqual(got["not_validated_but_claimed_live_ready_rows"], 1)
        self.assertEqual(got["authenticated_official_ready_rows"], 0)

    def test_missing_columns_are_explicit_not_silently_inferred(self):
        got = audit_other("MARKET_STATUS", [{"Market": "Unknown", "Status": "VALIDATED"}])
        self.assertEqual(got["missing_required_columns"],
                         ["Execution_Gate", "Live_Output_Ready", "Validation"])
        self.assertEqual(got["ambiguous_live_output_ready_rows"], 1)
        self.assertEqual(got["authenticated_official_ready_rows"], 0)

    def test_parlay_leg_labels_are_counted_without_guessing_from_selection(self):
        rows = [
            {"Market": "2-Pick Parlay", "Bet Price": "+803", "Stake": "7.32",
             "Result": "LOSS", "Profit": "-7.32", "Placed CDT": "A", "BetID": "1"},
            {"Market": "3-Pick Parlay", "Bet Price": "+295", "Stake": "26",
             "Result": "LOSS", "Profit": "-26", "Placed CDT": "B", "BetID": "2"},
            {"Market": "3-Pick Parlay", "Bet Price": "+395 boosted", "Stake": "10",
             "Result": "LOSS", "Profit": "-10", "Placed CDT": "C", "BetID": "3"},
            {"Market": "Pitcher Strikeouts O/U", "Bet Price": "-154", "Stake": "10",
             "Result": "LOSS", "Profit": "-10", "Placed CDT": "same", "BetID": "4"},
            {"Market": "Pitcher Strikeouts O/U", "Bet Price": "-151", "Stake": "10",
             "Result": "WIN", "Profit": "6.62", "Placed CDT": "same", "BetID": "5"},
        ]
        got = audit_ledger(rows)
        self.assertEqual(got["parlay_rows_by_declared_leg_count"], {"2": 1, "3": 2})
        self.assertEqual(got["boosted_price_text_rows"], 1)
        self.assertEqual(got["noncanonical_american_odds"], 1)
        self.assertEqual(got["duplicate_placed_time_groups"], 1)
        self.assertEqual(got["rows_sharing_placed_time"], 2)
        self.assertEqual(got["duplicate_bet_id_groups"], 0)
        self.assertEqual(got["arithmetic_issues"], [])
        self.assertEqual(got["recorded_stakes"], "63.32")
        self.assertEqual(got["recorded_profit"], "-46.70")

    def test_invalid_money_still_retains_offer_category_and_price_warning(self):
        rows = [
            {"Market": "3-Pick Parlay", "Bet Price": "+395 boosted",
             "Stake": "bad", "Profit": "", "Result": "LOSS",
             "Placed CDT": "same", "BetID": "A"},
            {"Market": "3-Pick Parlay", "Bet Price": "+295",
             "Stake": "1", "Profit": "-1", "Result": "LOSS",
             "Placed CDT": "same", "BetID": "B"},
        ]
        got = audit_ledger(rows)
        self.assertEqual(got["wager_rows"], 2)
        self.assertEqual(got["invalid_monetary_rows"], 1)
        self.assertEqual(got["parlay_rows_by_declared_leg_count"], {"3": 2})
        self.assertEqual(got["boosted_price_text_rows"], 1)
        self.assertEqual(got["noncanonical_american_odds"], 1)
        self.assertEqual(got["duplicate_placed_time_groups"], 1)
        self.assertEqual(got["recorded_stakes"], "1.00")

    def test_unknown_parlay_size_and_missing_times_not_inferred(self):
        rows = [{
            "Market": "Parlay", "Bet Price": "+200", "Stake": "1",
            "Result": "LOSS", "Profit": "-1",
            "Placed CDT": "", "BetID": "a",
        }]
        got = audit_ledger(rows)
        self.assertEqual(got["parlay_rows_unknown_leg_count"], 1)
        self.assertEqual(got["parlay_rows_by_declared_leg_count"], {})
        self.assertEqual(got["duplicate_placed_time_groups"], 0)


if __name__ == "__main__":
    unittest.main()
