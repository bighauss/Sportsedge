"""Fail-closed CBB feature-role admission regressions (research only)."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from sportsedge.markets.projection_bridge import from_claude_sport


class CBBFeatureAdmissionRegression(unittest.TestCase):
    def test_missing_injury_role_must_not_be_silently_assumed_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            teams = Path(tmp) / "teams.csv"
            games = Path(tmp) / "games.csv"
            teams.write_text("team,games,adjoe,adjde,adj_t\nHome,1,100,100,68\nAway,1,100,100,68\n")
            games.write_text("game_id,home,away,neutral\ng1,Home,Away,0\n")
            with self.assertRaisesRegex(ValueError, "CBB_REQUIRED_FEATURE_ROLE_MISSING:injuries"):
                from_claude_sport(
                    "CBB", {"teams": str(teams), "games": str(games)}, "g1",
                    asof_utc=datetime(2026, 11, 18, tzinfo=timezone.utc),
                )

    def test_missing_team_role_must_fail_before_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            games = Path(tmp) / "games.csv"
            games.write_text("game_id,home,away,neutral\ng1,Home,Away,0\n")
            with self.assertRaisesRegex(ValueError, "CBB_REQUIRED_FEATURE_ROLE_MISSING:teams"):
                from_claude_sport(
                    "CBB", {"games": str(games)}, "g1",
                    asof_utc=datetime(2026, 11, 18, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
