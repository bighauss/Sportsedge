"""Synthetic converter tests: do not infer pregame model/market evidence."""
import unittest

from audit_disagreement_calibration import audit
from ledger_grades_to_audit_csv import convert


class ConverterTests(unittest.TestCase):
    def test_explicit_results_and_blocks(self):
        md = """## NFL
| Play | Odds | Result |
|---|---|---|
| Jets ML | +350 | LOSS (12-31) |
| Browns ML | −185 | WIN (27-24) |
| Sample rush yds | -110 | LIKELY LOSS (team total) inferred |
| Under 19.5 | -108 | UNGRADED |
"""
        rows = convert(md)
        self.assertEqual(len(rows), 4)
        self.assertEqual([x["outcome"] for x in rows], ["0", "1", "UNVERIFIED", "UNVERIFIED"])
        self.assertEqual(rows[1]["odds"], "-185")
        self.assertTrue(all(r["model_p"] == "NOT_CAPTURED" for r in rows))
        self.assertTrue(all(r["source_sha256"] == "NOT_CAPTURED" for r in rows))
        self.assertEqual(audit(rows)["accepted"], 0)

    def test_distinct_rows_and_provenance(self):
        md = """## Morning
| Play | Odds | Result |
|---|---|---|
| Pick X | +100 | WIN |
## Evening
| Play | Odds | Result |
|---|---|---|
| Pick X | +100 | LOSS |
"""
        a, b = convert(md)
        self.assertNotEqual(a["event_id"], b["event_id"])
        self.assertEqual((a["ledger_section"], b["ledger_section"]), ("Morning", "Evening"))
        self.assertEqual(a["ledger_markdown_sha256"], b["ledger_markdown_sha256"])

    def test_no_fabricated_or_unparseable_price(self):
        rows = convert("## Test\n| Pick | abc | WIN |\n")
        self.assertEqual(rows[0]["odds"], "NOT_CAPTURED")
        self.assertEqual(audit(rows)["accepted"], 0)

    def test_missing_markdown_rows(self):
        self.assertEqual(convert("No tables here"), [])


if __name__ == "__main__":
    unittest.main()
