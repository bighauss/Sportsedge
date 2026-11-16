"""Synthetic prequential NFL score-probability audit leak and source tests."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from score_probability_audit_pit import evaluate_frozen_distributions, main
from score_walkforward_pit import REPO_ROOT


SHA = "sha256:" + "a"*64
AUDIT = "2026-11-15T23:00:00Z"


def iso(time):
    return time.isoformat().replace("+00:00", "Z")


def fixtures(n=90, *, lines=True):
    kickoff0 = datetime(2026, 1, 1, 21, tzinfo=timezone.utc)
    outcomes = ((24,21),(27,20),(21,21),(17,24))
    history = []
    quotes = []
    for i in range(n):
        kickoff = kickoff0 + timedelta(days=2*i)
        hs, aw = outcomes[i%4]
        history.append({
            "game_id":f"game_{i}",
            "home_id":"CHI" if i%2==0 else "GB",
            "away_id":"GB" if i%2==0 else "CHI",
            "kickoff_utc":iso(kickoff),
            "forecast_asof_utc":iso(kickoff-timedelta(hours=2)),
            "source_observed_utc":iso(kickoff-timedelta(hours=4)),
            "model_sha256":SHA,
            "projected_home":20.0+(i%3),
            "projected_away":20.0,
            "final_utc":iso(kickoff+timedelta(hours=4)),
            "result_available_utc":iso(kickoff+timedelta(hours=6)),
            "final_home":hs,
            "final_away":aw,
        })
        if lines:
            quotes.append({
                "game_id":f"game_{i}",
                "observed_at_utc":iso(kickoff-timedelta(hours=3)),
                "home_spread":-3.0,
                "game_total":45.0,
                "home_team_total":24.0,
                "away_team_total":21.0,
            })
    return history, quotes


def run(history, lines=None, **kw):
    return evaluate_frozen_distributions(
        history, lines=lines, audit_asof_utc=kw.pop("audit_asof_utc",AUDIT),
        min_history=kw.pop("min_history",50), **kw)


class NFLPrequentialProbabilityTests(unittest.TestCase):
    def test_all_games_and_market_families_are_preserved(self):
        history, lines = fixtures()
        out = run(history, lines)
        self.assertEqual(out["status"],"PAPER_HOLD_0U")
        self.assertEqual(out["official_counted"],0)
        self.assertEqual(out["approved_stake_u"],0)
        self.assertFalse(out["independently_authenticated_inputs"])
        self.assertFalse(out["score_probability_calibration_approved"])
        self.assertIsNone(out["exact_betting_ev"])
        self.assertEqual(out["history_rows_seen"],90)
        self.assertEqual(out["unique_games_seen"],90)
        self.assertEqual(len(out["event_ledger"]),90)
        self.assertEqual(out["event_ledger"][50]["training_only_prior_game_count"],50)
        for name in ("MONEYLINE","SPREAD","GAME_TOTAL",
                     "HOME_TEAM_TOTAL","AWAY_TEAM_TOTAL"):
            m=out["market_summaries"][name]
            self.assertEqual(m["evaluated_distinct_games"],40)
            self.assertTrue(m["has_30_independent_games"])
            self.assertIsNotNone(m["model_3way_brier"])
            self.assertIsNotNone(m["model_3way_logloss"])
            self.assertIsNotNone(m["train_only_raw_result_baseline_3way_brier"])
            self.assertEqual(len(m["paired_brier_gain_game_bootstrap_95pct_ci"]),2)
            self.assertEqual(out["withheld_census"][name+":NO_MODEL"],50)

    def test_same_event_final_cannot_affect_own_probability(self):
        hist, lines=fixtures()
        before=run(hist,lines)
        updated=deepcopy(hist)
        updated[60]["final_home"]=99
        updated[60]["final_away"]=0
        after=run(updated,lines)
        own_a=before["event_ledger"][60]["market_diagnostics"]["MONEYLINE"]
        own_b=after["event_ledger"][60]["market_diagnostics"]["MONEYLINE"]
        self.assertEqual(own_a["model_threeway_probabilities"],
                         own_b["model_threeway_probabilities"])
        self.assertEqual(own_a["baseline_threeway_probabilities"],
                         own_b["baseline_threeway_probabilities"])
        self.assertNotEqual(own_a["observed_class_0_home_or_over_1_push_2_away_or_under"],
                            own_b["observed_class_0_home_or_over_1_push_2_away_or_under"])

    def test_future_or_unpublished_final_cannot_enter_earlier_training(self):
        hist, lines=fixtures()
        before=run(hist,lines)
        new=deepcopy(hist)
        new[89]["final_home"]=98
        after=run(new,lines)
        # All earlier forecasts are identical; only the final game's own
        # observed grade can change, never the trained probabilities.
        for i in range(89):
            self.assertEqual(before["event_ledger"][i],
                             after["event_ledger"][i])

    def test_late_published_result_is_excluded_from_training(self):
        hist,lines=fixtures()
        before=run(hist,lines)
        new=deepcopy(hist)
        new[0]["result_available_utc"]="2026-06-20T00:00:00Z"
        after=run(new,lines)
        old_count=before["event_ledger"][60]["training_only_prior_game_count"]
        new_count=after["event_ledger"][60]["training_only_prior_game_count"]
        self.assertEqual(old_count,60)
        self.assertEqual(new_count,59)

    def test_missing_lines_are_not_claimed_as_unoffered_markets(self):
        hist,_=fixtures()
        out=run(hist)
        self.assertEqual(out["market_summaries"]["MONEYLINE"][
            "evaluated_distinct_games"],40)
        for name in ("SPREAD","GAME_TOTAL","HOME_TEAM_TOTAL","AWAY_TEAM_TOTAL"):
            self.assertEqual(out["market_summaries"][name][
                "evaluated_distinct_games"],0)
            self.assertEqual(out["withheld_census"][name+":NOT_CAPTURED"],40)
            self.assertEqual(out["withheld_census"][name+":NO_MODEL"],50)
        self.assertEqual(out["market_line_event_count"],0)

    def test_mixed_model_versions_are_never_pooling_history(self):
        hist, lines=fixtures()
        hist[0]["model_sha256"]="sha256:"+"b"*64
        out=run(hist,lines)
        self.assertEqual(out["event_ledger"][60]["training_only_prior_game_count"],59)
        self.assertFalse(out["score_probability_calibration_approved"])

    def test_short_history_stays_unscored_and_visible(self):
        hist,lines=fixtures(31)
        out=run(hist,lines)
        self.assertEqual(out["unique_games_seen"],31)
        self.assertEqual(out["market_summaries"]["MONEYLINE"][
            "evaluated_distinct_games"],0)
        self.assertIsNone(out["market_summaries"]["MONEYLINE"][
            "model_3way_brier"])
        self.assertFalse(out["market_summaries"]["MONEYLINE"][
            "has_30_independent_games"])
        self.assertEqual(out["withheld_census"]["MONEYLINE:NO_MODEL"],31)

    def test_no_training_threshold_below_30(self):
        hist, lines=fixtures()
        with self.assertRaisesRegex(ValueError,"MINIMUM_RESIDUAL_HISTORY"):
            run(hist,lines,min_history=20)

    def test_duplicate_or_missing_event_identity_is_refused(self):
        hist,lines=fixtures()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_FROZEN_EVENT_ID"):
            run(hist+[deepcopy(hist[0])],lines)
        hist[0].pop("game_id")
        with self.assertRaisesRegex(ValueError,"BAD_HISTORICAL_FORECAST_SCHEMA"):
            run(hist,lines)

    def test_own_report_cannot_grade_unavailable_future_finals(self):
        hist, lines=fixtures()
        hist[-1]["result_available_utc"]="2026-12-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"RESULT_NOT_AVAILABLE_BY_AUDIT_TIME"):
            run(hist,lines)

    def test_duplicate_unknown_or_postfreeze_market_lines_are_refused(self):
        hist,lines=fixtures()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PREGAME_LINE_EVENT"):
            run(hist,lines+[deepcopy(lines[0])])
        a=deepcopy(lines)
        a[0]["game_id"]="unknown_event"
        with self.assertRaisesRegex(ValueError,"UNKNOWN_LINE_EVENT_ID"):
            run(hist,a)
        a=deepcopy(lines)
        a[50]["observed_at_utc"]=hist[50]["kickoff_utc"]
        with self.assertRaisesRegex(ValueError,"MARKET_LINES_AFTER_FROZEN_FORECAST"):
            run(hist,a)

    def test_no_two_way_ml_tie_settlement_inferred(self):
        hist,lines=fixtures()
        out=run(hist,lines)
        r=out["event_ledger"][50]["market_diagnostics"]["MONEYLINE"]
        self.assertEqual(len(r["model_threeway_probabilities"]),3)
        self.assertIn(r["observed_class_0_home_or_over_1_push_2_away_or_under"],(0,1,2))
        self.assertNotIn("ev",r)
        self.assertNotIn("approved_stake",r)


class NFLProbabilityAuditCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        hist,lines=fixtures(85)
        self.originals={
            "history":json.dumps(hist).encode("utf-8"),
            "lines":json.dumps(lines).encode("utf-8"),
        }
        self.paths={}
        for key,raw in self.originals.items():
            path=self.root/(key+".json")
            path.write_bytes(raw)
            self.paths[key]=path
        self.out=self.root/"audit.json"

    def run_cli(self, **kwargs):
        paths=dict(self.paths)
        paths.update(kwargs)
        argv=["score_probability_audit_pit.py",
              "--history",str(paths["history"]),
              "--lines",str(paths["lines"]),
              "--out",str(kwargs.get("out",self.out))]
        with patch("sys.argv",argv),redirect_stdout(io.StringIO()):
            main()

    def test_private_output_sha_0600_no_wager_and_no_overwrite(self):
        self.run_cli()
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode),0o600)
        result=json.loads(self.out.read_bytes())
        self.assertEqual(result["approved_stake_u"],0)
        self.assertEqual(result["official_counted"],0)
        for key in self.originals:
            self.assertEqual(result["local_original_input_sha256"][key],
                             "sha256:"+sha256(self.originals[key]).hexdigest())
        before=self.out.read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_cli()
        self.assertEqual(before,self.out.read_bytes())

    def test_duplicate_json_keys_and_numeric_overflow_refused(self):
        original=self.paths["history"].read_bytes()
        self.paths["history"].write_bytes(b'[{"unused":{"key":1,"key":2}}]')
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
            self.run_cli()
        self.paths["history"].write_bytes(b'[{"unused":1e9999}]')
        with self.assertRaisesRegex(ValueError,"NONFINITE_JSON_NUMBER_OVERFLOW"):
            self.run_cli()
        self.paths["history"].write_bytes(original)
        self.assertFalse(self.out.exists())

    def test_public_input_or_output_path_is_refused(self):
        with self.assertRaisesRegex(ValueError,
                                    "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
            self.run_cli(history=REPO_ROOT/"models/nfl/score_probability_audit_pit.py")
        with self.assertRaisesRegex(ValueError,
                                    "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
            self.run_cli(out=REPO_ROOT/"forbidden_prequential_report.json")
        self.assertFalse(self.out.exists())

    def test_failed_fsync_removes_output_without_corrupting_inputs(self):
        before=self.paths["history"].read_bytes()
        with patch("score_walkforward_pit.os.fsync",
                   side_effect=OSError("synthetic report failure")):
            with self.assertRaisesRegex(OSError,"synthetic report failure"):
                self.run_cli()
        self.assertFalse(self.out.exists())
        self.assertEqual(before,self.paths["history"].read_bytes())


if __name__=="__main__":
    unittest.main()
