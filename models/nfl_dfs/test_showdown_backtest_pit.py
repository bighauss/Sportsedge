"""Synthetic-only regression tests; never treated as historical DFS evidence."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from showdown_backtest_pit import score

def put(p, content):
    p.write_text(content)
    return hashlib.sha256(p.read_bytes()).hexdigest()

class PITBacktestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        pd = put(self.root/"projections.csv", "player,mean\nA,12\nB,8\n")
        ad = put(self.root/"actual.csv", "player,dk_points\nA,10\nB,12\n")
        self.m = dict(event_id="SYNTHETIC", kickoff_at="2026-11-15T19:00:00-06:00",
                      snapshot_at="2026-11-15T18:00:00-06:00",
                      final_at="2026-11-16T00:00:00-06:00",
                      final_source_url="https://example.org/synthetic",
                      model_sha256="a"*64, projections_file="projections.csv",
                      projections_sha256=pd, actual_points_file="actual.csv",
                      actual_points_sha256=ad)
    def test_scores(self):
        r=score(self.m,self.root)
        self.assertEqual(r["matched_players"],2)
        self.assertEqual(r["mae"],3)
        self.assertEqual(r["rmse"],round((20/2)**0.5,4))
        self.assertEqual(r["bias"],-1)
        self.assertIn("BLOCKED",r["contest_ev"])
    def test_post_kickoff_snapshot_rejected(self):
        self.m["snapshot_at"]="2026-11-15T20:00:00-06:00"
        with self.assertRaisesRegex(ValueError,"point-in-time"):
            score(self.m,self.root)
    def test_modified_actuals_rejected(self):
        (self.root/"actual.csv").write_text("player,dk_points\nA,999\n")
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            score(self.m,self.root)
    def test_escape_rejected(self):
        self.m["actual_points_file"]="../actual.csv"
        with self.assertRaisesRegex(ValueError,"outside"):
            score(self.m,self.root)
    def test_duplicate_identity_rejected(self):
        self.m["actual_points_sha256"]=put(self.root/"actual.csv","player,dk_points\nA,10\nA,12\n")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            score(self.m,self.root)
    def test_naive_time_rejected(self):
        self.m["final_at"]="2026-11-16T00:00:00"
        with self.assertRaisesRegex(ValueError,"UTC offset"):
            score(self.m,self.root)
    def test_lineup_grading(self):
        lineup={"top_by_mean":[{"cpt":"A","flex":["B","C","D","E","F"]}]}
        self.m["lineups_file"]="lineups.json"
        self.m["lineups_sha256"]=put(self.root/"lineups.json",json.dumps(lineup))
        self.assertEqual(score(self.m,self.root)["graded_lineups"],[])

if __name__=="__main__":
    unittest.main()
