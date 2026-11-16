"""Synthetic adversarial tests for regulation period training → RUN IT research."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.markets.period_share_fit import fit_period_shares, FIT_VERSION
from sportsedge.markets.cli import run_from_manifest
from sportsedge.markets.test_cli import manifest


def ts(t):
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_rows(sport="NFL", *, count=56, start=None):
    start = start or datetime.now(timezone.utc).replace(microsecond=0)-timedelta(days=35)
    keys = ("Q1","Q2","Q3","Q4") if sport!="MLB" else tuple("I"+str(i) for i in range(1,10))
    rows=[]
    for i in range(count):
        dt=start+timedelta(days=i//8, minutes=(i%8)*30)
        if sport=="MLB":
            points={k: [(j+i)%3, ((j+2+i)%4)//2] for j,k in enumerate(keys)}
        else:
            points={k:[2+j+(i+j)%3, 1+j+(i%2)] for j,k in enumerate(keys)}
        rows.append({
            "sport": sport, "event_id": "synthetic-%03d"%i,
            "game_start_utc": ts(dt),
            "final_published_utc": ts(dt+timedelta(hours=4)),
            "final_captured_utc": ts(dt+timedelta(hours=5)),
            "source_original_sha256": "sha256:"+"b"*64,
            "periods":points,
            "regulation_home":sum(x[0] for x in points.values()),
            "regulation_away":sum(x[1] for x in points.values()),
            "settlement_scope":"REGULATION_ONLY",
        })
    return rows


def encode(rows):
    return ("\n".join(json.dumps(r,sort_keys=True,separators=(",",":"))
                      for r in rows)+"\n").encode()


class PeriodShareTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc).replace(microsecond=0)
        self.rows=make_rows(start=self.now-timedelta(days=35))
        self.cutoff=ts(self.now-timedelta(days=2))

    def fit(self, rows=None, *, sport="NFL"):
        return fit_period_shares(encode(self.rows if rows is None else rows),
                                 sport=sport,fit_asof_utc=self.cutoff)

    def test_earlier_four_quarter_training_research_only(self):
        fit=self.fit()
        self.assertEqual(fit["schema"], FIT_VERSION)
        self.assertEqual(fit["status"],"TRAIN_ONLY_PERIOD_SHARES_RESEARCH_UNCALIBRATED")
        self.assertEqual(fit["period_keys"],["Q1","Q2","Q3","Q4"])
        self.assertEqual(fit["accepted_rows"],56)
        self.assertEqual(fit["blocked_rows"],0)
        self.assertEqual(fit["distinct_dates"],7)
        self.assertAlmostEqual(sum(fit["period_shares"]),1.0)
        self.assertTrue(all(x>0 for x in fit["period_shares"]))
        self.assertEqual(fit["source_file_sha256"],"sha256:"+sha256(encode(self.rows)).hexdigest())
        self.assertFalse(fit["source_authenticated"])
        self.assertFalse(fit["holdout_calibrated"])
        self.assertFalse(fit["official"])
        self.assertEqual(fit["approved_stake_u"],0)

    def test_nine_mlb_innings_not_four_quarters(self):
        rows=make_rows("MLB",start=self.now-timedelta(days=35))
        x=self.fit(rows,sport="MLB")
        self.assertEqual(x["accepted_rows"],56)
        self.assertEqual(x["period_keys"],["I"+str(i) for i in range(1,10)])
        self.assertEqual(len(x["period_shares"]),9)
        self.assertAlmostEqual(sum(x["period_shares"]),1.0)

    def test_nfl_cfb_nba_are_actual_four_quarters(self):
        for sport in ("CFB","NBA"):
            with self.subTest(sport=sport):
                x=self.fit(make_rows(sport,start=self.now-timedelta(days=35)),sport=sport)
                self.assertEqual(x["accepted_rows"],56)
                self.assertEqual(len(x["period_shares"]),4)

    def test_cbb_half_data_never_forged_into_four_quarters(self):
        with self.assertRaisesRegex(ValueError,"CBB_MENS_HALVES_CANNOT_BE_FOUR_QUARTERS"):
            self.fit(sport="CBB")

    def test_reject_over_time_and_extra_periods(self):
        rows=make_rows(start=self.now-timedelta(days=35))
        rows[3]["periods"]["OT"]=[3,0]
        x=self.fit(rows)
        self.assertEqual(x["status"],"BLOCK_PERIOD_SHARE_FIT")
        self.assertIn("PERIOD_INCOMPLETE_OR_EXTRA_PERIOD",x["blocked_reasons"])
        rows=make_rows(start=self.now-timedelta(days=35))
        rows[0]["settlement_scope"]="INCLUDES_OVERTIME"
        self.assertIn("PERIOD_OVERTIME_OR_EXTRA_INNINGS_NOT_SEPARATED",
                      self.fit(rows)["blocked_reasons"])

    def test_regulation_score_reconciliation_fail_closed(self):
        rows=make_rows(start=self.now-timedelta(days=35))
        rows[2]["regulation_home"]+=2
        x=self.fit(rows)
        self.assertEqual(x["blocked_rows"],1)
        self.assertIn("PERIOD_REGULATION_TOTAL_RECONCILIATION_FAILED",x["blocked_reasons"])
        self.assertIsNone(x["period_shares"])

    def test_future_final_publication_or_capture_blocks_fit(self):
        for field in ("final_published_utc","final_captured_utc"):
            with self.subTest(field=field):
                rows=make_rows(start=self.now-timedelta(days=35))
                rows[2][field]=self.cutoff
                x=self.fit(rows)
                self.assertIn("PERIOD_FUTURE_OR_UNAVAILABLE_FINAL",x["blocked_reasons"])
                self.assertIsNone(x["period_shares"])

    def test_duplicate_and_case_space_variants_both_quarantined(self):
        rows=make_rows(start=self.now-timedelta(days=35))
        rows[1]["event_id"]="  SYNTHETIC-000  "
        x=self.fit(rows)
        self.assertEqual(x["blocked_reasons"]["PERIOD_DUPLICATE_EVENT_ALL_COPIES_QUARANTINED"],2)
        self.assertEqual(x["accepted_rows"],54)
        self.assertEqual(x["status"],"BLOCK_PERIOD_SHARE_FIT")

    def test_tampered_unhashable_identity_is_block_not_exception(self):
        rows=make_rows(start=self.now-timedelta(days=35))
        rows[0]["sport"]=[]
        rows[0]["event_id"]=["bad"]
        out=self.fit(rows)
        self.assertEqual(out["status"],"BLOCK_PERIOD_SHARE_FIT")
        self.assertEqual(out["blocked_rows"],1)

    def test_future_and_missing_inning_never_imputed_zero(self):
        rows=make_rows("MLB",start=self.now-timedelta(days=35))
        del rows[2]["periods"]["I9"]
        x=self.fit(rows,sport="MLB")
        self.assertIn("PERIOD_INCOMPLETE_OR_EXTRA_PERIOD",x["blocked_reasons"])
        self.assertEqual(x["blocked_rows"],1)

    def test_nonfinite_nested_dupkeys_boolean_score_and_empty_json_fail(self):
        rows=make_rows(start=self.now-timedelta(days=35))
        base=encode(rows)
        for extra in (
            b'{"sport":"NFL","sport":"CFB"}\n',
            b'{"sport":"NFL","periods":{"Q1":[NaN,0]}}\n',
            b'\n', b'null\n',
        ):
            with self.subTest(extra=extra):
                x=fit_period_shares(base+extra,sport="NFL",fit_asof_utc=self.cutoff)
                self.assertGreater(x["blocked_rows"],0)
                self.assertIsNone(x["period_shares"])
        rows[0]["periods"]["Q1"]=[True,0]
        self.assertIn("PERIOD_INVALID_REGULATION_POINTS",self.fit(rows)["blocked_reasons"])

    def test_repeat_same_raw_is_deterministic_different_source_is_not(self):
        a=self.fit()
        self.assertEqual(a,self.fit())
        rows=make_rows(start=self.now-timedelta(days=35))
        rows[3]["periods"]["Q1"][0]+=2
        rows[3]["regulation_home"]+=2
        b=self.fit(rows)
        self.assertNotEqual(a["source_file_sha256"],b["source_file_sha256"])
        self.assertNotEqual(a["period_fit_model_sha256"],b["period_fit_model_sha256"])
        self.assertNotEqual(a["period_shares"],b["period_shares"])

    def _private_manifest(self, path, raw, *, sport="NFL"):
        p=manifest()
        p["projection"]["sport"]=sport
        p["markets"]=[]
        p["distribution"]["sport"]=sport
        p["distribution"].pop("period_shares")
        p["period_fit_ref"]={
            "path":str(path), "raw_sha256":"sha256:"+sha256(raw).hexdigest(),
            "fit_asof_utc":self.cutoff,
        }
        return p

    def test_end_to_end_paper_run_it_has_fitted_share_lineage(self):
        raw=encode(self.rows)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"original-periods.jsonl";path.write_bytes(raw)
            p=self._private_manifest(path,raw)
            result=run_from_manifest(p)
            self.assertEqual(result["period_fit_accepted_n"],56)
            self.assertEqual(result["period_fit_status"],
                "TRAIN_ONLY_PERIOD_SHARES_RESEARCH_UNCALIBRATED")
            self.assertTrue(result["period_fit_model_sha256"].startswith("sha256:"))
            self.assertTrue(result["scenario_spec_sha256"].startswith("sha256:"))
            self.assertFalse(result["period_share_calibration_verified"])
            self.assertEqual(result["approved_stake_u"],0)
            self.assertIsNone(result["card"])

    def test_two_distinct_source_ledgers_change_run_it_scenario_fingerprint(self):
        a=make_rows(start=self.now-timedelta(days=35))
        b=make_rows(start=self.now-timedelta(days=35))
        b[5]["periods"]["Q1"][0]+=1
        b[5]["regulation_home"]+=1
        with tempfile.TemporaryDirectory() as d:
            one=Path(d)/"one.jsonl";two=Path(d)/"two.jsonl"
            aa,bb=encode(a),encode(b)
            one.write_bytes(aa);two.write_bytes(bb)
            x=run_from_manifest(self._private_manifest(one,aa))
            y=run_from_manifest(self._private_manifest(two,bb))
            self.assertNotEqual(x["period_fit_model_sha256"],y["period_fit_model_sha256"])
            self.assertNotEqual(x["scenario_spec_sha256"],y["scenario_spec_sha256"])

    def test_prior_score_width_and_period_fit_can_feed_same_research_run(self):
        from sportsedge.markets.test_score_dispersion_fit import (
            records as score_records, encode as encode_scores,
        )
        period_raw=encode(self.rows)
        score_rows=score_records(self.now-timedelta(days=35))
        for row in score_rows:
            row["sport"]="NFL"
        score_raw=encode_scores(score_rows)
        with tempfile.TemporaryDirectory() as d:
            period=Path(d)/"periods.jsonl"
            score=Path(d)/"scores.jsonl"
            period.write_bytes(period_raw)
            score.write_bytes(score_raw)
            p=self._private_manifest(period,period_raw)
            p["distribution"]={"sport":"NFL","status":"UNCALIBRATED_RESEARCH"}
            p["dispersion_fit_ref"]={
                "path":str(score),
                "raw_sha256":"sha256:"+sha256(score_raw).hexdigest(),
                "fit_asof_utc":self.cutoff,
            }
            result=run_from_manifest(p)
            self.assertEqual(result["dispersion_fit_accepted_n"],56)
            self.assertEqual(result["period_fit_accepted_n"],56)
            self.assertEqual(result["dispersion_fit_status"],
                "TRAIN_ONLY_WIDTHS_READY_RESEARCH_NOT_CALIBRATED")
            self.assertEqual(result["period_fit_status"],
                "TRAIN_ONLY_PERIOD_SHARES_RESEARCH_UNCALIBRATED")
            self.assertFalse(result["period_share_calibration_verified"])
            self.assertEqual(result["approved_stake_u"],0)
            self.assertIsNone(result["card"])

    def test_caller_supplied_manual_shares_disallowed_with_fit_reference(self):
        raw=encode(self.rows)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"source.jsonl";path.write_bytes(raw)
            p=self._private_manifest(path,raw)
            p["distribution"]["period_shares"]=[.25,.25,.25,.25]
            with self.assertRaisesRegex(ValueError,"UNSUPPORTED_OR_SECRET_FIELD"):
                run_from_manifest(p)

    def test_tampered_source_sha_and_late_fit_cutoff_block(self):
        raw=encode(self.rows)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"orig.jsonl";path.write_bytes(raw)
            p=self._private_manifest(path,raw)
            p["period_fit_ref"]["raw_sha256"]="sha256:"+"0"*64
            with self.assertRaisesRegex(ValueError,"PERIOD_SOURCE_ORIGINAL_HASH_MISMATCH"):
                run_from_manifest(p)
            p=self._private_manifest(path,raw)
            p["period_fit_ref"]["fit_asof_utc"]=ts(self.now+timedelta(hours=1))
            with self.assertRaisesRegex(ValueError,"PERIOD_FIT_AFTER_PROJECTION_FREEZE"):
                run_from_manifest(p)

    def test_invalid_cbb_period_fit_never_used_in_run_it(self):
        raw=encode(self.rows)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"orig.jsonl";path.write_bytes(raw)
            p=self._private_manifest(path,raw,sport="CBB")
            with self.assertRaisesRegex(ValueError,"CBB_MENS_HALVES_CANNOT_BE_FOUR_QUARTERS"):
                run_from_manifest(p)

    def test_too_small_and_zero_score_training_blocks(self):
        a=make_rows(count=20,start=self.now-timedelta(days=35))
        x=self.fit(a)
        self.assertEqual(x["status"],"BLOCK_PERIOD_SHARE_FIT")
        for row in self.rows:
            row["periods"]={key:[0,0] for key in row["periods"]}
            row["regulation_home"]=row["regulation_away"]=0
        x=self.fit()
        self.assertIn("PERIOD_ZERO_OBSERVED_REGULATION_SCORING",x["fit_failures"])
        self.assertIsNone(x["period_shares"])


if __name__=="__main__":
    unittest.main()
