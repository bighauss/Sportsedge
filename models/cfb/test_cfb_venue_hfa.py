"""Venue-HFA safeguard regressions for cfb_neutral_strict (issue #432, PR #556)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sportsedge_cfb_model as M
import cfb_neutral_strict as S
import test_cfb_neutral_strict as T


def _ctx_with_venue(**ven):
    ctx = T._ctx()
    ctx["venues"] = {"V": dict(ven)}
    return ctx


class VenueHfa(unittest.TestCase):
    def test_pinned_model_replaces_explicit_zero_with_default(self):
        p = M.run_game(T._game(neutralSite=False), _ctx_with_venue(hfa=0))
        self.assertEqual(p["hfa"], M.HFA_DEFAULT)

    def test_explicit_zero_withheld_when_not_neutral(self):
        for zero in (0, 0.0):
            with self.subTest(zero=zero):
                with self.assertRaisesRegex(S.VenueHfaError, S.HFA_ZERO_REASON):
                    S.run_game_strict(T._game(neutralSite=False), _ctx_with_venue(hfa=zero))

    def test_explicit_zero_allowed_when_neutral(self):
        p = S.run_game_strict(T._game(neutralSite=True), _ctx_with_venue(hfa=0))
        self.assertEqual(p["hfa"], 0.0)

    def test_missing_and_null_use_documented_default(self):
        for ven in ({}, {"hfa": None}):
            with self.subTest(ven=ven):
                p = S.run_game_strict(T._game(neutralSite=False), _ctx_with_venue(**ven))
                self.assertEqual(p["hfa"], M.HFA_DEFAULT)

    def test_positive_value_matches_pinned_model(self):
        a = S.run_game_strict(T._game(neutralSite=False), _ctx_with_venue(hfa=3.0))
        b = M.run_game(T._game(neutralSite=False), _ctx_with_venue(hfa=3.0))
        self.assertEqual(a["hfa"], 3.0)
        for k in ("pts_home", "pts_away", "margin", "total"):
            self.assertEqual(a[k], b[k])

    def test_malformed_negative_nonfinite_withheld(self):
        for bad in ("2.5", "", True, False, [], {}, -1, -0.5, float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=repr(bad)):
                with self.assertRaisesRegex(S.VenueHfaError, S.HFA_INVALID_REASON):
                    S.run_game_strict(T._game(neutralSite=False), _ctx_with_venue(hfa=bad))

    def test_invalid_neutral_flag_still_checked_first(self):
        with self.assertRaises(S.NeutralSiteError):
            S.run_game_strict(T._game(neutralSite="false"), _ctx_with_venue(hfa=0))


if __name__ == "__main__":
    unittest.main()
