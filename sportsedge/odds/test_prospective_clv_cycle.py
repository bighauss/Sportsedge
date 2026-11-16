"""Synthetic HTTP responses: no keys, network, paid history or user odds."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import csv
import io
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from sportsedge.odds.free_odds_aggregator_intake import SPORTS
from sportsedge.odds.prospective_clv_cycle import capture_cycle, REPO_ROOT

EVENT_ID = "0123456789abcdef0123456789abcdef"
KEY = "TEST_PROSPECTIVE_KEY_0123456789"


class Response(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.headers = {
            "Date": "Sun, 15 Nov 2026 20:00:00 GMT",
            "x-requests-remaining": "490",
            "x-requests-last": "1",
        }


def provider_payload(sport="NFL", *, minutes_to_kickoff=60, age_seconds=45, outcomes=2):
    now = datetime.now(timezone.utc)
    return [{
        "id": EVENT_ID,
        "sport_key": SPORTS[sport],
        "commence_time": (now + timedelta(minutes=minutes_to_kickoff)).isoformat(),
        "home_team": "Home Team",
        "away_team": "Away Team",
        "bookmakers": [{
            "key": "draftkings",
            "markets": [{
                "key": "h2h",
                "last_update": (now - timedelta(seconds=age_seconds)).isoformat(),
                "outcomes": [
                    {"name": "Home Team", "price": -110},
                    {"name": "Away Team", "price": +105},
                ][:outcomes],
            }],
        }],
    }]


def fake_opener(payload):
    raw = json.dumps(payload).encode()
    def opener(request, timeout):
        assert request.full_url.startswith("https://api.the-odds-api.com/v4/sports/")
        assert "apiKey=" + KEY in request.full_url
        assert timeout <= 30
        return Response(raw)
    return opener


class CaptureCycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.private = Path(temp.name) / "private"

    def capture(self, phase="TAKE", *, sport="NFL", payload=None, **kwargs):
        if payload is None:
            payload = provider_payload(sport)
        return capture_cycle(
            sport, self.private, EVENT_ID, phase,
            key=KEY, opener=fake_opener(payload), **kwargs
        )

    def test_private_full_cycle_preserves_original_and_paper_result(self):
        result = self.capture()
        self.assertEqual(result["phase"], "TAKE")
        self.assertEqual(result["normalized_two_sided_selection_rows"], 2)
        self.assertEqual(result["official_counted"], 0)
        self.assertFalse(result["original_books_independently_authenticated"])
        self.assertEqual(result["provider_credits_remaining"], "490")
        for field in ("original_json_filename", "original_manifest_filename",
                      "normalized_csv_filename", "normalized_audit_filename"):
            self.assertTrue((self.private/result[field]).is_file())
        with (self.private/result["normalized_csv_filename"]).open(newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({r["selection_id"] for r in rows}, {"HOME", "AWAY"})
        self.assertEqual({r["source"] for r in rows}, {"THE_ODDS_API"})
        for path in self.private.iterdir():
            self.assertNotIn(KEY, path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_supported_six_sports(self):
        for sport in SPORTS:
            with self.subTest(sport=sport):
                result = self.capture(sport=sport)
                self.assertEqual(result["sport"], sport)
                self.assertEqual(result["normalized_two_sided_selection_rows"], 2)

    def test_close_role_creates_history_csv_not_false_wager(self):
        result = self.capture(phase="CLOSE",
                              payload=provider_payload(minutes_to_kickoff=5))
        self.assertIn(".close.csv", result["normalized_csv_filename"])
        self.assertEqual(result["official_counted"], 0)
        self.assertTrue((self.private/result["normalized_audit_filename"]).exists())

    def test_missing_opposing_market_fails_closed_but_original_preserved(self):
        result = self.capture(payload=provider_payload(outcomes=1))
        self.assertEqual(result["normalized_two_sided_selection_rows"], 0)
        self.assertEqual(result["state"], "BLOCK_NO_VALID_FRESH_TWO_SIDED_QUOTES")
        self.assertTrue((self.private/result["original_json_filename"]).exists())
        self.assertEqual(result["market_groups_quarantined_by_reason"]["MARKET_NOT_TWO_SIDED"], 1)

    def test_stale_observation_fails_closed_but_raw_preserved(self):
        result = self.capture(payload=provider_payload(age_seconds=600))
        self.assertEqual(result["normalized_two_sided_selection_rows"], 0)
        self.assertEqual(result["market_groups_quarantined_by_reason"]["STALE_QUOTE_OVER_FIVE_MINUTES"], 1)

    def test_invalid_phase_blocks_before_api_request(self):
        called = []
        def opener(*args, **kwargs):
            called.append(True)
            raise AssertionError("Network must not run")
        with self.assertRaisesRegex(ValueError, "PHASE_MUST_BE"):
            capture_cycle("NFL",self.private,EVENT_ID,"WAGER",key=KEY,opener=opener)
        self.assertFalse(called)
        self.assertFalse(self.private.exists())

    def test_public_repository_path_blocks_before_api_request(self):
        called = []
        def opener(*args, **kwargs):
            called.append(True)
            raise AssertionError("Network must not run")
        with self.assertRaisesRegex(ValueError, "PRIVATE_CAPTURE_PATH_IS_PUBLIC_CHECKOUT"):
            capture_cycle("NFL",REPO_ROOT/"private-should-not-exist",EVENT_ID,"TAKE",
                          key=KEY,opener=opener)
        self.assertFalse(called)

    def test_missing_api_key_never_fetches_or_writes(self):
        called = []
        def opener(*args, **kwargs):
            called.append(True)
            raise AssertionError("Network must not run")
        with patch.dict(os.environ, {"SPORTSEDGE_ODDS_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "USER_API_KEY_MISSING_OR_UNSAFE"):
                capture_cycle("NFL",self.private,EVENT_ID,"TAKE",opener=opener)
        self.assertFalse(called)
        self.assertFalse(self.private.exists())

    def test_real_provider_event_id_required_before_fetch(self):
        called = []
        def opener(*args, **kwargs):
            called.append(True)
            raise AssertionError("Network must not run")
        with self.assertRaisesRegex(ValueError, "REAL_PROVIDER_EVENT_ID_REQUIRED"):
            capture_cycle("NFL",self.private,"","TAKE",key=KEY,opener=opener)
        self.assertFalse(called)

    def test_event_id_response_mismatch_blocks_without_output(self):
        payload = provider_payload()
        payload[0]["id"] = "b" * 32
        with self.assertRaisesRegex(ValueError, "EVENT_ID_RESPONSE_MISMATCH"):
            self.capture(payload=payload)
        self.assertFalse(self.private.exists())

if __name__ == "__main__":
    unittest.main()
