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
                        ("+100000", 100000), ("1500", 1500)):
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

    def test_huge_integer_is_bad_and_never_raises(self):
        for s in ("9" * 5000, "1" + "0" * 4400, "-" + "9" * 17):
            self.assertEqual(N.strict_price(s), N.BAD)

    def test_unicode_digits_are_not_folded(self):
        for s in ("\u00b9\u00b9\u2070", "\u2460\u2460\u24ea", "\uff11\uff11\uff10", "\u0661\u0661\u0660", "\u2081\u2081\u2080"):
            self.assertEqual(N.strict_price(s), N.BAD, repr(s))
            self.assertEqual(N.strict_line(s), N.BAD, repr(s))


class Line(unittest.TestCase):
    def test_good_lines(self):
        for s, want in (("-3.5", -3.5), ("+3.5", 3.5), ("144", 144.0), (".5", 0.5), ("0", 0.0), ("\u22123.5", -3.5),
                        ("144.25", 144.25), ("1000", 1000.0), ("1000.000", 1000.0)):
            self.assertEqual(N.strict_line(s), want, s)

    def test_negative_zero_is_normalised(self):
        self.assertEqual(math.copysign(1.0, N.strict_line("-0")), 1.0)

    def test_blank_is_none(self):
        self.assertIsNone(N.strict_line(""))

    def test_non_finite_and_malformed_lines_are_bad(self):
        for s in ("nan", "NaN", "inf", "-inf", "infinity", "1e2", "1e999", "4+4", "2+7", "3.5.1", "--3", "1,5",
                  "1001", "-1001", "abc", "0x10", "1000.001"):
            self.assertEqual(N.strict_line(s), N.BAD, s)

    def test_no_nan_ever_returned(self):
        for s in ("nan", "inf", "1e400"):
            v = N.strict_line(s)
            self.assertFalse(isinstance(v, float) and not math.isfinite(v))

    def test_precision_beyond_a_float_is_rejected_not_rounded(self):
        for s in ("0." + "0" * 400 + "1", "1000.0000000000000001", "144.5000000000000001", "0.0001", "3.14159"):
            self.assertEqual(N.strict_line(s), N.BAD, s)

    def test_distinct_accepted_lines_stay_distinct(self):
        vals = [N.strict_line("%d.%03d" % (a, b)) for a in (0, 1, 143, 144, 999) for b in range(0, 1000, 125)]
        self.assertEqual(len(vals), len(set(vals)))
        self.assertNotEqual(N.strict_line("144.5"), N.strict_line("144.501"))

    def test_overlong_cell_is_bad(self):
        self.assertEqual(N.strict_line("0" * 17), N.BAD)
        self.assertEqual(N.strict_line("1" * 5000), N.BAD)


class Identity(unittest.TestCase):
    def sem(self, **kw):
        base = dict(game_id="g1", period="FG", market="PLAYER_POINTS", line=19.5)
        base.update(kw)
        return N.semantic_identity(**base)

    def test_two_players_same_line_are_distinct(self):
        self.assertNotEqual(self.sem(player="Cooper Flagg"), self.sem(player="Khaman Maluach"))

    def test_same_player_formatting_is_one_identity(self):
        self.assertEqual(self.sem(player="Cooper  Flagg"), self.sem(player="cooper flagg "))

    def test_permanent_id_overrides_name_spelling(self):
        self.assertEqual(self.sem(player="C. Flagg", player_id="123"), self.sem(player="Cooper Flagg", player_id="123"))
        self.assertNotEqual(self.sem(player="Cooper Flagg", player_id="123"), self.sem(player="Cooper Flagg", player_id="124"))

    def test_name_only_identity_is_not_verified(self):
        self.assertFalse(N.player_identity_verified(None))
        self.assertFalse(N.player_identity_verified("  "))
        self.assertTrue(N.player_identity_verified("123"))

    def test_game_market_without_player_keeps_old_behaviour(self):
        self.assertEqual(N.semantic_identity("g1", "FG", "TOTAL", 144.5), N.semantic_identity("g1", "FG", "TOTAL", 144.5))
        self.assertNotEqual(N.semantic_identity("g1", "FG", "TOTAL", 144.5), N.semantic_identity("g1", "FG", "TOTAL", 145.5))

    def test_name_vs_id_never_collide(self):
        self.assertNotEqual(self.sem(player="123"), self.sem(player_id="123"))

    def test_same_bet_with_different_dk_market_ids_is_one_semantic_quote(self):
        a = N.semantic_identity("g1", "FG", "TOTAL", 144.5)
        self.assertEqual(a, N.semantic_identity("g1", "FG", "TOTAL", 144.5))
        pa = N.provider_identity("g1", "FG", "TOTAL", 144.5, dk_event_id="e1", dk_market_id="m1")
        pb = N.provider_identity("g1", "FG", "TOTAL", 144.5, dk_event_id="e1", dk_market_id="m2")
        self.assertNotEqual(pa, pb)
        self.assertEqual(pa[:5], pb[:5])
        self.assertEqual(pa[:5], a)

    def test_provider_identity_keeps_all_provider_ids(self):
        p = N.provider_identity("g1", "FG", "ML", None, dk_event_id=" e1 ", dk_market_id="", dk_selection_a="s1",
                                dk_selection_b="s2")
        self.assertEqual(p[5:], ("e1", None, "s1", "s2"))


if __name__ == "__main__":
    unittest.main()
