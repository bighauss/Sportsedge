"""Synthetic tests of permitted offline exports. No live DK feed is invoked."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.odds.seven_sport_authorized_export import (
    FAMILIES, SPORTS, audit, report_file, _parse,
)
from sportsedge.validation.seven_sport_pit_freeze import ROOT

NOW = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)


def put(path, payload):
    path.write_bytes(payload)
    path.chmod(0o600)
    return {"path": str(path), "sha256": "sha256:" + sha256(payload).hexdigest()}


class OfflineSourceCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        root.chmod(0o700)
        self.root = root
        self.raw = put(root / "original.provider.json", b'{"original":"fixture-only"}')
        self.quote = {
            "event_id": "event-101", "market_family": "ML",
            "period": "FG", "selection": "HOME", "selection_id": "team-home",
            "participant_id": "", "stat": "", "line": "",
            "price_american": -110, "provider_quote_id": "book-quote-1",
            "provider_market_id": "book-market-1",
            "observed_utc": "2026-11-15T23:59:00Z",
        }
        self.converted = {
            "schema": "sportsedge-seven-sport-converted-quotes-v1",
            "quotes": [dict(self.quote)]
        }
        self.conv_path = root / "converted.json"
        self.converted_descriptor = put(self.conv_path, json.dumps(self.converted).encode())
        inventory = [{"market_family": x,
                      "status": "CAPTURED" if x == "ML" else "OFFER_UNKNOWN"}
                     for x in sorted(FAMILIES)]
        self.request = {
            "schema": "sportsedge-seven-sport-offline-export-request-v1",
            "sport": "NFL", "provider": "fixture-permitted",
            "upstream_book": "DK", "upstream_provider": "fixture-original",
            "collection_path_id": "fixture-original-collection",
            "source_mapping_version": "fixture-v1",
            "permission_reference_claim": "fixture-permission",
            "source_observed_utc": "2026-11-15T23:58:00Z",
            "source_captured_utc": "2026-11-16T00:00:00Z",
            "original_provider_file": self.raw,
            "converted_quote_file": self.converted_descriptor,
            "events": [{
                "event_id": "event-101",
                "start_utc": "2026-11-16T02:00:00Z",
                "market_inventory": inventory,
            }]
        }

    def check(self, request=None, converted=None):
        return audit(self.request if request is None else request,
                     self.converted if converted is None else converted,
                     actual_now=NOW)

    def test_all_seven_sports_stay_paper(self):
        self.assertEqual(len(SPORTS), 7)
        for sport in SPORTS:
            with self.subTest(sport=sport):
                r = self.check(request=dict(self.request, sport=sport))
                self.assertEqual(r["approved_stake_u"], 0)
                self.assertEqual(r["official_counted"], 0)
                self.assertFalse(r["provider_authenticity_verified"])
                self.assertEqual(r["market_family_slots_declared"], len(FAMILIES))
                self.assertEqual(r["quote_rows_claimed"], 1)

    def test_no_missing_market_family(self):
        bad = dict(self.request)
        event = dict(bad["events"][0])
        event["market_inventory"] = event["market_inventory"][:-1]
        bad["events"] = [event]
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_MARKET_FAMILY_CENSUS"):
            self.check(request=bad)

    def test_unknown_is_not_not_offered(self):
        r = self.check()
        self.assertEqual(r["market_family_status_counts"]["OFFER_UNKNOWN"], len(FAMILIES)-1)
        self.assertNotIn("NOT_OFFERED", r["market_family_status_counts"])

    def test_fake_not_offered_disallowed(self):
        bad = dict(self.request)
        ev = dict(bad["events"][0])
        ev["market_inventory"] = [
            dict(row, status="NOT_OFFERED") if row["market_family"] == "ML" else row
            for row in ev["market_inventory"]
        ]
        bad["events"] = [ev]
        with self.assertRaisesRegex(ValueError, "INVALID_OR_DUPLICATE_MARKET_FAMILY"):
            self.check(request=bad)

    def test_fake_captured_without_quote_rejected(self):
        conv = dict(self.converted, quotes=[])
        with self.assertRaisesRegex(ValueError, "INVENTORY_QUOTE_POPULATION_DISAGREES"):
            self.check(converted=conv)

    def test_quote_under_unknown_family_rejected(self):
        bad = dict(self.converted, quotes=[dict(self.quote, market_family="SGP")])
        with self.assertRaisesRegex(ValueError, "QUOTE_FAMILY_NOT_DECLARED_CAPTURED"):
            self.check(converted=bad)

    def test_duplicate_normalized_quote_rejected(self):
        bad = dict(self.converted, quotes=[self.quote, dict(self.quote, provider_quote_id="book-quote-2")])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_EXACT_MARKET_OUTCOME"):
            self.check(converted=bad)

    def test_duplicate_provider_quote_id_rejected(self):
        alt = dict(self.quote, selection="AWAY", selection_id="team-away")
        with self.assertRaisesRegex(ValueError, "REUSED_PROVIDER_QUOTE_ID"):
            self.check(converted=dict(self.converted, quotes=[self.quote, alt]))

    def test_invalid_price_rejected(self):
        bad = dict(self.converted, quotes=[dict(self.quote, price_american=-90)])
        with self.assertRaisesRegex(ValueError, "INVALID_AMERICAN_ODDS"):
            self.check(converted=bad)

    def test_unknown_event_rejected(self):
        bad = dict(self.converted, quotes=[dict(self.quote, event_id="another-event")])
        with self.assertRaisesRegex(ValueError, "QUOTE_EVENT_NOT_IN_CENSUS"):
            self.check(converted=bad)

    def test_after_kickoff_quote_rejected(self):
        bad = dict(self.converted, quotes=[dict(self.quote, observed_utc="2026-11-16T02:01:00Z")])
        with self.assertRaisesRegex(ValueError, "FUTURE_OR_POST_START_QUOTE"):
            self.check(converted=bad)

    def test_post_kickoff_source_capture_rejected(self):
        bad = dict(self.request, source_captured_utc="2026-11-16T03:00:00Z")
        with self.assertRaisesRegex(ValueError, "SOURCE_CAPTURE_CHRONOLOGY"):
            self.check(request=bad)

    def test_duplicate_event_rejected(self):
        bad = dict(self.request, events=self.request["events"]*2)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_EVENT_ID"):
            self.check(request=bad)

    def test_missing_original_raw_file_rejected(self):
        bad = dict(self.request, original_provider_file=dict(
            self.raw, path=str(self.root / "gone.json")))
        with self.assertRaisesRegex(ValueError, "MISSING_REGULAR_SOURCE"):
            self.check(request=bad)

    def test_tampered_original_hash_rejected(self):
        bad = dict(self.request, original_provider_file=dict(
            self.raw, sha256="sha256:" + "0"*64))
        with self.assertRaisesRegex(ValueError, "ARTIFACT_HASH_MISMATCH"):
            self.check(request=bad)

    def test_unversioned_mapping_rejected(self):
        bad = dict(self.request, source_mapping_version="UNVERSIONED")
        with self.assertRaisesRegex(ValueError, "VERSIONED_SOURCE_MAPPING_REQUIRED"):
            self.check(request=bad)

    def test_invalid_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            _parse(b'{"schema":"a","schema":"b"}', "a")

    def test_create_only_private_report(self):
        req = self.root / "capture_request.json"
        req.write_text(json.dumps(self.request))
        req.chmod(0o600)
        dst = self.root / "new_capture_report.json"
        report = report_file(req, dst, actual_now=NOW)
        self.assertEqual(dst.stat().st_mode & 0o777, 0o600)
        self.assertEqual(report["approved_stake_u"], 0)
        self.assertEqual(report["quote_rows_claimed"], 1)
        self.assertNotIn("original.provider.json", dst.read_text())
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_NEW"):
            report_file(req, dst, actual_now=NOW)

    def test_public_output_refused(self):
        req = self.root / "request.json"
        req.write_text(json.dumps(self.request))
        req.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "PUBLIC_REPOSITORY_PATH"):
            report_file(req, ROOT / "untrusted_report.json", actual_now=NOW)

    def test_forward_player_prop_requires_id(self):
        bad_request = dict(self.request)
        ev = dict(bad_request["events"][0])
        ev["market_inventory"] = [
            dict(r, status="CAPTURED" if r["market_family"]=="PLAYER_PROP" else "OFFER_UNKNOWN")
            for r in ev["market_inventory"]
        ]
        bad_request["events"] = [ev]
        row = dict(self.quote, market_family="PLAYER_PROP")
        with self.assertRaisesRegex(ValueError, "PLAYER_PROP_ID_AND_STAT_REQUIRED"):
            self.check(request=bad_request, converted=dict(self.converted, quotes=[row]))


if __name__ == "__main__":
    unittest.main()
