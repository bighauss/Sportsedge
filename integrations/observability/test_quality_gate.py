"""Synthetic quality gate regression tests. Never use a synthetic receipt to promote markets."""
import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
import quality_gate as q

HASH_A = "a"*64
HASH_B = "b"*64
HASH_C = "c"*64


def sample():
    return {
        "sport": "CBB", "event_id": "game-1", "period": "FG",
        "market": "total", "side": "over", "line": "149.5",
        "tipoff_utc": "2026-11-15T19:00:00Z",
        "model": {"sha256": HASH_A,
                  "trained_until_utc": "2026-11-14T21:00:00Z",
                  "freeze_utc": "2026-11-15T17:45:00Z",
                  "probability": 0.58},
        "source": {"sha256": HASH_B, "provider": "public-ratings",
                   "data_through_utc": "2026-11-15T16:00:00Z",
                   "published_utc": "2026-11-15T16:15:00Z",
                   "captured_utc": "2026-11-15T17:00:00Z"},
        "quote": {"sha256": HASH_C, "book": "DraftKings",
                  "captured_utc": "2026-11-15T17:30:00Z",
                  "price_american": -110},
    }


def settled():
    r = sample()
    r["outcome"] = {"result": "W", "settled_utc": "2026-11-16T03:00:00Z"}
    return r


def closing():
    r = settled()
    r["close"] = {
        "sha256": HASH_A, "book": "DraftKings",
        "sport": "CBB", "event_id": "game-1",
        "market": "total", "period": "FG", "side": "over",
        "line": 149.5,
        "captured_utc": "2026-11-15T18:58:00Z",
        "price_american": -125,
    }
    return r


class QualityGateTests(unittest.TestCase):
    def test_unsettled_snapshot_is_research_only(self):
        x = q.inspect([sample()])
        self.assertEqual(x["input_rows"], 1)
        self.assertEqual(x["clock_consistent_rows"], 1)
        self.assertEqual(x["metrics"]["n_decided"], 0)
        self.assertIsNone(x["metrics"]["brier_descriptive_not_forward_certified"])
        self.assertFalse(x["source_authenticated"])
        self.assertFalse(x["official"])
        self.assertEqual(x["stake_u"], 0)

    def test_settlement_brier_and_logloss(self):
        x = q.inspect([settled()])
        self.assertAlmostEqual(x["metrics"]["brier_descriptive_not_forward_certified"], .1764)
        self.assertAlmostEqual(x["metrics"]["log_loss_descriptive_not_forward_certified"],
                               0.5447272, places=5)
        self.assertEqual(x["metrics"]["n_clv_unmatched"], 1)

    def test_matched_same_line_clv_positive_when_close_worse(self):
        x = q.inspect([closing()])
        self.assertEqual(x["metrics"]["n_clv_matched"], 1)
        self.assertGreater(x["metrics"]["clv_prob_gain_same_selection"], 0)
        self.assertEqual(x["blocked_rows"], 0)

    def test_closing_mismatch_is_blocked(self):
        r = closing()
        r["close"]["line"] = "148.5"
        x = q.inspect([r])
        self.assertEqual(x["blocked_rows"], 1)
        self.assertIn("CLOSE_MARKET_IDENTITY_MISMATCH", x["reasons"])

    def test_closing_from_wrong_book_is_blocked(self):
        r = closing()
        r["close"]["book"] = "FanDuel"
        self.assertIn("CLOSE_BOOK_MISMATCH", q.inspect([r])["reasons"])

    def test_future_source_data_blocked(self):
        r = sample()
        r["source"]["published_utc"] = "2026-11-15T19:05:00Z"
        self.assertIn("SOURCE_LOOKAHEAD_OR_CLOCK_ORDER", q.inspect([r])["reasons"])

    def test_future_quote_blocked(self):
        r = sample()
        r["quote"]["captured_utc"] = "2026-11-15T18:00:00Z"
        self.assertIn("QUOTE_AFTER_FREEZE_OR_TIPOFF", q.inspect([r])["reasons"])

    def test_model_training_leak_blocked(self):
        r = sample()
        r["model"]["trained_until_utc"] = r["model"]["freeze_utc"]
        self.assertIn("MODEL_FIT_FREEZE_TIPOFF_ORDER", q.inspect([r])["reasons"])

    def test_missing_source_hash_is_blocked(self):
        r = sample()
        r["source"]["sha256"] = "hi"
        x = q.inspect([r])
        self.assertIn("source:INVALID_SHA256", x["reasons"])

    def test_unbound_player_prop_blocked(self):
        r = sample()
        r.update(market="player_prop:points", line=20.5)
        self.assertIn("UNBOUND_SUBJECT_ID", q.inspect([r])["reasons"])

    def test_repeated_decisions_all_quarantined(self):
        a, b = settled(), settled()
        b["quote"]["captured_utc"] = "2026-11-15T17:31:00Z"
        b["quote"]["price_american"] = -112
        x = q.inspect([a,b])
        self.assertEqual(x["clock_consistent_rows"], 0)
        self.assertEqual(x["blocked_rows"], 2)
        self.assertEqual(x["reasons"]["DUPLICATE_SELECTION_ALL_COPIES_QUARANTINED"], 2)
        self.assertEqual(x["metrics"]["n_decided"], 0)

    def test_different_alt_lines_are_not_duplicates(self):
        a,b=sample(),sample()
        b["line"] = "151.5"
        x=q.inspect([a,b])
        self.assertEqual(x["clock_consistent_rows"],2)

    def test_same_line_different_subject_is_not_duplicate(self):
        a,b=sample(),sample()
        a.update(market="player_prop:points",subject_id="player-1",line=19.5)
        b.update(market="player_prop:points",subject_id="player-2",line=19.5)
        self.assertEqual(q.inspect([a,b])["clock_consistent_rows"],2)

    def test_settlement_before_tipoff_blocked(self):
        r=settled()
        r["outcome"]["settled_utc"]="2026-11-15T18:00:00Z"
        self.assertIn("OUTCOME_BEFORE_END",q.inspect([r])["reasons"])

    def test_poisoned_probability_blocked(self):
        for invalid in (True,"nan",0,1,1.2):
            with self.subTest(invalid=invalid):
                r=sample()
                r["model"]["probability"]=invalid
                self.assertEqual(q.inspect([r])["blocked_rows"],1)

    def test_bad_and_good_both_preserved_in_report(self):
        bad=sample()
        bad["quote"]["price_american"]=-50
        out=q.inspect([bad,settled()])
        self.assertEqual(out["input_rows"],2)
        self.assertEqual(len(out["rows"]),2)
        self.assertEqual(out["blocked_rows"],1)
        self.assertEqual(out["clock_consistent_rows"],1)
        self.assertNotIn("game-1",json.dumps(out))

    def test_private_cli_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/"input.jsonl"
            dest=Path(tmp)/"report.json"
            src.write_text(json.dumps(sample())+"\n")
            q.run_cli(["--input",str(src),"--out",str(dest)])
            self.assertEqual(json.loads(dest.read_text())["stake_u"],0)
            with self.assertRaises(SystemExit):
                q.run_cli(["--input",str(src),"--out",str(dest)])


if __name__ == "__main__":
    unittest.main()
