"""Synthetic-only contract tests."""
import csv
import tempfile
import unittest
from pathlib import Path
from board_receipt_contract_r4 import validate

BASE = dict(sport="NFL", event_id="evt-1", event_start_utc="2026-11-15T18:00:00Z",
            captured_utc="2026-11-15T16:00:00Z", book="DK", market="ML",
            period="FG", side="home", line="", price_american="+120",
            provider_quote_id="quote-1", receipt_sha256="a"*64,
            source_url="https://example.org/receipt")
FIELDS = list(BASE)

class ContractTests(unittest.TestCase):
    def run_rows(self, rows):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"board.csv"
            with p.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            return validate(p)
    def test_clean_still_blocked(self):
        r = self.run_rows([BASE])
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["status"], "BLOCK")
        self.assertEqual(r["approved_stake_u"], 0)
    def test_duplicate_selection(self):
        second = dict(BASE, provider_quote_id="quote-2")
        r = self.run_rows([BASE, second])
        self.assertIn("DUPLICATE_SELECTION_SNAPSHOT", r["errors"][-1]["reasons"])
    def test_two_sides_allowed(self):
        second = dict(BASE, side="away", provider_quote_id="quote-2")
        self.assertEqual(self.run_rows([BASE, second])["errors"], [])
    def test_reused_quote(self):
        second = dict(BASE, side="away")
        self.assertIn("REUSED_PROVIDER_QUOTE_ID", self.run_rows([BASE, second])["errors"][-1]["reasons"])
    def test_same_quote_other_book(self):
        second = dict(BASE, side="away", book="OTHER")
        self.assertEqual(self.run_rows([BASE, second])["errors"], [])
    def test_conflicting_start(self):
        second = dict(BASE, event_start_utc="2026-11-15T19:00:00Z", side="away", provider_quote_id="quote-2")
        self.assertIn("CONFLICTING_EVENT_START", self.run_rows([BASE, second])["errors"][-1]["reasons"])
    def test_post_start(self):
        row = dict(BASE, captured_utc="2026-11-15T19:00:00Z")
        self.assertIn("POST_START_CAPTURE", self.run_rows([row])["errors"][0]["reasons"])
    def test_invalid_price(self):
        row = dict(BASE, price_american="120")
        self.assertIn("INVALID_AMERICAN_PRICE", self.run_rows([row])["errors"][0]["reasons"])
    def test_invalid_receipt_hash(self):
        row = dict(BASE, receipt_sha256="not-a-hash")
        self.assertIn("INVALID_RECEIPT_HASH", self.run_rows([row])["errors"][0]["reasons"])
    def test_rematch_other_event(self):
        second = dict(BASE, event_id="evt-2", provider_quote_id="quote-2")
        self.assertEqual(self.run_rows([BASE, second])["errors"], [])

if __name__ == "__main__":
    unittest.main()
