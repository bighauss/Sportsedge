"""Synthetic 7-sport comparison, adapter, and anti-leakage regression tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import SPORTS, dead_heat_win_fraction, grade_row
from comparison import IntegrityError, evaluate_multisport
from ledger.multisport.cbb_star_audit import audit_stars
from ledger.multisport.comparison import IntegrityError as StarIntegrityError


def _make_run(run_id, sport, event_id, capture_utc, start_utc, rows, finals,
              stats=None, quarantined=False, coverage_inventory=None):
    graded = []
    for i, r in enumerate(rows):
        res, _ = grade_row(sport, r, finals, stats or {})
        graded.append(dict(r, pick_set="baseline", row=i, result=res, approved_stake_u=0))
    return {
        "manifest": {
            "run_id": run_id, "sport": sport, "event_id": event_id,
            "capture_utc": capture_utc, "start_utc": start_utc,
            "coverage_inventory": coverage_inventory or {},
        },
        "frozen_picks": {"baseline": rows},
        "quarantined": quarantined,
        "settlement": None if quarantined else {
            "run_id": run_id, "event_id": event_id, "source": "SYNTHETIC",
            "run_integrity_ok": True, "quarantined": False,
            "finals": finals, "stats": stats or {}, "graded": graded,
        },
    }


class MultiSportFrameworkTests(unittest.TestCase):
    def test_all_seven_sports_end_to_end(self):
        runs = [
            _make_run("r_nfl", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z", "2026-11-24T01:00:00Z",
                      [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=-110, model_p=0.7, market_p=0.5, blend_p=0.56, approved_stake_u=0),
                       dict(quote_id="q2", market="prop_atd", pick="yes", player="Ja'Marr Chase", line=0.5, price=120, model_p=0.55, market_p=0.45, blend_p=0.48, approved_stake_u=0)],
                      dict(away="CIN", home="WAS", away_score=10, home_score=20),
                      stats={("ja'marr chase", "atd"): 1.0},
                      coverage_inventory={"alt_line": "NOT_CAPTURED"}),
            _make_run("r_cfb", "CFB", "OSU@MICH", "2026-11-23T15:00:00Z", "2026-11-23T17:00:00Z",
                      [dict(quote_id="q1", market="1h_total", pick="over", player=None, line=24.5, price=-110, model_p=0.65, market_p=0.5, blend_p=0.55, approved_stake_u=0)],
                      dict(away="OSU", home="MICH", away_score=28, home_score=24, periods={"1H": [14, 14]})),
            _make_run("r_cbb", "CBB", "DUKE@UNC", "2026-11-23T22:00:00Z", "2026-11-24T00:00:00Z",
                      [dict(quote_id="q1", market="1h_spread", pick="UNC", player=None, line=-1.5, price=-110, model_p=0.6, market_p=0.5, blend_p=0.53, approved_stake_u=0)],
                      dict(away="DUKE", home="UNC", away_score=70, home_score=75, periods={"1H": [32, 36]})),
            _make_run("r_nba", "NBA", "BOS@LAL", "2026-11-23T23:00:00Z", "2026-11-24T03:00:00Z",
                      [dict(quote_id="q1", market="prop_pra", pick="over", player="LeBron James", line=40.5, price=-110, model_p=0.62, market_p=0.5, blend_p=0.54, approved_stake_u=0)],
                      dict(away="BOS", home="LAL", away_score=108, home_score=112),
                      stats={("lebron james", "pra"): 45.0}),
            _make_run("r_mlb", "MLB", "NYY@LAD", "2026-10-25T20:00:00Z", "2026-10-26T00:00:00Z",
                      [dict(quote_id="q1", market="f5_total", pick="under", player=None, line=4.5, price=-110, model_p=0.58, market_p=0.5, blend_p=0.52, approved_stake_u=0),
                       dict(quote_id="q2", market="prop_strikeouts", pick="over", player="Gerrit Cole", line=6.5, price=-115, model_p=0.64, market_p=0.52, blend_p=0.56, approved_stake_u=0)],
                      dict(away="NYY", home="LAD", away_score=4, home_score=3, periods={"F5": [2, 1]}),
                      stats={("gerrit cole", "strikeouts"): 8.0}),
            _make_run("r_nhl", "NHL", "TOR@BOS", "2026-11-23T22:00:00Z", "2026-11-24T00:00:00Z",
                      [dict(quote_id="q1", market="puck_line", pick="BOS", player=None, line=-1.5, price=140, model_p=0.45, market_p=0.4, blend_p=0.42, approved_stake_u=0)],
                      dict(away="TOR", home="BOS", away_score=2, home_score=4)),
            _make_run("r_pga", "PGA", "MASTERS_2026", "2026-04-09T10:00:00Z", "2026-04-09T12:00:00Z",
                      [dict(quote_id="q1", market="outright", pick="Scottie Scheffler", player="Scottie Scheffler", line=None, price=450, model_p=0.22, market_p=0.18, blend_p=0.19, approved_stake_u=0),
                       dict(quote_id="q2", market="top_5", pick="Rory McIlroy", player="Rory McIlroy", line=None, price=150, model_p=0.42, market_p=0.38, blend_p=0.39, prob_definition="conditional_no_push", approved_stake_u=0)],
                      dict(positions={"Scottie Scheffler": 1, "Rory McIlroy": 3})),
        ]
        report = evaluate_multisport(runs, "baseline")
        cands = report["candidates"]
        self.assertEqual(set(cands), {"market_only", "blend_90_10", "current_model", "independent_model"})
        self.assertEqual(set(cands["independent_model"]["by_sport"]), set(SPORTS))
        self.assertEqual({c["overall"]["n"] for c in cands.values()}, {10})
        self.assertTrue(cands["independent_model"]["overall"]["small_cluster_warning"])
        self.assertIsNotNone(cands["independent_model"]["overall"]["delta_brier_event_ci95"])
        self.assertIsNotNone(cands["independent_model"]["overall"]["delta_brier_row_ci95"])
        self.assertEqual(report["coverage_gaps"]["NFL"]["alt_line"], "NOT_CAPTURED")

    def test_no_survivorship_fallback_when_latest_pregame_quarantined(self):
        row = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=-110,
                    model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        early_valid = _make_run("r1", "NFL", "CIN@WAS", "2026-11-23T18:00:00Z", "2026-11-24T01:00:00Z", row, finals)
        late_quarantined = _make_run("r2", "NFL", "CIN@WAS", "2026-11-23T22:00:00Z", "2026-11-24T01:00:00Z", row, finals, quarantined=True)
        report = evaluate_multisport([early_valid, late_quarantined], "baseline")
        self.assertEqual(report["candidates"]["independent_model"]["overall"]["n"], 0)
        self.assertEqual(report["run_audit"]["quarantined_or_unsettled"], 1)
        self.assertEqual(report["run_audit"]["superseded_pregame_runs"], 1)

    def test_postgame_capture_excluded_to_prevent_lookahead(self):
        row = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=-110,
                    model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        postgame = _make_run("r_post", "NFL", "CIN@WAS", "2026-11-24T02:00:00Z", "2026-11-24T01:00:00Z", row, finals)
        report = evaluate_multisport([postgame], "baseline")
        self.assertEqual(report["candidates"]["independent_model"]["overall"]["n"], 0)
        self.assertEqual(report["run_audit"]["postgame_excluded"], 1)

    def test_pga_dead_heat_and_push_semantics(self):
        res, why = grade_row("PGA", dict(market="top_5", pick="A", player="A"),
                             dict(positions={"A": 5, "B": 5, "C": 5}))
        self.assertEqual(res, "P")
        self.assertIn("dead_heat", why)

    def test_equal_time_captures_fail_closed(self):
        row = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=-110,
                    model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        a = _make_run("r_a", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z", "2026-11-24T01:00:00Z", row, finals)
        b = _make_run("r_b", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z", "2026-11-24T01:00:00Z", row, finals)
        with self.assertRaises(IntegrityError):
            evaluate_multisport([a, b], "baseline")
        with self.assertRaises(IntegrityError):
            evaluate_multisport([b, a], "baseline")

    def test_inconsistent_start_times_fail_closed(self):
        row = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=-110,
                    model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        a = _make_run("r_a", "NFL", "CIN@WAS", "2026-11-23T18:00:00Z", "2026-11-24T01:00:00Z", row, finals)
        b = _make_run("r_b", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z", "2026-11-24T02:00:00Z", row, finals)
        with self.assertRaises(IntegrityError):
            evaluate_multisport([a, b], "baseline")

    def test_late_capture_cannot_hide_inconsistent_event_start(self):
        # The 01:30 quote is late under the first manifest and pregame
        # under the second. Both input orders must reject the clock conflict.
        row = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5,
                    price=-110, model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        late = _make_run("r_late", "NFL", "CIN@WAS", "2026-11-24T01:30:00Z",
                         "2026-11-24T01:00:00Z", row, finals)
        apparently_pregame = _make_run("r_other", "NFL", "CIN@WAS", "2026-11-24T01:30:00Z",
                                       "2026-11-24T02:00:00Z", row, finals)
        for runs in ([late, apparently_pregame], [apparently_pregame, late]):
            with self.subTest(order=[r["manifest"]["run_id"] for r in runs]):
                with self.assertRaisesRegex(IntegrityError, "inconsistent start_utc"):
                    evaluate_multisport(runs, "baseline")

    def test_push_counts_in_all_quote_roi_at_zero(self):
        rows = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.0, price=-110,
                     model_p=0.8, market_p=0.5, blend_p=0.6,
                     prob_definition="conditional_no_push", approved_stake_u=0),
                dict(quote_id="q2", market="total", pick="over", player=None, line=30.0, price=-110,
                     model_p=0.6, market_p=0.5, blend_p=0.55, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        run = _make_run("r_push", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z", "2026-11-24T01:00:00Z", rows, finals)
        report = evaluate_multisport([run], "baseline")
        overall = report["candidates"]["independent_model"]["overall"]
        # WAS -3.0 wins by 10 (profit 100/110); total 30.0 pushes exactly.
        self.assertEqual(overall["n"], 1)
        self.assertAlmostEqual(overall["hypothetical_roi_1u"], 100.0 / 110.0)
        self.assertEqual(overall["n_settled_quotes"], 2)
        self.assertAlmostEqual(overall["roi_all_quotes_1u"], (100.0 / 110.0) / 2)
        self.assertEqual(report["exclusion_audit"]["push_rows"], 1)

    def test_dead_heat_settles_at_fractional_book_payout(self):
        rows = [dict(quote_id="q1", market="top_5", pick="A", player="A", line=None, price=150,
                     model_p=0.42, market_p=0.38, blend_p=0.39,
                     prob_definition="conditional_no_push", approved_stake_u=0)]
        finals = dict(positions={"A": 5, "B": 5, "C": 5})
        frac = dead_heat_win_fraction(rows[0], finals)
        self.assertAlmostEqual(frac, 1.0 / 3.0)
        run = _make_run("r_dh", "PGA", "EVENT", "2026-04-09T10:00:00Z", "2026-04-09T12:00:00Z", rows, finals)
        report = evaluate_multisport([run], "baseline")
        overall = report["candidates"]["independent_model"]["overall"]
        self.assertEqual(overall["n"], 0)
        self.assertEqual(overall["n_settled_quotes"], 1)
        self.assertAlmostEqual(overall["roi_all_quotes_1u"], (1.0 / 3.0) * 1.5 - (2.0 / 3.0))
        self.assertEqual(report["exclusion_audit"]["dead_heat_rows"], 1)

    def test_missing_probability_rows_are_audited_not_silent(self):
        rows = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=-110,
                     model_p=None, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        run = _make_run("r_mp", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z", "2026-11-24T01:00:00Z", rows, finals)
        report = evaluate_multisport([run], "baseline")
        self.assertEqual(report["candidates"]["independent_model"]["overall"]["n"], 0)
        self.assertEqual(report["exclusion_audit"]["missing_probability_rows"], 1)
        self.assertEqual(report["sample_census"]["eligible_events"], 1)
        self.assertEqual(report["sample_census"]["paired_metric_events"], 0)
        self.assertEqual(report["sample_census"]["events_without_paired_rows"], ["NFL:CIN@WAS"])

    def test_superseded_equal_time_conflicts_rejected_in_every_order(self):
        from itertools import permutations
        row = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=-110,
                    model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        runs = [_make_run(rid, "NFL", "CIN@WAS", cap, "2026-11-24T01:00:00Z", row, finals)
                for rid, cap in (("a", "2026-11-23T18:00:00Z"), ("b", "2026-11-23T18:00:00Z"),
                                 ("c", "2026-11-23T20:00:00Z"))]
        for order in permutations(runs):
            with self.subTest(order=[r["manifest"]["run_id"] for r in order]):
                with self.assertRaisesRegex(IntegrityError, "ambiguous equal-time"):
                    evaluate_multisport(order, "baseline")

    def test_all_quote_roi_counts_missing_probability_losses(self):
        rows = [dict(quote_id="win", market="spread", pick="WAS", player=None, line=-3.5, price=-110,
                     model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0),
                dict(quote_id="loss", market="spread", pick="CIN", player=None, line=3.5, price=-110,
                     model_p=None, market_p=0.5, blend_p=0.4, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        run = _make_run("r_missing_loss", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z",
                        "2026-11-24T01:00:00Z", rows, finals)
        report = evaluate_multisport([run], "baseline")
        for candidate in report["candidates"].values():
            overall = candidate["overall"]
            self.assertEqual(overall["n"], 1)
            self.assertEqual(overall["n_settled_quotes"], 2)
            self.assertAlmostEqual(overall["roi_all_quotes_1u"], (100.0 / 110.0 - 1.0) / 2)
        self.assertEqual(report["exclusion_audit"]["missing_probability_rows"], 1)

    def test_invalid_prices_rejected_even_on_pushes(self):
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        for line in (29.5, 30.0, 30.5):
            for price in (float("inf"), float("-inf"), "nan", 0, -110.5, None, "bad"):
                with self.subTest(line=line, price=price):
                    rows = [dict(quote_id="q", market="total", pick="over", player=None,
                                 line=line, price=price, model_p=0.6, market_p=0.5,
                                 blend_p=0.55, prob_definition="conditional_no_push",
                                 approved_stake_u=0)]
                    run = _make_run("r", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z",
                                    "2026-11-24T01:00:00Z", rows, finals)
                    with self.assertRaises(IntegrityError):
                        evaluate_multisport([run], "baseline")

    def test_closing_probability_is_validated_and_not_authenticated(self):
        rows = [dict(quote_id="q", market="spread", pick="WAS", player=None, line=-3.5,
                     price=-110, model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        run = _make_run("r", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z",
                        "2026-11-24T01:00:00Z", rows, finals)
        for invalid in (True, -0.1, 1.1, float("inf"), "nan"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(IntegrityError):
                    evaluate_multisport([run], "baseline", closing_quotes={("r", "q"): invalid})
        report = evaluate_multisport([run], "baseline", closing_quotes={("r", "q"): 0.55})
        clv = report["candidates"]["independent_model"]["overall"]["clv"]
        self.assertAlmostEqual(clv["mean"], 0.05)
        self.assertEqual(clv["status"], "CALLER_SUPPLIED_CLOSING_PROBABILITIES_UNVERIFIED")

    def test_invalid_american_price_fails_closed(self):
        rows = [dict(quote_id="q1", market="spread", pick="WAS", player=None, line=-3.5, price=0,
                     model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0)]
        finals = dict(away="CIN", home="WAS", away_score=10, home_score=20)
        run = _make_run("r_bad", "NFL", "CIN@WAS", "2026-11-23T20:00:00Z", "2026-11-24T01:00:00Z", rows, finals)
        with self.assertRaises(IntegrityError):
            evaluate_multisport([run], "baseline")


class CBBStarTests(unittest.TestCase):
    def make(self):
        rows=[
            dict(quote_id="q1",market="spread",pick="UNC",player=None,line=-2.5,price=-110,model_p=.7,market_p=.5,blend_p=.6,on_card=True,stars=5),
            dict(quote_id="q2",market="total",pick="over",player=None,line=145.0,price=-110,model_p=.6,market_p=.5,blend_p=.55,on_card=True,stars=5),
            dict(quote_id="q3",market="total",pick="under",player=None,line=150.5,price=-110,model_p=.6,market_p=.5,blend_p=.55,on_card=True),
            dict(quote_id="q4",market="total",pick="over",player=None,line=140.5,price=-110,model_p=.6,market_p=.5,blend_p=.55,on_card=False,stars=5)]
        return _make_run("cbb","CBB","DUKE@UNC","2026-11-23T20:00:00Z","2026-11-24T00:00:00Z",rows,dict(away="DUKE",home="UNC",away_score=70,home_score=75))
    def test_nine_weights_common_sample_and_endpoints(self):
        run=self.make()
        report=evaluate_multisport([run],"baseline",include_nine_weights=True,n_boot=100)
        self.assertEqual(report["weight_grid"]["model_percent"],[0,25,50,60,75,80,90,95,100])
        self.assertEqual(len(report["candidates"]),13)
        cs=report["candidates"]
        self.assertEqual(cs["model_000_market_100"]["overall"]["brier"],cs["market_only"]["overall"]["brier"])
        self.assertEqual(cs["model_100_market_000"]["overall"]["brier"],cs["independent_model"]["overall"]["brier"])
        self.assertEqual({x["overall"]["n"] for x in cs.values()},{3})
        self.assertEqual(report["weight_grid"]["roi_scope"],"SAME_FROZEN_SELECTIONS_NOT_WEIGHT_SPECIFIC")
        self.assertEqual(cs["model_050_market_050"]["overall"]["n_settled_quotes"],4)
    def test_original_labels_and_push(self):
        report=audit_stars([self.make()],"baseline")
        five=report["stars"]["5"]
        self.assertEqual((five["wins"],five["losses"],five["pushes"]),(1,0,1))
        self.assertEqual(five["paired_n"],1)
        self.assertAlmostEqual(five["paper_roi_per_1u_risked"],100/110/2)
        self.assertEqual(report["holds"]["ORIGINAL_STAR_LABEL_MISSING_OR_INVALID"],1)
        self.assertEqual(report["holds"]["NOT_EXPLICITLY_ON_CARD"],1)
    def test_duplicate_event_and_late_run(self):
        run=self.make()
        with self.assertRaises(StarIntegrityError):audit_stars([run,run],"baseline")
        run["manifest"]["capture_utc"]=run["manifest"]["start_utc"]
        with self.assertRaises(StarIntegrityError):audit_stars([run],"baseline")

if __name__ == "__main__":
    unittest.main()
