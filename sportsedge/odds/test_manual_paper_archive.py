"""Synthetic-only manual capture tests. Never use fake lines as live markets."""
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest

from manual_paper_archive import HEADER, ManualCaptureError, analyze, archive, REPO_ROOT

CAPTURE = "2026-11-15T18:00:00Z"


def sample(**updates):
    values = dict(
        sport="NFL", event_id="SYNTH-GAME-001", game_start_utc="2026-11-15T19:00:00Z",
        book="DK", source_surface="DK_APP", market_family="TOTAL",
        provider_market_id="", period="FG", selection_id="TOTAL-45.5-OVER",
        side="OVER", participant_id="", stat="", line="45.5",
        price_american="-110", observed_at_utc="2026-11-15T17:59:00Z",
        offer_state="OBSERVED_PRICE", exclusion_reason="",
    )
    values.update(updates)
    return values


def csvbytes(*rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=HEADER, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return stream.getvalue().encode()


class ManualPaperArchiveTest(unittest.TestCase):
    def test_single_record_never_authenticates(self):
        raw = csvbytes(sample())
        report = analyze(raw, captured_at_utc=CAPTURE)
        self.assertEqual(report["paper_unverified_rows"], 1)
        self.assertFalse(report["gate_a_closed"])
        self.assertFalse(report["complete_market_inventory_authenticated"])
        self.assertEqual(report["approved_stake_u"], 0)
        self.assertEqual(report["rows"][0]["state"], "PAPER_UNVERIFIED")
        self.assertEqual(report["original_csv_sha256"], "sha256:" + sha256(raw).hexdigest())

    def test_missing_market_price_retained_with_reason(self):
        report = analyze(csvbytes(sample(offer_state="NOT_CAPTURED",
                                         price_american="", exclusion_reason="NO_PRICE")),
                         captured_at_utc=CAPTURE)
        self.assertEqual(report["paper_unverified_rows"], 1)
        self.assertEqual(report["rows"][0]["original_record"]["exclusion_reason"], "NO_PRICE")

    def test_claim_not_offered_not_authenticated(self):
        report = analyze(csvbytes(sample(offer_state="NOT_OFFERED",
                                         price_american="", exclusion_reason="NO_PRICE")),
                         captured_at_utc=CAPTURE)
        self.assertEqual(report["blocked_rows"], 1)
        self.assertIn("UNAUTHENTICATED_OFFER_STATE", report["rows"][0]["reasons"])

    def test_duplicate_all_snapshots_blocked(self):
        one = sample()
        two = sample(price_american="-108")
        report = analyze(csvbytes(one, two), captured_at_utc=CAPTURE)
        self.assertEqual(report["blocked_rows"], 2)
        self.assertTrue(all("DUPLICATE_MANUAL_QUOTE_SNAPSHOT" in x["reasons"]
                            for x in report["rows"]))

    def test_stale_and_poststart_blocked_no_deletion(self):
        r = sample(observed_at_utc="2026-11-15T17:30:00Z")
        report = analyze(csvbytes(r), captured_at_utc=CAPTURE)
        self.assertEqual(report["total_records"], 1)
        self.assertIn("STALE_MANUAL_OBSERVATION_OVER_300S", report["rows"][0]["reasons"])
        future = analyze(csvbytes(sample(game_start_utc="2026-11-15T17:58:00Z")),
                         captured_at_utc=CAPTURE)
        self.assertIn("NOT_PREGAME_OBSERVATION", future["rows"][0]["reasons"])

    def test_malformed_row_and_blank_row_stay_in_denominator(self):
        raw = csvbytes(sample()) + b"\n" + b"NFL,TOO,FEW\n"
        report = analyze(raw, captured_at_utc=CAPTURE)
        self.assertEqual(report["total_records"], 3)
        self.assertEqual(report["blocked_rows"], 2)
        self.assertTrue(all("MALFORMED_CSV_FIELD_COUNT" in x["reasons"]
                            for x in report["rows"][1:]))

    def test_header_duplicates_are_fatal_but_source_unmodified(self):
        raw = csvbytes(sample()).replace(b"book,source_surface", b"book,book")
        with self.assertRaisesRegex(ManualCaptureError, "INVALID_OR_DUPLICATE_CSV_HEADER"):
            analyze(raw, captured_at_utc=CAPTURE)

    def test_alt_lines_and_pga_do_not_silently_disappear(self):
        alt = sample(market_family="ALTERNATE", line="47.5", selection_id="ALT-47.5")
        pga = sample(sport="PGA", market_family="OUTRIGHT", event_id="SYNTH-GOLF-1",
                     line="", price_american="+750", selection_id="PLAYER-7",
                     participant_id="PLAYER-7")
        report = analyze(csvbytes(alt, pga), captured_at_utc=CAPTURE)
        self.assertEqual(report["paper_unverified_rows"], 2)
        self.assertEqual(len(report["by_sport_market_offer_state"]), 2)

    def test_private_exclusive_owner_only_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            source, dest = root / "input.csv", root / "output.json"
            source.write_bytes(csvbytes(sample()))
            source.chmod(0o600)
            old = source.read_bytes()
            report = archive(source, dest, captured_at_utc=CAPTURE)
            self.assertEqual(source.read_bytes(), old)
            self.assertEqual(dest.stat().st_mode & 0o077, 0)
            self.assertEqual(json.loads(dest.read_text())["original_csv_sha256"],
                             report["original_csv_sha256"])
            with self.assertRaises(FileExistsError):
                archive(source, dest, captured_at_utc=CAPTURE)

    def test_reject_exposed_private_input_and_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            source = root / "board.csv"
            source.write_bytes(csvbytes(sample()))
            with self.assertRaisesRegex(ManualCaptureError, "SOURCE_MUST_BE_OWNER_ONLY"):
                archive(source, root / "report.json", captured_at_utc=CAPTURE)
            source.chmod(0o600)
            root.chmod(0o755)
            with self.assertRaisesRegex(ManualCaptureError, "DESTINATION_DIRECTORY_MUST_BE_0700"):
                archive(source, root / "report.json", captured_at_utc=CAPTURE)

    def test_repository_or_symlink_path_refused(self):
        with self.assertRaisesRegex(ManualCaptureError, "PUBLIC_GIT_REPOSITORY"):
            archive(REPO_ROOT / "unsafe.csv", "/tmp/out.csv", captured_at_utc=CAPTURE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            source = root / "safe.csv"
            source.write_bytes(csvbytes(sample()))
            source.chmod(0o600)
            link = root / "linked.csv"
            link.symlink_to(source)
            with self.assertRaisesRegex(ManualCaptureError, "SYMLINK_PATH_REFUSED"):
                archive(link, root / "out.json", captured_at_utc=CAPTURE)

    def test_invalid_american_and_nonfinite_are_not_priced(self):
        report = analyze(csvbytes(sample(price_american="+99", line="NaN")),
                         captured_at_utc=CAPTURE)
        self.assertEqual(report["blocked_rows"], 1)
        self.assertIn("INVALID_AMERICAN_PRICE", report["rows"][0]["reasons"])
        self.assertIn("INVALID_LINE", report["rows"][0]["reasons"])

    def test_tamper_is_visible_in_raw_digest(self):
        original = csvbytes(sample())
        modified = csvbytes(sample(price_american="-115"))
        self.assertNotEqual(analyze(original, captured_at_utc=CAPTURE)["original_csv_sha256"],
                            analyze(modified, captured_at_utc=CAPTURE)["original_csv_sha256"])


if __name__ == "__main__":
    unittest.main()
