"""Validator-only regression for engine/run_nfl_wpl.validate_input against frozen v5's own market catalog."""
import csv
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_nfl_wpl as W  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

H = "sport,home,away,market,player,line,price_a,price_b,sgp,side\n"


def board(*rows):
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write(H + "".join(r + "\n" for r in rows))
    return p


class Validator(unittest.TestCase):
    def accepts(self, *rows):
        W.validate_input(board(*rows))

    def rejects(self, expect, *rows):
        with self.assertRaises(ValueError) as c:
            W.validate_input(board(*rows))
        self.assertIn(expect, str(c.exception))

    def test_every_frozen_v5_nfl_stat_prop_and_td_market_is_accepted(self):
        for m in sorted(v5.PROPS["drive"]):
            with self.subTest(m):
                self.accepts("NFL,A,B,%s,P1,59.5,-110,-110,," % m)
        for m in sorted(v5.TD_NAMES):
            with self.subTest(m):
                self.accepts("NFL,A,B,%s,P1,,150,-190,," % m)

    def test_valid_game_markets_including_non_line_and_sgp_rows(self):
        self.accepts("NFL,A,B,ML,,,-150,130,,", "NFL,A,B,1H_SPREAD,,-3.5,-110,-110,,", "NFL,A,B,OT,,,1000,-3000,,",
                     "NFL,A,B,REG_DRAW,,,2500,,,", "NFL,A,B,HOME_BY_1_6,,,300,,,", "NFL,A,B,SGP,,,600,,S1,",
                     "NFL,A,B,TOTAL,,44.5,-110,-110,,")

    def test_player_market_v5_does_not_price_is_rejected(self):
        self.rejects("not priced by frozen v5", "NFL,A,B,POINTS,P1,20.5,-110,-110,,")      # hoops stat on an NFL row
        self.rejects("not priced by frozen v5", "NFL,A,B,1H_PASS_YDS,P1,100.5,-110,-110,,")  # props are never period-split

    def test_period_prefix_on_full_game_only_market_is_rejected(self):
        self.rejects("unknown game-level market", "NFL,A,B,1H_OT,,,1000,-3000,,")

    def test_stat_prop_needs_a_line_but_td_prop_does_not(self):
        self.rejects("has no line", "NFL,A,B,REC_YDS,P1,,-110,-110,,")
        self.accepts("NFL,A,B,FTD,P1,,900,-2000,,")

    def test_game_market_carrying_a_player_is_rejected(self):
        self.rejects("carries player", "NFL,A,B,SPREAD,Bob,-3.5,-110,-110,,")


    def test_nfl_only_distinct_teams_and_exact_csv_width(self):
        for message, row in (
            ("no away team", "NFL,A,,TOTAL,,44.5,-110,-110,,"),
            ("distinct teams", "NFL,A,a,TOTAL,,44.5,-110,-110,,"),
            ("not an NFL row", "CBB,A,B,TOTAL,,144.5,-110,-110,,"),
            ("cells for", "NFL,A,B,TOTAL,,44.5,-110,-110,"),
            ("cells for", "NFL,A,B,TOTAL,,44.5,-110,-110,,,"),
        ):
            with self.subTest(row=row):
                self.rejects(message, row)
        self.rejects("not an NFL row", "NFL,A,B,TOTAL,,44.5,-110,-110,,",
                     "CBB,A,B,TOTAL,,144.5,-110,-110,,")
        self.rejects("no NFL rows")
        self.accepts("NFL,A,B,TOTAL,,44.5,-110,-110,,")

    def test_live_score_fields_are_not_pregame(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "board.csv")
            for suffix in ("0,,", ",0,", ",,0", ",,12.5"):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("sport,home,away,market,line,price_a,price_b,home_score,away_score,remaining\n"
                            "NFL,A,B,TOTAL,44.5,-110,-110," + suffix + "\n")
                with self.assertRaisesRegex(ValueError, "pregame-only"):
                    W.validate_input(p)


    def test_winning_margin_bands_must_have_ordered_positive_integer_bounds(self):
        for m in ("HOME_BY_1_6", "AWAY_BY_7_13", "HOME_BY_3_3"):
            self.accepts("NFL,A,B,%s,,,300,,," % m)
        for m in ("HOME_BY_ABC", "HOME_BY_6_1", "AWAY_BY_0_3",
                  "HOME_BY_1_2_3", "AWAY_BY_-2_3", "1H_HOME_BY_1_6"):
            with self.subTest(market=m):
                self.rejects("unknown game-level market", "NFL,A,B,%s,,,300,,," % m)

    def test_every_frozen_period_game_market_is_admitted(self):
        for period in v5.PERIODS["NFL"]:
            for market in ("ML", "SPREAD", "TOTAL", "HOME_TT", "AWAY_TT"):
                line = "" if market == "ML" else "3.5"
                self.accepts("NFL,A,B,%s_%s,,%s,-110,-110,," % (period, market, line))


if __name__ == "__main__":
    unittest.main()
