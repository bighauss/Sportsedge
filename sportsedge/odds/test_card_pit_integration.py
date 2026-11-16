"""Gate B card preflight stays fail-closed on empty PIT evidence."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from sportsedge.odds.card_gate import gate_candidate
from sportsedge.odds.evidence import DualSourceDecision, PITBinding

NOW = datetime(2026, 11, 16, 13, tzinfo=timezone.utc)
DUAL = DualSourceDecision("BLOCK", ("UNVERIFIED",), None, None, None)

class TestPitCardGate(unittest.TestCase):
    def test_empty_pit_package_is_explicitly_blocked(self):
        pit = PITBinding(features=(), required_features=frozenset(), freeze_at_utc=NOW)
        result = gate_candidate({}, DUAL, pit, None, NOW)
        self.assertIn("PIT_REQUIRED_FEATURE_SET_EMPTY", result["reasons"])
        self.assertIn("PIT_FEATURE_SNAPSHOTS_EMPTY", result["reasons"])
        self.assertIn("PIT_PRIMARY_QUOTE_UNAVAILABLE", result["reasons"])
        self.assertEqual((result["status"],result["approved_stake_u"],result["official_counted"]), ("BLOCK",0,0))

    def test_secondary_feature_lookahead_surfaces(self):
        pit = PITBinding(features=(), required_features=frozenset({"lineups"}), freeze_at_utc=NOW)
        with patch.object(PITBinding, "check", return_value=("FEATURE_LOOKAHEAD:lineups",)) as check:
            result = gate_candidate({}, DUAL, pit, None, NOW, secondary=object())
        check.assert_called_once()
        self.assertIn("SECONDARY_FEATURE_LOOKAHEAD:lineups", result["reasons"])

if __name__ == "__main__":
    unittest.main()
