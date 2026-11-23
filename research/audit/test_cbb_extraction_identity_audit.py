"""Synthetic-only CBB extraction identity regression tests."""
import copy
import unittest
from research.audit.cbb_extraction_identity_audit import reconcile


def case(event, source, market="full_game", away_spread="-2.5", away_ml="-148"):
    return {"market": market, "event": event, "start": "Today 1:00 PM",
            "source_file": "private-synthetic.pdf",
            "source_pdf_sha256": "not_authenticated",
            "raw_source_text": source, "identity_status": "CONFLICT_3WAY",
            "away_spread": away_spread, "home_spread": "2.5", "total": "163.5",
            "away_ml": away_ml, "away_sp_odds": "-110", "over_odds": "-110",
            "home_ml": "124", "home_sp_odds": "-110", "under_odds": "-110"}


class ExtractionReconcileTest(unittest.TestCase):
    def test_cyclic_label_shift_without_changing_quotes(self):
        rows = [
            case("Wyoming AT Duquesne",
                 "William &\nMary -2.5 O163.5\nAT\nYoungstow\n+2.5 U163.5\nn State"),
            case("San Diego AT Fordham",
                 "Wyoming -3.5 O136.5\nAT\nDuquesne +3.5 U136.5",
                 away_spread="-3.5", away_ml="-175"),
            case("William & Mary AT Youngstown State",
                 "San Diego +2.5 O143.5\nAT\nFordham -2.5 U143.5",
                 away_spread="+2.5", away_ml="+130"),
        ]
        original = copy.deepcopy(rows)
        r = reconcile(rows)
        self.assertEqual(rows, original)
        self.assertEqual(r["disputed_rows"], 3)
        self.assertEqual(len(r["candidate_reassignments"]), 3)
        self.assertEqual(r["blocked"], [])
        mp = {x["stored_event_label"]: x for x in r["candidate_reassignments"]}
        self.assertEqual(mp["Wyoming AT Duquesne"]["extracted_text_event_candidate"],
                         "William & Mary AT Youngstown State")
        self.assertEqual(mp["San Diego AT Fordham"]["extracted_text_event_candidate"],
                         "Wyoming AT Duquesne")
        self.assertEqual(mp["William & Mary AT Youngstown State"]["extracted_text_event_candidate"],
                         "San Diego AT Fordham")
        self.assertEqual(mp["Wyoming AT Duquesne"]["quote_fields_preserved"]["away_ml"], "-148")
        self.assertFalse(r["original_pdf_authenticated"])
        self.assertEqual(r["approved_stake_u"], 0)

    def test_duplicate_target_blocks_all_copies(self):
        r = reconcile([case("A Team AT Home One", "A Team AT Home One"),
                       case("B Team AT Home Two", "A Team AT Home One")])
        self.assertEqual(len(r["blocked"]), 2)
        self.assertEqual(r["candidate_reassignments"], [])

    def test_missing_home_identity_blocks(self):
        r = reconcile([case("Wyoming AT Duquesne", "Wyoming unknown opponent")])
        self.assertEqual(r["census"]["blocked_rows"], 1)

    def test_period_isolation(self):
        a = case("A Team AT Home One", "A Team AT Home One")
        b = case("A Team AT Home One", "A Team AT Home One", market="first_half")
        self.assertEqual(len(reconcile([a,b])["candidate_reassignments"]), 2)

    def test_unchanged_clean_rows(self):
        x = case("A Team AT Home One", "A Team AT Home One")
        x["identity_status"] = "OK"
        self.assertEqual(reconcile([x])["disputed_rows"], 0)

    def test_missing_source_rejected(self):
        x = case("A Team AT Home One", "A Team AT Home One")
        x["source_file"] = ""
        with self.assertRaisesRegex(ValueError, "CONFLICT_ROW_MISSING_SOURCE_FIELDS"):
            reconcile([x])


if __name__ == "__main__":
    unittest.main()
