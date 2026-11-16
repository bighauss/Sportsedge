"""Synthetic tests for local-only prospective forecast-to-freeze binding."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.validation.seven_sport_pit_freeze import ROOT, freeze_file
from sportsedge.validation.prospective_forecast_receipt import (
    assess, record_files, _parse,
)

NOW = datetime(2026, 11, 16, 1, 3, tzinfo=timezone.utc)


def file_desc(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)
    return {"path": str(path), "sha256": "sha256:" + sha256(raw).hexdigest()}


class ForecastReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)
        config = file_desc(self.root/"config.json", b'{"fixture":true}')
        feature = file_desc(self.root/"feature.json", b'{"prior":"asof"}')
        code_file = ROOT/"models/nfl/discrete_score_pit.py"
        code = {"path": str(code_file.relative_to(ROOT)),
                "sha256": "sha256:" + sha256(code_file.read_bytes()).hexdigest()}
        request = {
            "schema": "sportsedge-seven-sport-pit-freeze-request-v1",
            "sport": "NFL", "event_id": "SYNTHETIC-EVT-01",
            "market_family": "TOTAL", "period": "FG",
            "model_version": "fixture-v1",
            "training_cutoff_utc": "2026-11-15T21:00:00Z",
            "registered_utc": "2026-11-15T23:00:00Z",
            "freeze_utc": "2026-11-16T01:00:00Z",
            "event_start_utc": "2026-11-16T03:00:00Z",
            "evaluation_end_utc": "2026-11-16T06:00:00Z",
            "model_code": code, "model_config": config,
            "feature_sources": [{
                "source_id": "fixture-prior-snapshot",
                "file": feature,
                "data_through_utc": "2026-11-15T19:00:00Z",
                "published_utc": "2026-11-15T20:00:00Z",
                "observed_utc": "2026-11-15T20:30:00Z",
                "captured_utc": "2026-11-15T20:31:00Z",
            }],
        }
        request_path=self.root/"request.json"
        file_desc(request_path, json.dumps(request).encode())
        self.freeze_path=self.root/"freeze.json"
        self.freeze=freeze_file(request_path,self.freeze_path,
                                actual_now=datetime(2026,11,16,1,1,tzinfo=timezone.utc))
        self.forecast = {
            "schema":"sportsedge-prospective-forecast-v1",
            "state":"PAPER_0U",
            "sport":"NFL", "event_id":"SYNTHETIC-EVT-01",
            "market_family":"TOTAL", "period":"FG",
            "model_version":"fixture-v1",
            "freeze_record_sha256":"sha256:"+sha256(self.freeze_path.read_bytes()).hexdigest(),
            "model_code_sha256":self.freeze["model_code"]["sha256"],
            "model_config_sha256":self.freeze["model_config"]["sha256"],
            "feature_source_hashes":{
                r["source_id"]: r["raw_file"]["sha256"]
                for r in self.freeze["feature_sources"]},
            "generated_utc":"2026-11-16T01:02:00Z",
            "captured_utc":"2026-11-16T01:02:30Z",
            "predictions":[{
                "market_identity":["NFL","SYNTHETIC-EVT-01","TOTAL","FG",
                                   "OVER","42.5","","","","INCLUDES_OT"],
                "model_probability":"0.55",
            }],
        }
        self.forecast_path=self.root/"forecast.json"
        self.save()

    def save(self):
        file_desc(self.forecast_path,json.dumps(self.forecast).encode())

    def check(self, *, forecast=None, freeze=None, now=NOW):
        forecast=self.forecast if forecast is None else forecast
        freeze=self.freeze if freeze is None else freeze
        raw=json.dumps(forecast).encode()
        return assess(freeze, forecast, original_freeze=self.freeze_path.read_bytes(),
                      original_forecast=raw, actual_now=now)

    def test_real_freeze_to_forecast_private_archive_create_only(self):
        report_path=self.root/"receipt.json"
        report=record_files(self.freeze_path,self.forecast_path,report_path,actual_now=NOW)
        self.assertEqual(report["state"],"PAPER_0U_LOCAL_FORECAST_BOUND_TO_FREEZE")
        self.assertEqual(report["prediction_count"],1)
        self.assertEqual(report["feature_count"],1)
        self.assertEqual(report["official_counted"],0)
        self.assertEqual(report["approved_stake_u"],0)
        self.assertIsNone(report["card"])
        self.assertFalse(report["release_certified"])
        self.assertFalse(report["original_forecast_independently_attested"])
        self.assertEqual(report_path.stat().st_mode & 0o777,0o600)
        self.assertNotIn("INCLUDES_OT",report_path.read_text())
        self.assertNotIn("0.55",report_path.read_text())
        with self.assertRaisesRegex(ValueError,"OUTPUT_MUST_BE_NEW"):
            record_files(self.freeze_path,self.forecast_path,report_path,actual_now=NOW)

    def test_original_forecast_bytes_sha_is_exact(self):
        report=record_files(self.freeze_path,self.forecast_path,
                            self.root/"receipt.json",actual_now=NOW)
        self.assertEqual(report["original_forecast_sha256"],
                         "sha256:"+sha256(self.forecast_path.read_bytes()).hexdigest())
        self.assertEqual(report["original_freeze_sha256"],
                         "sha256:"+sha256(self.freeze_path.read_bytes()).hexdigest())

    def test_mutating_freeze_record_after_prediction_fails_link(self):
        blob=json.loads(self.freeze_path.read_text())
        blob["registered_utc_claimed"]="2026-11-15T23:01:00+00:00"
        file_desc(self.freeze_path,json.dumps(blob).encode())
        with self.assertRaisesRegex(ValueError,"FORECAST_DOES_NOT_BIND"):
            record_files(self.freeze_path,self.forecast_path,
                         self.root/"receipt.json",actual_now=NOW)

    def test_wrong_or_missing_code_config_and_feature_hashes_fail(self):
        for field in ("model_code_sha256","model_config_sha256"):
            f=deepcopy(self.forecast)
            f[field]="sha256:"+"0"*64
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"HASH_CHANGED"):
                self.check(forecast=f)
        f=deepcopy(self.forecast)
        f["feature_source_hashes"]={}
        with self.assertRaisesRegex(ValueError,"CENSUS_MISMATCH"):
            self.check(forecast=f)

    def test_cross_sport_event_period_model_version_fail(self):
        for k,v in (("sport","CBB"),("event_id","ANOTHER-EVT"),
                    ("market_family","SPREAD"),("period","1H"),
                    ("model_version","new-untested-model")):
            f=deepcopy(self.forecast);f[k]=v
            with self.subTest(field=k),self.assertRaisesRegex(ValueError,"NOT_SAME"):
                self.check(forecast=f)

    def test_forecast_generated_before_freeze_archive_rejected(self):
        f=deepcopy(self.forecast);f["generated_utc"]="2026-11-16T01:00:10Z"
        with self.assertRaisesRegex(ValueError,"NOT_PROSPECTIVE"):
            self.check(forecast=f)

    def test_capture_claim_after_wall_clock_rejected(self):
        f=deepcopy(self.forecast);f["captured_utc"]="2026-11-16T01:05:00Z"
        with self.assertRaisesRegex(ValueError,"NOT_PROSPECTIVE"):
            self.check(forecast=f)

    def test_late_or_retroactive_replays_rejected(self):
        with self.assertRaisesRegex(ValueError,"STALE_BACKDATED"):
            self.check(now=NOW+timedelta(minutes=6))
        with self.assertRaisesRegex(ValueError,"NOT_PROSPECTIVE"):
            self.check(now=NOW+timedelta(hours=2))

    def test_model_p_zero_one_nan_inf_or_negative_refused(self):
        for p in ("0","1","-0.1","1.1","NaN","Infinity", "hello", 0.55, True):
            f=deepcopy(self.forecast)
            f["predictions"][0]["model_probability"]=p
            with self.subTest(p=p),self.assertRaisesRegex(ValueError,"PROBABILITY"):
                self.check(forecast=f)

    def test_duplicate_selection_after_casefold_refused(self):
        f=deepcopy(self.forecast)
        duplicate=deepcopy(f["predictions"][0])
        duplicate["market_identity"][-1]="includes_ot"
        f["predictions"].append(duplicate)
        with self.assertRaisesRegex(ValueError,"DUPLICATE_CANONICAL"):
            self.check(forecast=f)

    def test_other_event_or_settlement_in_identity_rejected(self):
        for index,value in ((0,"CBB"),(1,"OTHER-EVENT"),(2,"ML"),(3,"1H"),(9,"")):
            f=deepcopy(self.forecast)
            f["predictions"][0]["market_identity"][index]=value
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,"MISMATCH"):
                self.check(forecast=f)

    def test_invalid_key_arity_unknown_fields_and_control_token(self):
        f=deepcopy(self.forecast)
        f["predictions"][0]["market_identity"].append("extra")
        with self.assertRaisesRegex(ValueError,"TEN_PART"):
            self.check(forecast=f)
        f=deepcopy(self.forecast);f["unexpected"]="hidden"
        with self.assertRaisesRegex(ValueError,"INVALID_FORECAST_FIELDS"):
            self.check(forecast=f)
        f=deepcopy(self.forecast);f["predictions"][0]["market_identity"][5]="42.5\n"
        with self.assertRaisesRegex(ValueError,"INVALID_CANONICAL"):
            self.check(forecast=f)

    def test_prediction_census_must_be_nonempty_and_bounded(self):
        f=deepcopy(self.forecast);f["predictions"]=[]
        with self.assertRaisesRegex(ValueError,"BOUNDED_FORECAST_ROWS"):
            self.check(forecast=f)
        f=deepcopy(self.forecast);f["predictions"]="no rows"
        with self.assertRaisesRegex(ValueError,"BOUNDED_FORECAST_ROWS"):
            self.check(forecast=f)

    def test_previously_promoted_freeze_claim_cannot_feed_receipt(self):
        f=deepcopy(self.freeze);f["release_certified"]=True
        with self.assertRaisesRegex(ValueError,"NOT_AN_UNPROMOTED"):
            self.check(freeze=f)
        f=deepcopy(self.freeze);f["official_counted"]=1
        with self.assertRaisesRegex(ValueError,"NOT_AN_UNPROMOTED"):
            self.check(freeze=f)

    def test_duplicate_original_json_keys_and_nonfinite_values_refused(self):
        with self.assertRaisesRegex(ValueError,"INVALID_OR_AMBIGUOUS_JSON"):
            _parse(b'{"a":1,"a":2}',"fixture")
        with self.assertRaisesRegex(ValueError,"INVALID_OR_AMBIGUOUS_JSON"):
            _parse(b'{"p":NaN}',"fixture")

    def test_public_repo_path_and_symlinked_files_refused(self):
        with self.assertRaisesRegex(ValueError,"PUBLIC_REPOSITORY"):
            record_files(self.freeze_path,self.forecast_path,
                         ROOT/"NEVER_WRITE_FORECAST_PRIVATE.json",actual_now=NOW)
        alias=self.root/"alias_forecast.json"
        alias.symlink_to(self.forecast_path)
        with self.assertRaisesRegex(ValueError,"SYMLINK"):
            record_files(self.freeze_path,alias,
                         self.root/"receipt.json",actual_now=NOW)

    def test_research_input_and_output_have_owner_only_permissions(self):
        self.forecast_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,"PRIVATE_FILE_PERMISSIONS"):
            record_files(self.freeze_path,self.forecast_path,
                         self.root/"receipt.json",actual_now=NOW)
        self.forecast_path.chmod(0o600)
        self.root.chmod(0o755)
        with self.assertRaisesRegex(ValueError,"PRIVATE_PARENT_PERMISSIONS"):
            record_files(self.freeze_path,self.forecast_path,
                         self.root/"receipt.json",actual_now=NOW)


if __name__=="__main__":
    unittest.main()
