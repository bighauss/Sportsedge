"""Synthetic regression tests for the research-only Issue #10 acceptance evaluator."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sportsedge.validation.forward_acceptance import analyze, report_file, REPO_ROOT

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

    def test_public_checkout_input_is_refused_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            # Existing public repo file is intentionally NOT evidence JSON;
            # privacy failure must precede parsing or recording its hash.
            source = REPO_ROOT / "sportsedge" / "validation" / "forward_acceptance.py"
            with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_PATH_REQUIRED:manifest"):
                report_file(source, out)
            self.assertFalse(out.exists())

    def test_public_checkout_report_is_refused_before_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "original.json"
            source.write_text(json.dumps(fixture(0, 0, 0)))
            output = REPO_ROOT / "sportsedge" / "validation" / "do_not_create_gate10.json"
            with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_PATH_REQUIRED:report"):
                report_file(source, output)
            self.assertFalse(output.exists())

    def test_symlink_into_public_checkout_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            alias = Path(tmp) / "repo_alias"
            try:
                alias.symlink_to(REPO_ROOT, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable")
            out = Path(tmp) / "audit.json"
            with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_PATH_REQUIRED:manifest"):
                report_file(alias / "sportsedge" / "validation" / "forward_acceptance.py", out)
            self.assertFalse(out.exists())

    def test_private_report_created_with_restrictive_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, out = root / "raw.json", root / "audit.json"
            src.write_text(json.dumps(fixture(0, 0, 0)))
            report_file(src, out)
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                report_file(src, out)

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
