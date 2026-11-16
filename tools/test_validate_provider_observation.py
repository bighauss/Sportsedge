import unittest
from tools.validate_provider_observation import validate_manifest

def good():
    return {
        "schema_version": 1, "gate_a": "OPEN", "market_state": "PAPER/0u",
        "no_original_bytes_archived": True, "not_a_point_in_time_quote_receipt": True,
        "observations": [
            {"source": name, "status": "observed", "research_only": True,
             "http_status": 200, "byte_count": 100, "sha256": "a" * 64,
             "top_level_type": "list", "observed_at_utc": "2026-11-16T13:00:00+00:00"}
            for name in ("cfbd_games_2026_w1", "odds_nfl_events", "apisports_football_status")
        ]
    }

class TestProviderObservation(unittest.TestCase):
    def test_valid_research_only(self):
        self.assertEqual(validate_manifest(good()), [])
    def test_reject_boolean_schema_version(self):
        d = good()
        d["schema_version"] = True  # True == 1 in Python
        self.assertIn("schema_version", validate_manifest(d))

    def test_reject_float_http_status(self):
        d = good()
        d["observations"][0]["http_status"] = 200.0
        self.assertIn("row_0_http", validate_manifest(d))

    def test_duplicate_source(self):
        d=good()
        d["observations"][1]["source"]=d["observations"][0]["source"]
        self.assertIn("missing_or_duplicate_source", validate_manifest(d))
    def test_no_gate_promotion(self):
        d=good()
        d["gate_a"]="CLOSED"
        self.assertIn("unsafe_market_state", validate_manifest(d))
    def test_reject_invalid_hash(self):
        d=good()
        d["observations"][0]["sha256"]="xyz"
        self.assertIn("row_0_sha", validate_manifest(d))
    def test_reject_naive_timestamp(self):
        d=good()
        d["observations"][0]["observed_at_utc"]="2026-11-16T13:00:00"
        self.assertIn("row_0_timestamp", validate_manifest(d))
    def test_reject_future_observation_clock(self):
        d = good()
        d["observations"][0]["observed_at_utc"] = "2099-01-01T00:00:00+00:00"
        self.assertIn("row_0_timestamp", validate_manifest(d))
    def test_reject_noncanonical_timestamp_suffix(self):
        d = good()
        d["observations"][0]["observed_at_utc"] = "2026-11-16T13:00:00Zgarbage"
        self.assertIn("row_0_timestamp", validate_manifest(d))
    def test_reject_missing(self):
        d=good()
        d["observations"].pop()
        self.assertIn("missing_or_duplicate_source", validate_manifest(d))
    def test_reject_blocked(self):
        d=good()
        d["observations"][0]["status"]="blocked"
        self.assertIn("row_0_not_observed", validate_manifest(d))
    def test_reject_oversize(self):
        d=good()
        d["observations"][0]["byte_count"]=2000001
        self.assertIn("row_0_bytes", validate_manifest(d))

if __name__=="__main__":
    unittest.main()
