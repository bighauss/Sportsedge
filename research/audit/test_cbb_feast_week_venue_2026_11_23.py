"""Provider-free regression checks for the 2026-11-23 CBB venue evidence census.

Research-only: validates the source-linked static census and cardinalities. It
does not authenticate source publication time, replay the production model, or
establish an EV edge. No network or sportsbook access.
"""
import json
import unittest
from collections import Counter
from pathlib import Path

PATH = Path(__file__).with_name("cbb_feast_week_venue_2026_11_23.json")
EXPECTED_MISSING = {
    ("Temple", "UT Martin"),
    ("Utah Valley", "Stephen F. Austin"),
}
EXPECTED_CARD = {
    ("Arkansas State", "Southern Utah"): "neutral",
    ("Yale", "Belmont"): "neutral",
    ("Tulsa", "Oregon State"): "neutral",
    ("Georgia Southern", "Northern Kentucky"): "home",
    ("Indiana State", "East Carolina"): "neutral",
    ("Akron", "Wright State"): "neutral",
    ("Washington", "BYU"): "neutral",
    ("Northern Iowa", "Davidson"): "neutral",
}
MAUI_KEYS = {
    "OleMiss@Clemson", "UW@BYU", "VCU@Prov", "CSU@Arizona"
}


def load():
    with PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def research_hca(row):
    """Only admits a sourced, explicit venue classification, never a default."""
    if not row.get("source_url", "").startswith("https://"):
        raise ValueError("VENUE_SOURCE_MISSING")
    if row.get("source_grade") != "PUBLIC_ORGANIZER_OR_TEAM_SCHEDULE_NOT_AUTHENTICATED_PIT":
        raise ValueError("VENUE_SOURCE_GRADE_UNKNOWN")
    venue = row.get("venue_class")
    if venue == "neutral":
        return 0.0
    if venue == "home":
        return 3.0
    raise ValueError("VENUE_UNKNOWN_HOLD")


class VenueCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = load()
        cls.rows = cls.payload["events"]

    def test_schema_and_no_wager_promotion(self):
        self.assertEqual(self.payload["schema"], "sportsedge-cbb-feast-venue-research-v1")
        self.assertFalse(self.payload["wager_eligible"])
        self.assertEqual(self.payload["official_counted"], 0)
        self.assertEqual(self.payload["approved_stake_u"], 0)
        self.assertEqual(len(self.rows), 32)

    def test_complete_unique_monday_board(self):
        unique = {(e["date_ct"], e["away"], e["home"]) for e in self.rows}
        self.assertEqual(len(unique), 32)
        self.assertTrue(all(e["date_ct"] == "2026-11-23" for e in self.rows))
        self.assertEqual([e["board_row"] for e in self.rows], list(range(1, 33)))

    def test_venue_census_and_fail_closed_grade(self):
        self.assertEqual(Counter(e["venue_class"] for e in self.rows),
                         {"neutral": 19, "home": 13})
        for e in self.rows:
            self.assertEqual(e["model_hca_points"], research_hca(e))
            self.assertTrue(e["venue_name"])
            self.assertTrue(e["location"])
            self.assertIn("not_authenticated_pit",
                          e["source_grade"].lower())
        with self.assertRaisesRegex(ValueError, "VENUE_UNKNOWN_HOLD"):
            research_hca({"venue_class": "unknown", "source_url": "https://example.org",
                          "source_grade": self.rows[0]["source_grade"]})

    def test_exact_claude_coverage_gap(self):
        got = {(e["away"], e["home"]) for e in self.rows if e["claude_key"] is None}
        self.assertEqual(got, EXPECTED_MISSING)
        self.assertEqual(len([e for e in self.rows if e["claude_key"]]), 30)
        codes = [e["claude_key"] for e in self.rows if e["claude_key"]]
        self.assertEqual(len(codes), len(set(codes)))

    def test_thirteen_non_maui_false_home_flags(self):
        mismatch = [e for e in self.rows if e["prior_claude_hca_points"] is not None
                    and e["prior_claude_hca_points"] != e["model_hca_points"]]
        self.assertEqual(len(mismatch), 13)
        self.assertTrue(all(e["venue_class"] == "neutral" and
                            e["prior_claude_hca_points"] == 3 for e in mismatch))
        for e in self.rows:
            if e["claude_key"] in MAUI_KEYS:
                self.assertEqual(e["prior_claude_hca_points"], 0)

    def test_eight_card_venues_and_no_unverified_home(self):
        by_game = {(e["away"], e["home"]): e for e in self.rows}
        self.assertEqual(
            {k: by_game[k]["venue_class"] for k in EXPECTED_CARD},
            EXPECTED_CARD,
        )

    def test_symmetric_home_edge_cancels_in_total(self):
        for e in self.rows:
            hca = research_hca(e)
            away_base, home_base = 76.2, 75.4
            adjusted_total = (home_base + hca / 2) + (away_base - hca / 2)
            self.assertAlmostEqual(adjusted_total, home_base + away_base)
            self.assertAlmostEqual(
                (home_base + hca / 2) - (away_base - hca / 2),
                home_base - away_base + hca
            )


if __name__ == "__main__":
    unittest.main()
