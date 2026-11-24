import hashlib
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from tools.cbb_run_request import resolve_request

class RunRequest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 24, 16, tzinfo=timezone.utc)
        p = "models/cbb/lines/board_2026-11-24_fixture.csv"
        board = self.root / p
        board.parent.mkdir(parents=True)
        raw = b"synthetic board\n"
        board.write_bytes(raw)
        self.request = {
            "schema": "cbb-paper-run-request-v1", "date_ct": "2026-11-24",
            "board_path": p, "board_blob_sha": hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
            "board_captured_utc": "2026-11-24T15:00:00Z", "season": 2027,
            "totals_order_verified": False, "label": "PAPER_0U",
        }

    def test_valid(self):
        out = resolve_request(self.root, self.request, self.now)
        self.assertEqual(out["board"], self.request["board_path"])
        self.assertEqual(out["season"], "2027")
        self.assertEqual(out["totals_verified"], "false")

    def test_rejects_invalid_requests(self):
        for key, value in (
            ("date_ct", "2026-11-23"), ("board_path", "../outside.csv"),
            ("board_blob_sha", "wrong"), ("season", 2026),
            ("label", "LIVE"), ("totals_order_verified", "false"),
            ("board_captured_utc", "2026-11-24T17:00:00Z"),
            ("board_captured_utc", "2026-11-22T15:00:00Z"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                resolve_request(self.root, dict(self.request, **{key: value}), self.now)

    def test_tampered_board(self):
        (self.root / self.request["board_path"]).write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "REQUEST_BOARD_HASH"):
            resolve_request(self.root, self.request, self.now)

if __name__ == "__main__":
    unittest.main()
