"""Synthetic 7-sport comparison, adapter, and anti-leakage regression tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import SPORTS, grade_row
from comparison import evaluate_multisport


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


if __name__ == "__main__":
    unittest.main()
