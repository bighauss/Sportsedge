"""MLB original-input structural tests; fake fixtures, not sportsbook proofs."""
import unittest
import sportsedge_mlb_model as m


def sample():
    game = {"game_id": "G", "away": "A", "home": "H",
            "away_sp_id": "a-sp", "home_sp_id": "h-sp"}
    inp = {
        "pitchers": {"a-sp": {"team": "A"}, "h-sp": {"team": "H"}},
        "batters": {f"{side}{n}": {"team": side}
                    for side in ("A", "H") for n in range(1, 10)},
        "lineups": [{"game_id": "G", "team": side, "slot": str(n),
                    "player_id": f"{side}{n}"}
                   for side in ("A", "H") for n in range(1, 10)],
    }
    return inp, game


def quote(side, book, line="8.5", market="TOTAL"):
    return {"game_id": "G", "market": market, "selection": side,
            "line": line, "price": "-110", "book": book}


class MLBSourceInputTest(unittest.TestCase):
    def test_valid_structural_inputs(self):
        inp, game = sample()
        self.assertEqual(m.preflight_game_inputs(inp, game), [])

    def test_missing_starter_fails_closed(self):
        inp, game = sample()
        del inp["pitchers"]["a-sp"]
        self.assertIn("AWAY_STARTER_MISSING", m.preflight_game_inputs(inp, game))

    def test_cross_team_starter_fails_closed(self):
        inp, game = sample()
        inp["pitchers"]["h-sp"]["team"] = "A"
        self.assertIn("HOME_STARTER_TEAM_MISMATCH", m.preflight_game_inputs(inp, game))

    def test_partial_duplicate_and_wrong_team_lineups(self):
        inp, game = sample()
        inp["lineups"] = inp["lineups"][:-1]
        self.assertIn("HOME_LINEUP_NOT_NINE_DISTINCT_SLOTS",
                      m.preflight_game_inputs(inp, game))
        inp, game = sample()
        inp["lineups"][-1]["slot"] = "1"
        self.assertIn("HOME_LINEUP_NOT_NINE_DISTINCT_SLOTS",
                      m.preflight_game_inputs(inp, game))
        inp, game = sample()
        inp["batters"]["H9"]["team"] = "A"
        self.assertIn("HOME_BATTER_TEAM_MISMATCH",
                      m.preflight_game_inputs(inp, game))

    def test_cross_book_opposite_quotes_never_combined(self):
        self.assertEqual(m._pair_game_odds(
            [quote("over", "DK"), quote("under", "FD")], "G"), {})

    def test_same_book_pair_and_two_independent_pairs(self):
        both = [quote("over", "DK"), quote("under", "DK")]
        pairs = m._pair_game_odds(both, "G")
        self.assertEqual(len(pairs), 1)
        self.assertIn(("TOTAL", 8.5, "DK"), pairs)
        all_books = both + [quote("over", "FD"), quote("under", "FD")]
        self.assertEqual(len(m._pair_game_odds(all_books, "G")), 2)

    def test_line_mismatch_rejected(self):
        self.assertEqual(m._pair_game_odds(
            [quote("over", "DK"), quote("under", "DK", line="9.5")], "G"), {})


if __name__ == "__main__":
    unittest.main()
