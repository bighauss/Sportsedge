"""Synthetic market completeness tests. No DK endpoint or historical prices."""
import unittest
from copy import deepcopy
from datetime import datetime

from sportsedge.odds.completeness_gate import CompletenessError, evaluate


def sample():
    event = {"event_id": "NFL-EXAMPLE-1", "sport": "NFL",
             "kickoff_utc": "2026-11-17T01:00:00Z",
             "market_inventory": [], "quotes": [], "exclusions": []}
    for f in ("ML", "SPREAD", "TOTAL"):
        item = {"book": "DK", "provider_market_id": "v1-" + f, "family": f, "period": "FG"}
        event["market_inventory"].append(item)
        event["quotes"].append({
            **item, "line": "" if f == "ML" else "0",
            "price_american": -110,
            "original_observed_utc": "2026-11-16T21:00:00Z",
            "captured_utc": "2026-11-16T21:00:01Z",
            "source_receipt_sha256": "f"*64,
        })
    return {"schema": "sportsedge-odds-completeness-v1", "events": [event]}


class CompletenessTests(unittest.TestCase):
    def test_all_core_present_still_unverified(self):
        z = evaluate(sample())
        self.assertFalse(z["gate_a_authenticated"])
        self.assertEqual(z["status"], "PAPER_0U_COMPLIANT_INVENTORY")
        self.assertEqual(z["approved_stake_u"], 0)

    def test_core_missing_without_exclusion(self):
        s = sample()
        s["events"][0]["quotes"].pop()
        z = evaluate(s)
        self.assertIn("OFFERED_MARKET_UNACCOUNTED_FOR", {r["reason"] for r in z["failures"]})

    def test_missing_core_catalog_requires_explicit_inventory(self):
        s = sample()
        s["events"][0]["market_inventory"].pop()
        s["events"][0]["quotes"].pop()
        z = evaluate(s)
        self.assertIn("CORE_MARKET_MISSING_WITHOUT_EXCLUSION", {r["reason"] for r in z["failures"]})

    def test_source_inventory_exclusion_is_recorded_not_verified(self):
        s = sample()
        q = s["events"][0]["quotes"].pop()
        s["events"][0]["exclusions"].append({
            **{k: q[k] for k in ("book", "provider_market_id", "family", "period")},
            "reason": "NO_AUTHORIZED_ACCESS", "noted_at_utc": "2026-11-16T21:00:02Z"})
        z = evaluate(s)
        self.assertEqual(z["failures"], [])
        self.assertFalse(z["gate_a_authenticated"])

    def test_offered_player_prop_not_omitted(self):
        s = sample()
        s["events"][0]["market_inventory"].append({"book": "DK", "provider_market_id": "player-1",
                                                     "family": "PLAYER_PROP", "period": "FG"})
        self.assertIn("OFFERED_MARKET_UNACCOUNTED_FOR", {r["reason"] for r in evaluate(s)["failures"]})

    def test_original_quote_after_capture_rejected(self):
        s = sample()
        s["events"][0]["quotes"][0]["original_observed_utc"] = "2026-11-16T22:00:00Z"
        self.assertIn("ORIGINAL_TIMESTAMP_AFTER_CAPTURE", {r["reason"] for r in evaluate(s)["failures"]})

    def test_post_start_quote_rejected(self):
        s = sample()
        s["events"][0]["quotes"][0]["captured_utc"] = "2026-11-17T01:00:00Z"
        self.assertIn("POST_START_QUOTE", {r["reason"] for r in evaluate(s)["failures"]})

    def test_duplicate_market_catalog_flagged(self):
        s = sample()
        s["events"][0]["market_inventory"].append(deepcopy(s["events"][0]["market_inventory"][0]))
        self.assertIn("DUPLICATE_INVENTORY_MARKET", {r["reason"] for r in evaluate(s)["failures"]})

    def test_missing_event_inventory_never_passes(self):
        s = sample()
        s["events"][0]["market_inventory"] = []
        self.assertIn("OFFERED_MARKET_INVENTORY_MISSING", {r["reason"] for r in evaluate(s)["failures"]})

    def test_never_bet(self):
        s = sample()
        self.assertEqual(evaluate(s)["official_counted"], 0)


if __name__ == "__main__":
    unittest.main()
