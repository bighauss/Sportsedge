"""Synthetic contract checks; no genuine historical source evidence."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from historical_coverage_preflight import audit

class HistoricalCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        assets = []
        for role in ("model", "game_config", "salary", "roster", "final"):
            path = self.root / (role + ".txt")
            path.write_text("synthetic " + role)
            assets.append({"role": role, "path": path.name,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "source_id": "synthetic", "source_url": "https://example.org/synthetic",
                           "observed_utc": "2026-11-15T18:00:00Z" if role != "final" else "2026-11-16T03:00:00Z",
                           "captured_utc": "2026-11-15T18:01:00Z" if role != "final" else "2026-11-16T03:01:00Z"})
        self.slate = {"event_id": "SYNTHETIC", "kickoff_utc": "2026-11-16T01:20:00Z", "assets": assets}
    def run_audit(self):
        return audit({"slates": [self.slate]}, self.root)
    def test_local_complete_not_authenticated(self):
        r = self.run_audit()
        self.assertEqual(r["local_pit_complete"], 1)
        self.assertEqual(r["authenticated_pit_complete"], 0)
        self.assertEqual(r["official_eligible"], 0)
    def test_after_kickoff_salary_block(self):
        self.slate["assets"][2]["captured_utc"] = "2026-11-16T01:21:00Z"
        self.assertIn("POST_KICKOFF_INPUT:salary", self.run_audit()["slates"][0]["reasons"])
    def test_hash_tamper_block(self):
        (self.root/"model.txt").write_text("changed")
        self.assertIn("HASH_MISMATCH:model", self.run_audit()["slates"][0]["reasons"])
    def test_missing_roster_block(self):
        self.slate["assets"] = [a for a in self.slate["assets"] if a["role"] != "roster"]
        self.assertIn("MISSING_ROLE:roster", self.run_audit()["slates"][0]["reasons"])
    def test_duplicate_role_block(self):
        self.slate["assets"].append(dict(self.slate["assets"][0]))
        self.assertIn("DUPLICATE_ROLE:model", self.run_audit()["slates"][0]["reasons"])
    def test_naive_timestamp_block(self):
        self.slate["assets"][0]["observed_utc"] = "2026-11-15T18:00:00"
        self.assertIn("INVALID_ASSET_TIME:model", self.run_audit()["slates"][0]["reasons"])
    def test_missing_source_block(self):
        self.slate["assets"][0]["source_id"] = ""
        self.assertIn("MISSING_SOURCE:model", self.run_audit()["slates"][0]["reasons"])
    def test_path_escape_block(self):
        self.slate["assets"][0]["path"] = "../outside.txt"
        self.assertIn("MISSING_OR_ESCAPED_FILE:model", self.run_audit()["slates"][0]["reasons"])
    def test_duplicate_event_block(self):
        r = audit({"slates": [self.slate, self.slate]}, self.root)
        self.assertEqual(r["local_pit_complete"], 0)
        self.assertTrue(all("DUPLICATE_EVENT" in x["reasons"] for x in r["slates"]))
    def test_pre_kickoff_final_block(self):
        self.slate["assets"][-1]["observed_utc"] = "2026-11-15T18:00:00Z"
        self.assertIn("PRE_KICKOFF_FINAL:final", self.run_audit()["slates"][0]["reasons"])

if __name__ == "__main__":
    unittest.main()
