"""CBB PIT source completeness regression: missing injury inputs must block."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from sportsedge.markets.projection_bridge import from_claude_sport


class CBBInjuryPITAdmissionTests(unittest.TestCase):
    def test_missing_injury_source_blocks_before_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            for role in ("games", "teams"):
                p = Path(tmp) / (role + ".csv")
                p.write_text("game_id,home,away\n" if role == "games" else "team,games,adjoe,adjde,adj_t\n", encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "CBB_REQUIRED_FEATURE_ROLE_MISSING:injuries"):
                from_claude_sport("CBB", files, "test", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))

    def test_missing_teams_role_blocks_before_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            games = Path(tmp) / "games.csv"
            games.write_text("game_id,home,away,neutral\ng1,Home,Away,0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CBB_REQUIRED_FEATURE_ROLE_MISSING:teams"):
                from_claude_sport("CBB", {"games": str(games)}, "g1", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))

    def test_missing_games_role_blocks_before_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            teams = Path(tmp) / "teams.csv"
            injuries = Path(tmp) / "injuries.csv"
            teams.write_text("team,games,adjoe,adjde,adj_t\n", encoding="utf-8")
            injuries.write_text("team,player,status,role\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CBB_REQUIRED_FEATURE_ROLE_MISSING:games"):
                from_claude_sport(
                    "CBB", {"teams": str(teams), "injuries": str(injuries)}, "g1",
                    asof_utc=datetime(2026, 11, 18, tzinfo=timezone.utc),
                )

    def test_header_only_injury_export_is_accepted_as_declared_not_authenticated(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            rows = {
                "games": "game_id,home,away,neutral\ng1,Home,Away,1\n",
                "teams": "team,games,adjoe,adjde,adj_t\nHome,1,105,105,67.5\nAway,1,105,105,67.5\n",
                "injuries": "team,player,status,role\n",
            }
            for role, content in rows.items():
                p = Path(tmp) / (role + ".csv")
                p.write_text(content, encoding="utf-8")
                files[role] = str(p)
            projection = from_claude_sport("CBB", files, "g1", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))
            self.assertEqual(projection.event_id, "g1")
            self.assertIn("NOT_CHRONOLOGICALLY_CALIBRATED", projection.warnings)

    def test_malformed_header_only_injuries_must_not_mean_zero_injuries(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            rows = {
                "games": "game_id,home,away,neutral\ng1,Home,Away,1\n",
                "teams": "team,games,adjoe,adjde,adj_t\nHome,1,105,105,67.5\nAway,1,105,105,67.5\n",
                "injuries": "unknown_column\n",
            }
            for role, content in rows.items():
                p = Path(tmp) / (role + ".csv")
                p.write_text(content, encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "CBB_INJURY_SOURCE_SCHEMA_INVALID"):
                from_claude_sport("CBB", files, "g1", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))

    def test_duplicate_injury_header_rejected_before_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            rows = {
                "games": "game_id,home,away,neutral\ng1,Home,Away,1\n",
                "teams": "team,games,adjoe,adjde,adj_t\nHome,1,105,105,67.5\nAway,1,105,105,67.5\n",
                "injuries": "team,player,status,status\nHome,Player A,out,questionable\n",
            }
            for role, content in rows.items():
                p = Path(tmp) / (role + ".csv")
                p.write_text(content, encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "CBB_INJURY_SOURCE_DUPLICATE_HEADER"):
                from_claude_sport("CBB", files, "g1", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))

    def test_blank_injury_status_is_not_a_verified_no_injuries_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            rows = {
                "games": "game_id,home,away,neutral\ng1,Home,Away,1\n",
                "teams": "team,games,adjoe,adjde,adj_t\nHome,1,105,105,67.5\nAway,1,105,105,67.5\n",
                "injuries": "team,player,status\nHome,Player A,\n",
            }
            for role, content in rows.items():
                p = Path(tmp) / (role + ".csv")
                p.write_text(content, encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "CBB_INJURY_SOURCE_ROW_INVALID"):
                from_claude_sport("CBB", files, "g1", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))

    def test_extra_injury_cells_are_rejected_not_silently_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            rows = {
                "games": "game_id,home,away,neutral\ng1,Home,Away,1\n",
                "teams": "team,games,adjoe,adjde,adj_t\nHome,1,105,105,67.5\nAway,1,105,105,67.5\n",
                "injuries": "team,player,status\nHome,Player A,out,questionable\n",
            }
            for role, content in rows.items():
                p = Path(tmp) / (role + ".csv")
                p.write_text(content, encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "CBB_INJURY_SOURCE_ROW_INVALID"):
                from_claude_sport("CBB", files, "g1", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))

    def test_noncanonical_injury_headers_fail_before_downstream_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            rows = {
                "games": "game_id,home,away,neutral\ng1,Home,Away,1\n",
                "teams": "team,games,adjoe,adjde,adj_t\nHome,1,105,105,67.5\nAway,1,105,105,67.5\n",
                "injuries": "Team,Player,Status\nHome,Player A,out\n",
            }
            for role, content in rows.items():
                p = Path(tmp) / (role + ".csv")
                p.write_text(content, encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "CBB_INJURY_SOURCE_SCHEMA_INVALID"):
                from_claude_sport("CBB", files, "g1",
                    asof_utc=datetime(2026, 11, 18, tzinfo=timezone.utc))

    def test_empty_injury_source_blocks_before_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            for role in ("games", "teams", "injuries"):
                p = Path(tmp) / (role + ".csv")
                p.write_text("game_id,home,away\n" if role == "games" else "team,games,adjoe,adjde,adj_t\n" if role == "teams" else "", encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "MODEL_FEATURE_FILE_EMPTY:injuries"):
                from_claude_sport("CBB", files, "test", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
