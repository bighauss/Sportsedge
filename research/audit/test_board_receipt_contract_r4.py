"""Synthetic-only contract tests."""
import csv
import tempfile
import unittest
from pathlib import Path
from research.audit.board_receipt_contract_r4 import validate

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
                fields=FIELDS+sorted({key for row in rows for key in row}-set(FIELDS))
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            return validate(p)
    def test_clean_still_blocked(self):
        r = self.run_rows([BASE])
        self.assertIn("UNMATCHED_TWO_SIDED_BOOK_OFFER", self._flatten(r))
        self.assertFalse(r["structural_ok"])
        self.assertEqual(r["status"], "BLOCK")
        self.assertEqual(r["approved_stake_u"], 0)
    def test_duplicate_selection(self):
        second = dict(BASE, provider_quote_id="quote-2")
        r = self.run_rows([BASE, second])
        self.assertIn("DUPLICATE_SELECTION_SNAPSHOT", r["errors"][-1]["reasons"])
    def test_two_sides_allowed(self):
        second = dict(BASE, side="away", price_american="-140", provider_quote_id="quote-2")
        self.assertEqual(self.run_rows([BASE, second])["errors"], [])
    def test_reused_quote(self):
        second = dict(BASE, side="away")
        self.assertIn("REUSED_PROVIDER_QUOTE_ID", self.run_rows([BASE, second])["errors"][-1]["reasons"])
    def test_same_quote_other_book(self):
        second = dict(BASE, side="away", book="OTHER")
        self.assertNotIn("REUSED_PROVIDER_QUOTE_ID",self._flatten(self.run_rows([BASE, second])))
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
    def test_casefold_duplicate_header_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"dupe.csv"
            path.write_text(",".join(FIELDS+["Book"])+"\n"+",".join(str(v) for v in BASE.values())+",DK\n")
            self.assertIn("DUPLICATE_CSV_HEADERS",self._invalid(path))

    def _invalid(self,path):
        return self._flatten(validate(path))

    @staticmethod
    def _flatten(report):
        return ",".join(",".join(e.get("reasons",[])) for e in report["errors"])

    def test_numeric_line_equivalent_is_duplicate(self):
        a=dict(BASE,market="SPREAD",side="home",line="-3.50")
        b=dict(a,provider_quote_id="q2",line="-3.5")
        self.assertIn("DUPLICATE_SELECTION_SNAPSHOT",
                      self._flatten(self.run_rows([a,b])))

    def test_ml_zero_is_duplicate_empty_line(self):
        a=dict(BASE,line="")
        b=dict(a,provider_quote_id="q2",line="0")
        self.assertIn("DUPLICATE_SELECTION_SNAPSHOT",
                      self._flatten(self.run_rows([a,b])))

    def test_distinct_player_props_same_market_not_conflated(self):
        a=dict(BASE,market="PLAYER_PROP",side="over",line="10.5",
               player_id="P1",stat="RECEPTIONS")
        b=dict(a,player_id="P2",provider_quote_id="q2")
        self.assertNotIn("CANONICAL_DUPLICATE_SELECTION",self._flatten(self.run_rows([a,b])))

    def test_player_prop_requires_player_and_stat(self):
        a=dict(BASE,market="PLAYER_PROP",side="over",line="10.5")
        r=self.run_rows([a])
        self.assertIn("PLAYER_ID_REQUIRED",self._flatten(r))
        self.assertIn("PLAYER_PROP_STAT_REQUIRED",self._flatten(r))

    def test_team_total_requires_team_identity(self):
        a=dict(BASE,market="TEAM_TOTAL",side="over",line="25.5")
        self.assertIn("TEAM_TOTAL_ID_REQUIRED",
                      self._flatten(self.run_rows([a])))

    def test_bad_numeric_line_refused(self):
        a=dict(BASE,market="SPREAD",line="NaN")
        self.assertIn("INVALID_NUMERIC_LINE",
                      self._flatten(self.run_rows([a])))

    def test_categorical_nonzero_line_refused(self):
        a=dict(BASE,market="ATTD",side="yes",line="1.5",player_id="P1")
        self.assertIn("CATEGORICAL_MARKET_HAS_LINE",
                      self._flatten(self.run_rows([a])))

    def test_incorrect_side_for_market_refused(self):
        a=dict(BASE,market="ML",side="over")
        self.assertIn("MARKET_SIDE_MISMATCH",
                      self._flatten(self.run_rows([a])))

    def test_normalized_utc_capture_timestamps_duplicate(self):
        a=dict(BASE,captured_utc="2026-11-15T16:00:00Z")
        b=dict(a,provider_quote_id="q2",
               captured_utc="2026-11-15T10:00:00-06:00")
        self.assertIn("DUPLICATE_SELECTION_SNAPSHOT",
                      self._flatten(self.run_rows([a,b])))

    def test_valid_different_books_with_same_quote_id(self):
        a=dict(BASE)
        b=dict(a,book="Pinnacle")
        self.assertEqual(self.run_rows([a,b])["errors"],[])

    def test_invalid_http_and_credential_url_refused(self):
        for url in ("http://provider.example/quote",
                    "https://user:password@provider.example/quote"):
            with self.subTest(url=url):
                self.assertIn("INVALID_SOURCE_URL",self._flatten(
                    self.run_rows([dict(BASE,source_url=url)])))

    def test_naive_datetime_refused(self):
        a=dict(BASE,captured_utc="2026-11-15T16:00:00")
        self.assertIn("INVALID_TIMESTAMP",
                      self._flatten(self.run_rows([a])))

    def test_ragged_row_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bad.csv"
            p.write_text(",".join(FIELDS)+"\n"+"NFL\n")
            self.assertIn("RAGGED_CSV_ROW",self._invalid(p))

    def test_no_externally_authenticated_source_even_if_all_valid(self):
        r=self.run_rows([BASE])
        self.assertEqual(r["status"],"BLOCK")
        self.assertEqual(r["official_counted"],0)
        self.assertFalse(r["source_authenticated"])
        self.assertFalse(r["bookmaker_independence_authenticated"])

    def test_unregistered_extra_sensitive_field_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"sensitive.csv"
            with p.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS+["api_key"])
                w.writeheader()
                w.writerow({**BASE,"api_key":"secret"})
            self.assertIn("UNREGISTERED_OR_SECRET_CSV_COLUMN",
                          self._invalid(p))

    def test_rematch_other_event(self):
        second = dict(BASE, event_id="evt-2", provider_quote_id="quote-2")
        self.assertNotIn("CANONICAL_DUPLICATE_SELECTION",self._flatten(self.run_rows([BASE, second])))


    def test_r4_now_blocks_lone_home_side(self):
        r=self.run_rows([BASE])
        self.assertFalse(r["structural_ok"])
        self.assertEqual(r["structural_rows_clean"],0)
        self.assertIn("UNMATCHED_TWO_SIDED_BOOK_OFFER",self._flatten(r))

    def test_r4_rejects_same_sign_spread(self):
        a=dict(BASE, market="SPREAD", line="-3.5",price_american="-110")
        b=dict(a,side="away",provider_quote_id="q2")
        self.assertIn("UNMATCHED_TWO_SIDED_BOOK_OFFER", self._flatten(self.run_rows([a,b])))

    def test_r4_accepts_canonical_opposite_spread(self):
        a=dict(BASE,market="SPREAD",line="-3.5",price_american="-110")
        b=dict(a,side="away",line="+3.5",provider_quote_id="q2")
        r=self.run_rows([a,b])
        self.assertEqual(r["errors"],[])
        self.assertEqual(r["structural_rows_clean"],2)
        self.assertTrue(r["structural_ok"])
        self.assertFalse(r["source_authenticated"])

    def test_r4_rejects_negative_total_and_unicode_line(self):
        a=dict(BASE,market="TOTAL",side="over",line="-2.5")
        self.assertIn("NEGATIVE_NON_SPREAD_LINE",self._flatten(self.run_rows([a])))
        a=dict(BASE,market="SPREAD",line="３.５")
        self.assertIn("NON_ASCII_OR_INVALID_NUMERIC_LINE",self._flatten(self.run_rows([a])))

    def test_r4_rejects_book_alias_duplicate_quote(self):
        a=dict(BASE,side="home",book="DK")
        b=dict(a,side="away",book="DraftKings",provider_quote_id=a["provider_quote_id"])
        self.assertIn("REUSED_CANONICAL_BOOK_QUOTE_ID",self._flatten(self.run_rows([a,b])))

    def test_r4_distinguishes_player_ladders_and_names(self):
        a=dict(BASE,market="PLAYER_PROP",player_id="P1",stat="PASS_YDS",
               side="over",line="249.5",price_american="-110")
        b=dict(a,side="under",provider_quote_id="u1")
        cc=dict(a,line="274.5",provider_quote_id="o2")
        d=dict(cc,side="under",provider_quote_id="u2")
        self.assertTrue(self.run_rows([a,b,cc,d])["structural_ok"])
        e=dict(a,player_id="p1",provider_quote_id="another")
        self.assertIn("CANONICAL_DUPLICATE_SELECTION",self._flatten(self.run_rows([a,e])))

    def test_r4_declared_same_book_underround_flag(self):
        a=dict(BASE,price_american="+150")
        b=dict(a,side="away",provider_quote_id="q2")
        self.assertIn("SUSPICIOUS_SAME_BOOK_OVERROUND_REVIEW",
                      self._flatten(self.run_rows([a,b])))

if __name__ == "__main__":
    unittest.main()
