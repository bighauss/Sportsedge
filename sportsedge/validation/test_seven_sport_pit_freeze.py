"""Fixture-only evidence tests; no real sportsbook or source authentication."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.validation.seven_sport_pit_freeze import (
    ROOT, SPORTS, analyze, freeze_file, _parse,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 16, 1, 1, tzinfo=UTC)


def desc(path, payload):
    path.write_bytes(payload)
    path.chmod(0o600)
    return {"path": str(path), "sha256": "sha256:" + sha256(payload).hexdigest()}


class SevenSportFreeze(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.root.chmod(0o700)
        config = desc(self.root / "config.json", b'{"fixture":"research"}')
        feature = desc(self.root / "original_feature.json", b'{"original":"synthetic fixture"}')
        path = ROOT / "models" / "common" / "guard.py"
        raw = path.read_bytes()
        model_code = {"path": str(path.relative_to(ROOT)),
                      "sha256": "sha256:" + sha256(raw).hexdigest()}
        self.req = {
            "schema": "sportsedge-seven-sport-pit-freeze-request-v1",
            "sport": "NFL", "event_id": "synthetic-20261116",
            "market_family": "SPREAD", "period": "FG",
            "model_version": "test-model-r1",
            "training_cutoff_utc": "2026-11-15T23:00:00Z",
            "registered_utc": "2026-11-16T00:00:00Z",
            "freeze_utc": "2026-11-16T01:00:00Z",
            "event_start_utc": "2026-11-16T02:00:00Z",
            "evaluation_end_utc": "2026-11-16T05:00:00Z",
            "model_code": model_code, "model_config": config,
            "feature_sources": [{
                "source_id": "fixture-rating-asof",
                "file": feature,
                "data_through_utc": "2026-11-15T20:00:00Z",
                "published_utc": "2026-11-15T21:00:00Z",
                "observed_utc": "2026-11-15T21:30:00Z",
                "captured_utc": "2026-11-15T22:00:00Z",
            }]
        }

    def analyze(self, **updates):
        x = dict(self.req)
        x.update(updates)
        return analyze(x, actual_now=NOW)

    def test_all_seven_sports_research_only(self):
        self.assertEqual(len(SPORTS), 7)
        for sport in SPORTS:
            with self.subTest(sport=sport):
                out = self.analyze(sport=sport)
                self.assertEqual(out["sport"], sport)
                self.assertEqual(out["approved_stake_u"], 0)
                self.assertEqual(out["official_counted"], 0)
                self.assertFalse(out["source_externally_authenticated"])
                self.assertFalse(out["release_certified"])

    def test_original_sha_bound_for_each_file(self):
        out = self.analyze()
        self.assertEqual(out["feature_count"], 1)
        self.assertEqual(out["feature_sources"][0]["raw_file"]["sha256"],
                         self.req["feature_sources"][0]["file"]["sha256"])

    def test_model_hash_tampering_rejected(self):
        code = dict(self.req["model_code"], sha256="sha256:" + "0"*64)
        with self.assertRaisesRegex(ValueError, "ARTIFACT_HASH_MISMATCH"):
            self.analyze(model_code=code)

    def test_feature_hash_tampering_rejected(self):
        source = dict(self.req["feature_sources"][0])
        source["file"] = dict(source["file"], sha256="sha256:" + "0"*64)
        with self.assertRaisesRegex(ValueError, "ARTIFACT_HASH_MISMATCH"):
            self.analyze(feature_sources=[source])

    def test_feature_published_after_freeze_is_rejected(self):
        row = dict(self.req["feature_sources"][0],
                   published_utc="2026-11-16T01:01:00Z")
        with self.assertRaisesRegex(ValueError, "FEATURE_PUBLICATION_OR_CAPTURE_AFTER_FREEZE"):
            self.analyze(feature_sources=[row])

    def test_feature_capture_after_freeze_is_rejected(self):
        row = dict(self.req["feature_sources"][0],
                   captured_utc="2026-11-16T01:01:00Z")
        with self.assertRaisesRegex(ValueError, "FEATURE_PUBLICATION_OR_CAPTURE_AFTER_FREEZE"):
            self.analyze(feature_sources=[row])

    def test_data_through_after_published_rejected(self):
        row = dict(self.req["feature_sources"][0],
                   data_through_utc="2026-11-16T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "FEATURE_PUBLICATION_OR_CAPTURE_AFTER_FREEZE"):
            self.analyze(feature_sources=[row])

    def test_duplicate_feature_sources_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_INVALID_FEATURE"):
            self.analyze(feature_sources=self.req["feature_sources"] * 2)

    def test_no_feature_snapshot_cannot_freeze(self):
        with self.assertRaisesRegex(ValueError, "NONEMPTY_BOUNDED_FEATURE"):
            self.analyze(feature_sources=[])

    def test_missing_config_file_fails_closed(self):
        cfg = dict(self.req["model_config"], path=str(self.root / "missing.json"))
        with self.assertRaisesRegex(ValueError, "MISSING_REGULAR_SOURCE"):
            self.analyze(model_config=cfg)

    def test_model_file_outside_repository_cannot_claim_repo_code(self):
        model = dict(self.req["model_code"], path="../../etc/passwd")
        with self.assertRaisesRegex(ValueError, "INVALID_MODEL_CODE_PATH"):
            self.analyze(model_code=model)

    def test_training_cutoff_after_registration_rejected(self):
        with self.assertRaisesRegex(ValueError, "TRAIN_FREEZE_EVENT"):
            self.analyze(training_cutoff_utc="2026-11-16T00:30:00Z")

    def test_naive_freeze_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "UTC_REQUIRED"):
            self.analyze(freeze_utc="2026-11-16T01:00:00")

    def test_retroactive_freeze_disallowed(self):
        with self.assertRaisesRegex(ValueError, "FREEZE_NOT_PROSPECTIVE"):
            analyze(self.req, actual_now=NOW+timedelta(minutes=8))

    def test_after_kickoff_cannot_archive(self):
        with self.assertRaisesRegex(ValueError, "FREEZE_NOT_PROSPECTIVE"):
            analyze(self.req, actual_now=NOW+timedelta(hours=2))

    def test_future_declared_freeze_cannot_archive(self):
        with self.assertRaisesRegex(ValueError, "FREEZE_NOT_PROSPECTIVE"):
            analyze(self.req, actual_now=NOW-timedelta(minutes=3))

    def test_duplicate_json_keys_forbidden(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            _parse(b'{"schema":"A","schema":"B"}')

    def test_nan_json_forbidden(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
            _parse(b'{"bad":NaN}')

    def test_private_create_only_archive(self):
        src = self.root / "request.json"
        src.write_text(json.dumps(self.req))
        src.chmod(0o600)
        dst = self.root / "freeze_archive.json"
        result = freeze_file(src, dst, actual_now=NOW)
        payload = json.loads(dst.read_text())
        self.assertEqual(payload["original_request_sha256"],
                         "sha256:" + sha256(src.read_bytes()).hexdigest())
        self.assertEqual(payload["model_code"]["sha256"], result["model_code"]["sha256"])
        self.assertEqual(dst.stat().st_mode & 0o777, 0o600)
        self.assertEqual(payload["approved_stake_u"], 0)
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_NEW"):
            freeze_file(src, dst, actual_now=NOW)

    def test_public_repo_output_refused(self):
        src = self.root / "private_request.json"
        src.write_text(json.dumps(self.req))
        src.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "PUBLIC_REPOSITORY_PATH"):
            freeze_file(src, ROOT / "insecure_public_freeze.json", actual_now=NOW)

    def test_source_mode_0644_refused(self):
        feature_path = Path(self.req["feature_sources"][0]["file"]["path"])
        feature_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "PRIVATE_FILE_PERMISSIONS_REQUIRED"):
            self.analyze()

    def test_policy_id_is_not_caller_supplied(self):
        self.assertEqual(self.analyze()["policy_version"],
                         "SPORTSEDGE_STRICT_V21_V22_20261115_R1")
        with self.assertRaisesRegex(ValueError, "INVALID_FREEZE_REQUEST_FIELDS"):
            self.analyze(policy_version="FAKE_APPROVED")


if __name__ == "__main__":
    unittest.main()
