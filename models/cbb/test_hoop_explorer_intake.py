"""Synthetic tests for phone-friendly Hoop-Explorer intake; no provider access."""
from pathlib import Path
import csv
import hashlib
import io
import json
import tempfile
import unittest

import hoop_explorer_intake as intake
import hoop_explorer_research as research


class ExportIntakeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def sample(self, *, fmt="csv", rows=None):
        rows = rows if rows is not None else [
            {"pid": "p1", "tid": "umd", "season": "2027",
             "minutes": "100", "rapm": "2.1", "name": "Sample Player"},
            {"pid": "p2", "tid": "ind", "season": "2027",
             "minutes": "500", "rapm": "1.7", "name": "Second Player"},
        ]
        if fmt == "csv":
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            raw = stream.getvalue().encode("utf-8")
        else:
            raw = json.dumps({"rows": rows}).encode("utf-8")
        path = self.root / ("export." + fmt)
        path.write_bytes(raw)
        return path

    def draft(self, path):
        output = intake.inspect_export(path, "player")
        m = output["draft_manifest"]
        m.update({
            "source_url": "https://hoop-explorer.com/PlayerLeaderboard",
            "access_basis": "manual_user_export",
            "scope_id": "2027-mens-d1",
            "season": 2027,
            "columns": {"player_id": "pid", "team_id": "tid",
                        "season": "season", "minutes": "minutes",
                        "rapm": "rapm", "name": "name"},
        })
        return m

    def test_draft_exposes_headers_but_not_raw_values(self):
        file = self.sample()
        result = intake.inspect_export(file, "player")
        self.assertEqual(result["observed_headers"], sorted(["pid", "tid", "season", "minutes", "rapm", "name"]))
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["sha256"], hashlib.sha256(file.read_bytes()).hexdigest())
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["data_values_included"])
        self.assertFalse(result["pregame_eligible"])
        self.assertEqual(result["draft_manifest"]["published_utc"], None)
        self.assertFalse(result["official"])
        self.assertNotIn("Sample Player", json.dumps(result))

    def test_json_inspection(self):
        result = intake.inspect_export(self.sample(fmt="json"), "player")
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["draft_manifest"]["format"], "json")

    def test_unmapped_template_is_not_auto_admitted(self):
        file = self.sample()
        result = intake.inspect_export(file, "player")
        mpath = self.root / "template.json"
        mpath.write_text(json.dumps(result["draft_manifest"]))
        with self.assertRaises(research.Blocked):
            research.load_export(file, mpath, kind="player", exploratory=True)

    def test_exploratory_missing_timestamps_is_explicitly_non_pit(self):
        file = self.sample()
        m = self.draft(file)
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(m))
        players, evidence = research.load_export(
            file, manifest, kind="player", exploratory=True)
        self.assertEqual(len(players), 2)
        self.assertFalse(evidence["point_in_time_admissible"])
        self.assertFalse(evidence["clock_consistent_not_source_authenticated"])
        self.assertEqual(evidence["provenance_status"], "UNVERIFIED_EXPLORATORY_NO_PIT")
        report = research.research_report(players, evidence, target_player_id="p1")
        self.assertFalse(report["official"])
        self.assertEqual(report["stake_u"], 0)
        self.assertFalse(report["pricing_enabled"])

    def test_strict_mode_rejects_missing_clocks_even_if_exploration_can_load(self):
        file = self.sample()
        m = self.draft(file)
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(m))
        with self.assertRaisesRegex(research.Blocked, "UTC_Z_REQUIRED"):
            research.load_export(
                file, manifest, kind="player", exploratory=False,
                freeze_utc="2026-11-15T18:00:00Z",
                tipoff_utc="2026-11-15T19:00:00Z")

    def test_digest_not_skipped_by_exploration(self):
        file = self.sample()
        m = self.draft(file)
        m["sha256"] = "0" * 64
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(m))
        with self.assertRaisesRegex(research.Blocked, "EXPORT_HASH_MISMATCH"):
            research.load_export(file, manifest, kind="player", exploratory=True)

    def test_cli_exploration_does_not_require_event_freeze(self):
        file = self.sample()
        mpath = self.root / "manifest.json"
        mpath.write_text(json.dumps(self.draft(file)))
        out = self.root / "report.json"
        research.main([
            "--players-export", str(file), "--players-manifest", str(mpath),
            "--target-player-id", "p1", "--exploratory", "--out", str(out)
        ])
        j = json.loads(out.read_text())
        self.assertFalse(j["official"])
        self.assertFalse(j["evidence"][0]["point_in_time_admissible"])

    def test_inspector_does_not_guess_missing_identifiers(self):
        path = self.sample(rows=[{"player": "Some Person", "minutes": "20"}])
        result = intake.inspect_export(path, "player")
        self.assertNotIn("player_id", result["observed_headers"])
        self.assertIsNone(result["draft_manifest"]["columns"]["player_id"])

    def test_empty_and_non_json_blocked(self):
        path = self.root/"empty.csv"
        path.write_bytes(b"")
        with self.assertRaisesRegex(research.Blocked, "EXPORT_EMPTY"):
            intake.inspect_export(path, "player")
        path = self.root/"bad.json"
        path.write_bytes(b"not json")
        with self.assertRaises(research.Blocked):
            intake.inspect_export(path, "player")

    def test_manifest_cli_output(self):
        file = self.sample()
        dest = self.root/"draft.json"
        intake.main(["--input", str(file), "--kind", "player", "--out", str(dest)])
        self.assertEqual(json.loads(dest.read_text())["rows"], 2)


if __name__ == "__main__":
    unittest.main()
