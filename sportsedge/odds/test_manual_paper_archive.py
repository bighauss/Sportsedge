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

    def test_player_prop_both_exact_sides_saved_separately(self):
        over = sample(market_family="PLAYER_PROP", provider_market_id="market1",
                      participant_id="nfl-p1", stat="PASS_YDS",
                      line="249.5", selection_id="p1-over", side="OVER")
        under = dict(over, selection_id="p1-under", side="UNDER",
                     price_american="+104")
        report = analyze(csvbytes(over, under), captured_at_utc=CAPTURE)
        self.assertEqual(report["total_records"], 2)
        self.assertEqual(report["blocked_rows"], 0)
        self.assertEqual(report["prop_pair_census"]["two_sided_recorded_unverified"], 1)
        self.assertEqual([r["original_record"]["price_american"] for r in report["rows"]],
                         ["-110", "+104"])
        self.assertTrue(all(r["prop_price_pair_state"] ==
                            "EXACT_BOTH_SIDES_RECORDED_UNVERIFIED" for r in report["rows"]))
        self.assertFalse(report["prop_pair_census"]["two_sided_no_vig_authenticated"])

    def test_missing_under_is_not_inferred(self):
        over = sample(market_family="PLAYER_PROP", provider_market_id="market1",
                      participant_id="nfl-p1", stat="RUSH_YDS",
                      line="85.5", selection_id="p1-o", side="OVER")
        result = analyze(csvbytes(over), captured_at_utc=CAPTURE)
        self.assertEqual(result["total_records"], 1)
        self.assertEqual(result["prop_pair_census"]["unrecorded_under_groups"], 1)
        self.assertEqual(result["rows"][0]["prop_price_pair_state"],
                         "COUNTERPART_UNDER_NOT_RECORDED")

    def test_explicitly_unavailable_under_preserved(self):
        over = sample(market_family="PLAYER_PROP", provider_market_id="market1",
                      participant_id="nfl-p1", stat="REC_YDS",
                      line="44.5", selection_id="p1-o", side="OVER")
        under = dict(over, selection_id="p1-u", side="UNDER",
                     price_american="", offer_state="NOT_CAPTURED",
                     exclusion_reason="NO_PRICE")
        result = analyze(csvbytes(over, under), captured_at_utc=CAPTURE)
        self.assertEqual(result["total_records"], 2)
        self.assertEqual(result["prop_pair_census"]["explicit_missing_side_groups"], 0)
        self.assertEqual(result["prop_pair_census"]["source_blocked_pair_groups"], 1)
        self.assertEqual(result["rows"][1]["original_record"]["offer_state"], "NOT_CAPTURED")

    def test_alt_ladder_rungs_have_distinct_two_sided_prices(self):
        records = []
        for rung in ("40.5", "60.5", "80.5"):
            for side in ("OVER", "UNDER"):
                records.append(sample(market_family="ALTERNATE", provider_market_id="m-alt",
                                      participant_id="nfl-p1", stat="REC_YDS",
                                      line=rung, selection_id="p1-"+side+rung,
                                      side=side, price_american="-110"))
        result = analyze(csvbytes(*records), captured_at_utc=CAPTURE)
        self.assertEqual(result["prop_pair_census"]["player_prop_and_alt_line_groups"], 3)
        self.assertEqual(result["prop_pair_census"]["two_sided_recorded_unverified"], 3)
        self.assertEqual(result["total_records"], 6)

    def test_alt_xplus_single_yes_is_not_two_sided(self):
        item = sample(market_family="ALTERNATE", provider_market_id="m-alt",
                      participant_id="nfl-p1", stat="REC_YDS",
                      line="100", selection_id="p1-100plus", side="YES", price_american="+325")
        result = analyze(csvbytes(item), captured_at_utc=CAPTURE)
        self.assertEqual(result["prop_pair_census"]["one_sided_alt_outcomes_unverified"], 1)
        self.assertEqual(result["prop_pair_census"]["two_sided_recorded_unverified"], 0)
        self.assertEqual(result["rows"][0]["prop_price_pair_state"],
                         "ONE_SIDED_ALT_NO_VIG_PAIR")

    def test_book_or_quote_time_or_market_id_never_cross_paired(self):
        over = sample(market_family="PLAYER_PROP", provider_market_id="m1",
                      participant_id="nfl-p1", stat="PASS_YDS",
                      line="251.5", selection_id="p1-o", side="OVER")
        under = dict(over, selection_id="p1-u", side="UNDER", book="OtherBook")
        result = analyze(csvbytes(over, under), captured_at_utc=CAPTURE)
        self.assertEqual(result["prop_pair_census"]["unrecorded_under_groups"], 1)
        self.assertEqual(result["prop_pair_census"]["unrecorded_over_groups"], 1)
        under["book"] = "DK"
        under["observed_at_utc"] = "2026-11-15T17:58:00Z"
        result = analyze(csvbytes(over, under), captured_at_utc=CAPTURE)
        self.assertEqual(result["prop_pair_census"]["two_sided_recorded_unverified"], 0)
        under["observed_at_utc"] = over["observed_at_utc"]
        under["provider_market_id"] = "m2"
        result = analyze(csvbytes(over, under), captured_at_utc=CAPTURE)
        self.assertEqual(result["prop_pair_census"]["two_sided_recorded_unverified"], 0)

    def test_conflicting_two_overs_block_all_copies(self):
        a = sample(market_family="PLAYER_PROP", provider_market_id="m1",
                   participant_id="nfl-p1", stat="RECEPTIONS", line="5.5",
                   selection_id="a", side="OVER")
        b = dict(a, selection_id="b", price_american="-115")
        u = dict(a, selection_id="c", side="UNDER")
        report = analyze(csvbytes(a, b, u), captured_at_utc=CAPTURE)
        self.assertEqual(report["blocked_rows"], 3)
        self.assertEqual(report["prop_pair_census"]["ambiguous_same_side_groups"], 1)
        self.assertTrue(all("AMBIGUOUS_PROP_SAME_SIDE" in row["reasons"]
                            for row in report["rows"]))

    def test_player_stat_identity_required(self):
        item = sample(market_family="PLAYER_PROP", provider_market_id="m1",
                      stat="PASS_YDS", line="242.5", selection_id="p1",
                      side="OVER", participant_id="")
        report = analyze(csvbytes(item), captured_at_utc=CAPTURE)
        self.assertEqual(report["blocked_rows"], 1)
        self.assertEqual(report["prop_pair_census"]["missing_player_or_stat_identity_rows"], 1)
        self.assertIn("PLAYER_ID_OR_STAT_MISSING", report["rows"][0]["reasons"])

    def test_decimal_equivalent_line_uses_one_group(self):
        a = sample(market_family="PLAYER_PROP", provider_market_id="m1",
                   participant_id="nfl-p1", stat="PASS_YDS", line="250.50",
                   selection_id="o", side="OVER")
        b = dict(a, selection_id="u", side="UNDER", line="250.5")
        report = analyze(csvbytes(a, b), captured_at_utc=CAPTURE)
        self.assertEqual(report["prop_pair_census"]["two_sided_recorded_unverified"], 1)

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
