"""Provider-free adversarial tests for NBA prior-only boxscore rate extraction."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from models.nba import nba_pit_boxscore_rates as M

TARGET = "2026-11-23T00:00:00Z"


def box(gid, *, pid="1001", status=3):
    return {
        "game": {
            "gameId": gid, "gameStatus": status,
            "gameTimeUTC": "2026-11-20T18:00:00Z",
            "homeTeam": {
                "teamId": 1610612737, "teamTricode": "ATL",
                "players": [
                    {"personId": pid, "played": "1",
                     "statistics": {"minutes": "PT30M0S", "points": 20,
                                    "reboundsTotal": 8, "assists": 4,
                                    "threePointersMade": 3}},
                    {"personId": "1002", "played": False, "statistics": {}},
                ]},
            "awayTeam": {
                "teamId": 1610612741, "teamTricode": "CHI",
                "players": [
                    {"personId": "2001", "played": True,
                     "statistics": {"minutes": "23:30", "points": 12,
                                    "reboundsTotal": 6, "assists": 2,
                                    "threePointersMade": 2}},
                ]}
        }
    }


def write_manifest(folder, n=5):
    folder = Path(folder)
    entries = []
    for i in range(n):
        gid = f"002260{i:04d}"
        raw = json.dumps(box(gid), sort_keys=True).encode()
        path = "boxscore_" + gid + ".json"
        (folder / path).write_bytes(raw)
        entries.append({"game_id": gid, "path": path,
                        "source_url": "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_" + gid + ".json",
                        "captured_at_utc": "2026-11-20T22:00:00Z",
                        "sha256": hashlib.sha256(raw).hexdigest()})
    manifest = {"schema": M.SCHEMA, "target_game_id": "0022609999",
                "target_tipoff_utc": TARGET, "records": entries}
    p = folder / "receipt-manifest.json"
    p.write_text(json.dumps(manifest))
    return p, manifest


def replace_box(path, gid, payload):
    name = path.parent / ("boxscore_" + gid + ".json")
    raw = json.dumps(payload, sort_keys=True).encode()
    name.write_bytes(raw)
    manifest = json.loads(path.read_text())
    for item in manifest["records"]:
        if item["game_id"] == gid:
            item["sha256"] = hashlib.sha256(raw).hexdigest()
    path.write_text(json.dumps(manifest))


class PriorBoxscoreRateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.path, self.data = write_manifest(self.root)

    def tearDown(self):
        self.dir.cleanup()

    def test_prior_only_player_rates_and_no_fake_minutes_projection(self):
        r = M.build_report(self.path)
        self.assertEqual(r["source_records"], 5)
        self.assertEqual(r["played_athletes"], 2)
        a = next(v for v in r["players"] if v["player_id"] == "1001")
        self.assertEqual(a["status"], "HISTORICAL_RATE_ONLY")
        self.assertEqual(a["sample_games"], 5)
        self.assertAlmostEqual(a["minutes_baseline_last5"], 30)
        self.assertAlmostEqual(a["pts_pm"], 20 / 30, delta=1e-6)
        self.assertAlmostEqual(a["fg3_pm"], 0.1, delta=1e-6)
        self.assertFalse(a["availability_verified"])
        self.assertFalse(a["minutes_projection_verified"])
        self.assertFalse(a["usable_for_betting"])
        self.assertFalse(r["authenticated_capture"])
        self.assertEqual(r["official_counted"], 0)
        self.assertEqual(r["approved_stake_u"], 0)
        self.assertTrue(all(len(row["source_sha256"]) == 64 for row in r["lineage"]))

    def test_small_prior_sample_not_established_forecast(self):
        self.path, _ = write_manifest(self.root, n=2)
        report = M.build_report(self.path)
        self.assertEqual(report["source_records"], 2)
        self.assertTrue(all(x["status"] == "INSUFFICIENT_PRIOR_GAMES"
                            for x in report["players"]))

    def test_post_tipoff_capture_rejected(self):
        m = copy.deepcopy(self.data)
        m["records"][0]["captured_at_utc"] = "2026-11-23T00:05:00Z"
        self.path.write_text(json.dumps(m))
        with self.assertRaisesRegex(M.InputBlocked, "POST_TIPOFF_CAPTURE"):
            M.build_report(self.path)

    def test_original_hash_tamper_rejected(self):
        item = self.data["records"][0]
        (self.root / item["path"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(M.InputBlocked, "ORIGINAL_SHA_MISMATCH|ORIGINAL_SIZE_INVALID"):
            M.build_report(self.path)

    def test_original_game_not_final_rejected(self):
        gid = self.data["records"][0]["game_id"]
        replace_box(self.path, gid, box(gid, status=2))
        with self.assertRaisesRegex(M.InputBlocked, "SOURCE_NOT_FINAL"):
            M.build_report(self.path)

    def test_duplicate_event_rejected(self):
        m = copy.deepcopy(self.data)
        m["records"].append(copy.deepcopy(m["records"][0]))
        self.path.write_text(json.dumps(m))
        with self.assertRaisesRegex(M.InputBlocked, "DUPLICATE_OR_TARGET_EVENT"):
            M.build_report(self.path)

    def test_team_player_id_collision_rejected(self):
        gid = self.data["records"][0]["game_id"]
        payload = box(gid)
        payload["game"]["awayTeam"]["players"][0]["personId"] = "1001"
        replace_box(self.path, gid, payload)
        with self.assertRaisesRegex(M.InputBlocked, "DUPLICATE_OR_MISSING_ATHLETE_ID"):
            M.build_report(self.path)

    def test_no_undated_or_postgame_fabricated_source(self):
        m = copy.deepcopy(self.data)
        m["records"][0]["captured_at_utc"] = ""
        self.path.write_text(json.dumps(m))
        with self.assertRaisesRegex(M.InputBlocked, "INVALID_UTC_CAPTURE"):
            M.build_report(self.path)

    def test_pre_final_capture_is_inconsistent(self):
        m = copy.deepcopy(self.data)
        m["records"][0]["captured_at_utc"] = "2026-11-20T17:59:00Z"
        self.path.write_text(json.dumps(m))
        with self.assertRaisesRegex(M.InputBlocked, "SOURCE_NOT_PRIOR_AND_COMPLETE"):
            M.build_report(self.path)

    def test_invalid_minute_and_numeric_rates_blocked(self):
        gid = self.data["records"][0]["game_id"]
        payload = box(gid)
        payload["game"]["homeTeam"]["players"][0]["statistics"]["minutes"] = "30:75"
        replace_box(self.path, gid, payload)
        with self.assertRaisesRegex(M.InputBlocked, "INVALID_PLAYER_MINUTES"):
            M.build_report(self.path)

    def test_game_id_and_provider_allowlist_guard(self):
        m = copy.deepcopy(self.data)
        m["records"][0]["source_url"] = "https://sportsbook.example/price"
        self.path.write_text(json.dumps(m))
        with self.assertRaisesRegex(M.InputBlocked, "SOURCE_URL_NOT_ALLOWLISTED"):
            M.build_report(self.path)

    def test_absolute_path_and_symlink_rejected(self):
        m = copy.deepcopy(self.data)
        m["records"][0]["path"] = "/tmp/not-a-source.json"
        self.path.write_text(json.dumps(m))
        with self.assertRaisesRegex(M.InputBlocked, "UNSAFE_SOURCE_PATH"):
            M.build_report(self.path)


if __name__ == "__main__":
    unittest.main()
