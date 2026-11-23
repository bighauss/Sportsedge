"""Synthetic-only conservation and fail-closed regressions for NHL player attribution."""
import copy
import math
import unittest
from models.nhl import nhl_shared_scenarios as team
from models.nhl import nhl_shared_player_challenger as player

SHA = "a" * 64


def params(**change):
    p = dict(game_id="SYNTH_NHL", home="HOM", away="AWY",
             home_goalie="Home Goalie", away_goalie="Away Goalie",
             shots_home=32., shots_away=29., goals_home=3.1, goals_away=2.9,
             period_shares=(.31, .34, .35), pace_dispersion=.1,
             confirmed_home_goalie=True, confirmed_away_goalie=True,
             model_sha256=SHA, input_sha256=SHA,
             frozen_utc="2026-11-21T10:00:00Z",
             kickoff_utc="2026-11-22T00:00:00Z")
    p.update(change)
    return team.Params(**p)


def profiles():
    return [dict(player_id=f"{side[0]}-{i:02d}", side=side,
                 projected_toi_minutes=15. + i / 10.,
                 shots_per_60=6. + i / 10.,
                 goals_per_shot=.05 + i / 200.,
                 feature_available_utc="2026-11-20T10:00:00Z",
                 feature_source_sha256="b" * 64)
            for side in ("home", "away") for i in range(1, 19)]


GOALIES = {"home": "home-goalie-id", "away": "away-goalie-id"}


class PlayerSharedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = params()
        cls.s = team.run(cls.p, n=80, seed=19)
        cls.x = player.allocate(cls.p, cls.s, profiles(), GOALIES, seed=23)

    def test_every_team_shot_and_goal_conserved_by_period(self):
        x = self.x
        for i, s in enumerate(self.s):
            for pi, period in enumerate(s.periods, 1):
                for side in ("home", "away"):
                    prefix = side[0]
                    ids = [f"{prefix}-{j:02d}" for j in range(1, 19)]
                    shots = sum(x["skaters"][pid][f"P{pi}_SOG"][i] for pid in ids)
                    goals = sum(x["skaters"][pid][f"P{pi}_GOALS"][i] for pid in ids)
                    self.assertEqual(shots, getattr(period, "shots_" + side))
                    self.assertEqual(goals, getattr(period, "goals_" + side))
                    for pid in ids:
                        self.assertLessEqual(x["skaters"][pid][f"P{pi}_GOALS"][i],
                                             x["skaters"][pid][f"P{pi}_SOG"][i])

    def test_goalie_saves_match_opposing_shots_minus_goals(self):
        for i, s in enumerate(self.s):
            for j, p in enumerate(s.periods, 1):
                self.assertEqual(self.x["goalies"][GOALIES["home"]][f"P{j}_SAVES"][i],
                                 p.shots_away - p.goals_away)
                self.assertEqual(self.x["goalies"][GOALIES["away"]][f"P{j}_SAVES"][i],
                                 p.shots_home - p.goals_home)
        for pid, arr in self.x["skaters"].items():
            self.assertEqual(arr["REG_SOG"][0],
                             sum(arr[f"P{k}_SOG"][0] for k in (1, 2, 3)))

    def test_scenario_hash_binds_seed_and_draw_values(self):
        a = player.allocate(self.p, self.s, profiles(), GOALIES, seed=23)
        b = player.allocate(self.p, self.s, profiles(), GOALIES, seed=24)
        self.assertEqual(a["scenario_sha256"], self.x["scenario_sha256"])
        self.assertNotEqual(b["scenario_sha256"], a["scenario_sha256"])
        changed = copy.deepcopy(self.s)
        q = changed[0].periods[0]
        # Change one valid period outcome and its opposing goalie saves.
        other = team.Period(q.shots_home + 1, q.shots_away, q.goals_home,
                            q.goals_away, q.saves_home_goalie,
                            q.saves_away_goalie + 1)
        changed[0] = team.Scenario((other,) + changed[0].periods[1:])
        c = player.allocate(self.p, changed, profiles(), GOALIES, seed=23)
        self.assertNotEqual(c["scenario_sha256"], a["scenario_sha256"])

    def test_integer_push_and_opposite_sides_share_draws(self):
        a = player.price(self.x, "REG_SOG", "over", 3, player_id="h-01",
                         settlement_scope="REGULATION_ONLY")
        b = player.price(self.x, "REG_SOG", "under", 3, player_id="h-01",
                         settlement_scope="REGULATION_ONLY")
        self.assertEqual(a["status"], "SIMULATED_REGULATION_RESEARCH_ONLY")
        self.assertEqual(a["wins"], b["losses"])
        self.assertEqual(a["losses"], b["wins"])
        self.assertEqual(a["pushes"], b["pushes"])
        self.assertEqual(a["wins"] + a["pushes"] + a["losses"], self.x["n"])
        c = player.price(self.x, "REG_GOALS", "over", .5, player_id="h-01",
                         settlement_scope="REGULATION_ONLY")
        self.assertEqual(c["pushes"], 0)

    def test_ot_unsettled_and_non_offered_features_block(self):
        for market in ("FG_SOG", "FG_GOALIE_SAVES", "REG_ASSISTS", "2PLUS_GOALS"):
            x = player.price(self.x, market, "over", .5, player_id="h-01",
                             settlement_scope="REGULATION_ONLY")
            self.assertEqual(x["status"], "NO_FORECAST")
        x = player.price(self.x, "REG_SOG", "over", .5, player_id="h-01")
        self.assertEqual(x["status"], "UNRESOLVED_MARKET")
        self.assertEqual(self.x["official_counted"], 0)

    def test_missing_duplicate_cross_team_and_nonfinite_player_inputs_block(self):
        arr = profiles()
        for changed in (arr[:-1], [dict(x) for x in arr], [dict(x) for x in arr]):
            if len(changed) == 36 and changed[0]["player_id"] == "h-01":
                if changed[1]["player_id"] == "h-02":
                    changed[1]["player_id"] = "h-01"
                else:
                    changed[0]["shots_per_60"] = math.nan
            with self.assertRaises(player.Blocked):
                player.allocate(self.p, self.s[:1], changed, GOALIES)
        wrong = profiles()
        wrong[0]["side"] = "away"
        with self.assertRaises(player.Blocked):
            player.allocate(self.p, self.s[:1], wrong, GOALIES)
        wrong2 = profiles()
        wrong2[0]["projected_toi_minutes"] = float("inf")
        with self.assertRaises(player.Blocked):
            player.allocate(self.p, self.s[:1], wrong2, GOALIES)

    def test_each_player_source_is_asof_and_sha_bound(self):
        cases = [
            ("feature_available_utc", "2026-11-22T12:00:00Z"),
            ("feature_available_utc", "2026-11-20T10:00:00"),
            ("feature_source_sha256", "unsigned"),
            ("feature_source_sha256", None),
        ]
        for field, bad in cases:
            candidate = profiles()
            candidate[0][field] = bad
            with self.assertRaises(player.Blocked):
                player.allocate(self.p, self.s[:1], candidate, GOALIES)

    def test_late_inputs_unconfirmed_goalie_and_ambiguous_goalie_ids_block(self):
        with self.assertRaises(team.Blocked):
            player.allocate(params(frozen_utc="2026-11-23T00:00:00Z"),
                            self.s[:1], profiles(), GOALIES)
        with self.assertRaises(team.Blocked):
            player.allocate(params(confirmed_home_goalie=False),
                            self.s[:1], profiles(), GOALIES)
        with self.assertRaises(player.Blocked):
            player.allocate(self.p, self.s[:1], profiles(),
                            {"home": "same", "away": "same"})

    def test_bad_selection_line_and_absent_roster_id_block(self):
        cases = [
            ("REG_SOG", "up", .5, "UNRESOLVED_MARKET"),
            ("REG_SOG", "over", math.nan, "UNRESOLVED_MARKET"),
            ("REG_SOG", "under", -1, "UNRESOLVED_MARKET"),
            ("REG_SOG", "over", .5, "SIMULATED_REGULATION_RESEARCH_ONLY"),
        ]
        for market, side, line, expected in cases:
            r = player.price(self.x, market, side, line, player_id="h-01",
                             settlement_scope="REGULATION_ONLY")
            self.assertEqual(r["status"], expected)
        r = player.price(self.x, "REG_SOG", "over", .5, player_id="missing",
                         settlement_scope="REGULATION_ONLY")
        self.assertEqual(r["status"], "NO_FORECAST")


if __name__ == "__main__":
    unittest.main()
