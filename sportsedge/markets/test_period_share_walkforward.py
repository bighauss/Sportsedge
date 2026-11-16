"""Adversarial synthetic walk-forward tests; no true provider or bet evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.markets.period_share_walkforward import audit, main
from sportsedge.markets.test_period_share_fit import make_rows, encode, ts


class PeriodWalkforwardTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.start = self.now-timedelta(days=45)
        self.asof = ts(self.now-timedelta(days=1))
        self.rows = make_rows("NFL", count=160, start=self.start)

    def run_audit(self, rows=None, sport="NFL", **kw):
        return audit(encode(self.rows if rows is None else rows),
                     sport=sport, evaluation_asof_utc=self.asof, **kw)

    def test_real_rolling_folds_and_full_census(self):
        result = self.run_audit()
        self.assertEqual(result["status"],
                         "RESEARCH_WALKFORWARD_DESCRIPTIVE_NOT_CERTIFIED")
        self.assertGreaterEqual(result["completed_folds"], 3)
        self.assertEqual(result["blocked_rows"], 0)
        self.assertEqual(result["input_rows"], 160)
        self.assertEqual(
            result["seed_games_before_first_eligible_fold"]
            + result["scored_holdout_games"] + result["short_tail_games_not_scored"],
            160)
        for fold in result["folds"]:
            self.assertGreaterEqual(fold["train_n"], 50)
            self.assertGreaterEqual(fold["training_distinct_dates"], 7)
            self.assertLess(fold["train_latest_final_captured_utc"],
                            fold["holdout_start_utc"])
            self.assertGreaterEqual(fold["holdout_n"],20)
            self.assertAlmostEqual(sum(fold["trained_period_shares"]),1)
            self.assertIsNotNone(fold["model_logloss_per_scoring_point"])
        self.assertEqual(result["official"],False)
        self.assertEqual(result["approved_stake_u"],0)
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["period_holdout_calibrated"])

    def test_same_original_bytes_and_cutoff_replay_identically(self):
        self.assertEqual(self.run_audit(),self.run_audit())
        changed=make_rows("NFL",count=160,start=self.start)
        changed[4]["periods"]["Q1"][0]+=2
        changed[4]["regulation_home"]+=2
        p=self.run_audit(changed)
        self.assertNotEqual(p["original_file_sha256"],
                            self.run_audit()["original_file_sha256"])
        self.assertNotEqual(p["folds"][0]["train_original_subset_sha256"],
                            self.run_audit()["folds"][0]["train_original_subset_sha256"])

    def test_late_final_cannot_enter_earlier_training(self):
        rows=make_rows("NFL",count=160,start=self.start)
        # Event started before the heldout period but finalized much later.
        late_time=self.start+timedelta(days=11)
        rows[0]["final_published_utc"]=ts(late_time)
        rows[0]["final_captured_utc"]=ts(late_time+timedelta(minutes=10))
        report=self.run_audit(rows)
        self.assertEqual(report["blocked_rows"],0)
        self.assertGreaterEqual(report["completed_folds"],3)
        for fold in report["folds"]:
            self.assertLess(fold["train_latest_final_captured_utc"],
                            fold["holdout_start_utc"])
        # Explicit original-byte refit proves the unavailable first record
        # was excluded from the first training subset.
        first_cutoff=datetime.fromisoformat(
            report["folds"][0]["holdout_start_utc"])
        eligible=[row for row in rows
                  if datetime.fromisoformat(
                         row["game_start_utc"].replace("Z","+00:00"))<first_cutoff
                  and datetime.fromisoformat(
                         row["final_captured_utc"].replace("Z","+00:00"))<first_cutoff]
        self.assertNotIn(rows[0],eligible)
        self.assertEqual(report["folds"][0]["train_n"],len(eligible))
        self.assertEqual(
            report["folds"][0]["train_original_subset_sha256"],
            "sha256:"+sha256(encode(eligible)).hexdigest())

    def test_same_start_cohort_never_split_across_holdouts(self):
        rows=make_rows("NFL",count=170,start=self.start)
        shared=self.start+timedelta(days=10)
        for row in rows[64:94]:
            row["game_start_utc"]=ts(shared)
            row["final_published_utc"]=ts(shared+timedelta(hours=4))
            row["final_captured_utc"]=ts(shared+timedelta(hours=5))
        out=self.run_audit(rows)
        self.assertEqual(out["blocked_rows"],0)
        for fold in out["folds"]:
            self.assertNotEqual(fold["holdout_n"],0)
        # Any same-start 30-event cohort must occur wholly in ONE holdout.
        spans=[f for f in out["folds"]
               if f["holdout_start_utc"]<=shared.isoformat()<
                  f["holdout_last_start_utc"] or
                  f["holdout_start_utc"]==shared.isoformat()]
        self.assertTrue(spans)
        self.assertGreaterEqual(spans[0]["holdout_n"],30)

    def test_all_duplicate_copies_block_entire_evaluation(self):
        rows=make_rows("NFL",count=160,start=self.start)
        rows[2]["event_id"]="  "+rows[1]["event_id"].upper()+"  "
        result=self.run_audit(rows)
        self.assertEqual(result["status"],"BLOCK_INVALID_OR_INSUFFICIENT_ORIGINAL_LEDGER")
        self.assertEqual(result["blocked_rows"],2)
        self.assertEqual(result["completed_folds"],0)
        self.assertEqual(result["scored_holdout_games"],0)
        self.assertIn("PERIOD_DUPLICATE_EVENT_ALL_COPIES_QUARANTINED",
                      result["blocked_reasons"])

    def test_bad_incomplete_or_future_result_blocks_all_folds(self):
        for change in ("late","badscore","extra"):
            with self.subTest(change=change):
                rows=make_rows("NFL",count=160,start=self.start)
                if change=="late":
                    rows[7]["final_captured_utc"]=self.asof
                elif change=="badscore":
                    rows[7]["regulation_away"]+=4
                else:
                    rows[7]["periods"]["OT"]=[3,0]
                x=self.run_audit(rows)
                self.assertEqual(x["completed_folds"],0)
                self.assertGreater(x["blocked_rows"],0)
                self.assertEqual(x["status"],"BLOCK_INVALID_OR_INSUFFICIENT_ORIGINAL_LEDGER")

    def test_malformed_json_cannot_disappear_from_denominator(self):
        payload=encode(self.rows)+b'{"sport":"NFL","sport":"CFB"}\n'
        x=audit(payload,sport="NFL",evaluation_asof_utc=self.asof)
        self.assertEqual(x["input_rows"],161)
        self.assertEqual(x["blocked_rows"],1)
        self.assertEqual(x["folds"],[])

    def test_mlb_nine_innings_and_cbb_actual_halves(self):
        for sport,expected in (("MLB",9),("CBB",2)):
            with self.subTest(sport=sport):
                rows=make_rows(sport,count=160,start=self.start)
                out=self.run_audit(rows,sport=sport)
                self.assertGreaterEqual(out["completed_folds"],3)
                self.assertEqual(len(out["folds"][0]["trained_period_shares"]),
                                 expected)
                self.assertEqual(out["blocked_rows"],0)

    def test_training_can_be_better_than_uniform_but_not_certified(self):
        x=self.run_audit()
        # Synthetically biased quarters, not evidence of real-world skill.
        self.assertLess(x["weighted_model_minus_uniform_logloss"],0)
        self.assertFalse(x["period_holdout_calibrated"])
        self.assertTrue(any("uniform baseline is NOT a sportsbook" in w
                            for w in x["warnings"]))

    def test_zero_scoring_holdout_games_visible_and_unscored(self):
        rows=make_rows("NFL",count=160,start=self.start)
        for row in rows[56:76]:
            row["periods"]={k:[0,0] for k in row["periods"]}
            row["regulation_home"]=0
            row["regulation_away"]=0
        out=self.run_audit(rows)
        self.assertGreaterEqual(out["completed_folds"],3)
        self.assertGreater(sum(f["zero_score_holdout_games"]
                               for f in out["folds"]),0)
        self.assertEqual(out["scored_holdout_games"] +
                         out["seed_games_before_first_eligible_fold"]+
                         out["short_tail_games_not_scored"],160)

    def test_future_evaluation_asof_and_weak_policy_rejected(self):
        with self.assertRaisesRegex(ValueError,"EVALUATION_ASOF_IN_FUTURE"):
            audit(encode(self.rows), sport="NFL",
                  evaluation_asof_utc=ts(self.now+timedelta(days=2)))
        for args in ({"minimum_training":20},{"holdout_per_fold":2},
                     {"minimum_folds":1},{"minimum_dates":2}):
            with self.subTest(args=args),self.assertRaisesRegex(ValueError,"WEAK"):
                self.run_audit(**args)

    def test_private_cli_create_only_and_no_source_data_emitted(self):
        with tempfile.TemporaryDirectory() as d:
            inp=Path(d)/"private_periods.jsonl"
            out=Path(d)/"research_report.json"
            inp.write_bytes(encode(self.rows))
            args=["--input",str(inp),"--out",str(out),
                  "--sport","NFL","--evaluation-asof-utc",self.asof]
            main(args)
            result=json.loads(out.read_text())
            self.assertEqual(result["input_rows"],160)
            self.assertNotIn("synthetic-001",out.read_text())
            with self.assertRaises(FileExistsError):
                main(args)

    def test_insufficient_folds_status_without_false_proof(self):
        rows=make_rows("NFL",count=75,start=self.start)
        x=self.run_audit(rows)
        self.assertEqual(x["status"],"INSUFFICIENT_CHRONOLOGICAL_HOLDOUTS")
        self.assertFalse(x["official"])


if __name__=="__main__":
    unittest.main()
