import unittest
from ledger_to_audit_csv import convert
class Tests(unittest.TestCase):
 def test_missing_snapshot_is_explicit(self):
  rows=convert("## Morning\n| Play | Odds | Result |\n|---|---|---|\n| Jets ML | +350 | LOSS (12-31) |")
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]["outcome"],"0")
  self.assertEqual(rows[0]["source_status"],"NOT_CAPTURED")
  self.assertEqual(rows[0]["snapshot_utc"],"")
 def test_inferred_is_not_graded(self):
  rows=convert("## Afternoon\n| Beck 180+ | +101 | LOSS (team total) inferred |")
  self.assertEqual(rows[0]["outcome"],"")
 def test_pending(self):
  rows=convert("## Afternoon\n| Ravens ML | -120 | PENDING |")
  self.assertEqual(rows[0]["outcome"],"")
 def test_ignores_invalid_price(self):
  self.assertEqual(convert("## A\n| X | unknown | WIN |"),[])
if __name__=="__main__":unittest.main()
