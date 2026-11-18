"""Regression: malformed offered line identities must never satisfy census coverage."""
import unittest

from sportsedge.odds.completeness_gate import CompletenessError, _key


class MarketLineIdentityTest(unittest.TestCase):
    def row(self, family, line):
        return dict(book="DK", provider_market_id="m1", family=family,
                    period="FG", side="OVER" if family == "TOTAL" else "HOME",
                    line=line)

    def test_malformed_numeric_lines_fail_closed(self):
        for family in ("SPREAD", "TOTAL", "TEAM_TOTAL", "ALT_SPREAD", "ALT_TOTAL"):
            for line in ("", " ", "not-a-number", "NaN", "Infinity", "1e999"):
                with self.subTest(family=family, line=line):
                    row = self.row(family, line)
                    if family == "TEAM_TOTAL":
                        row["team_id"] = "team-1"
                    with self.assertRaises(CompletenessError):
                        _key(row)

    def test_valid_numeric_lines_preserved(self):
        for family, line in (("SPREAD", "-8.5"), ("TOTAL", "150.0"), ("ALT_TOTAL", "151.5")):
            self.assertEqual(_key(self.row(family, line))[5], line)

    def test_moneyline_can_have_empty_line(self):
        self.assertEqual(_key(self.row("ML", ""))[5], "")


if __name__ == "__main__":
    unittest.main()
