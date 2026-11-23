"""Synthetic-only tests of the isolated CFB venue HFA research challenger."""
import pathlib
import sys
import unittest

CFB_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CFB_DIR))
from venue_hfa_v2_research import venue_hfa_v2


class VenueHfaV2ResearchRegression(unittest.TestCase):
    def test_explicit_zero(self):
        self.assertEqual(venue_hfa_v2(False, {"hfa": 0}, 2.5), 0.0)

    def test_missing_and_null(self):
        for venue in ({}, {"hfa": None}):
            with self.subTest(venue=venue):
                self.assertEqual(venue_hfa_v2(False, venue, 2.5), 2.5)

    def test_positive_and_clamped(self):
        for value, expected in [(1.25, 1.25), (-1, 0), (9, 4)]:
            with self.subTest(value=value):
                self.assertEqual(venue_hfa_v2(False, {"hfa": value}, 2.5), expected)

    def test_neutral_override(self):
        for venue in ({}, {"hfa": None}, {"hfa": 0}, {"hfa": 3.5}):
            with self.subTest(venue=venue):
                self.assertEqual(venue_hfa_v2(True, venue, 2.5), 0.0)

    def test_invalid_values_fail_closed(self):
        for value in ("nonsense", float("nan"), float("inf"), object()):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    venue_hfa_v2(False, {"hfa": value}, 2.5)

    def test_frozen_model_blob_unchanged(self):
        # Frozen v1 integrity is separately enforced by the repository's hash guard.
        text = (CFB_DIR / "sportsedge_cfb_model.py").read_text(encoding="utf-8")
        self.assertIn('ven.get("hfa") or HFA_DEFAULT', text)


if __name__ == "__main__":
    unittest.main()
