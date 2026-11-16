"""CBB shared possession and blocked market regression, synthetic only."""
import unittest
import cbb_shared_possessions as m

H="a"*64


def params(**kw):
    x=dict(game_id="C1",home="AAA",away="BBB",
        pace_mean=67.,pace_sd=3.,half1_share=.49,
        home_ppp=(.45,.05,.36,.13,.01,0,0),
        away_ppp=(.48,.05,.35,.11,.01,0,0),
        expected_home_pts=80.4,expected_away_pts=75.04,
        model_sha256=H,source_sha256=H,
        frozen_utc="2026-11-14T18:00:00Z",
        tipoff_utc="2026-11-15T18:00:00Z")
    x.update(kw)
    return m.Params(**x)


class PossessionTests(unittest.TestCase):
    def test_same_game_period_scores_and_possession_counts(self):
        xs=m.simulate(params(),n=400,seed=7)
        for g in xs:
            g.validate()
            self.assertEqual(g.first.home_possessions+g.second.home_possessions,
                g.first.away_possessions+g.second.away_possessions)
            self.assertEqual(sum(g.regulation()),
                g.first.home_score+g.first.away_score+
                g.second.home_score+g.second.away_score)

    def test_reproducibility_and_market_blockers(self):
        x=m.simulate(params(),n=1400,seed=8)
        self.assertEqual(x,m.simulate(params(),n=1400,seed=8))
        r=m.research_summary(params(),x)
        self.assertAlmostEqual(sum(r["REGULATION"][k] for k in
            ("p_home_leads","p_tied","p_away_leads")),1,places=4)
        self.assertAlmostEqual(r["REGULATION"]["home_mean"],80.4,delta=4)
        self.assertIn("OT_NOT_MODELED",r["blocked"]["FG_ML"])
        self.assertIn("NO_PLAYER",r["blocked"]["DFS"])
        self.assertIn("BLOCKED",r["market_ev"])

    def test_missing_or_incoherent_scoring_pmf_fails(self):
        for q in (params(home_ppp=(.3,.7)),
                  params(home_ppp=(1,0,0,0,0,0,0)),
                  params(away_ppp=(.5,.5,0,0,0,0,0))):
            with self.assertRaises(m.Blocked):
                m.simulate(q,n=3)

    def test_source_provenance_must_precede_tipoff(self):
        for q in (params(frozen_utc="2026-11-15T19:00:00Z"),
                  params(model_sha256=""),params(source_sha256="f"*63)):
            with self.assertRaises(m.Blocked):
                m.simulate(q,n=3)

    def test_invalid_possession_pace_and_half_share_fail(self):
        for q in (params(pace_mean=150),params(half1_share=0),
                  params(pace_sd=-1)):
            with self.assertRaises(m.Blocked):
                m.simulate(q,n=3)

    def test_existing_projection_adapter_requires_real_pmf_input(self):
        projected={"poss":67,"home_pts":80.4,"away_pts":75.04}
        game={"game_id":"C1","home":"AAA","away":"BBB"}
        x=m.from_existing_projection(
            projected,game,home_outcome_pmf=params().home_ppp,
            away_outcome_pmf=params().away_ppp,observed_pace_sd=3,
            observed_first_half_share=.49,model_sha256=H,source_sha256=H,
            frozen_utc="2026-11-14T18:00:00Z",
            tipoff_utc="2026-11-15T18:00:00Z")
        self.assertEqual(len(m.simulate(x,n=5)),5)


if __name__=="__main__":
    unittest.main()
