"""Synthetic only: cross-sport historical leakage safeguards."""
import csv
import tempfile
import unittest
from pathlib import Path
from feature_chronology_preflight import assess

SHA = "a" * 64

def projection(**changes):
    row = dict(
        selection_id="2026-11-15-NFL-event-1-over-50", sport="NFL",
        event_id="event-1", market="TOTAL", model_asof_utc="2026-11-15T16:00:00Z",
        quote_captured_utc="2026-11-15T16:05:00Z",
        kickoff_utc="2026-11-15T17:00:00Z",
        model_sha256=SHA, quote_sha256="b" * 64,
    )
    row.update(changes)
    return row

def feature(**changes):
    row = dict(
        selection_id="2026-11-15-NFL-event-1-over-50",
        feature_id="injury-report-QB", published_utc="2026-11-15T15:55:00Z",
        captured_utc="2026-11-15T15:56:00Z", source_sha256="c" * 64,
    )
    row.update(changes)
    return row


class ChronologyTests(unittest.TestCase):
    def test_valid_claimed_prelock_chronology_never_calls_it_authenticated(self):
        report = assess([projection()], [feature()])
        self.assertEqual(report["chronology_consistent_unverified"], 1)
        self.assertEqual(report["blocked"], 0)
        self.assertIn("NOT_VERIFIED", report["status"])
        self.assertIn("do not prove", report["limitations"])

    def test_future_injury_update_refused(self):
        report = assess([projection()], [feature(published_utc="2026-11-15T16:01:00Z",
                                                  captured_utc="2026-11-15T16:02:00Z")])
        self.assertEqual(report["blocked"], 1)
        self.assertTrue(any("AFTER_MODEL" in x for x in report["results"][0]["flags"]))

    def test_quote_and_model_clock_order_refused(self):
        r = assess([projection(model_asof_utc="2026-11-15T16:06:00Z")], [feature()])
        self.assertIn("MODEL_ASOF_AFTER_QUOTE_CAPTURE", r["results"][0]["flags"])

    def test_quote_after_kickoff_refused(self):
        r = assess([projection(quote_captured_utc="2026-11-15T17:10:00Z")], [feature()])
        self.assertIn("QUOTE_NOT_PREGAME", r["results"][0]["flags"])

    def test_feature_claim_captured_before_publication_refused(self):
        r = assess([projection()], [feature(published_utc="2026-11-15T15:58:00Z")])
        self.assertTrue(any("PUBLISHED_AFTER_CAPTURE" in x for x in r["results"][0]["flags"]))

    def test_duplicate_feature_version_refused(self):
        a, b = feature(), feature(captured_utc="2026-11-15T15:57:00Z")
        r = assess([projection()], [a, b])
        self.assertIn("DUPLICATE_FEATURE_VERSION", r["results"][0]["flags"])

    def test_duplicate_selection_both_blocked_even_if_reversed(self):
        a, b = projection(), projection(model_sha256="f" * 64)
        for records in ([a, b], [b, a]):
            r = assess(records, [feature()])
            self.assertEqual(r["blocked"], 2)
            self.assertTrue(all("DUPLICATE_SELECTION_ID" in x["flags"]
                                for x in r["results"]))

    def test_missing_feature_evidence_refused(self):
        r = assess([projection()], [])
        self.assertIn("NO_FEATURE_EVIDENCE", r["results"][0]["flags"])

    def test_unknown_sport_and_bad_hash_refused(self):
        r = assess([projection(sport="UNKNOWN", quote_sha256="not-a-hash")], [feature()])
        self.assertEqual(r["blocked"], 1)
        self.assertIn("UNKNOWN_SPORT", r["results"][0]["flags"])
        self.assertIn("INVALID_QUOTE_SHA256", r["results"][0]["flags"])

    def test_missing_feature_and_non_utc_time_refused(self):
        r = assess([projection()], [feature(source_sha256="", published_utc="2026-11-15T10:55:00-05:00")])
        self.assertEqual(r["blocked"], 1)
        self.assertTrue(any("INVALID_TIME" in x for x in r["results"][0]["flags"]))

    def test_unpaired_feature_retained_as_orphan(self):
        r = assess([projection()], [feature(), feature(selection_id="other", feature_id="weather")])
        self.assertEqual(len(r["orphan_features"]), 1)
        self.assertEqual(r["chronology_consistent_unverified"], 1)

    def test_alt_market_selections_must_have_own_evidence(self):
        other = projection(selection_id="2026-11-15-NFL-event-1-over-51")
        r = assess([projection(), other], [feature()])
        self.assertEqual(r["chronology_consistent_unverified"], 1)
        self.assertEqual(r["blocked"], 1)
        self.assertIn("NO_FEATURE_EVIDENCE", r["results"][1]["flags"])


if __name__ == "__main__":
    unittest.main()
