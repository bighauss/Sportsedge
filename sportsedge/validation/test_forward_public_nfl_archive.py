"""Pure synthetic source-capture tests; the real workflow fetches nflverse assets."""
from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsedge.validation.forward_public_nfl_archive import prospective_archive, utc, ALLOWED

NOW = datetime(2026, 11, 15, 22, 0, tzinfo=timezone.utc)


def fake_capture(asset, folder):
    raw = ("public-" + asset).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    p = Path(folder) / (asset + "_" + digest[7:23] + ".csv.gz")
    with p.open("xb") as f:
        f.write(raw)
    return {"asset": asset, "state": "RAW_PUBLIC_SOURCE_ARCHIVED_RESEARCH_ONLY",
            "original_bytes_sha256": digest, "size": len(raw), "rows": 3,
            "provider_updated_at_claim": "2026-11-15T08:00:00Z",
            "retrieved_at_utc": NOW.isoformat()}


class ProspectiveArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name) / "private_archive"

    def run_archive(self, **kw):
        return prospective_archive(self.parent, assets=kw.pop("assets", ("NFL_WEEKLY_2026",)),
                                   capture=kw.pop("capture", fake_capture), now_utc=kw.pop("now_utc", NOW), **kw)

    def test_pregame_capture_keeps_original_bytes_and_research_only(self):
        folder, manifest = self.run_archive(event_id="LAC_BAL_20261116",
                                           event_start_utc="2026-11-17T01:15:00Z")
        self.assertTrue(manifest["collected_before_declared_event"])
        self.assertEqual(manifest["captured_asset_count"], 1)
        self.assertEqual(manifest["official_counted"], 0)
        self.assertEqual(manifest["approved_stake_u"], 0)
        self.assertFalse(manifest["point_in_time_feature_admissible_for_betting"])
        self.assertEqual(json.loads((folder/"capture_manifest.json").read_text())["state"],
                         "PAPER_0U_RAW_PUBLIC_SOURCE_CAPTURE")

    def test_future_capture_uses_injected_clock_and_fails_closed(self):
        def future_capture(asset, folder):
            m = fake_capture(asset, folder)
            m["retrieved_at_utc"] = (NOW + timedelta(seconds=1)).isoformat()
            return m
        with self.assertRaisesRegex(RuntimeError, "FUTURE_CAPTURE_TIMESTAMP"):
            self.run_archive(capture=future_capture)
        manifests = list(self.parent.glob("forward_nfl_*/capture_manifest.json"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(json.loads(manifests[0].read_text())["state"], "BLOCK_INCOMPLETE_PUBLIC_CAPTURE")

    def test_github_provenance_claims_are_not_authentication(self):
        with patch.dict("os.environ", {"GITHUB_SHA": "abc123", "GITHUB_REF": "refs/heads/main"}):
            _, m = self.run_archive()
        self.assertEqual(m["github_sha_claim"], "abc123")
        self.assertEqual(m["github_ref_claim"], "refs/heads/main")
        self.assertFalse(m["independent_original_source_authentication"])

    def test_no_event_does_not_claim_pregame(self):
        _, manifest = self.run_archive()
        self.assertFalse(manifest["collected_before_declared_event"])

    def test_started_game_not_pregame_even_with_raw_data(self):
        _, m = self.run_archive(event_id="SEA_LV_20261115",
                                event_start_utc="2026-11-15T21:05:00Z")
        self.assertFalse(m["collected_before_declared_event"])

    def test_multiple_assets_all_originals(self):
        _, m = self.run_archive(assets=ALLOWED)
        self.assertEqual(m["captured_asset_count"], len(ALLOWED))
        self.assertEqual({o["asset_id"] for o in m["asset_receipts"]}, set(ALLOWED))

    def test_dup_asset_and_unregistered_rejected(self):
        for assets in (("NFL_WEEKLY_2026",)*2, ("UNKNOWN",)):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                self.run_archive(assets=assets)

    def test_event_pair_required(self):
        with self.assertRaises(ValueError):
            self.run_archive(event_id="NFL_GAME")
        with self.assertRaises(ValueError):
            self.run_archive(event_start_utc="2026-11-17T01:15:00Z")

    def test_bad_target_or_event_id_rejected(self):
        with self.assertRaises(ValueError):
            self.run_archive(event_id="../../etc", event_start_utc="2026-11-17T01:15:00Z")
        with self.assertRaises(ValueError):
            self.run_archive(event_id="LAC_BAL", event_start_utc="2026-11-17T01:15:00")

    def test_original_digest_mutation_rejected(self):
        def corrupt(asset, dest):
            m = fake_capture(asset, dest)
            p = next(Path(dest).glob("*.csv.gz"))
            p.write_bytes(p.read_bytes() + b"tampered")
            return m
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_RAW_NOT_STORED_OR_MUTATED"):
            self.run_archive(capture=corrupt)
        saved = list(self.parent.glob("forward_nfl_*/capture_manifest.json"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(json.loads(saved[0].read_text())["state"], "BLOCK_INCOMPLETE_PUBLIC_CAPTURE")

    def test_failed_fetch_no_fake_success(self):
        def fail(*args):
            raise IOError("provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            self.run_archive(capture=fail)

    def test_create_only_slug_collision(self):
        self.run_archive(run_id="test001")
        with self.assertRaises(FileExistsError):
            self.run_archive(run_id="test001")

    def test_bad_run_id_rejected(self):
        with self.assertRaises(ValueError):
            self.run_archive(run_id="../escape")

    def test_utc_requires_explicit_offset(self):
        with self.assertRaises(ValueError):
            utc("2026-11-16T19:15:00")
        self.assertEqual(utc("2026-11-17T01:15:00Z").utcoffset(),timedelta(0))


if __name__ == "__main__":
    unittest.main()
