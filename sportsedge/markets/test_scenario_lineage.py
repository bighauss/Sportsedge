"""Scenario reproducibility red-team: all tests synthetic, PAPER / 0u."""
from dataclasses import replace
from datetime import timedelta
import unittest

from sportsedge.markets.test_allmarkets_research import D,H,S,mk,quote,batch
from sportsedge.markets.allmarkets_research import SimulationBatch
from sportsedge.markets.projection_bridge import TeamProjection
from sportsedge.markets.projection_distribution import (
    DistributionInput, PlayerMoment, generate_score_scenarios,
)
from sportsedge.markets.run_it_research import MarketCandidate, run_research_board


def projection(home=24.0):
    return TeamProjection("NFL","e1","H","A",home,21.0,H,S,
                          D-timedelta(minutes=30))


def dispersion(sd_margin=12.0, shares=(.25,.25,.25,.25), model_hash=H):
    return DistributionInput("NFL",sd_margin,16.0,shares,model_hash,
                             D-timedelta(days=3))


def moment(player="P1", mean=270.0):
    return PlayerMoment(
        player_id=player,team_id="H" if player=="P1" else "A",
        stat="PASS_YDS",projected_mean=mean,standard_deviation=55.0,
        raw_features_sha256=S,trained_until_utc=D-timedelta(days=2),
        projection_asof_utc=D-timedelta(hours=2),confirmed_active=True)


def simulate(proj=None, dist=None, *, seed=73, count=1000, moments=()):
    return generate_score_scenarios(
        proj or projection(),dist or dispersion(),
        roster_ids=frozenset({"P1","P2"}),player_moments=moments,
        seed=seed,count=count,generated_at_utc=D)


class ScenarioLineageTests(unittest.TestCase):
    def test_same_complete_spec_yields_identical_hash_and_draws(self):
        a,b=simulate(),simulate()
        self.assertEqual(a.scenario_spec_sha256,b.scenario_spec_sha256)
        self.assertTrue(a.scenario_spec_sha256.startswith("sha256:"))
        self.assertEqual(a.outcomes,b.outcomes)
        self.assertIn("RESEARCH",a.scenario_generator_version)

    def test_changing_width_changes_fingerprint_without_changing_projection_hash(self):
        a=simulate(dist=dispersion(12.0))
        b=simulate(dist=dispersion(20.0))
        self.assertEqual(a.model_sha256,b.model_sha256)
        self.assertEqual(a.feature_sha256,b.feature_sha256)
        self.assertNotEqual(a.scenario_spec_sha256,b.scenario_spec_sha256)
        self.assertNotEqual(a.outcomes,b.outcomes)

    def test_seed_count_period_share_and_mean_all_change_fingerprint(self):
        a=simulate()
        variants=(simulate(seed=74),simulate(count=1100),
                  simulate(dist=dispersion(shares=(.15,.35,.25,.25))),
                  simulate(proj=projection(25.0)))
        self.assertEqual(len({a.scenario_spec_sha256}|
                             {x.scenario_spec_sha256 for x in variants}),5)

    def test_separate_dispersion_model_is_not_silently_identified_as_score_model(self):
        x=simulate(dist=dispersion(model_hash="sha256:"+"d"*64))
        y=simulate()
        self.assertEqual(x.model_sha256,y.model_sha256)
        self.assertNotEqual(x.scenario_spec_sha256,y.scenario_spec_sha256)

    def test_player_moment_and_iteration_order_change_fingerprint(self):
        a=simulate(moments=(moment("P1"),moment("P2",230.0)))
        b=simulate(moments=(moment("P1",271.0),moment("P2",230.0)))
        c=simulate(moments=(moment("P2",230.0),moment("P1")))
        self.assertNotEqual(a.scenario_spec_sha256,b.scenario_spec_sha256)
        self.assertNotEqual(a.scenario_spec_sha256,c.scenario_spec_sha256)

    def test_paper_run_it_research_carries_same_scenario_hash(self):
        s=simulate()
        m=mk()
        opp=mk(selection="AWAY",line="3.5")
        result=run_research_board(s,(MarketCandidate(m,
            quote(m,receipt="take",quote_id="qA"),
            quote(opp,receipt="opp",quote_id="qB"),
            {"sport":"NFL"}),),D)
        self.assertEqual(result["scenario_spec_sha256"],s.scenario_spec_sha256)
        self.assertEqual(result["rows"][0]["scenario_spec_sha256"],s.scenario_spec_sha256)
        self.assertEqual(result["rows"][0]["edge_signal"]["scenario_spec_sha256"],
                         s.scenario_spec_sha256)
        self.assertEqual(result["official_counted"],0)
        self.assertEqual(result["approved_stake_u"],0)

    def test_old_direct_batch_has_no_fake_generator_attestation(self):
        s=batch()
        self.assertIsNone(s.scenario_spec_sha256)
        self.assertIsNone(s.scenario_generator_version)

    def test_invalid_or_incomplete_spec_hash_rejected(self):
        s=batch()
        with self.assertRaisesRegex(ValueError,"SCENARIO_SPEC_LINEAGE"):
            replace(s,scenario_spec_sha256="not-hash",
                    scenario_generator_version="SPORTSEDGE_RESEARCH_GENERATOR")
        with self.assertRaisesRegex(ValueError,"SCENARIO_SPEC_LINEAGE"):
            replace(s,scenario_spec_sha256="sha256:"+"f"*64)


if __name__=="__main__":
    unittest.main()
