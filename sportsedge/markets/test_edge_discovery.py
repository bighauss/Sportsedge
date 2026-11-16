"""Synthetic red-team coverage for projections -> research market disagreement.

None of these examples is a genuine quote, validated calibration sample,
independent bookmaker source or official wagering recommendation.
"""
from __future__ import annotations

from datetime import timedelta
import math
import unittest

from sportsedge.markets.allmarkets_research import Market, price_market
from sportsedge.markets.edge_discovery import evaluate_signal, shortlist_signals
from sportsedge.markets.test_allmarkets_research import D, batch, mk, quote
from sportsedge.markets.run_it_research import MarketCandidate, run_research_board


def priced_home(*, count=1200, home_wins=700, line="-3.5", odds=-110):
    simulation = batch(count=count, home_wins=home_wins)
    market = mk(line=line)
    opposing = mk(selection="AWAY", line=str(-float(line)))
    take = quote(market, odds=odds)
    other = quote(opposing, odds=-110, receipt="r2", quote_id="q2")
    priced = price_market(simulation, market, take, other, D)
    return market, take, priced, other, simulation


class EdgeSignalRedTeam(unittest.TestCase):
    def test_model_fair_market_and_break_even_are_recoverable(self):
        market, take, priced, _, _ = priced_home()
        signal = evaluate_signal(priced, market, take)
        self.assertEqual(priced["status"], "PAPER_0U")
        self.assertAlmostEqual(signal["model_p_conditional_nonpush"], 700/1200)
        self.assertAlmostEqual(signal["no_vig_book_p_conditional"], .5)
        self.assertAlmostEqual(signal["quote_break_even_p_conditional"], 110/210)
        self.assertAlmostEqual(signal["model_minus_market_pp"], (700/1200-.5)*100)
        self.assertGreater(signal["mc_wilson95_lower_conditional"], .5)
        self.assertGreater(signal["mc_only_lower_minus_quote_pp"], 0)
        self.assertEqual(signal["source_authentication_verified"], False)
        self.assertEqual(signal["calibration_verified"], False)
        self.assertFalse(signal["official"])
        self.assertEqual(signal["approved_stake_u"], 0)
        self.assertEqual(signal["quoted_american_unverified"], -110)

    def test_correct_push_aware_break_even_and_binary_nonpush(self):
        market, take, priced, other, simulation = priced_home()
        altered = dict(priced, simulations=1200, wins=550, losses=450,
                       pushes=200, model_p_win=550/1200,
                       model_p_loss=450/1200, model_p_push=200/1200,
                       no_vig_market_p_conditional=.5)
        # Recalculate raw EV against same unverified quoted price.
        altered["raw_ev_unverified"] = 550/1200*(100/110)-450/1200
        signal = evaluate_signal(altered, market, take)
        self.assertAlmostEqual(signal["model_p_conditional_nonpush"], .55)
        self.assertAlmostEqual(signal["model_p_push"], 1/6)
        self.assertAlmostEqual(signal["model_minus_market_pp"], 5.0)
        self.assertEqual(signal["simulated_nonpush_count"], 1000)

    def test_missing_quote_returns_no_signal(self):
        market = mk()
        priced = price_market(batch(), market, None, None, D)
        self.assertEqual(priced["status"], "BLOCK")
        self.assertIsNone(evaluate_signal(priced, market, None))

    def test_blocked_quote_cannot_surface_in_shortlist(self):
        m=mk()
        row = {"market":m.identity(), "edge_signal":None, "research_state":"BLOCK"}
        self.assertEqual(shortlist_signals([(0,m,None)]), [])
        result=run_research_board(batch(),(MarketCandidate(m,None,None,{"sport":"NFL"}),),D)
        self.assertIsNone(result["rows"][0]["edge_signal"])
        self.assertEqual(result["research_shortlist"], [])

    def test_malformed_tampered_probability_refused(self):
        market,take,priced,_,_=priced_home()
        malicious= dict(priced, no_vig_market_p_conditional=.99)
        # Without verified bookmaker pair, a tampered no-vig number is not
        # caught by this pure formatter, but impossible/missing values must fail.
        for value in (float("nan"), float("inf"), -0.1, 1.1, True, None):
            with self.subTest(value=value):
                bad = dict(priced, no_vig_market_p_conditional=value)
                with self.assertRaises(ValueError):
                    evaluate_signal(bad, market, take)
        for bad in ({"wins":9999}, {"losses":-1},
                    {"simulations":1201}, {"raw_ev_unverified":999},
                    {"model_p_push":0.5}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                evaluate_signal({**priced,**bad},market,take)

    def test_pricing_market_identity_cannot_be_substituted(self):
        market,take,priced,_,_=priced_home()
        with self.assertRaisesRegex(ValueError,"SIGNAL_QUOTE_IDENTITY"):
            evaluate_signal(priced,mk(line="-4.5"),take)

    def test_negative_model_disagreement_retained_not_shortlisted(self):
        m, take, priced, other, _=priced_home(home_wins=400)
        signal=evaluate_signal(priced,m,take)
        self.assertLess(signal["model_minus_market_pp"],0)
        self.assertEqual(shortlist_signals([(0,m,signal)]),[])

    def test_mirrored_opposite_side_never_two_recommended_research_leans(self):
        simulation=batch()
        home=mk()
        away=mk(selection="AWAY",line="3.5")
        takes=[quote(home,receipt="take1",quote_id="qa"),
               quote(away,receipt="take2",quote_id="qb")]
        others=[quote(away,receipt="opp1",quote_id="oc"),
                quote(home,receipt="opp2",quote_id="od")]
        candidates=tuple(MarketCandidate(m,t,o,{"sport":"NFL"})
                         for m,t,o in zip((home,away),takes,others))
        board=run_research_board(simulation,candidates,D)
        self.assertEqual(len(board["rows"]),2)
        self.assertEqual(board["submitted_candidates"],2)
        self.assertEqual(board["guard_checked_count"],2)
        self.assertEqual(len(board["research_shortlist"]),1)
        self.assertEqual(board["research_shortlist"][0]["row_index"],0)
        self.assertEqual(board["official_counted"],0)

    def test_alternate_spread_rungs_remain_distinct(self):
        sim=batch()
        candidates=[]
        for j,line in enumerate(("-3.5","-5.5")):
            m=mk(line=line)
            opp=mk(selection="AWAY",line=str(-float(line)))
            candidates.append(MarketCandidate(
                m,quote(m,receipt=f"take{j}",quote_id=f"q{j}"),
                quote(opp,receipt=f"opp{j}",quote_id=f"other{j}"),
                {"sport":"NFL"}))
        board=run_research_board(sim,tuple(candidates),D)
        self.assertEqual(len(board["rows"]),2)
        self.assertEqual(len(board["research_shortlist"]),2)
        self.assertNotEqual(board["research_shortlist"][0]["market"],
                            board["research_shortlist"][1]["market"])

    def test_failure_in_simulation_pricing_never_yields_signal(self):
        m=mk()
        take=quote(m,observed=D+timedelta(minutes=1))
        other=quote(mk(selection="AWAY",line="3.5"),receipt="r2",quote_id="q2")
        board=run_research_board(batch(),(MarketCandidate(
            m,take,other,{"sport":"NFL"}),),D)
        self.assertEqual(board["rows"][0]["research_state"],"BLOCK")
        self.assertEqual(board["research_shortlist"],[])
        self.assertEqual(board["guard_checked_count"],1)


if __name__=="__main__":
    unittest.main()
