"""Red-team tests for training-only score variance and RUN IT consumption.

All receipts are SYNTHETIC and do not authenticate historic sportsbook lines.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.markets.score_dispersion_fit import (
    FITTER_VERSION, fit_score_residuals,
)
from sportsedge.markets.cli import run_from_manifest
from sportsedge.markets.test_cli import H, S, manifest


def stamp(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def records(start, count=56, *, model_hash=H):
    out=[]
    for i in range(count):
        t=start+timedelta(days=i//8,hours=i%8)
        out.append({
            "sport":"CBB","event_id":"synthetic-"+str(i),
            "start_utc":stamp(t),
            "forecast_asof_utc":stamp(t-timedelta(hours=2)),
            "model_trained_until_utc":stamp(t-timedelta(days=2)),
            "features_published_utc":stamp(t-timedelta(hours=4)),
            "features_captured_utc":stamp(t-timedelta(hours=3)),
            "final_published_utc":stamp(t+timedelta(hours=3)),
            "final_captured_utc":stamp(t+timedelta(hours=4)),
            "projection_home":70., "projection_away":68.,
            "final_home":72+(i%7), "final_away":66+(i%9),
            "model_sha256":model_hash, "feature_sha256":S,
            "forecast_sha256":H,"final_sha256":S,
        })
    return out


def encode(rows):
    return ("\n".join(json.dumps(x,sort_keys=True,
                      separators=(",",":")) for x in rows)+"\n").encode()


class TrainingOnlyFitter(unittest.TestCase):
    def setUp(self):
        # Ensure every synthetic final comes before fit; no historical source.
        self.today=datetime.now(timezone.utc).replace(microsecond=0)
        self.base=self.today-timedelta(days=40)
        self.cutoff=stamp(self.today-timedelta(days=10))
        self.rows=records(self.base)

    def fit(self, rows=None):
        return fit_score_residuals(encode(self.rows if rows is None else rows),
                                   sport="CBB",cutoff_utc=self.cutoff)

    def test_train_only_width_and_source_hash_not_certification(self):
        raw=encode(self.rows)
        x=self.fit()
        self.assertEqual(x["schema"],FITTER_VERSION)
        self.assertEqual(x["status"],"TRAIN_ONLY_WIDTHS_READY_RESEARCH_NOT_CALIBRATED")
        self.assertEqual(x["accepted_rows"],56)
        self.assertEqual(x["total_rows"],56)
        self.assertEqual(x["distinct_start_dates"],7)
        self.assertEqual(x["blocked_rows"],0)
        self.assertEqual(x["training_model_sha256"],H)
        self.assertEqual(x["source_file_sha256"],"sha256:"+sha256(raw).hexdigest())
        self.assertGreater(x["sd_margin"],.1)
        self.assertGreater(x["sd_total"],.1)
        self.assertFalse(x["official"])
        self.assertFalse(x["release_gate_cleared"])
        self.assertEqual(x["approved_stake_u"],0)

    def test_pre_cutoff_result_inclusion_is_strict(self):
        rows=records(self.base)
        rows[0]["final_captured_utc"]=self.cutoff
        out=self.fit(rows)
        self.assertEqual(out["status"],"BLOCK_DISPERSION_FIT")
        self.assertEqual(out["blocked_rows"],1)
        self.assertEqual(out["blocked_reasons"]["LOOKAHEAD_OR_UNAVAILABLE_RESULT"],1)
        self.assertIsNone(out["sd_margin"])

    def test_future_feature_capture_and_fitted_model_block(self):
        for field in ("features_captured_utc","model_trained_until_utc"):
            with self.subTest(field=field):
                rows=records(self.base)
                rows[2][field]=rows[2]["start_utc"]
                out=self.fit(rows)
                self.assertEqual(out["status"],"BLOCK_DISPERSION_FIT")
                self.assertIn("LOOKAHEAD_OR_UNAVAILABLE_RESULT",out["blocked_reasons"])

    def test_duplicates_quarantined_all_copies(self):
        rows=records(self.base)
        rows[3]["event_id"]=rows[2]["event_id"]
        report=self.fit(rows)
        self.assertEqual(report["blocked_rows"],2)
        self.assertEqual(report["blocked_reasons"]["DUPLICATE_EVENT_ALL_COPIES_QUARANTINED"],2)
        self.assertIsNone(report["sd_total"])

    def test_whitespace_and_case_variants_cannot_hide_duplicate_events(self):
        rows=records(self.base)
        rows[3]["event_id"]="  "+rows[2]["event_id"].upper()+"  "
        x=self.fit(rows)
        self.assertEqual(x["blocked_rows"],2)
        self.assertEqual(x["blocked_reasons"]["DUPLICATE_EVENT_ALL_COPIES_QUARANTINED"],2)
        self.assertEqual(x["status"],"BLOCK_DISPERSION_FIT")

    def test_malformed_unhashable_sport_fails_closed_without_crash(self):
        for invalid in ([], {}, ["CBB"]):
            with self.subTest(invalid=invalid):
                rows=records(self.base)
                rows[0]["sport"]=invalid
                report=self.fit(rows)
                self.assertEqual(report["status"],"BLOCK_DISPERSION_FIT")
                self.assertEqual(report["blocked_rows"],1)
                self.assertIn("MIXED_SPORT_IN_TRAINING_LEDGER",report["blocked_reasons"])

    def test_mixed_frozen_model_hashes_block_even_if_scores_valid(self):
        rows=records(self.base)
        rows[1]["model_sha256"]="sha256:"+"c"*64
        report=self.fit(rows)
        self.assertIn("MIXED_OR_MISSING_FORECAST_MODEL",report["fit_failures"])
        self.assertEqual(report["blocked_rows"],0)
        self.assertEqual(report["status"],"BLOCK_DISPERSION_FIT")

    def test_missing_row_is_not_silently_dropped(self):
        rows=records(self.base)
        del rows[2]["final_sha256"]
        report=self.fit(rows)
        self.assertEqual(report["blocked_rows"],1)
        self.assertIn("INVALID_TRAINING_ROW_SCHEMA",report["blocked_reasons"])

    def test_corrupt_json_nonfinite_and_duplicate_keys_block(self):
        for malicious in (
            b'{"sport":"CBB","sport":"NFL"}\n',
            b'{"sport":"CBB","x":NaN}\n',
            b'[]\n',
            b'\n',
        ):
            with self.subTest(malicious=malicious):
                raw=encode(self.rows)+malicious
                x=fit_score_residuals(raw,sport="CBB",cutoff_utc=self.cutoff)
                self.assertEqual(x["status"],"BLOCK_DISPERSION_FIT")
                self.assertGreaterEqual(x["blocked_rows"],1)

    def test_seven_dates_required_even_with_56_events(self):
        rows=records(self.base)
        for i,row in enumerate(rows):
            t=self.base+timedelta(minutes=i*10)
            row["start_utc"]=stamp(t)
            row["forecast_asof_utc"]=stamp(t-timedelta(hours=2))
            row["model_trained_until_utc"]=stamp(t-timedelta(days=2))
            row["features_published_utc"]=stamp(t-timedelta(hours=4))
            row["features_captured_utc"]=stamp(t-timedelta(hours=3))
            row["final_published_utc"]=stamp(t+timedelta(hours=3))
            row["final_captured_utc"]=stamp(t+timedelta(hours=4))
        x=self.fit(rows)
        self.assertEqual(x["accepted_rows"],56)
        self.assertEqual(x["distinct_start_dates"],1)
        self.assertEqual(x["status"],"BLOCK_DISPERSION_FIT")

    def test_replaying_same_source_and_cutoff_matches_fit(self):
        self.assertEqual(self.fit(),self.fit())
        mutated=records(self.base)
        mutated[3]["final_home"]+=3
        x=self.fit(mutated)
        self.assertNotEqual(self.fit()["source_file_sha256"],x["source_file_sha256"])
        self.assertNotEqual(self.fit()["fitter_model_sha256"],x["fitter_model_sha256"])

    def test_private_residual_source_can_feed_research_runner_without_official(self):
        raw=encode(self.rows)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"frozen-ledger.jsonl"
            path.write_bytes(raw)
            p=manifest()
            p["distribution"]={
                "sport":"CBB","period_shares":[.25,.25,.25,.25],
                "status":"UNCALIBRATED_RESEARCH",
            }
            p["dispersion_fit_ref"]={
                "path":str(path), "raw_sha256":"sha256:"+sha256(raw).hexdigest(),
                "fit_asof_utc":self.cutoff,
            }
            out=run_from_manifest(p)
            self.assertEqual(out["dispersion_fit_status"],
                             "TRAIN_ONLY_WIDTHS_READY_RESEARCH_NOT_CALIBRATED")
            self.assertEqual(out["dispersion_fit_accepted_n"],56)
            self.assertFalse(out["period_share_calibration_verified"])
            self.assertTrue(out["scenario_spec_sha256"].startswith("sha256:"))
            self.assertEqual(out["approved_stake_u"],0)
            self.assertEqual(out["official_counted"],0)
            self.assertIsNone(out["card"])

    def test_private_fit_rejects_tamper_or_injected_sd(self):
        raw=encode(self.rows)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"train.jsonl"
            path.write_bytes(raw)
            for wrong in (False,True):
                with self.subTest(wrong=wrong):
                    p=manifest()
                    p["distribution"]={
                        "sport":"CBB","period_shares":[.25,.25,.25,.25],
                        "status":"UNCALIBRATED_RESEARCH",
                    }
                    if wrong:p["distribution"]["sd_margin"]=100
                    p["dispersion_fit_ref"]={
                        "path":str(path),
                        "raw_sha256":"sha256:"+("0"*64 if not wrong
                                    else sha256(raw).hexdigest()),
                        "fit_asof_utc":self.cutoff,
                    }
                    with self.assertRaisesRegex(ValueError,
                              "DISPERSION_FIT_ORIGINAL_LEDGER_HASH_MISMATCH"
                              if not wrong else "UNSUPPORTED_OR_SECRET_FIELD"):
                        run_from_manifest(p)

    def test_fit_after_projection_or_wrong_frozen_model_blocked(self):
        raw=encode(self.rows)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"train.jsonl"
            path.write_bytes(raw)
            p=manifest()
            p["distribution"]={
                "sport":"CBB","period_shares":[.25,.25,.25,.25],
                "status":"UNCALIBRATED_RESEARCH",
            }
            p["dispersion_fit_ref"]={
                "path":str(path),"raw_sha256":"sha256:"+sha256(raw).hexdigest(),
                "fit_asof_utc":stamp(self.today+timedelta(days=1)),
            }
            with self.assertRaisesRegex(ValueError,"DISPERSION_FIT_AFTER_PROJECTION_FREEZE"):
                run_from_manifest(p)
            p["dispersion_fit_ref"]["fit_asof_utc"]=self.cutoff
            p["projection"]["model_sha256"]="sha256:"+"f"*64
            with self.assertRaisesRegex(ValueError,"DISPERSION_TRAINING_MODEL_MISMATCH"):
                run_from_manifest(p)


if __name__=="__main__":
    unittest.main()
