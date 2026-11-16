"""Synthetic chronology/identity/market tests for CBB research-only evaluator."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from point_in_time_score_walkforward import (
    ROOT, _no_duplicate_keys, _private, audit
)

H = "a" * 64


def make(i=0, season=2026, *, quote=True):
    start = datetime(season-1, 11, 1, 20, tzinfo=timezone.utc) + timedelta(days=i)
    fmt = lambda date: date.strftime("%Y-%m-%dT%H:%M:%SZ")
    freeze = start-timedelta(hours=4)
    game_id = f"SYNTH-{season}-{i}"
    sources = {k: {"sha256":H, "captured_utc":fmt(freeze-timedelta(hours=1))}
               for k in ("home","away","league","hca")}
    row = {
        "prediction": {
            "game_id":game_id, "season":season, "status":"PAPER_NON_COUNTED_UNCALIBRATED",
            "official":False, "stake_u":0, "home_team_id":"H1", "away_team_id":"A1",
            "freeze_utc":fmt(freeze),"tipoff_utc":fmt(start),
            "model_sha256":H,
            "source_clock_consistent_not_authenticated":sources,
            "home_points":75.0, "away_points":70.0, "margin_home":5.0,"total":145.0
        },
        "final": {
            "game_id":game_id, "season":season,
            "home_team_id":"H1", "away_team_id":"A1",
            "sha256":H, "status":"FINAL", "period":"FG_INCL_OT",
            "published_utc":fmt(start+timedelta(hours=3)),
            "captured_utc":fmt(start+timedelta(hours=4)),
            "home_score":73+i%7, "away_score":65+i%5
        }
    }
    if quote:
        row["quote"]={
            "game_id":game_id,"season":season,"period":"FG","book":"DK",
            "sha256":H,"captured_utc":fmt(freeze-timedelta(minutes=30)),
            "home_spread":-3.5,"home_price":-110,"away_price":-110,
            "total_line":144.5,"over_price":-110,"under_price":-110,
            "home_ml":-140,"away_ml":+120
        }
    return row


def slate(n=32, **kw):
    return [make(i,**kw) for i in range(n)]


class CBBWalkforwardTests(unittest.TestCase):
    def test_chronological_evaluation_and_market_pairs(self):
        rows=slate()
        report=audit(list(reversed(rows)),min_prior=30)
        self.assertEqual(report["input_rows"],32)
        self.assertEqual(report["walkforward_evaluated_n"],2)
        self.assertEqual(report["paired_spread"]["n"],2)
        self.assertEqual(report["paired_total"]["n"],2)
        self.assertEqual(report["paired_ml_brier"]["n"],2)
        self.assertIsNone(report["paired_spread"]["event_ci95"])
        self.assertEqual(report["stake_u"],0)
        self.assertFalse(report["official"])
        tested=[r for r in report["rows"] if r.get("evaluation_status")=="WALK_FORWARD_SCORED_PAPER_0U"]
        self.assertEqual({r["train_n"] for r in tested},{30,31})

    def test_only_published_finals_enter_prior_pool(self):
        rows=slate()
        rows[29]["final"]["published_utc"]=rows[31]["final"]["published_utc"]
        rows[29]["final"]["captured_utc"]=rows[31]["final"]["captured_utc"]
        result=audit(rows,min_prior=30)
        tested=[r for r in result["rows"] if r.get("evaluation_status")=="WALK_FORWARD_SCORED_PAPER_0U"]
        self.assertEqual(len(tested),1)
        self.assertEqual(tested[0]["game_id"],"SYNTH-2026-31")
        self.assertEqual(tested[0]["train_n"],30)


    def test_season_end_year_matches_tip(self):
        rows=[make()]
        rows[0]["prediction"]["season"]=2027
        self.assertIn("SEASON_END_YEAR_DOES_NOT_MATCH",audit(rows)["rows"][0]["reason"])

    def test_final_published_pre_forecast_but_captured_later_does_not_train(self):
        rows=slate()
        # Source claims the score was published on day 29, but the archive
        # did not acquire it until after day 31's freeze.
        rows[29]["final"]["captured_utc"]=rows[31]["final"]["captured_utc"]
        r=audit(rows,min_prior=30)
        self.assertEqual(r["walkforward_evaluated_n"],1)
        self.assertEqual(r["rows"][30]["evaluation_status"],"INSUFFICIENT_PRIOR_PUBLISHED_FINALS")
        self.assertEqual(r["rows"][31]["train_n"],30)

    def test_future_source_is_blocked(self):
        rows=slate()
        rows[0]["prediction"]["source_clock_consistent_not_authenticated"]["home"]["captured_utc"]=rows[0]["prediction"]["tipoff_utc"]
        res=audit(rows)
        self.assertEqual(res["rows"][0]["status"],"BLOCKED")
        self.assertIn("FUTURE_CAPTURE",res["rows"][0]["reason"])
        self.assertEqual(res["walkforward_evaluated_n"],1)

    def test_duplicate_rows_all_quarantined(self):
        rows=slate()+[copy.deepcopy(make(0))]
        report=audit(rows)
        self.assertEqual(report["rows"][0]["status"],"BLOCKED")
        self.assertEqual(report["rows"][-1]["status"],"BLOCKED")
        self.assertIn("DUPLICATE_EVENT_ALL_COPIES",report["rows"][0]["reason"])
        self.assertEqual(report["walkforward_evaluated_n"],1)

    def test_wrong_season_or_final_team_invalid(self):
        rows=[make()]
        rows[0]["final"]["season"]=2027
        self.assertIn("FINAL_IDENTITY_MISMATCH",audit(rows)["rows"][0]["reason"])
        rows=[make()]
        rows[0]["final"]["away_team_id"]="OTHER"
        self.assertIn("FINAL_IDENTITY_MISMATCH",audit(rows)["rows"][0]["reason"])


    def test_final_status_and_capture_clock_required(self):
        rows=[make()]
        rows[0]["final"]["status"]="HALFTIME"
        self.assertIn("FINAL_SETTLEMENT_STATUS",audit(rows)["rows"][0]["reason"])
        rows=[make()]
        rows[0]["final"]["captured_utc"]=rows[0]["prediction"]["freeze_utc"]
        self.assertIn("FINAL_RELEASE_OR_CAPTURE_CLOCK",audit(rows)["rows"][0]["reason"])

    def test_pending_final_retained(self):
        rows=[make()]
        rows[0]["final"]=None
        result=audit(rows)
        self.assertEqual(result["rows"][0]["status"],"PENDING_FINAL")
        self.assertEqual(result["walkforward_evaluated_n"],0)

    def test_quote_after_freeze_quarantined_but_score_remains(self):
        rows=slate()
        rows[30]["quote"]["captured_utc"]=rows[30]["prediction"]["tipoff_utc"]
        result=audit(rows)
        self.assertEqual(result["rows"][30]["quote_status"],"BLOCKED_QUOTE")
        self.assertEqual(result["rows"][30]["evaluation_status"],"WALK_FORWARD_SCORED_PAPER_0U")
        self.assertEqual(result["paired_spread"]["n"],1)

    def test_incomplete_two_sided_market_refused(self):
        rows=slate()
        del rows[30]["quote"]["away_price"]
        r=audit(rows)
        self.assertIn("PARTIAL_TWO_SIDED_SPREAD",r["rows"][30]["quote_reason"])
        self.assertEqual(r["paired_spread"]["n"],1)
        self.assertEqual(r["paired_ml_brier"]["n"],1)

    def test_quote_event_mismatch_refused(self):
        rows=slate()
        rows[30]["quote"]["game_id"]="MISMATCH"
        r=audit(rows)
        self.assertIn("QUOTE_EVENT_MISMATCH",r["rows"][30]["quote_reason"])

    def test_quote_stale_refused(self):
        rows=slate()
        freeze=datetime.fromisoformat(rows[30]["prediction"]["freeze_utc"].replace("Z","+00:00"))
        rows[30]["quote"]["captured_utc"]=(freeze-timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r=audit(rows,max_quote_age_hours=24)
        self.assertIn("QUOTE_STALE",r["rows"][30]["quote_reason"])

    def test_forged_prediction_math_refused(self):
        rows=[make()]
        rows[0]["prediction"]["margin_home"]=88
        r=audit(rows)
        self.assertIn("PREDICTION_MARGIN_INCONSISTENT",r["rows"][0]["reason"])

    def test_unsafe_probability_or_ev_not_emitted(self):
        r=audit(slate())
        for forbidden in ("ev","edge","units","wagers","certified_roi"):
            self.assertNotIn(forbidden,r)
        for x in r["rows"]:
            self.assertNotIn("bet",x)

    def test_cannot_evaluate_insufficient_training(self):
        r=audit(slate(29))
        self.assertEqual(r["walkforward_evaluated_n"],0)
        self.assertIsNone(r["model_margin_mae"])
        self.assertEqual(r["paired_total"]["n"],0)

    def test_older_season_does_not_train_new_season(self):
        rows=slate(35)
        rows+=slate(5,season=2027)
        r=audit(rows)
        self.assertEqual(r["per_season"]["2027"]["n_evaluated"],0)
        self.assertEqual(r["walkforward_evaluated_n"],5)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_KEY"):
            json.loads('{"a":1,"a":2}',object_pairs_hook=_no_duplicate_keys)

    def test_output_must_be_private_even_nested_cwd(self):
        with self.assertRaisesRegex(ValueError,"PRIVATE_SOURCE_AND_REPORT"):
            _private(ROOT/"models"/"cbb"/"test_torvik_point_in_time_baseline.py")
        with tempfile.TemporaryDirectory() as d:
            self.assertNotEqual(_private(Path(d)/"report.json"),ROOT)

    def test_no_confusing_price_containing_boolean_or_nan(self):
        rows=[make()]
        rows[0]["quote"]["home_price"]=True
        r=audit(rows)
        self.assertEqual(r["rows"][0]["quote_status"],"BLOCKED_QUOTE")
        rows=[make()]
        rows[0]["prediction"]["total"]=float("nan")
        self.assertEqual(audit(rows)["rows"][0]["status"],"BLOCKED")

    def test_policy_is_locked_minimum_size(self):
        with self.assertRaisesRegex(ValueError,"MIN_PRIOR"):
            audit([],min_prior=5)


if __name__=="__main__":
    unittest.main()
