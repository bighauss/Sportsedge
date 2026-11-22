"""Synthetic audit regressions; not evidence of source authenticity or edge."""
import hashlib
import json
import unittest
from research.nfl_beta_last_four import price_beta
from research.nfl_beta_calibration_audit import audit, freeze_predictions


def offer(kind="XPLUS", **extra):
    row = dict(event_id="e", book="DraftKings", quote_id="q", kind=kind,
               player_id="p", stat="rec_yds", threshold=50,
               captured_at_utc="2026-11-22T13:01:00Z",
               model_asof_utc="2026-11-22T13:00:00Z",
               kickoff_utc="2026-11-22T14:00:00Z",
               source_sha256="sha256:" + "a" * 64,
               model_sha256="sha256:" + "b" * 64,
               odds_american=150, joint_simulation=True)
    row.update(extra)
    return row


def sims():
    return [dict(event_id="e", players={"p": {"rec_yds": 60 if i % 2 else 20}},
                 ordered_touchdowns=["p"] if i % 4 == 0 else ["other"])
            for i in range(1000)]


def price(rows=None, samples=None):
    return price_beta(sims() if samples is None else samples,
                      [offer()] if rows is None else rows,
                      decision_utc="2026-11-22T13:02:00Z")


class HardeningTests(unittest.TestCase):
    def test_strict_joint_attestation(self):
        for bad in ("false", "true", 1, 0, [], {}, None, False):
            with self.subTest(value=bad):
                row = price([offer("SGP", joint_simulation=bad)])["rows"][0]
                self.assertIsNone(row["beta_probability"])
                self.assertIn("JOINT_SIMULATION_NOT_ATTESTED", row["reasons"])

    def test_invalid_legs_fail_closed(self):
        for leg in (None, [], "bad", 1, {"kind": []}):
            with self.subTest(leg=leg):
                row = price([offer("SGP", legs=[leg, {"kind": "FIRST_TD", "player_id": "p"}])])["rows"][0]
                self.assertIsNone(row["beta_probability"])
                self.assertIn("INCOMPLETE_OR_INVALID_JOINT_SCENARIOS", row["reasons"])

    def test_invalid_scenarios_fail_closed(self):
        for bad in (None, [], "bad", 1):
            ss = sims(); ss[0] = bad
            self.assertIsNone(price(samples=ss)["rows"][0]["beta_probability"])

    def test_invalid_players_fail_closed(self):
        for bad in (None, [], "bad", 1):
            ss = sims(); ss[0]["players"] = bad
            self.assertIsNone(price(samples=ss)["rows"][0]["beta_probability"])

    def test_zero_odds_rejected_without_division_error(self):
        self.assertIn("PRICE_INVALID", price([offer(odds_american=0)])["rows"][0]["reasons"])

    def test_valid_probabilities_unchanged(self):
        legs = [{"kind": "XPLUS", "player_id": "p", "stat": "rec_yds", "threshold": 10},
                {"kind": "FIRST_TD", "player_id": "p"}]
        rows = price([offer(), offer("FIRST_TD", quote_id="f"), offer("SGP", quote_id="s", legs=legs)])["rows"]
        self.assertEqual([r["beta_probability"] for r in rows], [0.5, 0.25, 0.25])
        self.assertTrue(all(r["stake_u"] == 0 for r in rows))

    def test_freeze_roundtrip_preserves_exact_offer(self):
        result = price()
        records, receipt = freeze_predictions(result, frozen_at_utc="2026-11-22T13:03:00Z")
        self.assertEqual(records[0]["offer"], offer())
        self.assertEqual(records[0]["receipt_sha256"], "sha256:" + hashlib.sha256(receipt).hexdigest())
        self.assertEqual(json.loads(receipt)["predictions"][0]["prediction_id"], records[0]["prediction_id"])
        result["rows"][0]["offer"]["threshold"] = 999
        self.assertEqual(records[0]["offer"]["threshold"], 50)
        report = audit(records, [{"prediction_id": records[0]["prediction_id"], "result": 1}])
        self.assertFalse(report["families"]["XPLUS"]["validated"])
        self.assertEqual(report["families"]["XPLUS"]["baseline_scope"], "IN_SAMPLE_DESCRIPTIVE_NOT_PROSPECTIVE")
        self.assertIsNone(report["families"]["XPLUS"]["prospective_baseline_brier"])

    def test_late_and_predecision_freezes_rejected(self):
        for stamp in ("2026-11-22T14:00:00Z", "2026-11-22T13:01:00Z"):
            with self.assertRaises(ValueError):
                freeze_predictions(price(), frozen_at_utc=stamp)

    def test_boolean_outcomes_rejected(self):
        for bad in (True, False, 1.0, "1"):
            with self.assertRaises(ValueError):
                audit([], [{"prediction_id": "a", "result": bad}])

    def test_orphan_outcomes_rejected(self):
        with self.assertRaisesRegex(ValueError, "ORPHAN_OUTCOME"):
            audit([], [{"prediction_id": "a", "result": 1}])

    def test_malformed_ledgers_rejected(self):
        for predictions, outcomes in (([None], []), ([], [None]), ([{"prediction_id": []}], [])):
            with self.assertRaises(ValueError):
                audit(predictions, outcomes)

    def test_duplicate_freeze_rejected(self):
        result = price(); result["rows"].append(result["rows"][0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PREDICTION"):
            freeze_predictions(result, frozen_at_utc="2026-11-22T13:03:00Z")


if __name__ == "__main__":
    unittest.main()
