"""Synthetic source-native ID versus claimed-canonical market lineage tests."""
import unittest

from research.evidence.source_lineage_gate import inspect_pair, Refused


def fixture():
    common = dict(
        canonical_sport="NFL", canonical_event_id="2026_CHI_GB",
        canonical_market_key="FG_TOTAL", canonical_period="FG",
        canonical_selection_id="OVER", canonical_opposite_selection_id="UNDER",
        crosswalk_source_sha256="c" * 64,
        crosswalk_observed_utc="2026-11-15T17:55:00Z",
        line="49.5", price="-110", opposite_price="-110",
        observed_utc="2026-11-15T18:00:00Z",
        captured_utc="2026-11-15T18:00:01Z",
        decision_utc="2026-11-15T18:00:02Z",
        kickoff_utc="2026-11-15T19:00:00Z", status="OPEN",
    )
    return [
        {**common, "source_id": "direct_dk", "upstream_operator_id": "DK",
         "aggregator_id": "direct-dk", "book_id": "DraftKings",
         "event_id": "DK_EVT_123", "market_id": "DK_MKT_997",
         "selection_id": "DK_OVER_001", "opposite_selection_id": "DK_UNDER_002",
         "receipt_id": "DK_HTTP_ORIGINAL_1", "raw_sha256": "a" * 64},
        {**common, "source_id": "direct_fd", "upstream_operator_id": "FD",
         "aggregator_id": "direct-fd", "book_id": "FanDuel",
         "event_id": "FD_333", "market_id": "FD_MM_85",
         "selection_id": "FD_O_33", "opposite_selection_id": "FD_U_44",
         "receipt_id": "FD_HTTP_ORIGINAL_1", "raw_sha256": "b" * 64},
    ]


class TestLineage(unittest.TestCase):
    def test_distinct_native_ids_same_claimed_canonical_stays_paper(self):
        result = inspect_pair(fixture())
        self.assertEqual(result["status"], "PAPER_SOURCE_CLAIMS_ONLY")
        self.assertFalse(result["authenticated"])
        self.assertFalse(result["crosswalk_attested"])
        self.assertEqual(result["approved_stake_u"], 0)

    def test_same_aggregator(self):
        r = fixture()
        r[1]["aggregator_id"] = r[0]["aggregator_id"]
        with self.assertRaisesRegex(Refused, "NOT_INDEPENDENT"):
            inspect_pair(r)

    def test_same_upstream_alias(self):
        r = fixture()
        r[1]["upstream_operator_id"] = "DraftKings"
        with self.assertRaisesRegex(Refused, "NOT_INDEPENDENT_UPSTREAM"):
            inspect_pair(r)

    def test_same_book_alias(self):
        r = fixture()
        r[1]["book_id"] = "DK"
        with self.assertRaisesRegex(Refused, "NOT_INDEPENDENT_BOOK"):
            inspect_pair(r)

    def test_stale(self):
        r = fixture()
        r[0]["observed_utc"] = "2026-11-15T17:00:00Z"
        with self.assertRaisesRegex(Refused, "STALE"):
            inspect_pair(r)

    def test_live(self):
        r = fixture()
        r[0]["decision_utc"] = r[0]["kickoff_utc"]
        with self.assertRaisesRegex(Refused, "LOOKAHEAD"):
            inspect_pair(r)

    def test_canonical_market_mismatch_even_if_native_mapping_claimed(self):
        r = fixture()
        for field,value in (
            ("line","50.5"), ("canonical_event_id","OTHER_EVENT"),
            ("canonical_market_key","FG_SPREAD"),
            ("canonical_selection_id","UNDER"),
            ("canonical_period","1H"),
            ("crosswalk_source_sha256","d" * 64),
        ):
            with self.subTest(field=field):
                altered = [dict(q) for q in r]
                altered[1][field] = value
                with self.assertRaisesRegex(Refused, "MISMATCH"):
                    inspect_pair(altered)

    def test_native_provider_market_id_can_differ(self):
        r = fixture()
        self.assertNotEqual(r[0]["market_id"], r[1]["market_id"])
        self.assertNotEqual(r[0]["selection_id"], r[1]["selection_id"])
        self.assertFalse(inspect_pair(r)["authenticated"])

    def test_missing_canonical_key_rejected(self):
        r = fixture()
        del r[0]["canonical_event_id"]
        with self.assertRaisesRegex(Refused, "SCHEMA"):
            inspect_pair(r)

    def test_missing_crosswalk_hash_refused(self):
        r = fixture()
        r[0]["crosswalk_source_sha256"] = "unhashed"
        with self.assertRaisesRegex(Refused, "INVALID_SHA256"):
            inspect_pair(r)

    def test_crosswalk_created_after_decision_refused(self):
        r = fixture()
        r[0]["crosswalk_observed_utc"] = "2026-11-15T18:00:03Z"
        with self.assertRaisesRegex(Refused, "FUTURE_CROSSWALK"):
            inspect_pair(r)

    def test_identical_raw_bytes_with_renamed_sources_quarantined(self):
        r = fixture()
        r[1]["raw_sha256"] = r[0]["raw_sha256"]
        with self.assertRaisesRegex(Refused, "SHARED_RAW_SOURCE_BYTES"):
            inspect_pair(r)

    def test_suspicious_shared_provider_native_ids_refused(self):
        r = fixture()
        for field in ("event_id","market_id","selection_id","opposite_selection_id"):
            r[1][field] = r[0][field]
        with self.assertRaisesRegex(Refused, "SUSPICIOUS_SHARED_PROVIDER_NATIVE_IDS"):
            inspect_pair(r)

    def test_nan(self):
        r = fixture()
        r[0]["line"] = "NaN"
        with self.assertRaisesRegex(Refused, "INVALID_NUMBER"):
            inspect_pair(r)

    def test_suspended(self):
        r = fixture()
        r[0]["status"] = "SUSPENDED"
        with self.assertRaisesRegex(Refused, "NOT_OPEN"):
            inspect_pair(r)

    def test_bool_policy(self):
        with self.assertRaisesRegex(Refused, "AGE_POLICY"):
            inspect_pair(fixture(), True)

    def test_missing_opposite_id(self):
        r = fixture()
        r[1]["selection_id"] = r[1]["opposite_selection_id"]
        with self.assertRaisesRegex(Refused, "INVALID_OPPOSITE"):
            inspect_pair(r)


if __name__ == "__main__":
    unittest.main()
