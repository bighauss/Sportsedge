"""Synthetic orchestration tests; mocked pricing is not model validation."""
import json
import unittest
from unittest.mock import patch
import nfl_beta_slate_handoff as h

NOW = "2026-11-22T13:02:00Z"


def package(event="e", model=True):
    quotes = dict(source="DraftKings", captured_at_utc="2026-11-22T13:01:00Z",
                  offers=[dict(event_id=event, quote_id="q", kind="XPLUS")])
    value = dict(event_id=event, quote_bytes=json.dumps(quotes).encode())
    if model:
        value["model_bytes"] = json.dumps(dict(event_id=event)).encode()
    return value


def priced():
    return dict(rows=[dict(event_id="e", offer_id="q", status="PAPER_HOLD_0U",
                          stake_u=0, beta_probability=0.5, beta_ev=0.1)])


class HandoffTests(unittest.TestCase):
    def run_slate(self, packages, expected=None):
        return h.run_slate(["e"] if expected is None else expected, packages, decision_utc=NOW)

    def test_all_twelve_games_remain_visible(self):
        result = self.run_slate([], [str(i) for i in range(12)])
        self.assertEqual(len(result["games"]), 12)
        self.assertEqual(result["official_bets"], 0)
        self.assertTrue(all(g["reasons"] == ["NO_PRICE_PACKAGE"] for g in result["games"]))

    def test_quotes_without_model_preserve_denominator(self):
        game = self.run_slate([package(model=False)])["games"][0]
        self.assertEqual(game["attempted_quotes"], 1)
        self.assertEqual(len(game["rows"]), 1)
        self.assertIn("NO_MODEL_PACKAGE", game["reasons"])
        self.assertIsNone(game["model_confidence"])

    def test_duplicate_and_extra_events_rejected(self):
        for values in ([package(), package()], [package("extra")]):
            with self.assertRaises(ValueError):
                self.run_slate(values)

    def test_wrong_model_event_never_calls_pricer(self):
        p = package(); p["model_bytes"] = b'{"event_id":"wrong"}'
        with patch.object(h, "_ingest") as mocked:
            self.assertIn("INVALID_EVIDENCE_OR_PRICER_RESULT", self.run_slate([p])["games"][0]["reasons"])
            mocked.assert_not_called()

    def test_duplicate_json_keys_rejected(self):
        p = package(); p["quote_bytes"] = b'{"source":"DraftKings","source":"other"}'
        self.assertIn("INVALID_EVIDENCE_OR_PRICER_RESULT", self.run_slate([p])["games"][0]["reasons"])

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            h._decode(b'{"value":NaN}')

    def test_pricer_exception_preserves_offers(self):
        with patch.object(h, "_ingest", side_effect=ValueError("STALE_CAPTURE")):
            game = self.run_slate([package()])["games"][0]
        self.assertEqual(len(game["rows"]), 1)
        self.assertIsNone(game["rows"][0]["beta_probability"])

    def test_valid_handoff_keeps_estimate_not_confidence(self):
        with patch.object(h, "_ingest", return_value=priced()):
            game = self.run_slate([package()])["games"][0]
        self.assertEqual(game["rows"][0]["beta_probability"], 0.5)
        self.assertIsNone(game["model_confidence"])
        self.assertEqual(game["stake_u"], 0)

    def test_pricer_cannot_drop_rows(self):
        with patch.object(h, "_ingest", return_value={"rows": []}):
            game = self.run_slate([package()])["games"][0]
        self.assertEqual(len(game["rows"]), 1)
        self.assertIn("INVALID_EVIDENCE_OR_PRICER_RESULT", game["reasons"])

    def test_pricer_cannot_promote_or_swap_identity(self):
        for field, value in (("stake_u", 1), ("stake_u", False), ("status", "OFFICIAL"), ("event_id", "other"), ("offer_id", "other")):
            result = priced(); result["rows"][0][field] = value
            with patch.object(h, "_ingest", return_value=result):
                game = self.run_slate([package()])["games"][0]
            self.assertIsNone(game["rows"][0]["beta_probability"])

    def test_naive_decision_rejected(self):
        with self.assertRaises(ValueError):
            h.run_slate(["e"], [], decision_utc="2026-11-22T13:00:00")

    def test_empty_offers_are_not_coverage(self):
        p = package(); q = json.loads(p["quote_bytes"]); q["offers"] = []
        p["quote_bytes"] = json.dumps(q).encode()
        self.assertIn("NO_OFFERS", self.run_slate([p])["games"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
