"""Offline promptfoo contract provider tests; no LLM tokens or network."""
import unittest
from promptfoo.policy_provider import call_api, safe_candidate


GOOD = {"schema": "SPORTSEDGE_RESEARCH_AI_V1", "status": "PAPER / 0u",
        "official": False, "stake_u": 0, "source_authenticated": False}


class PromptfooPolicyTests(unittest.TestCase):
    def test_valid_paper(self):
        self.assertTrue(safe_candidate(GOOD))
        self.assertEqual(call_api("ignored", {}, {"vars": {"candidate": GOOD}})["output"],
                         "PASS")

    def test_unsafe_fields_fail_closed(self):
        for extra in ({"official": True}, {"stake_u": 1},
                      {"source_authenticated": True},
                      {"verified_ev": .1}, {"bet_price": -110},
                      {"official_stars": 5}, {"unit_recommendation": 0.5},
                      {"stake_u": True}):
            with self.subTest(extra=extra):
                self.assertFalse(safe_candidate({**GOOD, **extra}))

    def test_non_json_and_missing_inputs_blocked(self):
        self.assertEqual(call_api("", {}, {"vars": {"candidate": "BROKEN"}})["output"],
                         "BLOCK")
        self.assertEqual(call_api("", {}, {"vars": {}})["output"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
