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

    def test_valid_boundaries_and_interior(self):
        for value in (0, 1.25, 4):
            with self.subTest(value=value):
                self.assertEqual(venue_hfa_v2(False, {"hfa": value}, 2.5), value)

    def test_out_of_range_rejected_not_clamped(self):
        for value in (-1, -0.001, 4.001, 9):
            with self.subTest(value=value), self.assertRaises(ValueError):
                venue_hfa_v2(False, {"hfa": value}, 2.5)

    def test_neutral_override(self):
        for venue in ({}, {"hfa": None}, {"hfa": 0}, {"hfa": 3.5}):
            with self.subTest(venue=venue):
                self.assertEqual(venue_hfa_v2(True, venue, 2.5), 0.0)

    def test_invalid_values_fail_closed(self):
        for value in ("nonsense", "2.5", float("nan"), float("inf"), object(), None):
            if value is None:
                continue  # Explicit null is a documented fallback.
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                venue_hfa_v2(False, {"hfa": value}, 2.5)

    def test_boolean_inputs_rejected(self):
        for value in (True, False):
            with self.subTest(hfa=value):
                with self.assertRaises(ValueError):
                    venue_hfa_v2(False, {"hfa": value}, 2.5)
                with self.assertRaises(ValueError):
                    venue_hfa_v2(False, {}, value)

    def test_neutral_flag_requires_boolean(self):
        for value in (0, 1, None, "false", "true"):
            with self.subTest(neutral=value), self.assertRaises(ValueError):
                venue_hfa_v2(value, {"hfa": 2}, 2.5)

    def test_bad_default_always_rejected(self):
        for default in (-1, 9, "2.5", True, float("nan"), float("inf")):
            for neutral in (False, True):
                for venue in ({"hfa": 2}, {}):
                    with self.subTest(default=default, neutral=neutral, venue=venue):
                        with self.assertRaises(ValueError):
                            venue_hfa_v2(neutral, venue, default)

    def test_neutral_does_not_hide_bad_venue(self):
        for venue in ({"hfa": 9}, {"hfa": "2.5"}, {"hfa": float("nan")}, None):
            with self.subTest(venue=venue), self.assertRaises(ValueError):
                venue_hfa_v2(True, venue, 2.5)

    def test_frozen_model_source_remains_unmodified(self):
        # Source guard only; repository's trusted frozen-file SHA gate is authoritative.
        text = (CFB_DIR / "sportsedge_cfb_model.py").read_text(encoding="utf-8")
        self.assertIn('ven.get("hfa") or HFA_DEFAULT', text)


if __name__ == "__main__":
    unittest.main()
