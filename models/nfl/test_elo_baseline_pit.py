"""Synthetic PIT-only Elo-style NFL baseline tests. No nflverse, no network."""
import hashlib
import unittest
from elo_baseline_pit import generate, Inadmissible

SHA = "a" * 64
VERSION = "b" * 64
OBS = "2026-11-14T12:00:00Z"
SOURCE = "2026-11-14T12:00:00Z"


def history():
    return [
        {"game_id": "h1", "season": "2026", "week": "10", "home": "Alpha", "away": "Beta",
         "kickoff_utc": "2026-11-07T18:00:00Z", "final_available_utc": "2026-11-07T23:00:00Z",
         "home_score": "24", "away_score": "17"},
        {"game_id": "h2", "season": "2026", "week": "11", "home": "Beta", "away": "Alpha",
         "kickoff_utc": "2026-11-12T18:00:00Z", "final_available_utc": "2026-11-12T23:00:00Z",
         "home_score": "21", "away_score": "17"},
    ]


def target(name="g1", home="Alpha", away="Beta"):
    return {"game_id": name, "season": "2026", "week": "12",
            "home": home, "away": away,
            "kickoff_utc": "2026-11-15T18:00:00Z",
            "forecast_utc": "2026-11-15T17:00:00Z"}


class TestEloBaseline(unittest.TestCase):
    def run_elo(self, h=None, t=None, observed=OBS, **kw):
        return generate(history() if h is None else h,
                        [target()] if t is None else t, observed,
                        SHA, VERSION, min_history=2, **kw)

    def test_research_projection_from_only_prior_outcomes(self):
        forecasts, report = self.run_elo()
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0]["model"], "elo")
        self.assertAlmostEqual(float(forecasts[0]["total"]), 39.5, places=5)
        self.assertGreater(float(forecasts[0]["home_win_prob"]), 0)
        self.assertLess(float(forecasts[0]["home_win_prob"]), 1)
        self.assertEqual(forecasts[0]["source_available_utc"], "2026-11-14T12:00:00+00:00")
        self.assertEqual(report["official_units"], 0)
        self.assertFalse(report["wager_eligible"])

    def test_insufficient_history_blocked_explicitly(self):
        outputs, report = generate(history(), [target()], OBS, SHA, VERSION, min_history=64)
        self.assertEqual(outputs, [])
        self.assertEqual(report["games_blocked"], 1)
        self.assertIn("INSUFFICIENT_PRIOR_HISTORY", report["blocked_games"][0]["reasons"])

    def test_unseen_team_blocked_not_assigned_default(self):
        outputs, report = self.run_elo(t=[target(away="Unknown")])
        self.assertEqual(outputs, [])
        self.assertIn("TEAM_UNSEEN_IN_PIT_HISTORY", report["blocked_games"][0]["reasons"])

    def test_untimely_history_results_refused(self):
        h = history()
        h[1]["final_available_utc"] = "2026-11-16T01:00:00Z"
        with self.assertRaisesRegex(Inadmissible, "HISTORICAL_RESULT_NOT_AVAILABLE"):
            self.run_elo(h=h)

    def test_archive_downloaded_after_forecast_refused(self):
        with self.assertRaisesRegex(Inadmissible, "TARGET_NOT_STRICTLY_PREGAME"):
            self.run_elo(observed="2026-11-15T19:00:00Z")

    def test_duplicate_history_refused(self):
        h = history()
        with self.assertRaisesRegex(Inadmissible, "DUPLICATE_HISTORY_GAME"):
            self.run_elo(h=h + [h[0]])

    def test_forecast_of_historical_game_refused(self):
        with self.assertRaisesRegex(Inadmissible, "DUPLICATE_OR_HISTORICAL_TARGET"):
            self.run_elo(t=[target(name="h1")])

    def test_unzoned_archive_time_refused(self):
        with self.assertRaisesRegex(Inadmissible, "SOURCE_OBSERVED_NAIVE"):
            self.run_elo(observed="2026-11-14T12:00:00")

    def test_hash_required(self):
        with self.assertRaisesRegex(Inadmissible, "SOURCE_MISSING_OR_NOT_SHA256"):
            generate(history(), [target()], OBS, "", VERSION, min_history=2)

    def test_deterministic_no_fabricated_data(self):
        a = self.run_elo()
        b = self.run_elo()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
