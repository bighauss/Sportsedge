"""Player-prop quotes must not price against a player on a different team (Claude, NFL lane)."""
import unittest

import book_ev as b
from test_book_ev import run


class PropTeamIdentity(unittest.TestCase):
    REC = {"market": "rec_yds", "player": "WR1", "line": 55.5, "over": -110, "under": -110}

    def reasons(self, out):
        return [u["reason"] for u in out["unpriced"]]

    def test_wrong_team_withheld(self):
        out = run([dict(self.REC, team="AWY")])
        self.assertEqual(out["rows"], [])
        self.assertEqual(self.reasons(out), ["PLAYER_TEAM_MISMATCH"])

    def test_team_not_in_game_withheld(self):
        for t in ("XXX", 7, ["HOM"]):
            with self.subTest(team=t):
                out = run([dict(self.REC, team=t)])
                self.assertEqual(out["rows"], [])
                self.assertEqual(self.reasons(out), ["PLAYER_TEAM_NOT_IN_GAME"])

    def test_td_wrong_team_withheld(self):
        out = run([{"market": "anytime_td", "player": "WR1", "team": "AWY", "yes": 150, "no": -190}])
        self.assertEqual(out["rows"], [])
        self.assertEqual(self.reasons(out), ["PLAYER_TEAM_MISMATCH"])

    def test_correct_or_absent_team_priced(self):
        for extra in ({}, {"team": "HOM"}, {"team": None}):
            with self.subTest(**extra):
                self.assertEqual(len(run([dict(self.REC, **extra)])["rows"]), 2)

    def test_blank_player_withheld(self):
        for pl in ("", "  ", None):
            with self.subTest(player=pl):
                out = run([dict(self.REC, player=pl)])
                self.assertEqual(out["rows"], [])
                self.assertEqual(self.reasons(out), ["MISSING_PLAYER_IDENTITY"])

    def test_misteamed_quote_does_not_quarantine_valid_one(self):
        out = run([dict(self.REC, team="HOM"), dict(self.REC, team="AWY", over=-150, under=120)])
        self.assertEqual(len(out["rows"]), 2)
        self.assertEqual(self.reasons(out), ["PLAYER_TEAM_MISMATCH"])

    def test_order_invariant(self):
        qs = [dict(self.REC, team="HOM"), dict(self.REC, team="AWY", over=-150, under=120)]
        self.assertEqual(run(qs)["rows"], run(list(reversed(qs)))["rows"])


if __name__ == "__main__":
    unittest.main()
