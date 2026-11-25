import copy
import unittest
from cbb_player_final_box import extract, outcome


def fixture():
    def athlete(pid, stats, dnp=False):
        return {"athlete": {"id": pid}, "stats": stats, "didNotPlay": dnp}
    return {"header": {"id": "g1", "competitions": [{"id": "g1", "status": {"type": {"completed": True}},
            "competitors": [{"homeAway": "home", "team": {"id": "h"}, "score": "80"},
                            {"homeAway": "away", "team": {"id": "a"}, "score": "70"}]}]},
            "boxscore": {"players": [
                {"team": {"id": "h"}, "statistics": [{"labels": ["MIN", "PTS", "REB", "AST", "3PT"],
                 "athletes": [athlete("p1", ["30", "15", "7", "3", "2-5"]),
                              athlete("p2", ["0", "0", "0", "0", "0-0"], True)]}]},
                {"team": {"id": "a"}, "statistics": [{"labels": ["MIN", "PTS", "REB", "AST", "3PT"],
                 "athletes": [athlete("p3", ["0:24", "0", "0", "0", "0-0"])]}]}]}}


class PlayerFinalBox(unittest.TestCase):
    def read(self, doc):
        return extract(doc, "g1", "h", "a", 80, 70)

    def test_exact_stats_and_outcome(self):
        records = self.read(fixture())
        self.assertEqual(records[("h", "p1")], {"PTS": 15, "REB": 7, "AST": 3, "3PM": 2})
        self.assertNotIn(("h", "p2"), records)
        self.assertIn(("a", "p3"), records)
        stats = records[("h", "p1")]
        self.assertEqual(outcome("PLAYER_PRA_OU", 25, stats), "push")
        self.assertEqual(outcome("PLAYER_PRA_AT_LEAST", 25, stats), "yes")
        self.assertEqual(outcome("PLAYER_3PM_OU", 2.5, stats), "under")

    def test_identity_score_and_completion(self):
        for field in ("id", "score", "completed"):
            doc = fixture()
            game = doc["header"]["competitions"][0]
            if field == "id": game["id"] = "other"
            if field == "score": game["competitors"][0]["score"] = "81"
            if field == "completed": game["status"]["type"]["completed"] = False
            with self.assertRaises(ValueError):
                self.read(doc)

    def test_duplicate_cross_team_and_bad_stats(self):
        doc = fixture()
        group = doc["boxscore"]["players"][0]["statistics"][0]
        group["athletes"].append(copy.deepcopy(group["athletes"][0]))
        self.assertNotIn(("h", "p1"), self.read(doc))
        doc = fixture()
        doc["boxscore"]["players"][1]["statistics"][0]["athletes"][0]["athlete"]["id"] = "p1"
        self.assertNotIn(("h", "p1"), self.read(doc))
        doc = fixture()
        doc["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][-1] = "6-5"
        self.assertNotIn(("h", "p1"), self.read(doc))


if __name__ == "__main__":
    unittest.main()
