import copy
import unittest
from cbb_player_matchup_forecast import admit, forecast, build, VERSION


def sample(day, *, opp_points=70):
    return {"event_id": str(day), "home_id": "h", "away_id": "a",
            "tip_utc": f"2026-11-{day:02d}T18:00:00Z",
            "observed_final_utc": f"2026-11-{day:02d}T21:00:00Z",
            "possessions": 70,
            "team_stats": {"h": {"PTS": opp_points, "REB": 35, "AST": 14, "3PM": 7},
                           "a": {"PTS": 65, "REB": 32, "AST": 12, "3PM": 6}},
            "players": [{"team_id": "h", "player_id": "p", "minutes": 30,
                         "stats": {"PTS": 15, "REB": 5, "AST": 3, "3PM": 2}}]}


TARGET = {"event_id": "target", "team_id": "h", "player_id": "p", "opponent_id": "a",
          "tip_utc": "2026-11-25T18:00:00Z", "frozen_utc": "2026-11-25T12:00:00Z"}


class MatchupForecast(unittest.TestCase):
    def test_chronological_and_matchup_forecast(self):
        games = [sample(d) for d in range(1, 11)]
        f, diag = forecast(TARGET, admit(games))
        self.assertEqual(f.model_version, VERSION)
        self.assertEqual(diag["minutes_if_participating"], 30)
        self.assertEqual(diag["appearances"], 10)
        self.assertGreater(diag["opponent_factors"]["PTS"], 1)
        self.assertGreater(f.means["PTS"], 15)
        self.assertLessEqual(3*f.means["3PM"], f.means["PTS"])
        late = sample(24, opp_points=120)
        late["observed_final_utc"] = "2026-11-25T13:00:00Z"
        self.assertEqual(f, forecast(TARGET, admit(games + [late]))[0])

    def test_bundle_replay_is_not_prospective(self):
        games = [sample(d) for d in range(1, 11)]
        bundle = build(games, [TARGET])
        self.assertEqual(len(bundle["targets"]), 1)
        self.assertEqual(len(bundle["history"]), 5)
        self.assertEqual(bundle["evidence_class"], "CHRONOLOGICAL_REPLAY_NOT_PROSPECTIVE")
        self.assertEqual(len(bundle["rejections"]), 5)
        self.assertEqual(bundle["approved_stake_u"], 0)

    def test_invalid_duplicate_and_missing_history(self):
        r = sample(1)
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            admit([r, copy.deepcopy(r)])
        bad = copy.deepcopy(r)
        bad["players"][0]["stats"]["REB"] = 36
        with self.assertRaisesRegex(ValueError, "PLAYER_TOTAL_EXCEEDS_TEAM"):
            admit([bad])
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT"):
            forecast(TARGET, admit([r]))
        with self.assertRaisesRegex(ValueError, "TARGET_ALREADY_IN_FINALS"):
            build([r], [dict(TARGET, event_id="1")])


if __name__ == "__main__":
    unittest.main()
