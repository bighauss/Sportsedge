"""Men's CBB real two-half scenario and settlement red-team (synthetic)."""
from __future__ import annotations

from datetime import timedelta
import unittest

from sportsedge.markets.allmarkets_research import (
    Market, Outcome, settle,
)
from sportsedge.markets.projection_bridge import TeamProjection
from sportsedge.markets.projection_distribution import (
    DistributionInput, generate_score_scenarios,
)
from sportsedge.markets.test_allmarkets_research import D, H, S


def model(shares=(.48,.52)):
    projection=TeamProjection("CBB","cbb-game","H","A",74.,70.,H,S,
                              D-timedelta(minutes=30))
    distribution=DistributionInput(
        "CBB",11.,16.,tuple(shares),H,D-timedelta(days=3))
    return generate_score_scenarios(
        projection,distribution,count=1000,seed=17,
        generated_at_utc=D)


def line(period,side,line="70.5"):
    return Market("CBB","cbb-game","TOTAL",period,side,line,
                  settlement="REGULATION")


class ActualMenHalves(unittest.TestCase):
    def test_two_halves_generate_actual_h1_h2_and_preserve_regulation_total(self):
        batch=model()
        self.assertEqual(batch.sport,"CBB")
        for outcome in batch.outcomes:
            self.assertEqual(set(outcome.periods),{"H1","H2"})
            self.assertEqual(len(outcome.periods),2)
            self.assertTrue(all(type(n) is int and n>=0 for p in
                                outcome.periods.values() for n in p))
        self.assertFalse(batch.calibration_status=="CERTIFIED")

    def test_actual_halves_settle_first_second_and_full_game(self):
        batch=model()
        outcome=Outcome({"H1":(40,35),"H2":(30,37)})
        self.assertEqual(settle(batch,outcome,line("1H","OVER","70.5")),"W")
        self.assertEqual(settle(batch,outcome,line("2H","UNDER","70.5")),"W")
        self.assertEqual(settle(batch,outcome,line("FG","OVER","141.5")),"W")
        self.assertEqual(settle(batch,outcome,
            Market("CBB","cbb-game","ML","FG","AWAY","",settlement="REGULATION")),"W")

    def test_mixed_or_incomplete_half_scores_fail_closed(self):
        batch=model()
        for periods in (
            {"H1":(40,34)},
            {"H1":(40,34),"H2":(35,35),"Q1":(0,0)},
        ):
            with self.subTest(periods=periods):
                with self.assertRaisesRegex(ValueError,"CBB_HALF_PERIODS_INVALID"):
                    settle(batch,Outcome(periods),line("1H","OVER"))

    def test_fake_quarter_market_disallowed_for_mens_cbb(self):
        for period in ("1Q","2Q","3Q","4Q"):
            with self.subTest(period=period),self.assertRaisesRegex(
                    ValueError,"CBB_MENS_QUARTER_MARKET_UNSUPPORTED"):
                line(period,"OVER")

    def test_unmodelled_overtime_blocks_inclusive_full_game(self):
        batch=model()
        outcome=Outcome({"H1":(35,35),"H2":(31,31)})
        m=Market("CBB","cbb-game","ML","FG","HOME","",
                 settlement="INCLUDES_OT")
        with self.assertRaisesRegex(ValueError,"OVERTIME_OUTCOME_MISSING"):
            settle(batch,outcome,m)

    def test_legacy_four_bin_cbb_remains_unverified_not_real_quarters(self):
        batch=model((.24,.26,.24,.26))
        self.assertTrue(all(set(o.periods)=={"Q1","Q2","Q3","Q4"}
                            for o in batch.outcomes))
        self.assertEqual(batch.calibration_status,"UNVERIFIED")

    def test_bad_three_share_cbb_distribution_refused(self):
        with self.assertRaisesRegex(ValueError,"PERIOD_SPLITS_MISSING"):
            model((.33,.33,.34))


if __name__=="__main__":
    unittest.main()
