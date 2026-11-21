import json, os, tempfile, unittest, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from sportsedge.odds import daily_pilot_artifact_gate as gate
from sportsedge.validation import daily_ratings_capture as d

CSV = b"rank,team,adjoe,adjde,adjt\r\n" + b"".join(b"%d,T%d,107,105,70\r\n" % (i, i) for i in range(365))
JS = json.dumps([{"team": "T%d" % i, "year": 2026, "rating": 1,
                  "offense": {"rating": 31}, "defense": {"rating": 30},
                  "specialTeams": {"rating": 0}} for i in range(130)]).encode()
CBBD = json.dumps([{"team": "T%d" % i, "teamId": i + 1, "season": 2027,
                    "offensiveRating": 110, "defensiveRating": 101, "netRating": 9}
                   for i in range(365)]).encode()
KEYS = {"CFBD_API_KEY": "football-key", "CBBD_API_KEY": "basketball-key"}
NOW = datetime(2026, 11, 21, 16, tzinfo=timezone.utc)


def fake(url, key):
    if "api.collegebasketballdata.com" in url and key == KEYS["CBBD_API_KEY"]:
        return 200, CBBD
    if "api.collegefootballdata.com" in url and key == KEYS["CFBD_API_KEY"]:
        return 200, JS
    raise AssertionError("Unexpected provider or credential routing")


class T(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "a"

    def test_captures_both_with_hash(self):
        with patch.dict(os.environ, KEYS, clear=True):
            out = d.capture(self.root, d.api_sources(2027, 2026), fetch=fake)
        self.assertEqual([r["state"] for r in out["receipts"]], ["CAPTURED", "CAPTURED"])
        self.assertEqual((self.root / "cbbd_ratings_adjusted.json").read_bytes(), CBBD)
        self.assertEqual((self.root / "cfbd_ratings_sp.json").read_bytes(), JS)
        self.assertEqual([r["row_count"] for r in out["receipts"]], [130, 365])
        self.assertEqual((self.root / "receipt.json").stat().st_mode & 0o777, 0o600)

    def test_missing_cbbd_key_never_calls_cbbd_and_preserves_cfbd(self):
        with patch.dict(os.environ, {"CFBD_API_KEY": KEYS["CFBD_API_KEY"]}, clear=True):
            out = d.capture(self.root, d.api_sources(2027, 2026), fetch=fake)
        self.assertEqual(out["receipts"][0]["state"], "CAPTURED")
        self.assertEqual(out["receipts"][1]["state"], "BLOCKED_KEY_ABSENT")
        self.assertFalse((self.root / "cbbd_ratings_adjusted.json").exists())

    def test_html_or_403_is_blocked_not_data(self):
        def bad(url, key):
            return (200, b"<!DOCTYPE html><html>verify</html>") if "basketball" in url else (403, b"")
        with patch.dict(os.environ, KEYS, clear=True):
            out = d.capture(self.root, d.api_sources(2027, 2026), fetch=bad)
        self.assertEqual([r["state"] for r in out["receipts"]], ["BLOCKED_HTTP_403", "BLOCKED_INVALID_JSON"])
        self.assertFalse((self.root / "cbbd_ratings_adjusted.json").exists())

    def test_key_never_in_receipt(self):
        with patch.dict(os.environ, KEYS, clear=True):
            d.capture(self.root, d.api_sources(2027, 2026), fetch=fake)
        for key in KEYS.values():
            self.assertNotIn(key, (self.root / "receipt.json").read_text())

    def test_rejects_group_readable_dir(self):
        self.root.mkdir(mode=0o755)
        os.chmod(self.root, 0o755)
        with self.assertRaises(FileExistsError):
            d.capture(self.root, d.api_sources(2027, 2026), fetch=fake)

    def test_cbbd_validation_rejects_bad_population_ids_and_ratings(self):
        self.assertEqual(d._inspect("cbbd_json", CBBD, 2027), (None, 365))
        self.assertEqual(d._inspect("cbbd_json", CBBD, 2026)[0], "CBBD_WRONG_SEASON_OR_SCHEMA")
        rows = json.loads(CBBD)
        self.assertEqual(d._inspect("cbbd_json", json.dumps(rows[:349]).encode(), 2027),
                         ("CBBD_CENSUS_OUT_OF_RANGE", 349))
        for update, problem in (({"teamId": 2}, "CBBD_TEAM_IDENTITY_INVALID"),
                                ({"teamId": True}, "CBBD_TEAM_IDENTITY_INVALID"),
                                ({"team": " t1 "}, "CBBD_TEAM_IDENTITY_INVALID"),
                                ({"offensiveRating": "110"}, "CBBD_RATING_INVALID"),
                                ({"netRating": None}, "CBBD_RATING_INVALID")):
            changed = [{**rows[0], **update}, *rows[1:]]
            self.assertEqual(d._inspect("cbbd_json", json.dumps(changed).encode(), 2027)[0], problem)
        self.assertEqual(d._inspect("cbbd_json", CBBD.replace(b'"netRating": 9', b'"netRating": NaN', 1), 2027)[0],
                         "INVALID_JSON")

    def test_schema_and_wrong_season(self):
        junk = b"text\n" * 365
        self.assertEqual(d._inspect("csv", junk, 2027)[0], "CSV_SCHEMA")
        self.assertEqual(d._inspect("csv", CSV + b"1,bad\r\n", 2027)[0], "CSV_ROW_WIDTH")
        self.assertEqual(d._inspect("csv", CSV.replace(b"T2,107", b"T1,107"), 2027)[0],
                         "CSV_TEAM_OR_RATING_INVALID")
        self.assertEqual(d._inspect("json", JS, 2025)[0], "SP_WRONG_SEASON_OR_SCHEMA")
        records = json.loads(JS)
        self.assertEqual(d._inspect("json", json.dumps(records[:120]).encode(), 2026)[0], "SP_CENSUS_OUT_OF_RANGE")
        records[-1]["team"] = records[-2]["team"]
        self.assertEqual(d._inspect("json", json.dumps(records).encode(), 2026)[0], "SP_TEAM_OR_RATING_INVALID")
        self.assertEqual(d._inspect("json", b"[NaN]", 2026)[0], "INVALID_JSON")
        self.assertEqual(d._inspect("csv", b"x" * (d.MAX_BYTES + 1), 2027)[0], "BODY_TOO_LARGE")

    def test_redirect_not_followed(self):
        url = d.sources(2027, 2026)[1]["url"]
        with patch.object(d.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(url, 302, "Found", None, None)
            self.assertEqual(d._fetch(url, "SYNTHETIC_KEY"), (302, b""))
            handler = opener.call_args.args[0]
            self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://other.test/"))

    def test_response_read_is_bounded(self):
        url = d.api_sources(2027, 2026)[1]["url"]
        with patch.object(d.urllib.request, "build_opener") as opener:
            handle = opener.return_value.open.return_value.__enter__.return_value
            handle.geturl.return_value, handle.status, handle.read.return_value = url, 200, b"data"
            self.assertEqual(d._fetch(url, None), (200, b"data"))
            handle.read.assert_called_once_with(d.MAX_BYTES + 1)

    def test_after_fetch_clock_and_replay_gate(self):
        later = NOW + timedelta(seconds=5)
        cbbd = d.api_sources(2027, 2026)[1]
        with patch.dict(os.environ, KEYS, clear=True):
            out = d.capture(self.root, [cbbd], fetch=fake, clock=iter([NOW, later]).__next__)
        receipt = out["receipts"][0]
        opts = dict(source=cbbd["name"], season=2027, decision=later,
                    kickoff=later + timedelta(hours=2), max_age_seconds=600)
        self.assertEqual(d.eligible_bytes(CBBD, receipt, **opts), CBBD)
        for changes in ({"decision": NOW}, {"season": 2028}, {"kickoff": later},
                        {"decision": later + timedelta(seconds=601)}, {"source": "torvik_team_results"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                d.eligible_bytes(CBBD, receipt, **{**opts, **changes})
        with self.assertRaisesRegex(ValueError, "BYTES_MISMATCH"):
            d.eligible_bytes(CBBD.replace(b"110", b"111"), receipt, **opts)

    def test_claim_rollover_before_provider_calls(self):
        out = d.capture(self.root, d.api_sources(2027, 2026),
                        fetch=lambda *_: self.fail("provider call not allowed"),
                        clock=lambda: NOW, claim_date="2026-11-20")
        self.assertEqual([r["state"] for r in out["receipts"]], ["BLOCKED_CLAIM_DATE_CHANGED"] * 2)

    def test_original_torvik_file_import_never_fetches_or_backdates(self):
        original = self.root.parent / "original.csv"
        original.write_bytes(CSV)
        os.utime(original, (1, 1))
        src = d.sources(2027, 2026)[:1]
        out = d.capture(self.root, src, local_torvik=original, clock=lambda: NOW,
                        fetch=lambda *_: self.fail("must not call network"))
        row = out["receipts"][0]
        self.assertEqual(row["state"], "CAPTURED")
        self.assertEqual(row["observed_utc"], "2026-11-21T16:00:00Z")
        self.assertEqual(row["observation_basis"], "LOCAL_FILE_NOT_PROVIDER_ATTESTED")
        self.assertIsNone(row["http_status"])
        self.assertEqual((self.root / row["file"]).read_bytes(), CSV)

    def test_torvik_network_capture_is_refused_even_when_programmatic(self):
        with self.assertRaisesRegex(ValueError, "TORVIK_LOCAL_IMPORT_ONLY"):
            d.capture(self.root, d.sources(2027, 2026)[:1],
                      fetch=lambda *_: self.fail("must not call network"))
        self.assertFalse(self.root.exists())

    def test_durable_ratings_claim_isolated_from_nfl(self):
        repo = "bighauss/Sportsedge"
        rates = "daily-ratings-attempt-2026-11-21"
        marker = {"name": rates, "expired": False, "workflow_run": {"id": 123}}
        opts = dict(repository=repo, run_id="123", token="stub", now=NOW, pilot="ratings")
        seen = []

        def lookup(r, token, name):
            seen.append(name)
            rows = [marker] if name == rates and len(seen) >= 2 else []
            return {"total_count": len(rows), "artifacts": rows}

        root = self.root.parent
        self.assertEqual(gate.reserve(root, lookup=lookup, **opts)["name"], rates)
        self.assertEqual(gate.verify(root, lookup=lookup, **opts)["name"], rates)
        with self.assertRaisesRegex(gate.Blocked, "ALREADY_ATTEMPTED"):
            gate.reserve(root, lookup=lookup, **{**opts, "run_id": "456"})
        self.assertEqual(seen, [rates] * 3)


if __name__ == "__main__":
    unittest.main()
