"""Synthetic tests for PGA research-only market receipt admission."""
import unittest
from market_preflight import preflight, MARKETS

def row(**kw):
    x = dict(event_id="tournament-1", player_id="pga-1", market="outright",
             source="SYNTHETIC", captured_utc="2026-11-15T12:00:00Z",
             start_utc="2026-11-16T12:00:00Z", odds_american="+2500",
             line="0", side="yes", round="tournament", source_hash="a"*64)
    x.update(kw)
    return x

class TestPgaPreflight(unittest.TestCase):
    def test_valid_is_not_a_bet(self):
        r=preflight([row()])
        self.assertEqual(len(r["accepted"]),1)
        self.assertEqual(r["betting_status"],"PAPER_0U")
        self.assertEqual(r["model_status"],"NO_VALIDATED_PGA_MODEL")
    def test_all_markets_admitted(self):
        r=preflight([row(market=m) for m in sorted(MARKETS)])
        self.assertEqual(len(r["accepted"]),len(MARKETS))
    def test_future_capture_blocked(self):
        self.assertIn("NOT_PRESTART",preflight([row(captured_utc="2026-11-17T12:00:00Z")])["blocked"][0]["reasons"])
    def test_missing_receipt_blocked(self):
        self.assertIn("INVALID_SOURCE_HASH",preflight([row(source_hash="bad")])["blocked"][0]["reasons"])
    def test_bad_price_and_line(self):
        r=preflight([row(odds_american="0",line="nan")])
        self.assertEqual(set(r["blocked"][0]["reasons"]),{"INVALID_ODDS","INVALID_LINE"})
    def test_unsupported_market_blocked(self):
        self.assertIn("UNKNOWN_MARKET",preflight([row(market="imaginary")])["blocked"][0]["reasons"])
    def test_retains_all_blocked(self):
        r=preflight([row(market="fake"),row(odds_american="bad")])
        self.assertEqual(len(r["blocked"]),2)
    def test_missing_and_malformed(self):
        self.assertEqual(len(preflight([None,{},row(captured_utc="2026-11-15T12:00:00")])["blocked"]),3)

if __name__=="__main__":
    unittest.main()
