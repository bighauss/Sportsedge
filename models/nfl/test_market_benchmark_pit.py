"""Synthetic regression contract for NFL same-line, as-of odds baseline."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from market_benchmark_pit import evaluate_market_rows

SHA = "sha256:" + "f"*64


def iso(dt):
    return dt.isoformat().replace("+00:00","Z")


def row(i=0, market="SPREAD", selection="HOME", line=-3.0):
    kickoff = datetime(2026, 11, 15, 21, tzinfo=timezone.utc) + timedelta(days=i)
    if market=="MONEYLINE_2WAY":
        line,settlement = None,"TIE_PUSH"
    else:
        settlement="PUSH_ON_EXACT_LINE"
    return {
        "sport":"NFL","game_id":f"game{i}","home_id":"CHI","away_id":"GB",
        "market":market,"selection":selection,"book":"DraftKings",
        "period":"FG",
        "provider_event_id":f"dk_event_{i}",
        "provider_market_id":f"dk_market_{market}_{i}",
        "provider_outcome_id":f"dk_outcome_{selection}_{i}",
        "provider_opposite_outcome_id":f"dk_opposite_{i}",
        "quote_receipt_id":f"dk_quote_{i}",
        "home_spread_or_total_line":line,
        "american_taken":-110,"american_opposite":-110,
        "model_p_win":0.5,"model_p_push":0.25,"model_p_loss":0.25,
        "model_sha256":SHA,"model_forecast_sha256":SHA,
        "provider_quote_sha256":SHA,
        "kickoff_utc":iso(kickoff),
        "model_features_observed_utc":iso(kickoff-timedelta(hours=2)),
        "model_asof_utc":iso(kickoff-timedelta(hours=1)),
        "quote_observed_utc":iso(kickoff-timedelta(minutes=62)),
        "quote_captured_utc":iso(kickoff-timedelta(minutes=61)),
        "decision_utc":iso(kickoff-timedelta(minutes=60)),
        "final_utc":iso(kickoff+timedelta(hours=4)),
        "result_available_utc":iso(kickoff+timedelta(hours=5)),
        "final_home":24,"final_away":21,
        "tie_settlement":settlement,
    }


class NFLPITMarketBenchmarkTests(unittest.TestCase):
    def test_original_110_price_and_50pct_market_baseline(self):
        x=evaluate_market_rows([row()])
        self.assertEqual(x["accepted_research_rows"],1)
        self.assertEqual(len(x["rejected_rows"]),0)
        pick=x["research_rows"][0]
        self.assertEqual(pick["outcome"],"P")
        self.assertEqual(pick["market_novig_conditional_win"],.5)
        self.assertAlmostEqual(pick["model_conditional_win"],2/3)
        self.assertAlmostEqual(pick["raw_model_ev_per_unit"],
                               .5*100/110-.25)
        self.assertEqual(x["market_evaluations"]["SPREAD"]["pushes"],1)
        self.assertEqual(x["market_evaluations"]["SPREAD"]["model_conditional_brier"],None)
        self.assertEqual(x["approved_stake_u"],0)

    def test_home_away_spread_and_different_line_settlement(self):
        r=row()
        r["home_spread_or_total_line"]=-2.5
        result=evaluate_market_rows([r])["research_rows"][0]
        self.assertEqual(result["outcome"],"W")
        r["selection"]="AWAY"
        result=evaluate_market_rows([r])["research_rows"][0]
        self.assertEqual(result["outcome"],"L")
        self.assertAlmostEqual(result["profit_one_hypothetical_unit"],-1.0)

    def test_total_over_under_and_push(self):
        r=row(market="TOTAL",selection="OVER",line=45)
        self.assertEqual(evaluate_market_rows([r])["research_rows"][0]["outcome"],"P")
        r["home_spread_or_total_line"]=44.5
        self.assertEqual(evaluate_market_rows([r])["research_rows"][0]["outcome"],"W")
        r["selection"]="UNDER"
        self.assertEqual(evaluate_market_rows([r])["research_rows"][0]["outcome"],"L")

    def test_both_team_total_sides(self):
        h=row(market="HOME_TEAM_TOTAL",selection="OVER",line=24)
        a=row(1,market="AWAY_TEAM_TOTAL",selection="UNDER",line=22)
        x=evaluate_market_rows([h,a])
        self.assertEqual([r["outcome"] for r in x["research_rows"]],["P","W"])

    def test_two_way_ml_tie_requires_explicit_push(self):
        r=row(market="MONEYLINE_2WAY",selection="HOME")
        r["final_away"]=24
        self.assertEqual(evaluate_market_rows([r])["research_rows"][0]["outcome"],"P")
        r["tie_settlement"]="HOUSE_RULE"
        out=evaluate_market_rows([r])
        self.assertEqual(out["accepted_research_rows"],0)
        self.assertIn("MONEYLINE_TIE_SETTLEMENT_NOT_EXPLICIT",
                      out["rejected_rows"][0]["reason"])

    def test_original_odds_positive_and_negative_payout(self):
        a=row()
        a["home_spread_or_total_line"]=-2.5
        a["american_taken"]=120
        a["american_opposite"]=-140
        x=evaluate_market_rows([a])
        pick=x["research_rows"][0]
        self.assertEqual(pick["profit_one_hypothetical_unit"],1.2)
        self.assertAlmostEqual(pick["book_overround"],
                               100/220+140/240-1.0)
        self.assertAlmostEqual(x["market_evaluations"]["SPREAD"][
            "net_units_at_original_prices_hypothetical_1u_each"],1.2)

    def test_stale_quotes_retained_as_explicit_rejection(self):
        a=row()
        a["quote_observed_utc"]=iso(datetime(2026,11,15,19,0,tzinfo=timezone.utc))
        out=evaluate_market_rows([a])
        self.assertEqual(out["input_rows"],1)
        self.assertEqual(out["accepted_research_rows"],0)
        self.assertIn("STALE_PROVIDER_OR_LOCAL_QUOTE",
                      out["rejected_rows"][0]["reason"])

    def test_future_model_or_quote_rejected(self):
        a=row()
        a["model_asof_utc"]=a["final_utc"]
        out=evaluate_market_rows([a])
        self.assertIn("POINT_IN_TIME",out["rejected_rows"][0]["reason"])
        a=row()
        a["quote_captured_utc"]=a["final_utc"]
        out=evaluate_market_rows([a])
        self.assertIn("POINT_IN_TIME",out["rejected_rows"][0]["reason"])

    def test_missing_fields_bad_identity_price_and_hash_do_not_zero_fill(self):
        a=row()
        del a["american_taken"]
        out=evaluate_market_rows([a])
        self.assertIn("MARKET_EVALUATION_SCHEMA_MISMATCH",
                      out["rejected_rows"][0]["reason"])
        a=row()
        a["american_taken"]=0
        out=evaluate_market_rows([a])
        self.assertIn("INVALID_AMERICAN_PRICE",
                      out["rejected_rows"][0]["reason"])
        a=row()
        a["model_forecast_sha256"]="backdated"
        out=evaluate_market_rows([a])
        self.assertIn("BAD_SOURCE_OR_MODEL_HASH",
                      out["rejected_rows"][0]["reason"])

    def test_malformed_probability_simplex_rejected(self):
        a=row()
        a["model_p_win"]=1.5
        out=evaluate_market_rows([a])
        self.assertIn("MODEL_PROBABILITY_SIMPLEX_INVALID",
                      out["rejected_rows"][0]["reason"])
        a=row()
        a["model_p_win"]=0
        a["model_p_push"]=1
        a["model_p_loss"]=0
        out=evaluate_market_rows([a])
        self.assertIn("NO_NONPUSH_MODEL_MASS",
                      out["rejected_rows"][0]["reason"])

    def test_duplicate_same_observation_not_double_counted(self):
        a=row()
        b=deepcopy(a)
        out=evaluate_market_rows([a,b])
        self.assertEqual(out["input_rows"],2)
        self.assertEqual(out["accepted_research_rows"],1)
        self.assertIn("DUPLICATE_SAME_MARKET_OUTCOME_PRICE",
                      out["rejected_rows"][0]["reason"])

    def test_thirty_distinct_events_cluster_ci_reported(self):
        rows=[]
        for i in range(40):
            a=row(i)
            a["home_spread_or_total_line"]=-2.5
            if i%3==0:
                a["final_home"]=17
                a["final_away"]=24
            rows.append(a)
        report=evaluate_market_rows(rows)
        subset=report["market_evaluations"]["SPREAD"]
        self.assertEqual(subset["evaluated_distinct_games"],40)
        self.assertTrue(subset["has_30_independent_games"])
        self.assertEqual(subset["evaluated_nonpush_rows"],40)
        self.assertIsNotNone(subset["paired_brier_gain_cluster_95pct_ci"])
        self.assertEqual(len(subset["paired_brier_gain_cluster_95pct_ci"]),2)
        self.assertEqual(report["official_counted"],0)

    def test_small_event_count_flagged_and_all_losses_retained(self):
        rows=[]
        for i in range(10):
            a=row(i)
            a["home_spread_or_total_line"]=-2.5
            a["final_home"]=7
            a["final_away"]=28
            rows.append(a)
        out=evaluate_market_rows(rows)
        p=out["market_evaluations"]["SPREAD"]
        self.assertEqual(p["losses"],10)
        self.assertEqual(p["net_units_at_original_prices_hypothetical_1u_each"],-10)
        self.assertFalse(p["has_30_independent_games"])
        self.assertIsNone(p["paired_brier_gain_cluster_95pct_ci"])

    def test_all_market_types_remain_in_inventory(self):
        r=row()
        out=evaluate_market_rows([r])
        self.assertEqual(out["market_evaluations"]["TOTAL"]["status"],"NOT_CAPTURED")
        self.assertEqual(out["market_evaluations"]["SPREAD"]["status"],"PAPER_HOLD_0U")
        self.assertFalse(out["market_quotes_verified"])
        self.assertFalse(out["closing_line_verified"])

    def test_non_fg_period_and_provider_id_collisions_are_rejected(self):
        a=row()
        a["period"]="1H"
        out=evaluate_market_rows([a])
        self.assertIn("EXPLICIT_FULL_GAME_PERIOD_REQUIRED",
                      out["rejected_rows"][0]["reason"])
        a=row()
        a["provider_outcome_id"]=a["provider_opposite_outcome_id"]
        out=evaluate_market_rows([a])
        self.assertIn("SAME_PROVIDER_OUTCOME_ID_BOTH_SIDES",
                      out["rejected_rows"][0]["reason"])
        a=row()
        a["provider_market_id"]=""
        out=evaluate_market_rows([a])
        self.assertIn("EVENT_OR_BOOK_ID_MISSING",
                      out["rejected_rows"][0]["reason"])

    def test_custom_freshness_limit_must_be_bounded(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PREGAME_FRESHNESS_LIMIT"):
            evaluate_market_rows([row()],freshness_seconds=1000)


if __name__=="__main__":
    unittest.main()
