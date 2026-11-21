"""Offline Torvik original-byte capture tests. Synthetic team fixtures only."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from torvik_exact_raw_capture import Reject, extract, download, persist


def synthetic(n=360, oe=107, tempo=69):
    head = "team,adjoe,adjde,adj_t\n"
    return (head + "".join(f"Fake Team {i},{oe},{oe},{tempo}\n" for i in range(n))).encode()


class TestTorvikRawCapture(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)

    def test_full_candidate_mean_and_no_full_source_claim(self):
        x = extract(synthetic())
        self.assertEqual(x["n_teams"], 360)
        self.assertEqual(x["arithmetic_mean_oe"], 107)
        self.assertEqual(x["arithmetic_mean_tempo"], 69)
        self.assertFalse(x["season_census_verified"])
        self.assertFalse(x["source_publication_verified"])

    def test_partial_file_fails(self):
        with self.assertRaisesRegex(Reject, "NOT_FULL_D1_CANDIDATE"):
            extract(synthetic(102))

    def test_duplicate_team_rejected(self):
        x = synthetic()
        x = x.replace(b"Fake Team 359", b"Fake Team 358")
        with self.assertRaisesRegex(Reject, "DUPLICATE_OR_BLANK_TEAM"):
            extract(x)

    def test_binary_change_reflected_in_sha(self):
        raw = synthetic()
        receipt = persist(raw, self.root / "new", "https://barttorvik.com/2027_team_results.csv",
                          "2026-11-21T14:00:00Z")
        self.assertEqual(receipt["original_bytes_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual((self.root / "new" / "original_response.csv").read_bytes(), raw)
        self.assertEqual(json.loads((self.root / "new" / "capture_receipt.json").read_text())["status"],
                         "UNVALIDATED_FULL_CENSUS_CANDIDATE")
        self.assertNotEqual(hashlib.sha256(raw + b" ").hexdigest(), receipt["original_bytes_sha256"])

    def test_create_only_refuses_overwrite(self):
        raw = synthetic()
        persist(raw, self.root / "one", "https://barttorvik.com/2027_team_results.csv",
                "2026-11-21T14:00:00Z")
        with self.assertRaises(FileExistsError):
            persist(raw, self.root / "one", "https://barttorvik.com/2027_team_results.csv",
                    "2026-11-21T14:00:00Z")

    def test_invalid_capture_clock_rejected(self):
        with self.assertRaisesRegex(Reject, "CAPTURE_CLOCK_NEEDS_OFFSET"):
            persist(synthetic(), self.root / "no", "https://barttorvik.com/2027_team_results.csv",
                    "2026-11-21T14:00:00")

    def test_csv_html_or_malformed_rejected(self):
        with self.assertRaises(Reject):
            extract(b"<html>403 Forbidden</html>")

    def test_nan_rejected(self):
        with self.assertRaisesRegex(Reject, "NONFINITE"):
            extract(synthetic().replace(b",107,107,", b",nan,107,", 1))

    def test_invalid_tempo_range_rejected(self):
        with self.assertRaisesRegex(Reject, "IMPLAUSIBLE_TORVIK_UNITS"):
            extract(synthetic(tempo=120))

    def test_source_host_allowlist(self):
        with self.assertRaisesRegex(Reject, "URL_NOT_ALLOWED_TORVIK_RAW_CSV"):
            download("https://example.com/2027_team_results.csv")

    def test_http_403_propagates_no_summary_fallback(self):
        with patch("torvik_exact_raw_capture.urlopen", side_effect=HTTPError(
            "https://barttorvik.com/2027_team_results.csv", 403,
            "Forbidden", None, None)):
            with self.assertRaises(HTTPError):
                download("https://barttorvik.com/2027_team_results.csv")

    def test_no_opaque_utf8_replacement(self):
        with self.assertRaisesRegex(Reject, "INVALID_CSV"):
            extract(synthetic() + b"\xff")

    def test_bad_numeric_row_rejected(self):
        with self.assertRaisesRegex(Reject, "MISSING_NUMERIC"):
            extract(synthetic().replace(b",107,107,", b",abc,107,", 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
