"""CFB neutral-status admission: no bool(None) conversion to home-field."""
from __future__ import annotations

import copy
from datetime import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfb_run_it as R
import test_cfb_run_it as fixtures

NOW = datetime.fromisoformat("2026-11-21T17:00:00+00:00")


class NeutralSiteGuard(unittest.TestCase):
    def test_missing_rejected(self):
        with self.assertRaisesRegex(R.Fail, "neutralSite"):
            R.require_cfbd_neutral_flag({})

    def test_null_rejected(self):
        with self.assertRaisesRegex(R.Fail, "neutralSite"):
            R.require_cfbd_neutral_flag({"neutralSite": None})

    def test_string_false_rejected(self):
        with self.assertRaisesRegex(R.Fail, "neutralSite"):
            R.require_cfbd_neutral_flag({"neutralSite": "false"})

    def test_integer_zero_rejected(self):
        with self.assertRaisesRegex(R.Fail, "neutralSite"):
            R.require_cfbd_neutral_flag({"neutralSite": 0})

    def test_explicit_true(self):
        self.assertIs(R.require_cfbd_neutral_flag({"neutralSite": True}), True)

    def test_explicit_false(self):
        self.assertIs(R.require_cfbd_neutral_flag({"neutralSite": False}), False)

    def test_unknown_prevents_weather_call_and_projection(self):
        for bad in (None, "false", 0):
            with self.subTest(bad=bad):
                cap = fixtures.fixture()
                cap["games"][0]["neutralSite"] = bad
                called = []
                def weather(*args):
                    called.append(args)
                    return cap["_weather"]
                _, projs, withheld, _ = R.run(
                    copy.deepcopy(fixtures.INTAKE), cap, NOW, weather
                )
                self.assertFalse(projs)
                self.assertFalse(called)
                self.assertIn("CFBD neutralSite missing or not boolean",
                              " | ".join(reason for _, reason in withheld))

    def test_missing_flag_cannot_appear_as_non_neutral(self):
        cap = fixtures.fixture()
        cap["games"][0].pop("neutralSite")
        _, projs, withheld, _ = R.run(
            copy.deepcopy(fixtures.INTAKE), cap, NOW, lambda *_: cap["_weather"]
        )
        self.assertFalse(projs)
        self.assertIn("CFBD neutralSite missing or not boolean",
                      " | ".join(reason for _, reason in withheld))

    def test_true_neutral_zero_hfa(self):
        cap = fixtures.fixture()
        cap["games"][0]["neutralSite"] = True
        _, projs, _, _ = R.run(copy.deepcopy(fixtures.INTAKE), cap, NOW,
                               lambda *_: cap["_weather"])
        self.assertEqual(len(projs), 1)
        self.assertEqual(projs[0]["hfa"], 0.0)


if __name__ == "__main__":
    unittest.main()
