import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.sportsleader.run_intake import run
from research.sportsleader.intake import ROOT

class RunIntakeTests(unittest.TestCase):
    def test_orchestration(self):
        entry = dict(league="cbb", dataset="games", season=2025,
                     url=ROOT+"cbb_games/2025.parquet", sha256="a"*64,
                     bytes=100, rows=2)
        with tempfile.TemporaryDirectory() as root:
            manifest = Path(root)/"manifest.json"
            manifest.write_text(json.dumps([entry]))
            with patch("research.sportsleader.run_intake.ingest", return_value=Path(root)/"asset") as ingest:
                result = run(manifest, "cbb", "games", 2025, root)
                ingest.assert_called_once_with(entry, root)
                self.assertEqual(result["release_state"], "PAPER_0U_NON_COUNTED")
                self.assertEqual(result["entry"], entry)
            with patch("research.sportsleader.run_intake.ingest") as ingest:
                with self.assertRaises(ValueError):
                    run(manifest, "nfl", "games", 2025, root)
                ingest.assert_not_called()
