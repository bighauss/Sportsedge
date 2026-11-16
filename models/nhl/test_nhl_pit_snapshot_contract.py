"""NHL original-source/PIT freeze contract: synthetic adversarial tests only."""
import copy
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from models.nhl import nhl_pit_snapshot_contract as m


def h(data):
    return "sha256:" + sha256(data).hexdigest()


class NHLSourceFreeze(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lineup = dict(event_id="EVT1", home_team_id="AAA",
                           away_team_id="BBB", home_goalie_id="GOALIE1",
                           away_goalie_id="GOALIE2", home_confirmed=True,
                           away_confirmed=True,
                           observed_utc="2026-11-14T14:00:00Z")
        self.raw = {
            "MODEL": b"frozen NHL candidate model\n",
            "TEAM_XG": b"team,xg\nAAA,2\nBBB,3\n",
            "GOALIE_STATS": b"goalie_id,team\nGOALIE1,AAA\nGOALIE2,BBB\n",
            "SKATER_STATS": b"player_id,team\n1234,AAA\n5678,BBB\n",
            "LINEUP": json.dumps(self.lineup, sort_keys=True).encode(),
        }
        sources = []
        for role, raw in self.raw.items():
            path = self.root / (role.lower() + ".txt")
            path.write_bytes(raw)
            sources.append({
                "role": role, "path": str(path),
                "sha256": h(raw), "provider": "CLAIMED_FEED",
                "data_through_utc": "2026-11-14T12:00:00Z",
                "published_utc": "2026-11-14T13:00:00Z",
                "observed_utc": "2026-11-14T14:00:00Z",
                "captured_utc": "2026-11-14T15:00:00Z",
            })
        self.manifest = {
            "schema": m.SCHEMA,
            "event": {
                "event_id": "EVT1", "home_team_id": "AAA",
                "away_team_id": "BBB", "home_goalie_id": "GOALIE1",
                "away_goalie_id": "GOALIE2",
                "freeze_utc": "2026-11-14T16:00:00Z",
                "kickoff_utc": "2026-11-15T23:00:00Z",
            },
            "sources": sources
        }

    def row(self, role):
        return next(x for x in self.manifest["sources"] if x["role"] == role)

    def test_all_original_bytes_and_timestamps_paper_0u(self):
        result = m.assess(self.manifest)
        self.assertEqual(set(result["roles_present"]), m.ROLES)
        self.assertEqual(result["official_market_count"], 0)
        self.assertFalse(result["release_certified"])
        self.assertEqual(result["approved_stake_u"], 0)
        self.assertFalse(result["external_provider_authentication"])
        self.assertTrue(all(x["provider_authenticated"] is False
                            for x in result["source_receipts"]))
        self.assertTrue(all("path" not in x for x in result["source_receipts"]))

    def test_missing_and_duplicate_role_are_blocked(self):
        self.manifest["sources"].pop()
        with self.assertRaisesRegex(m.Blocked, "REQUIRED_ROLE_CENSUS"):
            m.assess(self.manifest)
        self.manifest["sources"].append(copy.deepcopy(self.manifest["sources"][0]))
        with self.assertRaisesRegex(m.Blocked, "UNKNOWN_OR_DUPLICATE_ROLE"):
            m.assess(self.manifest)

    def test_modified_raw_bytes_are_blocked(self):
        Path(self.row("GOALIE_STATS")["path"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(m.Blocked, "SOURCE_BYTES_HASH_MISMATCH"):
            m.assess(self.manifest)

    def test_missing_and_truncated_raw_source_are_blocked(self):
        path = Path(self.row("TEAM_XG")["path"])
        path.unlink()
        with self.assertRaisesRegex(m.Blocked, "SOURCE_NOT_A_FILE"):
            m.assess(self.manifest)
        path.write_bytes(b"")
        with self.assertRaisesRegex(m.Blocked, "SOURCE_EMPTY_OR_TOO_LARGE"):
            m.assess(self.manifest)

    def test_after_puck_drop_and_late_source_are_blocked(self):
        self.manifest["event"]["freeze_utc"] = self.manifest["event"]["kickoff_utc"]
        with self.assertRaisesRegex(m.Blocked, "FREEZE_NOT_BEFORE_PUCK_DROP"):
            m.assess(self.manifest)
        self.manifest["event"]["freeze_utc"] = "2026-11-14T16:00:00Z"
        self.row("TEAM_XG")["captured_utc"] = "2026-11-15T23:00:00Z"
        with self.assertRaisesRegex(m.Blocked, "LATE_OR_CONTRADICTORY_SOURCE_CLOCK"):
            m.assess(self.manifest)

    def test_future_data_through_and_bad_publication_order(self):
        self.row("GOALIE_STATS")["data_through_utc"] = "2026-11-15T23:00:00Z"
        with self.assertRaisesRegex(m.Blocked, "LATE_OR_CONTRADICTORY_SOURCE_CLOCK"):
            m.assess(self.manifest)
        self.row("GOALIE_STATS")["data_through_utc"] = "2026-11-14T12:00:00Z"
        self.row("GOALIE_STATS")["published_utc"] = "2026-11-14T15:30:00Z"
        with self.assertRaisesRegex(m.Blocked, "LATE_OR_CONTRADICTORY_SOURCE_CLOCK"):
            m.assess(self.manifest)

    def test_no_naive_or_local_offsets(self):
        for value in ("2026-11-14T16:00:00", "2026-11-14T10:00:00-06:00"):
            self.manifest["event"]["freeze_utc"] = value
            with self.assertRaisesRegex(m.Blocked, "UTC_REQUIRED"):
                m.assess(self.manifest)

    def test_goalie_status_and_id_disagreement_block(self):
        self.lineup["away_confirmed"] = False
        self.rewrite_lineup()
        with self.assertRaisesRegex(m.Blocked, "STARTING_GOALIE_NOT_CONFIRMED"):
            m.assess(self.manifest)
        self.lineup["away_confirmed"] = True
        self.lineup["away_goalie_id"] = "DIFFERENT"
        self.rewrite_lineup()
        with self.assertRaisesRegex(m.Blocked, "LINEUP_AWAY_GOALIE_ID_MISMATCH"):
            m.assess(self.manifest)

    def rewrite_lineup(self):
        raw = json.dumps(self.lineup, sort_keys=True).encode()
        Path(self.row("LINEUP")["path"]).write_bytes(raw)
        self.row("LINEUP")["sha256"] = h(raw)

    def test_lineup_original_observed_timestamp_mismatch(self):
        self.lineup["observed_utc"] = "2026-11-14T13:00:00Z"
        self.rewrite_lineup()
        with self.assertRaisesRegex(m.Blocked, "LINEUP_ORIGINAL_OBSERVATION_MISMATCH"):
            m.assess(self.manifest)

    def test_public_repository_path_is_not_original_private_source(self):
        self.row("TEAM_XG")["path"] = str(Path(m.__file__).resolve())
        with self.assertRaisesRegex(m.Blocked, "SOURCE_INSIDE_PUBLIC_REPOSITORY"):
            m.assess(self.manifest)

    def test_reused_raw_file_across_distinct_roles_refused(self):
        self.row("SKATER_STATS")["path"] = self.row("GOALIE_STATS")["path"]
        with self.assertRaisesRegex(m.Blocked, "SAME_RAW_FILE_REUSED"):
            m.assess(self.manifest)

    def test_duplicate_json_key_and_nonfinite_refused_before_output(self):
        original = self.root / "manifest.json"
        output = self.root / "report.json"
        for body, expected in (
            ('{"schema":"v1","schema":"v2"}', "DUPLICATE_JSON_KEY"),
            ('{"schema":NaN}', "NONFINITE_JSON"),
        ):
            original.write_text(body)
            with self.assertRaisesRegex(m.Blocked, expected):
                m.report_file(original, output)
            self.assertFalse(output.exists())

    def test_lineup_malformed_json_and_duplicate_keys(self):
        raw = b'{"event_id":"EVT1","event_id":"EVT1"}'
        Path(self.row("LINEUP")["path"]).write_bytes(raw)
        self.row("LINEUP")["sha256"] = h(raw)
        with self.assertRaisesRegex(m.Blocked, "DUPLICATE_JSON_KEY"):
            m.assess(self.manifest)

    def test_report_create_only_permissions_and_sanitized_cli(self):
        manifest = self.root / "manifest.json"
        output = self.root / "report.json"
        manifest.write_text(json.dumps(self.manifest))
        with redirect_stdout(StringIO()) as capture:
            self.assertEqual(m.main([str(manifest), "--report", str(output)]), 0)
        self.assertIn("PAPER_0U", capture.getvalue())
        report = json.loads(output.read_text())
        self.assertEqual(report["manifest_sha256"], h(manifest.read_bytes()))
        self.assertEqual(report["approved_stake_u"], 0)
        if os.name == "posix":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            m.report_file(manifest, output)

    def test_no_private_manifest_or_report_in_public_repo(self):
        with self.assertRaisesRegex(m.Blocked, "SOURCE_INSIDE_PUBLIC_REPOSITORY"):
            m.report_file(Path(m.__file__), self.root / "out.json")
        with self.assertRaisesRegex(m.Blocked, "SOURCE_INSIDE_PUBLIC_REPOSITORY"):
            m.report_file(self.root / "MODEL.txt", Path(m.__file__).parent / "out.json")

    def test_source_file_swap_detected_on_second_read(self):
        original = m._bytes
        n = {"team": 0}

        def flaky(path, label):
            raw = original(path, label)
            if label == "TEAM_XG":
                n["team"] += 1
                if n["team"] == 2:
                    return raw + b"\nCHANGED"
            return raw

        with patch.object(m, "_bytes", side_effect=flaky):
            with self.assertRaisesRegex(m.Blocked, "SOURCE_CHANGED_DURING_FREEZE"):
                m.assess(self.manifest)


if __name__ == "__main__":
    unittest.main()
