"""Synthetic regression tests for the research-only Issue #10 acceptance evaluator."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sportsedge.validation.forward_acceptance import analyze, report_file

UTC=timezone.utc
BASE=datetime(2026,11,10,17,tzinfo=UTC)
H="sha256:"+"a"*64

def stamp(dt):return dt.isoformat()
def clean_card(i):
    return {"card_id":f"card-{i}","generated_utc":stamp(BASE+timedelta(days=i//20,minutes=i%20)),
            "price_rows":10,"missing_price_rows":0,"stale_quote_rows":0,
            "unauthenticated_quote_rows":0,"guard_bypasses":0,"pit_total":10,"pit_complete":10}
def close(i):
    t=BASE+timedelta(days=i//40,minutes=i%40)
    return {"bet_id":f"bet-{i}","event_start_utc":stamp(t+timedelta(hours=3)),
            "open_observed_utc":stamp(t),
            "taken_observed_utc":stamp(t+timedelta(minutes=1)),
            "close_observed_utc":stamp(t+timedelta(hours=2)),
            "settled_at_utc":stamp(t+timedelta(hours=7)),
            "settlement":"WIN" if i%2 else "LOSS",
            "market_identity_matched":True,"upstream_book_matched":True}
def cycle(i):
    t=BASE+timedelta(days=i*40)
    return {"cycle_id":f"cycle-{i}","registered_utc":stamp(t-timedelta(days=1)),
            "window_start_utc":stamp(t),"window_end_utc":stamp(t+timedelta(days=25)),
            "leakage_findings":0,"report_sha256":H}
def fixture(cards=100,closes=200,cycles=3):
    return {"schema":"sportsedge-issue10-structural-v1",
            "cards":[clean_card(i) for i in range(cards)],
            "clv_triples":[close(i) for i in range(closes)],
            "calibration_cycles":[cycle(i) for i in range(cycles)]}

class AuditContract(unittest.TestCase):
    def test_empty_history_never_promotes(self):
        r=analyze(fixture(0,0,0))
        self.assertFalse(r["reported_all_structural_thresholds_met"])
        self.assertFalse(r["release_certified"])
        self.assertEqual(r["approved_stake_u"],0)

    def test_even_thresholds_met_do_not_prove_authenticity_or_release(self):
        r=analyze(fixture())
        self.assertTrue(r["reported_all_structural_thresholds_met"])
        self.assertFalse(r["release_certified"])
        self.assertEqual(r["official_counted"],0)
        self.assertTrue(all(not x["externally_certified"] for x in r["gates"].values()))

    def test_recent_bad_card_resets_clean_streak(self):
        p=fixture()
        p["cards"][-1]["stale_quote_rows"]=1
        r=analyze(p)
        self.assertEqual(r["gates"]["A_prices"]["reported_clean_recent_streak"],0)

    def test_guard_bypass_resets_e_only(self):
        p=fixture()
        p["cards"][-1]["guard_bypasses"]=1
        r=analyze(p)
        self.assertEqual(r["gates"]["E_guard"]["reported_no_bypass_recent_streak"],0)
        self.assertEqual(r["gates"]["A_prices"]["reported_clean_recent_streak"],100)

    def test_pit_94_percent_below_threshold(self):
        p=fixture()
        for row in p["cards"]:
            row["pit_total"]=100
            row["pit_complete"]=94
        r=analyze(p)
        self.assertFalse(r["gates"]["B_PIT"]["structural_threshold_met"])

    def test_structural_clv_requires_exact_market_and_later_close(self):
        p=fixture()
        p["clv_triples"][0]["market_identity_matched"]=False
        p["clv_triples"][1]["close_observed_utc"]=p["clv_triples"][1]["taken_observed_utc"]
        r=analyze(p)
        self.assertEqual(r["gates"]["D_CLV"]["reported_structurally_comparable_closes"],198)
        self.assertFalse(r["gates"]["D_CLV"]["structural_threshold_met"])

    def test_duplicate_bet_id_refused(self):
        p=fixture()
        p["clv_triples"][1]["bet_id"]=p["clv_triples"][0]["bet_id"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_ID"):
            analyze(p)

    def test_duplicate_card_id_refused(self):
        p=fixture()
        p["cards"][1]["card_id"]=p["cards"][0]["card_id"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_ID"):
            analyze(p)

    def test_overlapping_calibration_cycles_refused(self):
        p=fixture()
        p["calibration_cycles"][1]["window_start_utc"]=p["calibration_cycles"][0]["window_end_utc"]
        p["calibration_cycles"][1]["window_start_utc"]=stamp(BASE+timedelta(days=10))
        with self.assertRaisesRegex(ValueError,"OVERLAPPING_CALIBRATION"):
            analyze(p)

    def test_unregistered_or_leaking_cycle_not_clean(self):
        p=fixture()
        p["calibration_cycles"][2]["registered_utc"]=p["calibration_cycles"][2]["window_start_utc"]
        p["calibration_cycles"][1]["leakage_findings"]=1
        r=analyze(p)
        self.assertEqual(r["gates"]["C_calibration"]["reported_clean_registered_cycles"],1)

    def test_five_dates_must_be_consecutive(self):
        p=fixture()
        for i,x in enumerate(p["cards"]):
            when=BASE+timedelta(days=(i//20)*2,minutes=i%20)
            x["generated_utc"]=stamp(when)
        r=analyze(p)
        self.assertEqual(r["gates"]["five_days"]["reported_calendar_date_streak"],1)


    def test_last_calibration_cycle_leak_resets_latest_streak_even_if_old_three_clean(self):
        p=fixture(cycles=4)
        p["calibration_cycles"][-1]["leakage_findings"]=1
        r=analyze(p)
        g=r["gates"]["C_calibration"]
        self.assertEqual(g["reported_clean_registered_cycles"],3)
        self.assertEqual(g["reported_latest_clean_cycle_streak"],0)
        self.assertFalse(g["structural_threshold_met"])
        self.assertFalse(r["reported_all_structural_thresholds_met"])

    def test_last_unregistered_calibration_cycle_blocks_three_cycle_gate(self):
        p=fixture(cycles=4)
        last=p["calibration_cycles"][-1]
        last["registered_utc"]=last["window_start_utc"]
        r=analyze(p)
        self.assertEqual(r["gates"]["C_calibration"]["reported_latest_clean_cycle_streak"],0)
        self.assertFalse(r["gates"]["C_calibration"]["structural_threshold_met"])

    def test_late_failure_resets_current_five_day_streak_not_historical_best(self):
        p=fixture(cards=120)
        # First five dates can be clean; final date's run fails.
        p["cards"][-1]["unauthenticated_quote_rows"]=1
        r=analyze(p)
        self.assertEqual(r["gates"]["five_days"]["reported_calendar_date_streak"],0)
        self.assertFalse(r["gates"]["five_days"]["structural_threshold_met"])

    def test_one_bad_card_among_good_cards_on_latest_day_blocks_day(self):
        p=fixture()
        p["cards"][-2]["guard_bypasses"]=1
        r=analyze(p)
        self.assertEqual(r["gates"]["five_days"]["reported_calendar_date_streak"],0)

    def test_five_clean_reported_days_pass_structural_streak_only(self):
        p=fixture()
        r=analyze(p)
        self.assertEqual(r["gates"]["five_days"]["reported_calendar_date_streak"],5)
        self.assertTrue(r["gates"]["five_days"]["structural_threshold_met"])
        self.assertFalse(r["gates"]["five_days"]["externally_certified"])
        self.assertFalse(r["release_certified"])

    def test_naive_datetime_rejected(self):
        p=fixture()
        p["cards"][0]["generated_utc"]="2026-11-15T17:00:00"
        with self.assertRaisesRegex(ValueError,"UTC_TIMESTAMP_REQUIRED"):
            analyze(p)

    def test_bad_count_rejected(self):
        p=fixture()
        p["cards"][0]["price_rows"]=-1
        with self.assertRaisesRegex(ValueError,"INVALID_COUNT"):
            analyze(p)

    def test_unexpected_sensitive_field_rejected(self):
        p=fixture()
        p["cards"][0]["api_token"]="do-not-record"
        with self.assertRaisesRegex(ValueError,"INVALID_FIELDS"):
            analyze(p)

    def test_report_is_create_only_and_inputs_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"raw.json";out=root/"audit.json"
            source.write_text(json.dumps(fixture(3,1,1)))
            original=source.read_bytes()
            r=report_file(source,out)
            self.assertFalse(r["release_certified"])
            self.assertEqual(source.read_bytes(),original)
            self.assertTrue(r["input_sha256"].startswith("sha256:"))
            with self.assertRaises(FileExistsError):report_file(source,out)

    def test_private_input_and_output_must_be_outside_public_checkout(self):
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/"source.json"
            src.write_text(json.dumps(fixture(3,1,1)))
            bad_output = repo/"sportsedge"/"validation"/"do_not_create_private_report.json"
            with self.assertRaisesRegex(ValueError, "PRIVATE_ACCEPTANCE_REPORT_INSIDE_PUBLIC_REPOSITORY"):
                report_file(src, bad_output)
            self.assertFalse(bad_output.exists())
            bad_input = repo/"sportsedge"/"validation"/"do_not_read_private_evidence.json"
            with self.assertRaisesRegex(ValueError, "PRIVATE_ACCEPTANCE_INPUT_INSIDE_PUBLIC_REPOSITORY"):
                report_file(bad_input, Path(tmp)/"out.json")

    def test_symlinked_public_repo_path_is_refused(self):
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/"source.json"
            src.write_text(json.dumps(fixture(3,1,1)))
            symlink = Path(tmp)/"public_alias"
            try:
                symlink.symlink_to(repo/"sportsedge", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "PRIVATE_ACCEPTANCE_REPORT_INSIDE_PUBLIC_REPOSITORY"):
                report_file(src, symlink/"validation"/"do_not_write.json")

    def test_nonfinite_manifest_token_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/"source.json"
            dest = Path(tmp)/"report.json"
            raw = json.dumps(fixture(1,0,0))
            raw = raw.replace('"price_rows": 10', '"price_rows": NaN')
            src.write_text(raw)
            with self.assertRaisesRegex(ValueError, "NONFINITE_MANIFEST_JSON"):
                report_file(src, dest)
            self.assertFalse(dest.exists())

    def test_create_only_private_report_mode_and_original_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/"source.json"
            dest = Path(tmp)/"report.json"
            src.write_text(json.dumps(fixture(1,1,1)))
            original = src.read_bytes()
            report = report_file(src, dest)
            self.assertFalse(report["release_certified"])
            self.assertEqual(src.read_bytes(), original)
            self.assertEqual(json.loads(dest.read_text())["state"],
                             "PAPER_0U_EXTERNAL_EVIDENCE_NOT_AUTHENTICATED")
            import os, stat
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                report_file(src, dest)

    def test_public_lexical_alias_outside_target_still_refused(self):
        from sportsedge.validation.forward_acceptance import REPOSITORY_ROOT
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as private, tempfile.TemporaryDirectory(
                prefix=".test_public_path_", dir=REPOSITORY_ROOT) as in_repo:
            original = Path(private)/"source.json"
            original.write_text(json.dumps(fixture(0,0,0)))
            alias = Path(in_repo)/"outside.json"
            try:
                alias.symlink_to(original)
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation unavailable")
            result = Path(private)/"report.json"
            with self.assertRaisesRegex(ValueError, "PRIVATE_ACCEPTANCE_INPUT_INSIDE_PUBLIC_REPOSITORY"):
                report_file(alias, result)
            self.assertFalse(result.exists())

    def test_partial_output_removed_on_sync_failure(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as private:
            original = Path(private)/"input.json"
            output = Path(private)/"report.json"
            original.write_text(json.dumps(fixture(0,0,0)))
            original_bytes = original.read_bytes()
            with patch("sportsedge.validation.forward_acceptance.os.fsync",
                       side_effect=OSError("simulated disk failure")):
                with self.assertRaisesRegex(OSError, "simulated disk failure"):
                    report_file(original, output)
            self.assertFalse(output.exists())
            self.assertEqual(original.read_bytes(), original_bytes)

    def test_duplicate_manifest_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"raw.json";out=root/"audit.json"
            source.write_text('{"schema":"sportsedge-issue10-structural-v1","schema":"fake","cards":[],"clv_triples":[],"calibration_cycles":[]}')
            with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
                report_file(source,out)
            self.assertFalse(out.exists())
if __name__=="__main__":
    unittest.main()
