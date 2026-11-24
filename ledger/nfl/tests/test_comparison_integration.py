"""Synthetic integration only; never real performance evidence."""
import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison import compare
from freeze import freeze, verify
from settle import settle
from scorecard import load_week


class ComparisonIntegration(unittest.TestCase):
    def test_freeze_settle_compare_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = root / "board.csv"
            board.write_text("quote_id\nq1\n")
            projection = root / "projection.json"
            projection.write_text("{}")
            picks = {}
            for label, p, selected in (("baseline", .8, "true"), ("challenger", .6, "")):
                path = root / (label + ".csv")
                row = dict(row_id=0, quote_id="q1", market="ml", pick="WAS",
                           price=-110, model_p=p, market_p=.5, blend_p=.6,
                           selected_for_card=selected, approved_stake_u=0)
                with path.open("w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerow(row)
                picks[label] = str(path)
            runs_dir, settlements = root / "runs", root / "settlements"
            run = freeze("CIN@WAS", str(board), str(projection), picks,
                         runs_dir=str(runs_dir), start_utc="2026-11-24T01:00:00Z",
                         now=datetime(2026, 11, 23, tzinfo=timezone.utc))
            before = {str(p): p.read_bytes() for p in Path(run).rglob("*") if p.is_file()}
            settle(run, dict(away="CIN", home="WAS", away_score=10, home_score=20),
                   "SYNTHETIC TEST ONLY", settle_dir=str(settlements))
            saved = {str(p): p.read_bytes() for p in settlements.glob("*")}
            report = compare(load_week("2026-11-23", "2026-11-23", str(runs_dir),
                                       str(settlements)), "baseline", "challenger")
            score = report["scores"]["model_p"]
            self.assertAlmostEqual(score["left"], .04)
            self.assertAlmostEqual(score["right"], .16)
            self.assertEqual(score["n"], 1)
            self.assertEqual(report["selection"]["challenger"]["unknown"], 1)
            self.assertFalse(verify(run))
            self.assertEqual(before, {str(p): p.read_bytes() for p in Path(run).rglob("*") if p.is_file()})
            self.assertEqual(saved, {str(p): p.read_bytes() for p in settlements.glob("*")})
            # Tamper detection uses the same verifier used by the report CLI.
            target = Path(run) / "inputs" / "board.csv"
            os.chmod(target, 0o600)
            target.write_text("tampered")
            loaded = load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements))
            loaded[0]["quarantined"] = bool(verify(run))
            excluded = compare(loaded, "baseline", "challenger")
            self.assertEqual(excluded["counts"]["excluded_runs"], 1)
            self.assertEqual(excluded["scores"]["model_p"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
