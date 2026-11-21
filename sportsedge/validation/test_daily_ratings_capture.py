import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from sportsedge.validation import daily_ratings_capture as d

CSV = b"rank,team,adjoe\n" + b"".join(b"%d,T%d,107\n" % (i, i) for i in range(365))
JS = json.dumps([{"team": "T%d" % i, "rating": 1} for i in range(130)]).encode()


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
        self.assertEqual([r["state"] for r in out["receipts"]], ["BLOCKED_HTML_NOT_CSV", "BLOCKED_HTTP_403"])
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


if __name__ == "__main__":
    unittest.main()
