"""Synthetic CBB PIT roster and research run-it guard regressions."""
from datetime import timedelta
import unittest

from sportsedge.markets.cbb_quality_gate import (
    CBBBlocked,audit_cbb_availability,screen_cbb_disagreement,
    cbb_direction_diagnostic,
)
from sportsedge.markets.run_it_research import MarketCandidate,run_research_board
from sportsedge.markets.test_allmarkets_research import D,quote
from sportsedge.markets.test_cbb_real_halves import model,line

H="a"*64
EVENT={"event_id":"cbb-game","home_team_id":"H","away_team_id":"A",
 "freeze_utc":"2026-11-15T16:50:00Z",
 "tipoff_utc":"2026-11-15T20:00:00Z",
 "roster_sha256":H,"roster_published_utc":"2026-11-15T16:00:00Z",
 "roster_captured_utc":"2026-11-15T16:30:00Z"}
ROSTER=[{"player_id":"p1","team_id":"H"},{"player_id":"p2","team_id":"A"}]
OBS=[{"player_id":x["player_id"],"team_id":x["team_id"],
      "status":"ACTIVE","source_sha256":H,
      "published_utc":"2026-11-15T16:00:00Z",
      "captured_utc":"2026-11-15T16:30:00Z"} for x in ROSTER]
RAW={"event":EVENT,"roster":ROSTER,"observations":OBS}

class TestCBBQuality(unittest.TestCase):
    def test_shape_not_proof_of_availability_impact(self):
        a=audit_cbb_availability(**RAW)
        self.assertEqual(a["state"],"PIT_SHAPE_ONLY_UNAUTHENTICATED")
        self.assertFalse(a["independent_source_attested"])
        self.assertFalse(a["may_change_frozen_projection"])
        self.assertTrue(screen_cbb_disagreement(
            {"model_minus_market_pp":2.,"raw_ev_unverified":.01},
            availability=a)[0])

    def test_missing_duplicate_out_transfer_future_block(self):
        for obs in (OBS[:1],OBS+[OBS[0]],
                    [{**OBS[0],"status":"OUT"},OBS[1]],
                    [{**OBS[0],"team_id":"A"},OBS[1]],
                    [{**OBS[0],"published_utc":"2026-11-15T17:00:00Z"},OBS[1]]):
            self.assertEqual(audit_cbb_availability(EVENT,ROSTER,obs)["state"],"BLOCK")

    def test_pregame_roster_release_required(self):
        with self.assertRaises(CBBBlocked):
            audit_cbb_availability(
                {**EVENT,"roster_published_utc":"2026-11-15T17:00:00Z"},ROSTER,OBS)

    def test_symmetric_extreme_model_disagreement_quarantine(self):
        a=audit_cbb_availability(**RAW)
        for gap,ev in [(15.,.01),(-15.,.01),(1.,.25)]:
            allow,reasons=screen_cbb_disagreement(
                {"model_minus_market_pp":gap,"raw_ev_unverified":ev},availability=a)
            self.assertFalse(allow)
            self.assertIn("MODEL_DOUBTED_EXTREME_DISAGREEMENT",reasons)

    def test_under_bias_diagnostic_does_not_force_balance(self):
        rows=[{"quality_state":"RESEARCH_SCREEN_ONLY",
               "market":("CBB","X"+str(i),"TOTAL","FG","UNDER",
                         "148.5","","","","REGULATION"),
               "edge_signal":{"model_minus_market_pp":6.0}}
              for i in range(11)]
        self.assertTrue(cbb_direction_diagnostic(rows)["one_sided_warning"])

    def test_run_it_fails_closed_without_raw_availability(self):
        m=line("FG","OVER","144.5")
        opposite=line("FG","UNDER","144.5")
        c=MarketCandidate(m,quote(m),quote(opposite,receipt="r2",quote_id="q2"),
                          {"sport":"CBB"})
        out=run_research_board(model(),(c,),D)
        self.assertEqual(out["cbb_availability_state"],"BLOCK")
        self.assertEqual(out["rows"][0]["quality_state"],"QUARANTINED_PAPER_CBB")
        self.assertEqual(out["research_shortlist"],[])
        self.assertEqual(out["rows"][0]["approved_stake_u"],0)

    def test_forged_pass_label_never_authorizes_signal(self):
        m=line("FG","OVER","144.5")
        other=line("FG","UNDER","144.5")
        c=MarketCandidate(m,quote(m),quote(other,receipt="r2",quote_id="q2"),{"sport":"CBB"})
        out=run_research_board(model(),(c,),D,cbb_availability={"state":"PIT_SHAPE_ONLY_UNAUTHENTICATED"})
        self.assertEqual(out["cbb_availability_state"],"BLOCK")

    def test_valid_shape_only_enables_unverified_research_screen(self):
        m=line("FG","OVER","144.5");other=line("FG","UNDER","144.5")
        c=MarketCandidate(m,quote(m),quote(other,receipt="r2",quote_id="q2"),{"sport":"CBB"})
        out=run_research_board(model(),(c,),D,cbb_availability=RAW)
        self.assertEqual(out["cbb_availability_state"],"PIT_SHAPE_ONLY_UNAUTHENTICATED")
        self.assertEqual(out["official_counted"],0)
        self.assertFalse(out["research_shortlist_is_verified_edges"])
        self.assertNotEqual(out["rows"][0]["quality_state"],"NOT_CBB")

if __name__=="__main__":
    unittest.main()
