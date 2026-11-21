import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from sportsedge.validation import daily_ratings_capture as d

CSV = b"rank,team,adjoe,adjde,adj_t\n" + b"".join(
    b"%d,T%d,107,107,69\n" % (i, i) for i in range(365))
JS = json.dumps([{"team": "T%d" % i, "rating": 1,
                  "offense": {"rating": 30}, "defense": {"rating": 25},
                  "specialTeams": {"rating": 0}} for i in range(138)]).encode()


def fake(url, key):
    return (200, CSV) if "barttorvik" in url else (200, JS)


class T(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / "a"

    def test_captures_both_with_hash(self):
        with patch.dict(os.environ, {"CFBD_API_KEY": "k"}):
            out = d.capture(self.root, d.sources(2027, 2026), fetch=fake)
        self.assertEqual([r["state"] for r in out["receipts"]], ["CAPTURED", "CAPTURED"])
        self.assertEqual((self.root / "torvik_team_results.csv").read_bytes(), CSV)
        self.assertEqual((self.root / "receipt.json").stat().st_mode & 0o777, 0o600)

    def test_missing_key_never_calls_cfbd(self):
        calls = []
        with patch.dict(os.environ, {}, clear=True):
            out = d.capture(self.root, d.sources(2027, 2026),
                            fetch=lambda u, k: (calls.append(u), fake(u, k))[1])
        self.assertEqual(out["receipts"][1]["state"], "BLOCKED_KEY_ABSENT")
        self.assertTrue(all("barttorvik" in u for u in calls))

    def test_html_or_403_is_blocked_not_data(self):
        def bad(url, key):
            return (200, b"<!DOCTYPE html><html>verify</html>") if "barttorvik" in url else (403, b"")
        with patch.dict(os.environ, {"CFBD_API_KEY": "k"}):
            out = d.capture(self.root, d.sources(2027, 2026), fetch=bad)
        self.assertEqual([r["state"] for r in out["receipts"]], ["BLOCKED_HTML_NOT_RATINGS", "BLOCKED_HTTP_403"])
        self.assertFalse((self.root / "torvik_team_results.csv").exists())

    def test_key_never_in_receipt(self):
        with patch.dict(os.environ, {"CFBD_API_KEY": "SECRETVALUE"}):
            d.capture(self.root, d.sources(2027, 2026), fetch=fake)
        self.assertNotIn("SECRETVALUE", (self.root / "receipt.json").read_text())

    def test_rejects_group_readable_dir(self):
        self.root.mkdir(mode=0o755)
        os.chmod(self.root, 0o755)
        with self.assertRaises(ValueError):
            d.capture(self.root, d.sources(2027, 2026), fetch=fake)


    def test_rejects_long_but_schema_weak_csv(self):
        bad = b"rank,team,adjoe\n" + b"".join(
            b"%d,T%d,107\n" % (i, i) for i in range(365))
        self.assertEqual(d.check_body("csv", bad), "CSV_REQUIRED_RATINGS_MISSING")

    def test_rejects_duplicated_or_nonfinite_torvik_ratings(self):
        duplicate = CSV.replace(b"T364", b"T363")
        self.assertEqual(d.check_body("csv", duplicate), "CSV_TEAM_DUPLICATE_OR_MISSING")
        self.assertEqual(d.check_body("csv", CSV.replace(b",107,107,69", b",nan,107,69", 1)),
                         "CSV_RATINGS_INVALID")

    def test_rejects_weaker_or_duplicate_cfbd_json(self):
        weak = json.dumps([{"team": "T%d" % i, "rating": 1} for i in range(138)]).encode()
        self.assertEqual(d.check_body("json", weak), "CFBD_RATING_SCHEMA_INVALID")
        repeated = json.loads(JS)
        repeated[-1]["team"] = repeated[-2]["team"]
        self.assertEqual(d.check_body("json", json.dumps(repeated).encode()),
                         "CFBD_TEAM_DUPLICATE_OR_MISSING")

    def test_undercount_or_html_json_is_blocked(self):
        self.assertEqual(d.check_body("json", b"<html>Authentication required</html>"),
                         "HTML_NOT_RATINGS")
        self.assertEqual(d.check_body("json", JS.replace(b'"team": "T137"', b'"team": "T136"')),
                         "CFBD_TEAM_DUPLICATE_OR_MISSING")
        self.assertEqual(d.check_body("json", json.dumps(json.loads(JS)[:101]).encode()),
                         "CFBD_FBS_CENSUS_INCOMPLETE")

    def test_source_redirect_refused_before_following_authorization(self):
        import urllib.error
        from unittest.mock import patch as mock_patch
        fake_request = urllib.error.HTTPError(
            "https://api.collegefootballdata.com/ratings/sp?year=2026",
            302, "Found", None, None)
        with mock_patch("sportsedge.validation.daily_ratings_capture.urllib.request.build_opener") as op:
            op.return_value.open.side_effect = fake_request
            self.assertEqual(d._fetch("https://api.collegefootballdata.com/ratings/sp?year=2026",
                                     "SYNTHETIC_KEY"), (302, b""))
        self.assertEqual(d._NoRedirect().redirect_request(None, None, 302, "Found", {},
            "https://attacker.invalid/"), None)

    def test_response_bytes_are_bounded(self):
        with patch("sportsedge.validation.daily_ratings_capture.urllib.request.build_opener") as op:
            import io
            class Response:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def geturl(self): return "https://barttorvik.com/2027_team_results.csv"
                def read(self, n): return b"0" * n
            op.return_value.open.return_value = Response()
            self.assertEqual(d._fetch("https://barttorvik.com/2027_team_results.csv", None),
                             (413, b""))


if __name__ == "__main__":
    unittest.main()
