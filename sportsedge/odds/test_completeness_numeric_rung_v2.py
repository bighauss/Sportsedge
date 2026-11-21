"""Offline regression: numeric spread/total identities are bounded and finite.

No provider authentication, source repair, odds pricing, model changes or staking.
"""
import unittest

from sportsedge.odds.completeness_gate import CompletenessError, _key


class NumericMarketRungIdentityTests(unittest.TestCase):
    @staticmethod
    def row(family, line):
        row = dict(book="DK", provider_market_id="market-A", family=family,
                   period="FG", side="HOME" if "SPREAD" in family else "OVER",
                   line=line)
        if "TEAM_TOTAL" in family:
            row["team_id"] = "team_1"
        return row

    def test_non_ml_empty_and_malformed_lines_fail_closed(self):
        bad = ("", " ", "n/a", "NaN", "Infinity", "inf", "1e999",
               "1e9999999999", "-1e999", "1_000", "10001", "-10001",
               "999999999999999999", "3.141592653589793")
        for family in ("SPREAD", "TOTAL", "TEAM_TOTAL", "ALT_SPREAD",
                       "ALT_TOTAL", "1H_TOTAL", "1H_SPREAD"):
            for line in bad:
                with self.subTest(family=family, line=line):
                    with self.assertRaisesRegex(
                        CompletenessError, "NUMERIC_MARKET_LINE_INVALID"
                    ):
                        _key(self.row(family, line))

    def test_valid_period_quarter_and_standard_rungs_preserve_exact_text(self):
        for family, line in (
            ("SPREAD", "-8.5"), ("SPREAD", "+0.25"),
            ("TOTAL", "150.0"), ("TOTAL", "0"),
            ("ALT_TOTAL", "150.25"), ("ALT_SPREAD", "-7.75"),
            ("TEAM_TOTAL", "84.5"), ("1H_TOTAL", "72.5"),
            ("TOTAL", "10000"), ("TOTAL", "-10000")
        ):
            with self.subTest(family=family, line=line):
                self.assertEqual(_key(self.row(family, line))[5], line)

    def test_moneyline_can_have_blank_line(self):
        row = self.row("ML", "")
        row["side"] = "HOME"
        self.assertEqual(_key(row)[5], "")

    def test_no_model_or_price_side_effect(self):
        row = self.row("TOTAL", "44.5")
        row["source_receipt_sha256"] = "a" * 64
        old = dict(row)
        _key(row)
        self.assertEqual(row, old)


if __name__ == "__main__":
    unittest.main()
