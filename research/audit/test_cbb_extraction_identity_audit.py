"""Synthetic-only CBB extraction identity regression tests."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from research.audit.cbb_extraction_identity_audit import reconcile, main, REPO_ROOT


def case(event, source, market="full_game", away_spread="-2.5", away_ml="-148"):
    return {"market": market, "event": event, "start": "Today 1:00 PM",
            "source_file": "private-synthetic.pdf",
            "source_pdf_sha256": "not_authenticated",
            "raw_source_text": source, "identity_status": "CONFLICT_3WAY",
            "away_spread": away_spread, "home_spread": "2.5", "total": "163.5",
            "away_ml": away_ml, "away_sp_odds": "-110", "over_odds": "-110",
            "home_ml": "124", "home_sp_odds": "-110", "under_odds": "-110"}


class ExtractionReconcileTest(unittest.TestCase):
    def test_cyclic_label_shift_without_changing_quotes(self):
        rows = [
            case("Wyoming AT Duquesne",
                 "William &\nMary -2.5 O163.5\nAT\nYoungstow\n+2.5 U163.5\nn State"),
            case("San Diego AT Fordham",
                 "Wyoming -3.5 O136.5\nAT\nDuquesne +3.5 U136.5",
                 away_spread="-3.5", away_ml="-175"),
            case("William & Mary AT Youngstown State",
                 "San Diego +2.5 O143.5\nAT\nFordham -2.5 U143.5",
                 away_spread="+2.5", away_ml="+130"),
        ]
        original = copy.deepcopy(rows)
        r = reconcile(rows)
        self.assertEqual(rows, original)
        self.assertEqual(r["disputed_rows"], 3)
        self.assertEqual(len(r["candidate_reassignments"]), 3)
        self.assertEqual(r["blocked"], [])
        mp = {x["stored_event_label"]: x for x in r["candidate_reassignments"]}
        self.assertEqual(mp["Wyoming AT Duquesne"]["extracted_text_event_candidate"],
                         "William & Mary AT Youngstown State")
        self.assertEqual(mp["San Diego AT Fordham"]["extracted_text_event_candidate"],
                         "Wyoming AT Duquesne")
        self.assertEqual(mp["William & Mary AT Youngstown State"]["extracted_text_event_candidate"],
                         "San Diego AT Fordham")
        self.assertEqual(mp["Wyoming AT Duquesne"]["quote_fields_preserved"]["away_ml"], "-148")
        self.assertFalse(r["original_pdf_authenticated"])
        self.assertEqual(r["approved_stake_u"], 0)

    def test_duplicate_target_blocks_all_copies(self):
        r = reconcile([case("A Team AT Home One", "A Team AT Home One"),
                       case("B Team AT Home Two", "A Team AT Home One")])
        self.assertEqual(len(r["blocked"]), 2)
        self.assertEqual(r["candidate_reassignments"], [])

    def test_missing_home_identity_blocks(self):
        r = reconcile([case("Wyoming AT Duquesne", "Wyoming unknown opponent")])
        self.assertEqual(r["census"]["blocked_rows"], 1)

    def test_period_isolation(self):
        a = case("A Team AT Home One", "A Team AT Home One")
        b = case("A Team AT Home One", "A Team AT Home One", market="first_half")
        self.assertEqual(len(reconcile([a,b])["candidate_reassignments"]), 2)

    def test_unchanged_clean_rows(self):
        x = case("A Team AT Home One", "A Team AT Home One")
        x["identity_status"] = "OK"
        self.assertEqual(reconcile([x])["disputed_rows"], 0)

    def test_missing_source_rejected(self):
        x = case("A Team AT Home One", "A Team AT Home One")
        x["source_file"] = ""
        with self.assertRaisesRegex(ValueError, "CONFLICT_ROW_MISSING_SOURCE_FIELDS"):
            reconcile([x])

    def test_clean_event_target_occupancy_blocks_full_disputed_group(self):
        x = case("A Team AT Home One", "B Team AT Home Two")
        y = case("B Team AT Home Two", "A Team AT Home One")
        clean = case("A Team AT Home One", "A Team AT Home One")
        clean["identity_status"] = "OK"
        r = reconcile([x, y, clean])
        self.assertEqual(r["disputed_rows"], 2)
        self.assertEqual(len(r["blocked"]), 2)
        self.assertEqual(r["candidate_reassignments"], [])

    @staticmethod
    def _write_rows(path, rows):
        data = io.StringIO(newline="")
        w = csv.DictWriter(data, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        path.write_text(data.getvalue(), encoding="utf-8")
        path.chmod(0o600)

    def test_cli_private_0600_source_and_report_create_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o700)
            source, result = directory / "source.csv", directory / "result.json"
            self._write_rows(source, [case("A Team AT Home One", "A Team AT Home One")])
            old = source.read_bytes()
            self.assertEqual(main([str(source), "--out", str(result)]), 0)
            self.assertEqual(source.read_bytes(), old)
            self.assertEqual(result.stat().st_mode & 0o077, 0)
            self.assertFalse(json.loads(result.read_text())["original_pdf_authenticated"])
            with self.assertRaises(FileExistsError):
                main([str(source), "--out", str(result)])

    def test_public_repo_input_and_output_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o700)
            source = directory / "source.csv"
            self._write_rows(source, [case("A Team AT Home One", "A Team AT Home One")])
            with self.assertRaisesRegex(ValueError, "PUBLIC_GIT_REPOSITORY_PATH_REFUSED"):
                main([str(source), "--out", str(REPO_ROOT / "unsafe-private.json")])
            with self.assertRaisesRegex(ValueError, "PUBLIC_GIT_REPOSITORY_PATH_REFUSED"):
                main([str(REPO_ROOT / "research" / "audit" / "test_cbb_extraction_identity_audit.py"),
                      "--out", str(directory / "out.json")])

    def test_unsafe_source_permission_parent_or_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o700)
            source = directory / "source.csv"
            self._write_rows(source, [case("A Team AT Home One", "A Team AT Home One")])
            source.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "SOURCE_NOT_OWNER_ONLY_0600"):
                main([str(source), "--out", str(directory / "out.json")])
            source.chmod(0o600)
            directory.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "DESTINATION_DIRECTORY_MUST_BE_PRIVATE_0700"):
                main([str(source), "--out", str(directory / "out.json")])
            directory.chmod(0o700)
            link = directory / "link.csv"
            link.symlink_to(source)
            with self.assertRaisesRegex(ValueError, "SYMLINK_SOURCE_OR_OUTPUT_REFUSED"):
                main([str(link), "--out", str(directory / "out.json")])

    def test_csv_duplicate_header_and_ragged_rows_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            directory.chmod(0o700)
            source = directory / "bad.csv"
            self._write_rows(source, [case("A Team AT Home One", "A Team AT Home One")])
            raw = source.read_text()
            header, rest = raw.split("\n", 1)
            cols = header.split(",")
            cols[-1] = cols[0]
            source.write_text(",".join(cols)+"\n"+rest)
            source.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_MISSING_CSV_HEADERS"):
                main([str(source), "--out", str(directory / "out.json")])



if __name__ == "__main__":
    unittest.main()
