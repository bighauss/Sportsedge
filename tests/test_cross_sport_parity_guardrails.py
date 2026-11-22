"""Provider-free cross-sport regression review of incumbent intake safeguards.

This is a narrow *adversarial fixture* suite, not a test of real data, independent
model forecasts, full attempted-offer coverage, authenticated prices, or profit.
Run: python -m unittest discover -s tests -p test_cross_sport_parity_guardrails.py -v
"""
import datetime as dt
import unittest

from models.cbb import cbb_run_it as CBB
from models.cfb import cfb_run_it as CFB
from models.mlb import sportsedge_mlb_model as MLB


UTC = dt.timezone.utc


class CBBIntakeGuards(unittest.TestCase):
    def test_unknown_slate_neutral_withheld(self):
        future = {
            "id": 101, "startDate": "2026-11-22T17:00:00Z",
            "startTimeTbd": False, "neutralSite": None,
            "homeTeamId": 1, "awayTeamId": 2,
            "homeTeam": "Synthetic Home", "awayTeam": "Synthetic Away",
        }
        misses = []
        got = CBB.slate([future], dt.date(2026, 11, 22),
                        dt.datetime(2026, 11, 22, 15, tzinfo=UTC),
                        2027, misses)
        self.assertEqual(got, [])
        self.assertEqual(len(misses), 1)
        self.assertIn("neutral", misses[0][1].lower())

    def test_duplicate_prior_game_ids_quarantined(self):
        g = {
            "id": 12, "status": "final", "startTimeTbd": False,
            "startDate": "2026-11-01T17:00:00Z",
            "homeTeamId": 1, "awayTeamId": 2, "neutralSite": False,
            "homePoints": 70, "awayPoints": 60,
        }
        boxes = [
            {"gameId": 12, "teamId": 1, "teamStats": {"possessions": 68}},
            {"gameId": 12, "teamId": 2, "teamStats": {"possessions": 67}},
        ]
        rows, census = CBB.prior_games(
            [g, dict(g)], boxes, "2026-11-22T16:00:00Z", 2027)
        self.assertEqual(rows, [])
        self.assertEqual(census["duplicate_game_id"], 2)

    def test_unverified_total_orientation_is_withheld(self):
        offer = {
            "sport": "CBB", "market": "TOTAL", "home": "Synthetic Home",
            "away": "Synthetic Away", "line": 150.5,
            "price_a": -110, "price_b": -110,
        }
        rows, withheld = CBB.board_quotes(
            [offer], [], "2026-11-22T15:00:00Z",
            totals_order_verified=False)
        self.assertEqual(rows, [])
        self.assertEqual(len(withheld), 1)
        self.assertIn("order", withheld[0][2])


class CFBIntakeGuards(unittest.TestCase):
    def test_duplicate_completed_event_id_quarantines_affected_teams(self):
        def game(gid, a, h):
            return {
                "id": gid, "awayTeam": a, "homeTeam": h,
                "completed": True, "startDate": "2026-11-01T19:00:00Z",
            }
        out = CFB.games_played(
            [game(1, "A", "B"), game(1, "C", "D"),
             game(2, "E", "F")],
            dt.datetime(2026, 11, 22, 15, tzinfo=UTC))
        self.assertEqual(out.get("E"), 1)
        self.assertEqual(out.get("F"), 1)
        for team in ("A", "B", "C", "D"):
            self.assertNotIn(team, out)

    def test_cross_team_provider_player_id_collision_quarantined(self):
        def stat(team):
            return {
                "playerId": "501", "player": "Synthetic Player",
                "team": team, "statType": "CAR", "stat": 25,
            }
        table = CFB.player_table({
            "player_rushing": [stat("A"), stat("B")],
            "player_passing": [], "player_receiving": [],
        })
        self.assertEqual(table, {})

    def test_ambiguous_same_name_within_game_does_not_map(self):
        table = {
            ("A", "101"): {"name": "Synthetic Player"},
            ("B", "102"): {"name": "Synthetic Player"},
        }
        self.assertIsNone(
            CFB.match_player("Synthetic Player", ("A", "B"), table))

    def test_started_card_row_moves_to_withheld_on_recheck(self):
        doc = {
            "model_projections": {
                "games": [{"game": "A @ B",
                           "kickoff_utc": "2026-11-22T14:00:00+00:00"}]
            },
            "card": {
                "rows": [{"game": "A @ B", "market": "Total",
                          "pick": "Over 50.5"}],
                "withheld": [],
            },
        }
        result = CFB.recheck(
            doc, dt.datetime(2026, 11, 22, 15, tzinfo=UTC))
        self.assertEqual(result["card"]["rows"], [])
        self.assertEqual(len(result["card"]["withheld"]), 1)
        self.assertEqual(result["model_projections"]["games"], [])


class MLBIntakeGuards(unittest.TestCase):
    @staticmethod
    def pair_rows():
        return [
            {"game_id": "G1", "market": "TOTAL", "selection": "over",
             "line": "8.5", "price": "-110", "book": "DK"},
            {"game_id": "G1", "market": "TOTAL", "selection": "under",
             "line": "8.5", "price": "-110", "book": "DK"},
        ]

    def test_valid_book_pair_requires_complementary_sides(self):
        rows = self.pair_rows()
        self.assertEqual(len(MLB._pair_game_odds(rows, "G1")), 1)
        rows.append(dict(rows[0]))  # duplicate third outcome
        self.assertEqual(MLB._pair_game_odds(rows, "G1"), {})

    def test_different_books_cannot_create_two_sided_quote(self):
        rows = self.pair_rows()
        rows[1]["book"] = "OTHER"
        self.assertEqual(MLB._pair_game_odds(rows, "G1"), {})

    @staticmethod
    def fixture():
        game = {
            "game_id": "G1", "away": "A", "home": "B",
            "away_sp_id": "pa", "home_sp_id": "pb",
        }
        inp = {
            "pitchers": {"pa": {"team": "A"}, "pb": {"team": "B"}},
            "batters": {
                f"{team}{slot}": {"team": team}
                for team in ("A", "B") for slot in range(1, 10)
            },
            "lineups": [
                {"game_id": "G1", "team": team, "slot": str(slot),
                 "player_id": f"{team}{slot}"}
                for team in ("A", "B") for slot in range(1, 10)
            ],
        }
        return inp, game

    def test_duplicate_batting_slot_blocks_game(self):
        inp, game = self.fixture()
        self.assertEqual(MLB.preflight_game_inputs(inp, game), [])
        inp["lineups"][1]["slot"] = "1"
        reasons = MLB.preflight_game_inputs(inp, game)
        self.assertIn("AWAY_LINEUP_NOT_NINE_DISTINCT_SLOTS", reasons)

    def test_incorrect_starting_pitcher_team_blocks_game(self):
        inp, game = self.fixture()
        inp["pitchers"]["pa"]["team"] = "B"
        self.assertIn("AWAY_STARTER_TEAM_MISMATCH",
                      MLB.preflight_game_inputs(inp, game))

    def test_integer_push_mass_refunded_in_ev(self):
        priced = MLB.ev_row(.6, -110, .55, push=.2)
        self.assertAlmostEqual(priced["model_p"], .48)
        self.assertAlmostEqual(priced["p_push"], .2)
        self.assertAlmostEqual(
            priced["ev_raw"], .48 * (100 / 110) - .32)
        self.assertAlmostEqual(
            priced["model_p"] + priced["p_push"] + (1 - .6) * .8, 1.0)


if __name__ == "__main__":
    unittest.main()
