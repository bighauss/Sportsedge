"""Adversarial synthetic fixtures for Firecrawl ESPN injury-source PIT guard.

No real player data is stored or imported. The real feed can contain Active
rows and dated recaps; fixture outcomes cannot certify source authenticity.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.validation.firecrawl_espn_injury_intake import (
    InjuryEvidenceError, analyze, archive,
)
from sportsedge.validation.seven_sport_pit_freeze import ROOT

UTC = timezone.utc
NOW = datetime(2026, 11, 16, 5, 9, 15, tzinfo=UTC)
START = "2026-11-16T07:00:00Z"


def make_row(ident, status, *, date="2026-11-16T05:00:00Z", team="3"):
    return {
        "athlete_id": ident,
        "current_team_id": team,
        "display_name": "SYNTHETIC_PLAYER_" + ident,
        "date": date,
        "status": status,
        "long_comment": "synthetic notes are not injuries",
    }


def fixture():
    people = [
        make_row("1001", "Out"),
        make_row("1002", "Active"),
        make_row("1003", "Questionable"),
    ]
    return {
        "success": True,
        "data": {
            "alexandria": [{
                "provider": "espn-com",
                "capability": "sports-data/injuries",
                "upstreamStatus": 200,
                "workflow": {
                    "version": "test-1.3.0",
                    "digest": "sha256:" + "a"*64,
                },
                "providerRequestId": "synthetic-request-1",
                "data": {
                    "sport": "football", "league": "nfl",
                    "team_filter": "CHI", "status_filter": None,
                    "observed_at_ms": int(datetime(2026, 11, 16, 5, 9, tzinfo=UTC).timestamp() * 1000),
                    "feed_timestamp": "2026-11-16T05:08:00Z",
                    "player_count": len(people), "team_count": 1,
                    "teams": [{
                        "abbreviation": "CHI", "team_id": "3",
                        "count": len(people), "injuries": people,
                    }],
                },
            }],
        },
    }


def blob(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


class FirecrawlEspnEvidenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.root.chmod(0o700)
        self.data = fixture()

    def inspect(self, data=None, **opts):
        return analyze(blob(self.data if data is None else data),
                       team=opts.get("team", "CHI"),
                       event_id=opts.get("event_id", "SYNTHETIC-EVT-01"),
                       event_start_utc=opts.get("start", START),
                       now_utc=opts.get("now", NOW))

    def test_meaningful_status_only_active_excluded_and_no_release(self):
        r = self.inspect()
        self.assertEqual(r["state"], "PAPER_0U_UNAUTHENTICATED_INJURY_CONTEXT")
        self.assertEqual(r["reported_nonactive_status_rows"], 2)
        self.assertEqual(r["non_injury_active_rows_excluded"], 1)
        self.assertEqual(r["provider_rows_received"], 3)
        self.assertFalse(r["model_feature_admissible"])
        self.assertFalse(r["gate_b_pit_certified"])
        self.assertFalse(r["release_certified"])
        self.assertEqual(r["official_counted"], 0)
        self.assertEqual(r["approved_stake_u"], 0)
        self.assertIsNone(r["card"])

    def test_raw_export_hash_and_private_create_only_sanitized_report(self):
        raw = blob(self.data)
        original = self.root/"original-provider.json"
        original.write_bytes(raw)
        original.chmod(0o600)
        dest = self.root/"report.json"
        report = archive(original, dest, team="CHI", event_id="SYNTHETIC-EVT-01",
                         event_start_utc=START, now_utc=NOW)
        self.assertEqual(report["original_response_sha256"],
                         "sha256:" + sha256(raw).hexdigest())
        self.assertEqual(original.read_bytes(), raw)
        self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("SYNTHETIC_PLAYER_", dest.read_text())
        self.assertNotIn("1001", dest.read_text())
        self.assertFalse(json.loads(dest.read_text())["source_independently_authenticated"])
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_NEW"):
            archive(original, dest, team="CHI", event_id="SYNTHETIC-EVT-01",
                    event_start_utc=START, now_utc=NOW)

    def test_zero_rows_are_not_proof_of_healthy_team(self):
        d = deepcopy(self.data)
        feed = d["data"]["alexandria"][0]["data"]
        feed["teams"][0]["injuries"] = []
        feed["teams"][0]["count"] = 0
        feed["player_count"] = 0
        report = self.inspect(d)
        self.assertEqual(report["state"], "BLOCK_INJURY_CONTEXT_INCOMPLETE_OR_STALE")
        self.assertEqual(report["provider_rows_received"], 0)
        self.assertIn("EMPTY_PROVIDER_REPORT_CANNOT_PROVE_HEALTH_OR_ROSTER_COMPLETENESS",
                      report["exclusion_reasons"])

    def test_active_only_does_not_become_injury(self):
        d = deepcopy(self.data)
        for row in d["data"]["alexandria"][0]["data"]["teams"][0]["injuries"]:
            row["status"] = "Active"
        r = self.inspect(d)
        self.assertEqual(r["state"], "BLOCK_INJURY_CONTEXT_INCOMPLETE_OR_STALE")
        self.assertEqual(r["reported_nonactive_status_rows"], 0)
        self.assertEqual(r["non_injury_active_rows_excluded"], 3)

    def test_unrecognized_status_not_silently_mapped_to_out(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["teams"][0]["injuries"][0]["status"] = "Pending Unlisted"
        r = self.inspect(d)
        self.assertEqual(r["unsupported_status_rows_excluded"], 1)
        self.assertEqual(r["state"], "BLOCK_INJURY_CONTEXT_INCOMPLETE_OR_STALE")

    def test_report_note_over_seven_days_blocks_even_with_out(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["teams"][0]["injuries"][0]["date"] = "2026-11-01T00:00:00Z"
        r = self.inspect(d)
        self.assertEqual(r["older_than_seven_days_notes"], 1)
        self.assertEqual(r["state"], "BLOCK_INJURY_CONTEXT_INCOMPLETE_OR_STALE")

    def test_status_after_original_observation_rejected(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["teams"][0]["injuries"][0]["date"] = "2026-11-16T05:10:00Z"
        with self.assertRaisesRegex(InjuryEvidenceError, "INJURY_NOTE_IN_FUTURE"):
            self.inspect(d)

    def test_provider_census_mismatch_rejected_not_silently_dropped(self):
        for field in ("player_count",):
            d = deepcopy(self.data)
            d["data"]["alexandria"][0]["data"][field] = 1
            with self.assertRaisesRegex(InjuryEvidenceError, "COUNT_CONFLICT"):
                self.inspect(d)
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["teams"][0]["count"] = 4
        with self.assertRaisesRegex(InjuryEvidenceError, "COUNT_CONFLICT"):
            self.inspect(d)

    def test_boolean_player_counts_refused_as_not_integer(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["player_count"] = True
        with self.assertRaisesRegex(InjuryEvidenceError, "INVALID_SOURCE_COUNT"):
            self.inspect(d)
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["teams"][0]["count"] = True
        with self.assertRaisesRegex(InjuryEvidenceError, "INVALID_SOURCE_COUNT"):
            self.inspect(d)

    def test_same_athlete_duplicate_rejected(self):
        d = deepcopy(self.data)
        people = d["data"]["alexandria"][0]["data"]["teams"][0]["injuries"]
        people[1]["athlete_id"] = people[0]["athlete_id"]
        with self.assertRaisesRegex(InjuryEvidenceError, "DUPLICATE_ESPN_ATHLETE"):
            self.inspect(d)

    def test_wrong_current_player_team_rejected(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["teams"][0]["injuries"][0]["current_team_id"] = "999"
        with self.assertRaisesRegex(InjuryEvidenceError, "ATHLETE_CURRENT_TEAM_MISMATCH"):
            self.inspect(d)

    def test_team_filter_mismatch_or_missing_status_filter_rejected(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["team_filter"] = "DET"
        with self.assertRaisesRegex(InjuryEvidenceError, "UNFILTERED"):
            self.inspect(d)
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["status_filter"] = "OUT"
        with self.assertRaisesRegex(InjuryEvidenceError, "UNFILTERED"):
            self.inspect(d)
        with self.assertRaisesRegex(InjuryEvidenceError, "EXPLICIT_NFL_TEAM"):
            self.inspect(team="Chicago")

    def test_provider_identity_wrong_or_failed_request_rejected(self):
        d = deepcopy(self.data)
        d["success"] = False
        with self.assertRaisesRegex(InjuryEvidenceError, "UNSUCCESSFUL"):
            self.inspect(d)
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["provider"] = "unknown-webpage"
        with self.assertRaisesRegex(InjuryEvidenceError, "WRONG_PROVIDER"):
            self.inspect(d)
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["upstreamStatus"] = 403
        with self.assertRaisesRegex(InjuryEvidenceError, "NON_200"):
            self.inspect(d)

    def test_workflow_digest_and_request_id_required(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["workflow"]["digest"] = "sha256:fake"
        with self.assertRaisesRegex(InjuryEvidenceError, "WORKFLOW_DIGEST"):
            self.inspect(d)
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["providerRequestId"] = ""
        with self.assertRaisesRegex(InjuryEvidenceError, "INVALID_SOURCE_STRING"):
            self.inspect(d)

    def test_future_timestamp_and_after_event_rejected(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["feed_timestamp"] = "2026-11-16T05:20:00Z"
        with self.assertRaisesRegex(InjuryEvidenceError, "CHRONOLOGY"):
            self.inspect(d)
        with self.assertRaisesRegex(InjuryEvidenceError, "POST_EVENT"):
            self.inspect(now=NOW+timedelta(hours=3))
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["observed_at_ms"] = int(
            (NOW + timedelta(seconds=3)).timestamp() * 1000)
        with self.assertRaisesRegex(InjuryEvidenceError, "CHRONOLOGY"):
            self.inspect(d)

    def test_stale_capture_or_source_feed_blocked(self):
        with self.assertRaisesRegex(InjuryEvidenceError, "TOO_STALE"):
            self.inspect(now=NOW+timedelta(minutes=6))
        d = deepcopy(self.data)
        d["data"]["alexandria"][0]["data"]["feed_timestamp"] = "2026-10-01T05:08:00Z"
        with self.assertRaisesRegex(InjuryEvidenceError, "SEVEN_DAYS_OLD"):
            self.inspect(d)

    def test_ambiguous_json_duplicate_field_and_nonfinite_refused(self):
        with self.assertRaisesRegex(InjuryEvidenceError, "DUPLICATE_JSON_KEY"):
            analyze(b'{"success":true,"success":false}', team="CHI",
                    event_id="SYN", event_start_utc=START, now_utc=NOW)
        with self.assertRaisesRegex(InjuryEvidenceError, "NONFINITE_JSON_NUMBER"):
            analyze(b'{"x":NaN}', team="CHI", event_id="SYN",
                    event_start_utc=START, now_utc=NOW)

    def test_private_permission_and_symlink_enforced(self):
        raw = blob(self.data)
        source = self.root/"src.json"
        source.write_bytes(raw)
        source.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "PRIVATE_FILE_PERMISSIONS"):
            archive(source, self.root/"result.json", team="CHI",
                    event_id="SYN", event_start_utc=START, now_utc=NOW)
        source.chmod(0o600)
        alias = self.root/"alias.json"
        alias.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "SYMLINK"):
            archive(alias, self.root/"result.json", team="CHI",
                    event_id="SYN", event_start_utc=START, now_utc=NOW)
        with self.assertRaisesRegex(ValueError, "PUBLIC_REPOSITORY"):
            archive(source, ROOT/"DO_NOT_CREATE_INJURY_REPORT.json", team="CHI",
                    event_id="SYN", event_start_utc=START, now_utc=NOW)
        self.assertFalse((ROOT/"DO_NOT_CREATE_INJURY_REPORT.json").exists())

    def test_event_id_required_and_time_utc_required(self):
        with self.assertRaisesRegex(InjuryEvidenceError, "EXPLICIT_EVENT_ID"):
            self.inspect(event_id="other event")
        with self.assertRaisesRegex(InjuryEvidenceError, "UTC_TIMESTAMP"):
            self.inspect(start="2026-11-16T07:00:00")
        with self.assertRaisesRegex(InjuryEvidenceError, "ACTUAL_CAPTURE_CLOCK"):
            self.inspect(now=datetime(2026, 11, 16, 5, 9, 15))

    def test_response_rejected_if_not_exactly_one_provider(self):
        d = deepcopy(self.data)
        d["data"]["alexandria"].append(deepcopy(d["data"]["alexandria"][0]))
        with self.assertRaisesRegex(InjuryEvidenceError, "ONE_ALEXANDRIA"):
            self.inspect(d)


if __name__ == "__main__":
    unittest.main()
