"""Synthetic adversarial covariance fitter and simulation replay tests.

No historical source is authenticated; no market is promoted or staked.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import math
from pathlib import Path
from statistics import correlation
import tempfile
import unittest

from sportsedge.markets.score_dispersion_fit import fit_score_residuals
from sportsedge.markets.projection_distribution import (
    DistributionInput, generate_score_scenarios,
)
from sportsedge.markets.projection_bridge import TeamProjection
from sportsedge.markets.test_score_dispersion_fit import records, encode, stamp
from sportsedge.markets.test_cli import H, S, manifest
from sportsedge.markets.cli import run_from_manifest

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def score_fixture():
    return records(NOW-timedelta(days=40))


def fit_fixture(rows=None):
    return fit_score_residuals(encode(rows if rows is not None else score_fixture()),
        sport="CBB",cutoff_utc=stamp(NOW-timedelta(days=10)))


def projected():
    return TeamProjection(
        sport="NFL", event_id="demo1", home_id="H", away_id="A",
        expected_home=36.0, expected_away=34.0,
        model_sha256=H, feature_sha256=S, asof_utc=NOW-timedelta(hours=2))


def dispersion(rho=0.0):
    return DistributionInput(
        sport="NFL",sd_margin=10.0,sd_total=18.0,
        period_shares=(.25,.25,.25,.25),model_sha256=H,
        training_end_utc=NOW-timedelta(days=2),
        margin_total_correlation=rho)


def simulate(rho=0.0, *, n=3500):
    return generate_score_scenarios(
        projected(),dispersion(rho),count=n,seed=1001,
        generated_at_utc=NOW,roster_ids=frozenset())


def realized_corr(batch):
    margin,total=[],[]
    for outcome in batch.outcomes:
        home=sum(period[0] for period in outcome.periods.values())
        away=sum(period[1] for period in outcome.periods.values())
        margin.append(home-away)
        total.append(home+away)
    return correlation(margin,total)


class CovarianceContract(unittest.TestCase):
    def test_train_only_original_paired_residual_correlation(self):
        rows=score_fixture()
        a=fit_fixture(rows)
        self.assertEqual(a["status"],
                         "TRAIN_ONLY_WIDTHS_READY_RESEARCH_NOT_CALIBRATED")
        self.assertEqual(a["accepted_rows"],56)
        m=[(r["final_home"]-r["final_away"])-
           (r["projection_home"]-r["projection_away"]) for r in rows]
        t=[(r["final_home"]+r["final_away"])-
           (r["projection_home"]+r["projection_away"]) for r in rows]
        self.assertAlmostEqual(a["margin_total_residual_correlation"],
                               correlation(m,t),places=9)
        self.assertFalse(a["release_gate_cleared"])
        self.assertEqual(a["approved_stake_u"],0)
        self.assertIn("NOT_FORWARD_CALIBRATED",a["correlation_status"])

    def test_different_original_results_yield_new_fit_sha_and_correlation(self):
        rows=score_fixture()
        prior=fit_fixture(rows)
        rows[5]["final_away"]+=8
        after=fit_fixture(rows)
        self.assertNotEqual(after["source_file_sha256"],prior["source_file_sha256"])
        self.assertNotEqual(after["fitter_model_sha256"],prior["fitter_model_sha256"])
        self.assertNotEqual(after["margin_total_residual_correlation"],
                            prior["margin_total_residual_correlation"])

    def test_future_and_invalid_row_quarantine_correlation(self):
        rows=score_fixture()
        rows[2]["final_captured_utc"]=stamp(NOW)
        blocked=fit_fixture(rows)
        self.assertEqual(blocked["status"],"BLOCK_DISPERSION_FIT")
        self.assertEqual(blocked["blocked_rows"],1)
        self.assertIsNone(blocked["margin_total_residual_correlation"])
        self.assertIsNone(blocked["sd_margin"])

    def test_perfectly_correlated_residuals_not_silently_clipped(self):
        rows=score_fixture()
        for i,r in enumerate(rows):
            r["final_home"]=70+(i%6)
            r["final_away"]=68
        x=fit_fixture(rows)
        self.assertEqual(x["status"],"BLOCK_DISPERSION_FIT")
        self.assertIn("DEGENERATE_MARGIN_TOTAL_COVARIANCE",x["fit_failures"])
        self.assertIsNone(x["margin_total_residual_correlation"])

    def test_rho_bounds_are_rejected_without_imputation(self):
        for invalid in (True,float("nan"),float("inf"),1.0,-1.0,.999,-.999, "0.6"):
            with self.subTest(invalid=invalid),self.assertRaisesRegex(
                 ValueError,"MARGIN_TOTAL_CORRELATION_INVALID"):
                dispersion(invalid)

    def test_legacy_zero_correlation_is_replay_stable(self):
        a=simulate()
        b=simulate(0.0)
        self.assertEqual(a.scenario_spec_sha256,b.scenario_spec_sha256)
        self.assertEqual(a.outcomes,b.outcomes)
        self.assertEqual(a.calibration_status,"UNVERIFIED")

    def test_correlation_changes_hash_and_team_total_joint_outcomes(self):
        a=simulate(.65)
        b=simulate(-.65)
        self.assertNotEqual(a.scenario_spec_sha256,b.scenario_spec_sha256)
        self.assertNotEqual(a.outcomes,b.outcomes)
        self.assertGreater(realized_corr(a),.4)
        self.assertLess(realized_corr(b),-.4)

    def test_correlation_changes_team_total_tail_without_score_mean_hacking(self):
        positive=simulate(.70)
        negative=simulate(-.70)
        def home_over(batch):
            return sum(sum(p[0] for p in o.periods.values())>=42
                       for o in batch.outcomes)/len(batch.outcomes)
        # Score mean, SD, roster, seed are identical: only fitted dependence
        # moves the derived team total. Neither is a genuine +EV claim.
        self.assertGreater(home_over(positive),home_over(negative)+.05)
        self.assertEqual(positive.model_sha256,negative.model_sha256)
        self.assertEqual(positive.feature_sha256,negative.feature_sha256)

    def test_private_fitted_correlation_wired_into_research_only_run_it(self):
        original=encode(score_fixture())
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"original-score-ledger.jsonl"
            path.write_bytes(original)
            payload=manifest()
            payload["distribution"]={
                "sport":"CBB",
                "period_shares":[.25,.25,.25,.25],
                "status":"UNCALIBRATED_RESEARCH"}
            payload["dispersion_fit_ref"]={
                "path":str(path),
                "raw_sha256":"sha256:"+sha256(original).hexdigest(),
                "fit_asof_utc":stamp(NOW-timedelta(days=10))}
            out=run_from_manifest(payload)
            fitted=fit_fixture()
            self.assertAlmostEqual(out["margin_total_correlation_used"],
                                   fitted["margin_total_residual_correlation"])
            self.assertEqual(out["margin_total_correlation_source"],
                             "TRAIN_ONLY_SAME_GAME_RESIDUALS_UNCALIBRATED")
            self.assertFalse(out["margin_total_correlation_forward_calibrated"])
            self.assertEqual(out["approved_stake_u"],0)
            self.assertEqual(out["official_counted"],0)
            self.assertIsNone(out["card"])

    def test_injected_manual_rho_rejected_for_source_fit(self):
        raw=encode(score_fixture())
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"scores.jsonl";path.write_bytes(raw)
            p=manifest()
            p["distribution"]={
                "sport":"CBB","period_shares":[.25,.25,.25,.25],
                "status":"UNCALIBRATED_RESEARCH",
                "margin_total_correlation":.98}
            p["dispersion_fit_ref"]={
                "path":str(path),
                "raw_sha256":"sha256:"+sha256(raw).hexdigest(),
                "fit_asof_utc":stamp(NOW-timedelta(days=10))}
            with self.assertRaisesRegex(ValueError,"UNSUPPORTED_OR_SECRET_FIELD"):
                run_from_manifest(p)

    def test_manual_legacy_path_keeps_zero_assumption_labeled(self):
        out=run_from_manifest(manifest())
        self.assertEqual(out["margin_total_correlation_used"],0.0)
        self.assertEqual(out["margin_total_correlation_source"],
                         "LEGACY_ZERO_ASSUMPTION_UNCALIBRATED")
        self.assertEqual(out["approved_stake_u"],0)


if __name__=="__main__":
    unittest.main()
