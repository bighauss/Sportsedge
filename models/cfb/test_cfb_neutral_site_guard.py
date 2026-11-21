"""CFBD neutral-site classification must be explicit and correctly typed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sportsedge_cfb_model import checked_neutral_site


class NeutralSiteTests(unittest.TestCase):
    def test_missing_rejected(self):
        with self.assertRaisesRegex(ValueError, "neutralSite"):
            checked_neutral_site({})

    def test_null_rejected(self):
        with self.assertRaisesRegex(ValueError, "neutralSite"):
            checked_neutral_site({"neutralSite": None})

    def test_string_false_rejected(self):
        with self.assertRaisesRegex(ValueError, "neutralSite"):
            checked_neutral_site({"neutralSite": "false"})

    def test_integer_rejected(self):
        with self.assertRaisesRegex(ValueError, "neutralSite"):
            checked_neutral_site({"neutralSite": 0})

    def test_explicit_true(self):
        self.assertIs(checked_neutral_site({"neutralSite": True}), True)

    def test_explicit_false(self):
        self.assertIs(checked_neutral_site({"neutralSite": False}), False)


if __name__ == "__main__":
    unittest.main()
