"""Strict CBB quote parsing and identity (pure python)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cbb_numeric as N  # noqa: E402


class Price(unittest.TestCase):
    def test_exact_integers_accepted(self):
        for s, want in (("-110", -110), ("+110", 110), ("  -115 ", -115), ("100", 100), ("\u2212110", -110),
                        ("+100000", 100000)):
            self.assertEqual(N.strict_price(s), want, s)

    def test_blank_is_none(self):
        for s in ("", "   ", None):
            self.assertIsNone(N.strict_price(s))

    def test_malformed_prices_are_bad_not_silently_repaired(self):
        for s in ("1+10", "+1+10", "110.5", "110.0", "99", "-99", "0", "1e3", "inf", "-inf", "nan", "--110",
                  "1,10", "0x6E", "1_10", "100001", "abc", "\uff11\uff11\uff10x"):
            self.assertEqual(N.strict_price(s), N.BAD, s)

    def test_inf_never_raises(self):
        for s in ("inf", "-inf", "nan", "infinity", "1e999"):
            self.assertEqual(N.strict_price(s), N.BAD)


class Line(unittest.TestCase):
    def test_good_lines(self):
        for s, want in (("-3.5", -3.5), ("+3.5", 3.5), ("144", 144.0), (".5", 0.5), ("0", 0.0), ("\u22123.5", -3.5)):
            self.assertEqual(N.strict_line(s), want, s)

    def test_blank_is_none(self):
        self.assertIsNone(N.strict_line(""))

    def test_non_finite_and_malformed_lines_are_bad(self):
        for s in ("nan", "NaN", "inf", "-inf", "infinity", "1e2", "1e999", "4+4", "2+7", "3.5.1", "--3", "1,5",
                  "1001", "-1001", "abc", "0x10"):
            self.assertEqual(N.strict_line(s), N.BAD, s)

    def test_no_nan_ever_returned(self):
        for s in ("nan", "inf", "1e400"):
            v = N.strict_line(s)
            self.assertFalse(isinstance(v, float) and not math.isfinite(v))


class Identity(unittest.TestCase):
    def k(self, **kw):
        base = dict(game_id="g1", period="FG", market="PLAYER_POINTS", line=19.5)
        base.update(kw)
        return N.quote_identity(**base)

    def test_two_players_same_line_are_distinct(self):
        self.assertNotEqual(self.k(player="Cooper Flagg"), self.k(player="Khaman Maluach"))

    def test_same_player_formatting_is_one_identity(self):
        self.assertEqual(self.k(player="Cooper  Flagg"), self.k(player="cooper flagg "))

    def test_permanent_id_overrides_name_spelling(self):
        self.assertEqual(self.k(player="C. Flagg", player_id="123"), self.k(player="Cooper Flagg", player_id="123"))
        self.assertNotEqual(self.k(player="Cooper Flagg", player_id="123"), self.k(player="Cooper Flagg", player_id="124"))

    def test_game_market_without_player_keeps_old_behaviour(self):
        self.assertEqual(N.quote_identity("g1", "FG", "TOTAL", 144.5), N.quote_identity("g1", "FG", "TOTAL", 144.5))
        self.assertNotEqual(N.quote_identity("g1", "FG", "TOTAL", 144.5), N.quote_identity("g1", "FG", "TOTAL", 145.5))

    def test_name_vs_id_never_collide(self):
        self.assertNotEqual(self.k(player="123"), self.k(player_id="123"))


if __name__ == "__main__":
    unittest.main()
