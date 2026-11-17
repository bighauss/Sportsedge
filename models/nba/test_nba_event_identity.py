"""Synthetic NBA player identity tests; no real player data or provider claims."""
import unittest
import sportsedge_nba_model as m


def player(name, team, pid):
    return {"player": name, "team": team, "player_id": pid, "pos": "G",
            "starter": "1", "minutes": "30", "usage": "0.25",
            "pts_pm": "0.65", "reb_pm": "0.17", "ast_pm": "0.16",
            "fg3m_pm": "0.07"}


def samples():
    data = {"players": [player("Twin", "H", "h1"), player("Twin", "A", "a1")],
            "injuries": [], "teams": {t: {"pace": "99", "games": "20"}
                                    for t in ("H", "A", "X")},
            "posdef": {}, "props": []}
    projs = {
        "G1": {"home": "H", "away": "A", "margin": 3, "pace": 99},
        "G2": {"home": "H", "away": "X", "margin": 6, "pace": 101},
    }
    return data, projs


class NBAIdentityTest(unittest.TestCase):
    def test_two_games_create_distinct_event_projections(self):
        data, projs = samples()
        p = m.project_players(data, projs)
        self.assertIn(("G1", "H", "Twin", "h1"), p)
        self.assertIn(("G2", "H", "Twin", "h1"), p)
        self.assertEqual(p[("G1", "H", "Twin", "h1")]["opp"], "A")
        self.assertEqual(p[("G2", "H", "Twin", "h1")]["opp"], "X")

    def test_same_name_different_team_requires_team_or_id(self):
        data, projs = samples()
        p = m.project_players(data, projs)
        self.assertIsNone(m.resolve_prop_player({"game_id": "G1", "player": "Twin"}, p))
        self.assertEqual(m.resolve_prop_player(
            {"game_id": "G1", "player": "Twin", "team": "H"}, p)["team"], "H")
        self.assertEqual(m.resolve_prop_player(
            {"game_id": "G1", "player_id": "a1"}, p)["team"], "A")

    def test_unknown_event_or_id_never_falls_back(self):
        data, projs = samples()
        p = m.project_players(data, projs)
        self.assertIsNone(m.resolve_prop_player(
            {"game_id": "BAD", "player": "Twin"}, p))
        self.assertIsNone(m.resolve_prop_player(
            {"game_id": "G1", "player": "Twin", "player_id": "missing"}, p))
        self.assertIsNone(m.resolve_prop_player(
            {"game_id": "G1", "player": "Twin", "team": "X"}, p))

    def test_injury_only_affects_same_team_name(self):
        data, projs = samples()
        data["injuries"] = [{"player": "Twin", "team": "H", "status": "OUT"}]
        p = m.project_players(data, projs)
        self.assertEqual(p[("G1", "H", "Twin", "h1")]["min"], 0)
        self.assertGreater(p[("G1", "A", "Twin", "a1")]["min"], 0)

    def test_duplicate_same_subject_quarantined(self):
        data, projs = samples()
        data["players"].append(dict(data["players"][0]))
        p = m.project_players(data, projs)
        self.assertIsNone(p[("G1", "H", "Twin", "h1")])
        self.assertIsNone(m.resolve_prop_player(
            {"game_id": "G1", "player": "Twin", "team": "H"}, p))

    def test_prop_price_uses_event_scoped_player(self):
        data, projs = samples()
        data["props"] = [{"game_id": "G1", "player": "Twin", "stat": "PTS",
                          "line": "19.5", "over_price": "-110", "under_price": "-110"}]
        self.assertEqual(m.price_props(data, m.project_players(data, projs)), [])
        data["props"][0]["team"] = "H"
        self.assertEqual(len(m.price_props(data, m.project_players(data, projs))), 2)

    def test_unique_legacy_name_alias_still_available(self):
        data, projs = samples()
        data["players"] = [player("Solo", "H", "s1")]
        projs = {"G1": projs["G1"]}
        p = m.project_players(data, projs)
        self.assertEqual(p["Solo"]["team"], "H")


if __name__ == "__main__":
    unittest.main()
