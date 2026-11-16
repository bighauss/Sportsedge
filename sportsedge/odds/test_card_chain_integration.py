"""Offline regression tests: independent chain evidence is never silently trusted."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from sportsedge.odds.card_gate import gate_candidate
from sportsedge.odds.evidence import DualSourceDecision
from sportsedge.odds.independent_chain_contract import ChainHold

NOW = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)

class ChainCardIntegrationTests(unittest.TestCase):
    def run_gate(self, **kw):
        dual = DualSourceDecision("BLOCK", ("UNVERIFIED",), None, None, None)
        return gate_candidate({"rules_version": "not-certified"}, dual, None, None, NOW, **kw)

    def test_missing_chain_is_explicit_block(self):
        result = self.run_gate()
        self.assertIn("INDEPENDENT_CHAIN_EVIDENCE_MISSING", result["reasons"])
        self.assertEqual(result["approved_stake_u"], 0)

    def test_shared_transport_is_first_class_reason(self):
        with patch("sportsedge.odds.card_gate.inspect_independent_chain",
                   side_effect=ChainHold("SHARED_TRANSPORT")) as check:
            result = self.run_gate(chain_primary={}, chain_secondary={})
        check.assert_called_once()
        self.assertIn("INDEPENDENT_CHAIN:SHARED_TRANSPORT", result["reasons"])
        self.assertEqual(result["status"], "BLOCK")

    def test_shared_upstream_is_first_class_reason(self):
        with patch("sportsedge.odds.card_gate.inspect_independent_chain",
                   side_effect=ChainHold("SHARED_UPSTREAM_CHAIN")):
            result = self.run_gate(chain_primary={}, chain_secondary={})
        self.assertIn("INDEPENDENT_CHAIN:SHARED_UPSTREAM_CHAIN", result["reasons"])

    def test_claim_success_never_promotes(self):
        with patch("sportsedge.odds.card_gate.inspect_independent_chain",
                   return_value={"status": "RESEARCH_CHAIN_CLAIMS_ONLY"}):
            result = self.run_gate(chain_primary={}, chain_secondary={})
        self.assertEqual((result["status"], result["official_counted"], result["approved_stake_u"]),
                         ("BLOCK", 0, 0))

if __name__ == "__main__":
    unittest.main()
