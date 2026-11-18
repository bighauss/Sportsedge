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
                p.write_text("game_id,home,away\\n" if role == "games" else "team,games,adjoe,adjde,adj_t\\n", encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "CBB_CRITICAL_INJURY_SOURCE_REQUIRED"):
                from_claude_sport("CBB", files, "test", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))

    def test_empty_injury_source_blocks_before_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            for role in ("games", "teams", "injuries"):
                p = Path(tmp) / (role + ".csv")
                p.write_text("game_id,home,away\\n" if role == "games" else "team,games,adjoe,adjde,adj_t\\n" if role == "teams" else "", encoding="utf-8")
                files[role] = str(p)
            with self.assertRaisesRegex(ValueError, "MODEL_FEATURE_FILE_EMPTY:injuries"):
                from_claude_sport("CBB", files, "test", asof_utc=datetime(2026,11,18,tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
