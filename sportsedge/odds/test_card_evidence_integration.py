"""Research card-gate integration must fail closed without evidence."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from sportsedge.odds.card_gate import gate_candidate
from sportsedge.odds.evidence import DualSourceDecision
from research.edge.forward_holdout_contract import Hold

NOW = datetime(2026, 11, 16, 13, tzinfo=timezone.utc)

def run(**kwargs):
    dual = DualSourceDecision("BLOCK", ("UNVERIFIED",), None, None, None)
    return gate_candidate({}, dual, None, None, NOW, **kwargs)

class TestEvidenceIntegration(unittest.TestCase):
    def test_missing_evidence_explicit(self):
        reasons = run()["reasons"]
        self.assertIn("COMPLETENESS_EVIDENCE_MISSING", reasons)
        self.assertIn("FORWARD_HOLDOUT_EVIDENCE_MISSING", reasons)
    def test_invalid_inventory_explicit(self):
        reasons = run(completeness_archive={})["reasons"]
        self.assertTrue(any(x.startswith("COMPLETENESS_INVALID:") for x in reasons))
    def test_invalid_holdout_explicit(self):
        reasons = run(forward_freeze={}, forward_rows=[])["reasons"]
        self.assertTrue(any(x.startswith("FORWARD_HOLDOUT_INVALID:") for x in reasons))
    def test_incomplete_inventory_is_block_reason(self):
        with patch("sportsedge.odds.card_gate.evaluate_completeness",
                   return_value={"status": "PAPER_0U_INCOMPLETE", "failures": ["missing"]}):
            reasons = run(completeness_archive={"dummy": 1})["reasons"]
        self.assertIn("COMPLETENESS_INCOMPLETE", reasons)
    def test_valid_research_evidence_never_promotes(self):
        with patch("sportsedge.odds.card_gate.evaluate_completeness",
                   return_value={"status": "PAPER_0U_COMPLIANT_INVENTORY", "failures": []}), patch(
                   "sportsedge.odds.card_gate.evaluate_forward",
                   return_value={"status": "PAPER_0U_UNATTESTED_FORWARD_RESEARCH"}):
            result = run(completeness_archive={}, forward_freeze={}, forward_rows=[])
        self.assertEqual((result["status"], result["approved_stake_u"], result["official_counted"]),
                         ("BLOCK", 0, 0))

if __name__ == "__main__":
    unittest.main()
