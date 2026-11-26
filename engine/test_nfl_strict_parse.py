"""Strict projection/score parsing: '2+7' must never become 27 (frozen v5's num() deletes every '+')."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfl_provenance as P  # noqa: E402
import run_nfl_wpl as W  # noqa: E402

H = "sport,home,away,home_proj,away_proj,player,team,proj,market,line,price_a,price_b,home_score,away_score,remaining\n"


def board(*rows):
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write(H + "".join(r + "\n" for r in rows))
    return p


class Provenance(unittest.TestCase):
    def test_num_accepts_plain_decimals_only(self):
        for s, want in (("27", 27.0), ("27.5", 27.5), ("+27", 27.0), ("-3", -3.0), (".5", 0.5), ("\u22123", -3.0)):
            self.assertEqual(P._num(s), want, s)
        self.assertIsNone(P._num(""))
        self.assertIsNone(P._num(None))

    def test_num_rejects_everything_v5_would_repair(self):
        for s in ("2+7", "+2+7", "1e1", "nan", "inf", "-inf", "0x1", "2 7", "1,5", "1234567", "0.1234567", "1" * 17,
                  "\u0662\u0667", "\u00b2\u2077"):
            self.assertEqual(P._num(s), "bad", s)

    def test_malformed_team_projection_is_invalid(self):
        p = board("NFL,A,B,2+7,20,,,,TOTAL,44.5,-110,-110,,,")
        self.assertEqual(P.classify(p)[("B @ A", "TOTAL", "", "")][0], P.INVALID)

    def test_malformed_player_projection_is_invalid(self):
        p = board("NFL,A,B,27,20,,,,TOTAL,44.5,-110,-110,,,", "NFL,A,B,,,P1,A,7+0,REC_YDS,59.5,-110,-110,,,")
        self.assertEqual(P.classify(p)[("B @ A", "REC_YDS", "P1", "")][0], P.INVALID)


class Validator(unittest.TestCase):
    def rejects(self, *rows):
        with self.assertRaises(ValueError) as c:
            W.validate_input(board(*rows))
        self.assertIn("non-canonical projection/score", str(c.exception))

    def test_malformed_projection_score_and_remaining_are_rejected_before_v5(self):
        self.rejects("NFL,A,B,2+7,20,,,,TOTAL,44.5,-110,-110,,,")
        self.rejects("NFL,A,B,27,2+0,,,,TOTAL,44.5,-110,-110,,,")
        self.rejects("NFL,A,B,,,P1,A,7+0,REC_YDS,59.5,-110,-110,,,")
        self.rejects("NFL,A,B,,,,,,TOTAL,44.5,-110,-110,1+4,,")
        self.rejects("NFL,A,B,,,,,,TOTAL,44.5,-110,-110,,,0.5.1")
        self.rejects("NFL,A,B,nan,20,,,,TOTAL,44.5,-110,-110,,,")
        self.rejects("NFL,A,B,1e1,20,,,,TOTAL,44.5,-110,-110,,,")

    def test_plain_decimal_projections_pass(self):
        W.validate_input(board("NFL,A,B,27.5,20,,,,TOTAL,44.5,-110,-110,,,",
                               "NFL,A,B,,,P1,A,70.25,REC_YDS,59.5,-110,-110,,,",
                               "CBB,A,B,2+7,,,,,TOTAL,144.5,-110,-110,,,"))


if __name__ == "__main__":
    unittest.main()
