"""Synthetic independent all-market research regression suite; never real bets."""
from __future__ import annotations
import gzip
import hashlib
import json
import math
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

from sportsedge.markets.allmarkets_research import (
    Market,Outcome,ScoreEvent,SimulationBatch,PriceReceipt,settle,
    price_market,price_sgp,validate_pair,
)
from sportsedge.markets.source_ingestion import (
    SOURCES,parse_snapshot_bytes,check_feature_cutoff,
)
from sportsedge.markets.nfl_td_shares import build_offensive_td_shares
from sportsedge.markets.projection_bridge import TeamProjection,sha_inputs
from sportsedge.markets.projection_distribution import (
    DistributionInput,PlayerMoment,generate_score_scenarios,
)
from sportsedge.markets.chronological_calibration import FrozenGame,walk_forward_score_audit

D=datetime(2026,11,15,17,0,0,tzinfo=timezone.utc)
H="sha256:"+"a"*64
S="sha256:"+"b"*64
START=D+timedelta(hours=3)
EA=ScoreEvent("RUSH_TD","H", "P1")
EB=ScoreEvent("DEF_TD","A")


def mk(kind="SPREAD",selection="HOME",line="-3.5",sport="NFL",period="FG",
       team="",player="",stat="",settlement="INCLUDES_OT",event_id="e1"):
    return Market(sport,event_id,kind,period,selection,line,team,player,stat,settlement)


def sample_outcome(home: bool=True, events_complete:bool=True):
    return Outcome(
        {"Q1":(7,0) if home else (0,7),
         "Q2":(7,3) if home else (0,7),
         "Q3":(3,7) if home else (3,7),
         "Q4":(7,7) if home else (4,0)},
        {"P1":{"PASS_YDS":280,"RUSH_YDS":30}},
        (EA,EB,EA) if home else (EB,EA),
        events_complete)


def batch(count=1200,home_wins=700,score_type="NFL"):
    return SimulationBatch(score_type,"e1","H","A",frozenset({"P1"}),
        H,S,D-timedelta(minutes=30),D-timedelta(minutes=4),
        tuple(sample_outcome(i<home_wins) for i in range(count)))


def quote(market, odds=-110, receipt="r1", quote_id="q1", observed=None, book="DraftKings"):
    return PriceReceipt(market,odds,book,"dk-feed","event1","market1",quote_id,
        receipt,H,observed or D-timedelta(minutes=2),
        D-timedelta(minutes=1),START)


class MarketSettlement(unittest.TestCase):
    def test_spread_two_sides(self):
        s=sample_outcome()
        self.assertEqual(settle(batch(),s,mk()),"W")
        self.assertEqual(settle(batch(),s,mk(selection="AWAY",line="3.5")),"L")

    def test_half_player_prop_cannot_reuse_full_game_stat(self):
        half=mk(kind="PLAYER_PROP",period="1H",selection="OVER",
                line="140.5",player="P1",stat="PASS_YDS")
        with self.assertRaisesRegex(ValueError,"PERIOD_PLAYER_STAT_PROJECTION_MISSING"):
            settle(batch(),sample_outcome(),half)

    def test_explicit_half_player_stat_settles_as_half(self):
        full=sample_outcome()
        scenario=Outcome(full.periods,full.player_stats,full.events,True,
                         player_period_stats={"1H":{"P1":{"PASS_YDS":120}}})
        half=mk(kind="PLAYER_PROP",period="1H",selection="UNDER",
                line="140.5",player="P1",stat="PASS_YDS")
        self.assertEqual(settle(batch(),scenario,half),"W")

    def test_full_game_total(self):
        self.assertEqual(settle(batch(),sample_outcome(),
            mk(kind="TOTAL",selection="OVER",line="40.5")),"W")
        self.assertEqual(settle(batch(),sample_outcome(),
            mk(kind="TOTAL",selection="UNDER",line="40.5")),"L")

    def test_first_half_does_not_use_full_total(self):
        s=sample_outcome()
        self.assertEqual(settle(batch(),s,mk(kind="TOTAL",period="1H",
            selection="UNDER",line="24.5")),"W")

    def test_team_total(self):
        s=sample_outcome()
        self.assertEqual(settle(batch(),s,mk(kind="TEAM_TOTAL",selection="OVER",
            line="21.5",team="H")),"W")

    def test_player_prop(self):
        self.assertEqual(settle(batch(),sample_outcome(),mk(kind="PLAYER_PROP",
            selection="OVER",line="250.5",player="P1",stat="PASS_YDS")),"W")

    def test_missing_player_stat_blocks_not_assumes_zero(self):
        with self.assertRaisesRegex(ValueError,"PLAYER_STAT_PROJECTION_MISSING"):
            settle(batch(),sample_outcome(),mk(kind="PLAYER_PROP",
                selection="UNDER",line="1.5",player="P1",stat="INTERCEPTIONS"))

    def test_first_td_defense_not_credited(self):
        s=sample_outcome(home=False)
        self.assertEqual(settle(batch(),s,mk(kind="FIRST_TD",
            selection="NO",line="",player="P1")),"W")

    def test_anytime_and_two_td_count(self):
        s=sample_outcome()
        for kind in ("ATTD","TD_2PLUS"):
            self.assertEqual(settle(batch(),s,mk(kind=kind,
                selection="YES",line="",player="P1")),"W")

    def test_no_events_invents_no_touchdown_probability(self):
        s=sample_outcome(events_complete=False)
        with self.assertRaisesRegex(ValueError,"FULL_EVENT_SEQUENCE_MISSING"):
            settle(batch(),s,mk(kind="ATTD",selection="YES",line="",player="P1"))

    def test_baseball_nrfi_yrfi(self):
        b=SimulationBatch("MLB","e1","H","A",frozenset(),H,S,
            D-timedelta(hours=1),D-timedelta(minutes=5),
            (Outcome({**{"I"+str(i):(0,0) for i in range(1,10)}, "EXTRA":(0,1)}),))
        self.assertEqual(settle(b,b.outcomes[0],
            mk("NRFI","YES","",sport="MLB",period="1IN",settlement="REGULATION")),"W")
        self.assertEqual(settle(b,b.outcomes[0],
            mk("YRFI","YES","",sport="MLB",period="1IN",settlement="REGULATION")),"L")

    def test_basketball_first_basket(self):
        s=Outcome({"Q1":(24,25),"Q2":(20,20),"Q3":(20,20),"Q4":(20,20)},
                  {},(ScoreEvent("BASKET","H","P1"),),True)
        b=SimulationBatch("NBA","e1","H","A",frozenset({"P1"}),H,S,
                          D-timedelta(hours=1),D-timedelta(minutes=5),(s,))
        self.assertEqual(settle(b,s,mk("FIRST_BASKET","YES","",sport="NBA",
                                      player="P1",settlement="REGULATION")),"W")

    def test_invalid_sport_period(self):
        with self.assertRaisesRegex(ValueError,"PERIOD_NOT_SUPPORTED_BY_SPORT"):
            mk("TOTAL","OVER","9.5",sport="MLB",period="1H")



class CompleteGameAndSynchronousQuotes(unittest.TestCase):
    def test_basketball_regulation_tie_needs_overtime_for_all_fg_markets(self):
        o=Outcome({"Q1":(20,20),"Q2":(18,18),"Q3":(21,21),"Q4":(22,22)})
        b=SimulationBatch("NBA","e1","H","A",frozenset(),H,S,
                          D-timedelta(hours=1),D-timedelta(minutes=4),(o,))
        for kind,line,selection in (("ML","","HOME"),("TOTAL","160.5","OVER"),
                                    ("TEAM_TOTAL","80.5","OVER")):
            with self.subTest(kind=kind):
                m=mk(kind,selection,line,sport="NBA",
                     team="H" if kind=="TEAM_TOTAL" else "")
                with self.assertRaisesRegex(ValueError,"OVERTIME_OUTCOME_MISSING"):
                    settle(b,o,m)

    def test_overtime_resolution_and_unresolved_further_overtime(self):
        reg={"Q1":(20,20),"Q2":(18,18),"Q3":(21,21),"Q4":(22,22)}
        b=SimulationBatch("NBA","e1","H","A",frozenset(),H,S,
                          D-timedelta(hours=1),D-timedelta(minutes=4),(Outcome(reg),))
        self.assertEqual(settle(b,Outcome({**reg,"OT":(5,7)}),
                           mk("ML","AWAY","",sport="NBA")),"W")
        with self.assertRaisesRegex(ValueError,"OVERTIME_FINAL_TIE_UNRESOLVED"):
            settle(b,Outcome({**reg,"OT":(5,5)}),
                   mk("TOTAL","OVER","155.5",sport="NBA"))

    def test_nfl_regulation_tie_no_ot_blocks_but_regulation_only_settles(self):
        reg={"Q1":(7,7),"Q2":(0,0),"Q3":(3,3),"Q4":(7,7)}
        with self.assertRaisesRegex(ValueError,"OVERTIME_OUTCOME_MISSING"):
            settle(batch(),Outcome(reg),mk("TOTAL","OVER","35.5"))
        self.assertEqual(settle(batch(),Outcome(reg),
                         mk("TOTAL","UNDER","35.5",settlement="REGULATION")),"W")
        self.assertEqual(settle(batch(),Outcome({**reg,"OT":(0,0)}),
                         mk("ML","HOME","")),"P")

    def test_phantom_overtime_after_decided_regulation_is_blocked(self):
        o=Outcome({"Q1":(7,0),"Q2":(0,0),"Q3":(0,0),"Q4":(0,0),"OT":(3,0)})
        with self.assertRaisesRegex(ValueError,"OVERTIME_WITHOUT_REGULATION_TIE"):
            settle(batch(),o,mk("SPREAD","HOME","-3.5"))

    def test_mlb_nine_inning_tie_needs_extras_for_fg_markets(self):
        reg={"I"+str(i):(0,0) for i in range(1,10)}
        b=SimulationBatch("MLB","e1","H","A",frozenset(),H,S,
                          D-timedelta(hours=1),D-timedelta(minutes=4),(Outcome(reg),))
        for kind,line,side in (("ML","","HOME"),("TOTAL","0.5","UNDER")):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError,"MLB_EXTRA_INNINGS_OUTCOME_MISSING"):
                    settle(b,Outcome(reg),mk(kind,side,line,sport="MLB"))
        self.assertEqual(settle(b,Outcome(reg),
                         mk("TOTAL","UNDER","0.5",sport="MLB",
                            period="F5",settlement="REGULATION")),"W")

    def test_mlb_extra_innings_resolved_vs_phantom_or_incomplete(self):
        reg={"I"+str(i):(0,0) for i in range(1,10)}
        b=SimulationBatch("MLB","e1","H","A",frozenset(),H,S,
                          D-timedelta(hours=1),D-timedelta(minutes=4),(Outcome(reg),))
        self.assertEqual(settle(b,Outcome({**reg,"EXTRA":(1,0)}),
                         mk("ML","HOME","",sport="MLB")),"W")
        with self.assertRaisesRegex(ValueError,"MLB_FINAL_TIE_UNRESOLVED"):
            settle(b,Outcome({**reg,"EXTRA":(1,1)}),
                   mk("ML","HOME","",sport="MLB"))
        with self.assertRaisesRegex(ValueError,"EXTRA_INNINGS_WITHOUT_NINE_INNING_TIE"):
            settle(b,Outcome({**reg,"I9":(1,0),"EXTRA":(1,0)}),
                   mk("TOTAL","OVER","0.5",sport="MLB"))

    def test_unverified_posted_rules_do_not_resolve_a_regulation_tie(self):
        reg={"Q1":(7,7),"Q2":(0,0),"Q3":(0,0),"Q4":(0,0)}
        with self.assertRaisesRegex(ValueError,"POSTED_SETTLEMENT_RULE_UNVERIFIED"):
            settle(batch(),Outcome(reg),mk("TOTAL","OVER","20.5",
                                         settlement="POSTED_RULES"))

    def test_missing_overtime_blocks_all_market_probabilities(self):
        tied=Outcome({"Q1":(7,7),"Q2":(0,0),"Q3":(7,7),"Q4":(0,0)})
        b=SimulationBatch("NFL","e1","H","A",frozenset(),H,S,
                          D-timedelta(hours=1),D-timedelta(minutes=4),
                          tuple([tied]*1200))
        m=mk("ML","HOME","")
        r=price_market(b,m,quote(m),
            quote(mk("ML","AWAY",""),receipt="r2",quote_id="q2"),D)
        self.assertEqual(r["status"],"BLOCK")
        self.assertIn("OVERTIME_OUTCOME_MISSING",r["reasons"])
        self.assertEqual(r["approved_stake_u"],0)

    def test_two_sided_quotes_must_be_from_nearby_observations(self):
        m=mk()
        x=quote(m,observed=D-timedelta(seconds=70))
        y=quote(mk(selection="AWAY",line="3.5"),
                receipt="r2",quote_id="q2",observed=D-timedelta(seconds=170))
        p=price_market(batch(),m,x,y,D)
        self.assertEqual(p["status"],"BLOCK")
        self.assertIn("TWO_SIDED_QUOTE_SNAPSHOT_SKEW",p["reasons"])
        self.assertEqual(p["approved_stake_u"],0)

    def test_close_in_time_two_sided_quotes_remain_paper(self):
        m=mk()
        x=quote(m,observed=D-timedelta(seconds=80))
        y=quote(mk(selection="AWAY",line="3.5"),
                receipt="r2",quote_id="q2",observed=D-timedelta(seconds=100))
        p=price_market(batch(),m,x,y,D)
        self.assertEqual(p["status"],"PAPER_0U")
        self.assertEqual(p["approved_stake_u"],0)

    def test_unsafe_quote_pair_skew_configuration_rejected(self):
        m=mk()
        x=quote(m,observed=D-timedelta(seconds=80))
        y=quote(mk(selection="AWAY",line="3.5"),
                receipt="r2",quote_id="q2",observed=D-timedelta(seconds=100))
        with self.assertRaisesRegex(ValueError,"UNSAFE_TWO_SIDED_QUOTE_SKEW_LIMIT"):
            validate_pair(x,y,m,D,max_pair_skew_seconds=301)


class CapturedOdds(unittest.TestCase):
    def test_no_vig_exact_pair_unpromotable(self):
        a=mk()
        b=mk(selection="AWAY",line="3.5")
        p=price_market(batch(),a,quote(a),quote(b,receipt="r2",quote_id="q2"),D)
        self.assertEqual(p["status"],"PAPER_0U")
        self.assertIsNone(p["card"])
        self.assertEqual((p["approved_stake_u"],p["official_counted"]),(0,0))
        self.assertGreater(p["wins"],25)
        self.assertAlmostEqual(p["no_vig_market_p_conditional"],.5,5)

    def test_provider_market_id_cannot_be_mixed(self):
        from dataclasses import replace
        a=mk(); b=mk(selection="AWAY",line="3.5")
        other=replace(quote(b,receipt="r2",quote_id="q2"),
                      provider_market_id="another_market")
        r=price_market(batch(),a,quote(a),other,D)
        self.assertIn("DIFFERENT_QUOTE_SOURCE_EVENT_OR_MARKET",r["reasons"])

    def test_model_feature_freeze_after_quote_blocks_ev(self):
        from dataclasses import replace
        late=replace(batch(),asof_utc=D-timedelta(minutes=1),generated_at_utc=D)
        a=mk()
        b=mk(selection="AWAY",line="3.5")
        result=price_market(late,a,quote(a),quote(b,receipt="r2",quote_id="q2"),
                            D+timedelta(seconds=5))
        self.assertEqual(result["status"],"BLOCK")
        self.assertIn("MODEL_FEATURE_FREEZE_AFTER_ODDS_QUOTE",result["reasons"])

    def test_missing_other_side_blocks(self):
        r=price_market(batch(),mk(),quote(mk()),None,D)
        self.assertEqual(r["status"],"BLOCK")
        self.assertIn("MISSING_TWO_SIDED_PRICE",r["reasons"])

    def test_mismatched_line_does_not_match(self):
        r=price_market(batch(),mk(),quote(mk()),
            quote(mk(selection="AWAY",line="4.5"),receipt="r2",quote_id="q2"),D)
        self.assertIn("TWO_SIDED_MARKET_LINE_MISMATCH",r["reasons"])

    def test_missing_actual_price_cannot_be_inferred(self):
        r=price_market(batch(),mk(),None,None,D)
        self.assertEqual(r["raw_ev"],None) if "raw_ev" in r else self.assertEqual(r["status"],"BLOCK")

    def test_future_or_stale_quote(self):
        r=price_market(batch(),mk(),
            quote(mk(),observed=D-timedelta(minutes=8)),
            quote(mk(selection="AWAY",line="3.5"),receipt="r2",quote_id="q2"),D)
        self.assertIn("STALE_QUOTE",r["reasons"])

    def test_no_lookahead_of_simulation(self):
        b=batch()
        r=price_market(b,mk(),quote(mk()),
            quote(mk(selection="AWAY",line="3.5"),receipt="r2",quote_id="q2"),
            D-timedelta(minutes=6))
        self.assertIn("SIMULATION_GENERATED_AFTER_DECISION",r["reasons"])

    def test_duplicate_quote_receipt(self):
        r=price_market(batch(),mk(),quote(mk()),
            quote(mk(selection="AWAY",line="3.5")),D)
        self.assertIn("DUPLICATE_QUOTE_RECEIPT",r["reasons"])

    def test_three_way_no_vig_not_faked(self):
        with self.assertRaises(ValueError):
            mk(kind="ML",selection="DRAW",line="")


class SGPResearch(unittest.TestCase):
    def test_exact_sgp_quote_has_only_joint_raw_ev(self):
        legs=(mk("ML","HOME",""),mk("TOTAL","OVER","40.5"))
        raw=json.dumps([m.identity() for m in legs],sort_keys=True,separators=(",",":")).encode()
        h="sha256:"+hashlib.sha256(raw).hexdigest()
        r=price_sgp(batch(),legs,+220,H,h,D-timedelta(seconds=40),D,
                    quote_book="DraftKings",event_start_at_utc=START)
        self.assertEqual(r["status"],"PAPER_0U")
        self.assertEqual(r["official_counted"],0)
        self.assertIn("JOINT_MODEL_CALIBRATION_NOT_PROVEN",r["reasons"])
        self.assertIsNone(r.get("blended_ev"))

    def test_sgp_fingerprint_mismatch_blocked(self):
        legs=(mk("ML","HOME",""),mk("TOTAL","OVER","40.5"))
        r=price_sgp(batch(),legs,+220,H,S,D-timedelta(seconds=40),D,
                    quote_book="DraftKings",event_start_at_utc=START)
        self.assertIn("SGP_LEG_FINGERPRINT_MISMATCH",r["reasons"])

    def test_sgp_feature_freeze_after_quote_blocks_probability(self):
        from dataclasses import replace
        late=replace(batch(),asof_utc=D-timedelta(seconds=30),
                     generated_at_utc=D-timedelta(seconds=10))
        legs=(mk("ML","HOME",""),mk("TOTAL","OVER","40.5"))
        raw=json.dumps([m.identity() for m in legs],
                       sort_keys=True,separators=(",",":")).encode()
        fingerprint="sha256:"+hashlib.sha256(raw).hexdigest()
        result=price_sgp(late,legs,220,H,fingerprint,
                         D-timedelta(seconds=40),D+timedelta(seconds=5),
                         quote_book="DraftKings",event_start_at_utc=START)
        self.assertEqual(result["status"],"BLOCK")
        self.assertIn("SGP_MODEL_FEATURES_AFTER_POSTED_QUOTE",result["reasons"])

    def test_sgp_no_actual_quote_blocked(self):
        legs=(mk("ML","HOME",""),mk("TOTAL","OVER","40.5"))
        r=price_sgp(batch(),legs,None,None,None,None,D,
                    quote_book="DraftKings",event_start_at_utc=START)
        self.assertEqual(r["status"],"BLOCK")

    def test_sgp_non_dk_quote_blocked(self):
        legs=(mk("ML","HOME",""),mk("TOTAL","OVER","40.5"))
        r=price_sgp(batch(),legs,220,H,S,D-timedelta(seconds=40),D,
                    quote_book="BestBook",event_start_at_utc=START)
        self.assertIn("EXACT_DK_SGP_PRICE_RECEIPT_REQUIRED",r["reasons"])


class SourceAndShare(unittest.TestCase):
    def test_public_source_inventory_five_sports(self):
        self.assertEqual({s.sport for s in SOURCES.values()},
                         {"NFL","CFB","CBB","NBA","MLB"})

    def test_nflverse_share_builder_filters_future_and_no_probability(self):
        header="season,week,season_type,player_id,recent_team,rushing_tds,receiving_tds\n"
        raw=(header+"2026,1,REG,p1,BUF,2,1\n2026,2,REG,p2,BUF,0,1\n"
             +"2026,10,REG,p1,BUF,8,8\n").encode()
        snap=build_offensive_td_shares(gzip.compress(raw),through_week=9,
             season=2026,source_observed_at_utc=D-timedelta(hours=2),
             fetched_at_utc=D,require_all_32_teams=False)
        self.assertEqual(snap["excluded_future_weekly_rows"],1)
        self.assertEqual(snap["p_anytime_td"],None)
        a=next(e for e in snap["entries"] if e["player_id"]=="p1")
        self.assertEqual(a["share"],"0.75")
        self.assertEqual(snap["official_counted"],0)

    def test_nflverse_wrong_hash_blocks(self):
        raw=b"season,week,season_type,player_id,recent_team,rushing_tds,receiving_tds\n2026,1,REG,p1,BUF,1,0\n"
        with self.assertRaisesRegex(ValueError,"WEEKLY_SOURCE_SHA_MISMATCH"):
            build_offensive_td_shares(raw,through_week=9,season=2026,
                source_observed_at_utc=D-timedelta(hours=2),fetched_at_utc=D,
                expected_raw_sha256=H,require_all_32_teams=False)

    def test_source_ragged_rows_rejected(self):
        bad=b"season,week,season_type,player_id,recent_team,rushing_tds,receiving_tds\n2026,1,REG,p1,BUF,1\n"
        with self.assertRaisesRegex(ValueError,"SOURCE_RAGGED_CSV_ROW"):
            parse_snapshot_bytes("NFLVERSE_WEEKLY",bad,D-timedelta(hours=1),D)

    def test_pit_after_odds_marked_unusable(self):
        raw=b"season,week,season_type,player_id,recent_team,rushing_tds,receiving_tds\n2026,1,REG,p1,BUF,1,0\n"
        receipt,_=parse_snapshot_bytes("NFLVERSE_WEEKLY",raw,D-timedelta(minutes=1),D)
        problems=check_feature_cutoff(receipt,decision_at_utc=D,
                                       quote_observed_at_utc=D-timedelta(minutes=2))
        self.assertIn("FEATURE_COLLECTED_AFTER_ODDS",problems)


class ProjectionsAndForward(unittest.TestCase):
    def test_generated_score_scenarios_are_unverified(self):
        p=TeamProjection("NFL","e1","H","A",25,22,H,S,D-timedelta(minutes=45))
        disp=DistributionInput("NFL",13.5,13.0,(.24,.26,.24,.26),H,
                               D-timedelta(days=4))
        batch=generate_score_scenarios(p,disp,count=1000,seed=2,
                generated_at_utc=D-timedelta(minutes=4))
        self.assertEqual(len(batch.outcomes),1000)
        self.assertEqual(batch.calibration_status,"UNVERIFIED")
        self.assertTrue(all(not x.events_complete for x in batch.outcomes))

    def test_score_scenarios_do_not_invent_touchdowns(self):
        p=TeamProjection("NFL","e1","H","A",25,22,H,S,D-timedelta(minutes=45))
        disp=DistributionInput("NFL",13.5,13,(.24,.26,.24,.26),H,
                               D-timedelta(days=4))
        b=generate_score_scenarios(p,disp,count=1000,seed=3,
                roster_ids=frozenset({"P1"}),generated_at_utc=D-timedelta(minutes=4))
        r=price_market(b,mk("ATTD","YES","",player="P1"),None,None,D)
        self.assertEqual(r["status"],"BLOCK")

    def test_nfl_receiving_volume_floor(self):
        p=PlayerMoment("P1","H","RECEPTIONS",5.0,1.4,H,
            D-timedelta(days=2),D-timedelta(hours=1),True,projected_targets=3)
        with self.assertRaisesRegex(ValueError,"RECEIVING_PROP_TARGET_VOLUME_BELOW_FLOOR"):
            p.validate("NFL",D)

    def test_nba_minutes_floor(self):
        p=PlayerMoment("P1","H","POINTS",20,5,H,
            D-timedelta(days=2),D-timedelta(hours=1),True,projected_minutes=12)
        with self.assertRaisesRegex(ValueError,"NBA_PROP_MINUTES_BELOW_FLOOR"):
            p.validate("NBA",D)

    def test_baseball_pitcher_unconfirmed(self):
        p=PlayerMoment("P1","H","PITCHER_K",6,2,H,
            D-timedelta(days=2),D-timedelta(hours=1),True,confirmed_pitcher=False)
        with self.assertRaisesRegex(ValueError,"STARTING_PITCHER_NOT_CONFIRMED"):
            p.validate("MLB",D)

    def test_calibration_requires_three_chronological_folds(self):
        rows=[]
        for i in range(135):
            at=D+timedelta(days=i)
            actual_h=20+(i%6)
            actual_a=17+(i%3)
            # Holdout test uses a genuinely frozen model fitted before ALL windows.
            rows.append(FrozenGame(str(i),"NFL",at,at-timedelta(hours=1),
                D-timedelta(days=2),23,19,actual_h,actual_a,H))
        report=walk_forward_score_audit(rows)
        self.assertEqual(report["status"],"RESEARCH_HOLDOUT_REVIEW")
        self.assertGreaterEqual(report["completed_folds"],3)
        self.assertEqual(report["official_counted"],0)

    def test_calibration_lookahead_rejected(self):
        with self.assertRaisesRegex(ValueError,"FUTURE_LEAK_OR_SAME_GAME_TRAINING"):
            FrozenGame("e","NFL",D,D+timedelta(minutes=1),
                       D-timedelta(days=2),23,19,20,17,H)


if __name__=="__main__":
    unittest.main()
