"""Offline regression tests for the opt-in public-replay ratings bridge (PAPER/0u)."""
import json
import unittest

import cbb_run_it_pipeline as PIPE
import public_replay_adapted as A


def game(gid, home="1", away="2", neutral=False):
    return {"id": gid, "home_id": home, "away_id": away, "neutral": neutral, "home_score": 70,
            "away_score": 60, "possessions": 68.0, "tip_utc": "2026-11-20T18:00Z"}


class Admission(unittest.TestCase):
    def test_evidence_is_required_not_inferred(self):
        with self.assertRaisesRegex(ValueError, "D1_MEMBERSHIP_EVIDENCE_REQUIRED"):
            A.admit([game("a")], d1_ids=None, verified_home_ids=set())
        with self.assertRaisesRegex(ValueError, "VENUE_EVIDENCE_REQUIRED"):
            A.admit([game("a")], d1_ids={"1", "2"}, verified_home_ids=None)

    def test_site_rules_and_counts(self):
        prior = [game("a", neutral=True), game("b"), game("c"), game("d", neutral=None),
                 game("e", home="x1")]
        games, by_id, census = A.admit(prior, d1_ids={"1", "2"}, verified_home_ids={"b"})
        sites = {g["game_id"]: g["site"] for g in games}
        self.assertEqual(sites, {"a": "NEUTRAL", "b": "HOME_VERIFIED"})
        self.assertEqual(census, {"dropped_bad_team_id": 1, "dropped_site_unknown": 1,
                                  "dropped_home_unverified": 1})
        self.assertEqual(set(by_id), {"a", "b"})
        self.assertEqual(games[0]["date"], "2026-11-20")


class LegacyBody(unittest.TestCase):
    def body(self, **over):
        rows = [{"team": "10", "teamId": 10, "offensiveRating": 105.12345, "defensiveRating": 100.0,
                 "netRating": 5.1, "pace": 69.0, "n_games": 3},
                {"team": "20", "teamId": 20, "offensiveRating": 101.0, "defensiveRating": 102.0,
                 "netRating": -1.0, "pace": 68.0, "n_games": 0}]
        rows[0].update(over)
        return json.dumps(rows).encode()

    def test_schema_and_zero_game_teams(self):
        legacy = json.loads(A.to_legacy_body(self.body(), 2027))
        self.assertEqual(legacy, [{"season": 2027, "teamId": 10, "team": "10", "offensiveRating": 105.123,
                                   "defensiveRating": 100.0, "netRating": 5.123, "games": 3}])
        both = json.loads(A.to_legacy_body(self.body(), 2027, include_zero_game_teams=True))
        self.assertEqual([r["teamId"] for r in both], [10, 20])

    def test_contract_violations_raise(self):
        with self.assertRaisesRegex(ValueError, "RATINGS_OUT_OF_CONTRACT"):
            A.to_legacy_body(self.body(offensiveRating=170.0), 2027)
        with self.assertRaisesRegex(ValueError, "RATINGS_BAD_TEAM_ID"):
            A.to_legacy_body(self.body(team="abc"), 2027)


class RuntimeIsolation(unittest.TestCase):
    def test_bridge_fails_closed_without_evidence(self):
        project = A.make_public_replay_project(d1_ids=None, verified_home_ids=None)
        out, leak, body = project({}, [], 2027, "2026-11-25T17:25:00Z", {"sd_margin": 11.8, "sd_total": 17.2})
        self.assertEqual(out, {})
        self.assertIn("D1_MEMBERSHIP_EVIDENCE_REQUIRED", leak["reason"])
        self.assertEqual(body, b"")

    def test_install_restores_legacy_function(self):
        original = PIPE.public_replay_project
        sentinel = lambda *a, **k: None
        previous = A.install(sentinel)
        try:
            self.assertIs(previous, original)
            self.assertIs(PIPE.public_replay_project, sentinel)
        finally:
            PIPE.public_replay_project = previous
        self.assertIs(PIPE.public_replay_project, original)
        self.assertTrue(callable(PIPE.d1_filter))
        self.assertTrue(callable(PIPE.public_ratings))


if __name__ == "__main__":
    unittest.main()
