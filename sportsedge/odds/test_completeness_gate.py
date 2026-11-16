"""Offline, synthetic DK core and all-outcome completeness regressions."""
import unittest
from copy import deepcopy

from sportsedge.odds.completeness_gate import evaluate


def sample():
    event = {"event_id": "NFL-EXAMPLE-1", "sport": "NFL",
             "kickoff_utc": "2026-11-17T01:00:00Z",
             "market_inventory": [], "quotes": [], "exclusions": []}
    for family in ("ML", "SPREAD", "TOTAL"):
        for side in (("HOME", "AWAY") if family != "TOTAL" else ("OVER", "UNDER")):
            line = "" if family == "ML" else ("-3.5" if side == "HOME" and family == "SPREAD" else "+3.5" if family == "SPREAD" else "43.5")
            item = {"book": "DK", "provider_market_id": "v1-" + family,
                    "family": family, "period": "FG", "side": side, "line": line}
            event["market_inventory"].append(item)
            event["quotes"].append({
                **item, "price_american": -110,
                "original_observed_utc": "2026-11-16T21:00:00Z",
                "captured_utc": "2026-11-16T21:00:01Z",
                "source_receipt_sha256": "f"*64,
            })
    return {"schema": "sportsedge-odds-completeness-v1", "events": [event]}


def reasons(archive):
    return {f["reason"] for f in evaluate(archive)["failures"]}


class CompletenessTests(unittest.TestCase):
    def test_all_six_core_sides_present_still_unverified(self):
        z = evaluate(sample())
        self.assertFalse(z["gate_a_authenticated"])
        self.assertEqual(z["status"], "PAPER_0U_COMPLIANT_INVENTORY")
        self.assertEqual(z["approved_stake_u"], 0)

    def test_one_missing_dk_core_side_refused(self):
        s = sample()
        s["events"][0]["quotes"].pop()
        self.assertIn("OFFERED_MARKET_UNACCOUNTED_FOR", reasons(s))

    def test_missing_counterparty_from_catalog_rejected(self):
        s = sample()
        s["events"][0]["market_inventory"].pop()
        s["events"][0]["quotes"].pop()
        self.assertIn("CORE_SIDE_MISSING_WITHOUT_EXCLUSION", reasons(s))

    def test_excluded_core_side_with_clock(self):
        s = sample()
        q = s["events"][0]["quotes"].pop()
        s["events"][0]["exclusions"].append({
            **{k: q[k] for k in ("book", "provider_market_id", "family", "period", "side", "line")},
            "reason": "NO_AUTHORIZED_ACCESS", "noted_at_utc": "2026-11-16T21:00:02Z"})
        z = evaluate(s)
        self.assertEqual(z["failures"], [])
        self.assertFalse(z["gate_a_authenticated"])

    def test_unaccounted_player_outcome(self):
        s = sample()
        s["events"][0]["market_inventory"].append(
            {"book": "DK", "provider_market_id": "prop-1", "family": "PLAYER_PROP",
             "period": "FG", "side": "OVER", "line": "61.5"})
        self.assertIn("OFFERED_MARKET_UNACCOUNTED_FOR", reasons(s))

    def test_original_quote_after_capture_rejected(self):
        s = sample()
        s["events"][0]["quotes"][0]["original_observed_utc"] = "2026-11-16T22:00:00Z"
        self.assertIn("ORIGINAL_TIMESTAMP_AFTER_CAPTURE", reasons(s))

    def test_post_start_quote_rejected(self):
        s = sample()
        s["events"][0]["quotes"][0]["captured_utc"] = "2026-11-17T01:00:00Z"
        self.assertIn("POST_START_QUOTE", reasons(s))

    def test_duplicate_outcome_catalog_flagged(self):
        s = sample()
        s["events"][0]["market_inventory"].append(deepcopy(s["events"][0]["market_inventory"][0]))
        self.assertIn("DUPLICATE_INVENTORY_MARKET", reasons(s))

    def test_conflicting_same_selection_prices_all_copies_quarantined(self):
        s = sample()
        # Two source rows make one alleged offer ambiguous; do not pick first.
        competing = deepcopy(s["events"][0]["quotes"][0])
        competing["price_american"] = -145
        s["events"][0]["quotes"].append(competing)
        result = evaluate(s)
        self.assertEqual(result["status"], "PAPER_0U_INCOMPLETE")
        self.assertIn("DUPLICATE_OR_CONFLICTING_SOURCE_DISPOSITION", reasons(s))
        self.assertIn("OFFERED_MARKET_UNACCOUNTED_FOR", reasons(s))
        self.assertEqual(result["checks"][0]["quote_row_count"], 7)
        self.assertEqual(result["checks"][0]["accounted_count"], 5)
        self.assertEqual(result["approved_stake_u"], 0)

    def test_identical_source_quote_copies_do_not_double_count(self):
        s = sample()
        s["events"][0]["quotes"].append(deepcopy(s["events"][0]["quotes"][0]))
        result = evaluate(s)
        self.assertIn("DUPLICATE_OR_CONFLICTING_SOURCE_DISPOSITION", reasons(s))
        self.assertEqual(result["checks"][0]["accounted_count"], 5)

    def test_quote_and_not_offered_claim_same_market_are_conflicted(self):
        s = sample()
        quote = s["events"][0]["quotes"][0]
        s["events"][0]["exclusions"].append({
            **{k:quote[k] for k in ("book","provider_market_id","family",
                                    "period","side","line")},
            "reason": "NOT_OFFERED", "noted_at_utc": "2026-11-16T21:00:01Z",
        })
        result = evaluate(s)
        self.assertIn("DUPLICATE_OR_CONFLICTING_SOURCE_DISPOSITION", reasons(s))
        self.assertEqual(result["checks"][0]["accounted_count"], 5)

    def test_two_exclusions_for_one_core_outcome_are_conflicted(self):
        s = sample()
        quote = s["events"][0]["quotes"].pop()
        base = {k:quote[k] for k in ("book","provider_market_id","family",
                                      "period","side","line")}
        s["events"][0]["exclusions"].extend([
            {**base,"reason":"NO_PRICE","noted_at_utc":"2026-11-16T21:00:01Z"},
            {**base,"reason":"NOT_CAPTURED","noted_at_utc":"2026-11-16T21:00:02Z"},
        ])
        self.assertIn("DUPLICATE_OR_CONFLICTING_SOURCE_DISPOSITION", reasons(s))
        self.assertEqual(evaluate(s)["checks"][0]["accounted_count"], 5)

    def test_distinct_alternate_lines_do_not_collide(self):
        s = sample()
        original = s["events"][0]["quotes"][0]
        alt = deepcopy(original)
        alt["line"] = "1.5"
        alt["provider_market_id"] = "alternate-rung-1"
        s["events"][0]["quotes"].append(alt)
        s["events"][0]["market_inventory"].append({
            k: alt[k] for k in ("book","provider_market_id","family",
                                "period","side","line")
        })
        report = evaluate(s)
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["checks"][0]["accounted_count"], 7)

    def test_missing_offered_inventory(self):
        s = sample()
        s["events"][0]["market_inventory"] = []
        self.assertIn("OFFERED_MARKET_INVENTORY_MISSING", reasons(s))

    def test_fake_clv_and_official_not_created(self):
        s = sample()
        z = evaluate(s)
        self.assertEqual(z["official_counted"], 0)
        self.assertNotIn("clv", z)


if __name__ == "__main__":
    unittest.main()
