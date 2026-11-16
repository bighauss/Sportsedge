"""NHL same-shot goalie saves and score consistency, synthetic only."""
import unittest
import nhl_shared_scenarios as s

H="a"*64


def params(**kw):
    data=dict(game_id="SYN1",home="AAA",away="BBB",
              home_goalie="AAA-G",away_goalie="BBB-G",
              shots_home=32.,shots_away=29.,goals_home=3.1,goals_away=2.9,
              period_shares=(.31,.34,.35),pace_dispersion=.1,
              confirmed_home_goalie=True,confirmed_away_goalie=True,
              model_sha256=H,input_sha256=H,
              frozen_utc="2026-11-14T11:00:00Z",
              kickoff_utc="2026-11-15T23:00:00Z")
    data.update(kw)
    return s.Params(**data)


class SharedScenarioTests(unittest.TestCase):
    def test_shot_goal_save_conservation_in_every_period(self):
        a=s.run(params(),n=700,seed=7)
        for game in a:
            game.validate()
            self.assertEqual(len(game.periods),3)
            for period in game.periods:
                self.assertEqual(period.saves_home_goalie+period.goals_away,
                                 period.shots_away)
                self.assertEqual(period.saves_away_goalie+period.goals_home,
                                 period.shots_home)

    def test_reproducible_and_regulation_settlement(self):
        a=s.run(params(),n=100,seed=12)
        self.assertEqual(a,s.run(params(),n=100,seed=12))
        prices=s.price_regulation(params(),a)
        self.assertAlmostEqual(sum(prices["REG"][k] for k in
                  ("p_home_win","p_draw","p_away_win")),1.0,places=4)
        self.assertIn("NO_OT_SO",prices["blocked"]["FG_ML"])
        self.assertIn("NO_PLAYER",prices["blocked"]["DFS"])
        self.assertIn("BLOCKED",prices["market_ev"])

    def test_unconfirmed_starting_goalies_block(self):
        with self.assertRaises(s.Blocked):
            s.run(params(confirmed_away_goalie=False),2)

    def test_source_capture_and_sha_requirements(self):
        for v in (params(frozen_utc="2026-11-16T00:00:00Z"),
                  params(model_sha256=""),params(input_sha256="f"*63)):
            with self.assertRaises(s.Blocked):
                s.run(v,2)

    def test_invalid_shot_rates_or_period_splits_block(self):
        for v in (params(goals_home=40),params(shots_away=0),
                  params(period_shares=(.5,.5,.5)),params(pace_dispersion=-1)):
            with self.assertRaises(s.Blocked):
                s.run(v,2)

    def test_existing_model_adapter_preserves_goalie_confirmation(self):
        game={"game_id":"SYN1","home":"AAA","away":"BBB",
              "home_goalie":"AAA-G","away_goalie":"BBB-G",
              "home_goalie_confirmed":"1","away_goalie_confirmed":"0"}
        proj={"shots_h":30,"shots_a":31,"lam_h":3,"lam_a":2.5}
        p=s.from_existing_projection(proj,game,sha_model=H,sha_input=H,
            frozen_utc="2026-11-14T11:00:00Z",
            kickoff_utc="2026-11-15T23:00:00Z",
            period_shares=(.31,.34,.35),pace_dispersion=.1)
        with self.assertRaises(s.Blocked):
            s.run(p,2)


if __name__=="__main__":
    unittest.main()
