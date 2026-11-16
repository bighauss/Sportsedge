"""Synthetic, adversarial tests: authenticated Firecrawl transport and sealed archive."""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError

from cryptography.fernet import Fernet

from sportsedge.validation.firecrawl_espn_forward_archive import (
    BUNDLE_SCHEMA, URL, InjuryEvidenceError, capture, fetch_original,
)
from sportsedge.validation.test_firecrawl_espn_injury_intake import (
    NOW, START, blob, fixture,
)
from sportsedge.validation.seven_sport_pit_freeze import ROOT


class HTTPResponse:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self, max_bytes):
        return self.raw[:max_bytes]


class FirecrawlAuthenticatedForwardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.scratch = self.root / "private"
        self.artifact = self.root / "artifact"
        for folder in (self.scratch, self.artifact):
            folder.mkdir(mode=0o700)
        self.key = Fernet.generate_key().decode("ascii")
        self.response = blob(fixture())
        self.calls = []

    def fake(self, req, timeout):
        self.calls.append((req, timeout))
        return HTTPResponse(self.response)

    def capture(self, **opts):
        return capture(private_dir=opts.get("scratch", self.scratch),
                       artifact_dir=opts.get("artifact", self.artifact),
                       team=opts.get("team", "CHI"),
                       event_id=opts.get("event_id", "SYNTHETIC-NFL-EVENT"),
                       event_start_utc=opts.get("start", START),
                       api_key=opts.get("api_key", "fc-test-example-auth-key-000"),
                       archive_key=opts.get("archive_key", self.key),
                       run_id=opts.get("run_id", "test-123"),
                       now=opts.get("now", NOW),
                       opener=opts.get("opener", self.fake))

    def test_one_authenticated_request_no_other_source_or_retry(self):
        result = self.capture()
        self.assertEqual(len(self.calls), 1)
        req, timeout = self.calls[0]
        self.assertEqual(req.full_url, URL)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(timeout, 30)
        self.assertEqual(req.get_header("Authorization"),
                         "Bearer fc-test-example-auth-key-000")
        self.assertTrue(req.get_header("X-request-id").startswith("test-123-"))
        self.assertEqual(json.loads(req.data), {
            "alexandria": {"provider": "espn-com",
                           "capability": "sports-data/injuries",
                           "options": {"sport": "football", "league": "nfl",
                                       "team": "CHI"}}
        })
        self.assertEqual(result["state"],
                         "PAPER_0U_UNAUTHENTICATED_INJURY_CONTEXT")
        self.assertEqual(result["official_counted"], 0)
        self.assertEqual(result["approved_stake_u"], 0)
        self.assertFalse(result["gate_a_closed"])
        self.assertFalse(result["gate_b_closed"])
        self.assertFalse(result["gate_c_closed"])
        self.assertFalse(result["gate_d_closed"])
        self.assertFalse(result["gate_e_closed"])

    def test_persistent_archive_contains_exact_original_after_decrypt_only(self):
        status = self.capture()
        public = self.artifact / "firecrawl-status-test-123.json"
        cipher_file = self.artifact / "firecrawl-archive-test-123.fernet"
        self.assertTrue(public.is_file())
        self.assertTrue(cipher_file.is_file())
        self.assertEqual(public.stat().st_mode & 0o777, 0o600)
        self.assertEqual(cipher_file.stat().st_mode & 0o777, 0o600)
        ciphertext = cipher_file.read_bytes()
        self.assertNotIn(b"SYNTHETIC_PLAYER_", ciphertext)
        self.assertNotIn(b"SYNTHETIC_PLAYER_", public.read_bytes())
        self.assertNotIn(b"fc-test-example-auth-key", public.read_bytes())
        unsealed = Fernet(self.key).decrypt(ciphertext)
        inside = json.loads(gzip.decompress(unsealed))
        self.assertEqual(inside["schema"], BUNDLE_SCHEMA)
        raw = base64.b64decode(inside["original_http_response_b64"], validate=True)
        self.assertEqual(raw, self.response)
        self.assertEqual(inside["original_http_response_sha256"],
                         "sha256:" + sha256(raw).hexdigest())
        receipt = inside["sanitized_intake_receipt"]
        self.assertEqual(receipt["original_response_sha256"],
                         "sha256:" + sha256(self.response).hexdigest())
        self.assertFalse(receipt["model_feature_admissible"])
        self.assertEqual(status["encrypted_bytes_sha256"],
                         "sha256:" + sha256(ciphertext).hexdigest())

    def test_scratch_plaintext_deleted_after_success(self):
        self.capture()
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_missing_credential_preflight_zero_network_calls(self):
        for missing in ("api_key", "archive_key"):
            with self.subTest(missing=missing):
                with self.assertRaises(ValueError):
                    self.capture(**{missing: ""})
                self.assertEqual(len(self.calls), 0)
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(list(self.artifact.iterdir()), [])

    def test_malformed_archive_encryption_key_preflight_before_billing(self):
        with self.assertRaisesRegex(ValueError, "INVALID_FERNET"):
            self.capture(archive_key="not-a-valid-fernet-key")
        self.assertEqual(self.calls, [])

    def test_post_event_or_unverified_event_binding_block_before_billing(self):
        with self.assertRaisesRegex(ValueError, "EVENT_ALREADY_STARTED"):
            self.capture(now=NOW+timedelta(hours=3))
        with self.assertRaisesRegex(ValueError, "EXPLICIT_EVENT_ID"):
            self.capture(event_id="bad space")
        with self.assertRaisesRegex(ValueError, "EXPLICIT_NFL_TEAM"):
            self.capture(team="CHICAGO Bears")
        self.assertEqual(self.calls, [])

    def test_reuse_run_id_does_not_rebill_or_overwrite(self):
        self.capture()
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_NEW"):
            self.capture()
        self.assertEqual(len(self.calls), 1)

    def test_private_repo_or_world_readable_directory_refused_preflight(self):
        self.scratch.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "PRIVATE_PARENT_PERMISSIONS"):
            self.capture()
        self.assertEqual(self.calls, [])
        self.scratch.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "PUBLIC_REPOSITORY_PATH"):
            self.capture(scratch=ROOT)
        self.assertEqual(self.calls, [])

    def test_provider_failure_does_not_publish_or_keep_unencrypted_files(self):
        d = deepcopy(fixture())
        d["data"]["alexandria"][0]["provider"] = "unauthorized-site"
        self.response = blob(d)
        with self.assertRaisesRegex(InjuryEvidenceError, "WRONG_PROVIDER"):
            self.capture()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(list(self.artifact.iterdir()), [])

    def test_active_only_block_is_still_encrypted_without_admitting_features(self):
        d = deepcopy(fixture())
        for row in d["data"]["alexandria"][0]["data"]["teams"][0]["injuries"]:
            row["status"] = "Active"
        self.response = blob(d)
        out = self.capture()
        self.assertEqual(out["state"], "BLOCK_INJURY_CONTEXT_INCOMPLETE_OR_STALE")
        self.assertFalse(out["gate_b_closed"])
        self.assertEqual(out["approved_stake_u"], 0)

    def test_wrong_provider_http_status_no_plaintext_or_artifact(self):
        def opener(request, timeout):
            self.calls.append((request, timeout))
            response = HTTPResponse(self.response)
            response.status = 401
            return response
        with self.assertRaisesRegex(InjuryEvidenceError, "NOT_200"):
            self.capture(opener=opener)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(list(self.artifact.iterdir()), [])

    def test_http_error_does_not_log_provider_body_or_retry(self):
        def opener(request, timeout):
            self.calls.append((request, timeout))
            raise HTTPError(request.full_url, 403, "token-was-revoked",
                            None, None)
        with self.assertRaisesRegex(InjuryEvidenceError, "BLOCKED_403"):
            self.capture(opener=opener)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_timeout_or_dns_uncertain_never_auto_retries(self):
        def opener(request, timeout):
            self.calls.append((request, timeout))
            raise URLError("PRIVATE_URL_OR_TOKEN_SHOULD_NOT_APPEAR")
        with self.assertRaisesRegex(InjuryEvidenceError, "UNCERTAIN_NO_AUTORETRY"):
            self.capture(opener=opener)
        self.assertEqual(len(self.calls), 1)

    def test_truncated_or_zero_response_rejected(self):
        for raw in (b"", b"x" * (10_000_001)):
            with self.subTest(size=len(raw)):
                self.response = raw
                with self.assertRaisesRegex(InjuryEvidenceError, "ORIGINAL_SIZE"):
                    self.capture()
                self.assertEqual(list(self.artifact.iterdir()), [])

    def test_non_utc_capture_clock_fails_closed_before_network(self):
        with self.assertRaisesRegex(InjuryEvidenceError, "ACTUAL_CLOCK"):
            self.capture(now=datetime(2026, 11, 16, 5, 9))
        self.assertEqual(self.calls, [])

    def test_existing_status_path_also_blocks_before_bill(self):
        (self.artifact / "firecrawl-status-test-123.json").write_text("reserved")
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_NEW"):
            self.capture()
        self.assertEqual(self.calls, [])

    def test_symlink_artifact_directory_refused(self):
        alias = self.root / "alias"
        alias.symlink_to(self.artifact, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "SYMLINK"):
            self.capture(artifact=alias)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
