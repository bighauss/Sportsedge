"""Regression: unknown ESPN neutral-site status must not become home court."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cbb_run_it import registry


class VenueFlagTests(unittest.TestCase):
    def setUp(self):
        self.slate = [{
            "game_id": "123", "_home": "Home State", "_away": "Away State",
            "tipoff_utc": "2026-11-22T01:00:00Z",
        }]

    def event(self, **overrides):
        competition = {
            "date": "2026-11-22T01:00:00Z",
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Home State"}},
                {"homeAway": "away", "team": {"displayName": "Away State"}},
            ],
        }
        competition.update(overrides)
        return {"events": [{"competitions": [competition]}]}

    def test_missing_flag_is_withheld(self):
        rows, misses = registry(self.slate, self.event(), "abc", "2026-11-21T20:00:00Z")
        self.assertEqual(rows, [])
        self.assertIn(("123", "ESPN neutral-site flag missing or not boolean"), misses)

    def test_non_boolean_flag_is_withheld(self):
        rows, misses = registry(self.slate, self.event(neutralSite="false"), "abc", "2026-11-21T20:00:00Z")
        self.assertEqual(rows, [])
        self.assertEqual(len(misses), 1)

    def test_explicit_false_remains_home(self):
        rows, misses = registry(self.slate, self.event(neutralSite=False), "abc", "2026-11-21T20:00:00Z")
        self.assertEqual(misses, [])
        self.assertEqual(rows[0]["neutral"], "0")

    def test_explicit_true_remains_neutral(self):
        rows, misses = registry(self.slate, self.event(neutralSite=True), "abc", "2026-11-21T20:00:00Z")
        self.assertEqual(misses, [])
        self.assertEqual(rows[0]["neutral"], "1")


if __name__ == "__main__":
    unittest.main()
