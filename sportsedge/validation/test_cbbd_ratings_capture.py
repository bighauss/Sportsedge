import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from sportsedge.validation import daily_ratings_capture as d

CB = json.dumps([{"season": 2027, "teamId": i + 1, "team": "T%d" % i, "conference": "C",
                  "offensiveRating": 110.5, "defensiveRating": 104.0, "netRating": 6.5,
                  "rankings": {}} for i in range(365)]).encode()


class CBBD(unittest.TestCase):
    def test_runner_sources_skip_torvik(self):
        names = [s["name"] for s in d.automated_sources(2027, 2026)]
        self.assertEqual(names, ["cbbd_ratings_adjusted", "cfbd_ratings_sp"])

    def test_valid_payload(self):
        self.assertEqual(d._inspect("cbbd_json", CB, 2027), (None, 365))

    def test_rejects_bad_payloads(self):
        rows = json.loads(CB)
        self.assertEqual(d._inspect("cbbd_json", CB, 2026)[0], "CBBD_WRONG_SEASON_OR_SCHEMA")
        self.assertEqual(d._inspect("cbbd_json", json.dumps(rows[:200]).encode(), 2027)[0],
                         "CBBD_CENSUS_OUT_OF_RANGE")
        dup = [dict(r) for r in rows]; dup[1]["team"] = "T0"
        self.assertEqual(d._inspect("cbbd_json", json.dumps(dup).encode(), 2027)[0],
                         "CBBD_TEAM_OR_RATING_INVALID")
        dup_id = [dict(r) for r in rows]; dup_id[1]["teamId"] = dup_id[0]["teamId"]
        self.assertEqual(d._inspect("cbbd_json", json.dumps(dup_id).encode(), 2027)[0],
                         "CBBD_TEAM_INVALID")
        bad = [dict(r) for r in rows]; bad[0]["offensiveRating"] = "110"
        self.assertEqual(d._inspect("cbbd_json", json.dumps(bad).encode(), 2027)[0],
                         "CBBD_TEAM_OR_RATING_INVALID")
        self.assertEqual(d._inspect("cbbd_json", b"<html>denied</html>", 2027)[0], "INVALID_JSON")

    def test_capture_with_key_and_without(self):
        src = [d.cbbd_source(2027)]
        with tempfile.TemporaryDirectory() as t:
            with patch.dict(os.environ, {"CBBD_API_KEY": "k"}):
                out = d.capture(Path(t) / "a", src, fetch=lambda u, k: (200, CB))
            self.assertEqual(out["receipts"][0]["state"], "CAPTURED")
            self.assertEqual((Path(t) / "a" / "cbbd_ratings_adjusted.json").read_bytes(), CB)
            self.assertNotIn("k\"", json.dumps(out))
            env = {k: v for k, v in os.environ.items() if k != "CBBD_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                out = d.capture(Path(t) / "b", src, fetch=lambda *_: self.fail("no call"))
            self.assertEqual(out["receipts"][0]["state"], "BLOCKED_KEY_ABSENT")

    def test_torvik_network_capture_is_refused(self):
        with tempfile.TemporaryDirectory() as t, self.assertRaisesRegex(ValueError, "TORVIK_LOCAL_IMPORT_ONLY"):
            d.capture(Path(t) / "archive", d.sources(2027, 2026)[:1],
                      fetch=lambda *_: self.fail("network must not be called"))


if __name__ == "__main__":
    unittest.main()
