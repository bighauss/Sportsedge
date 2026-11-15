"""No-network public-release smoke tests, with synthetic GitHub response fixtures."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import gzip
import json
import unittest

from sportsedge.markets.nflverse_public_research_smoke import (
    verify_weekly_public_archive,
)
from sportsedge.markets.public_release_capture import (
    capture_public_release, get_release_asset_info,
)

PUBLIC_URL=("https://github.com/nflverse/nflverse-data/releases/"
            "download/stats_player/stats_player_week_2026.csv.gz")


def sample_gzip() -> bytes:
    raw=(
        "season,week,season_type,player_id,recent_team,rushing_tds,receiving_tds\n"
        "2026,1,REG,P1,BUF,1,2\n"
        "2026,2,REG,P2,BUF,0,1\n"
        "2026,10,REG,P1,BUF,3,5\n"
    ).encode("utf-8")
    return gzip.compress(raw,mtime=0)


class GitHubReleaseFixture:
    def __init__(self, *, corrupt_digest=False, wrong_url=False):
        self.raw=sample_gzip()
        dig=sha256(self.raw).hexdigest()
        if corrupt_digest:dig="0"*64
        self.meta={
            "tag_name":"stats_player",
            "id":123,
            "assets":[{
                "name":"stats_player_week_2026.csv.gz",
                "browser_download_url":(PUBLIC_URL+"/wrong" if wrong_url else PUBLIC_URL),
                "digest":"sha256:"+dig,
                "size":len(self.raw),
                "updated_at":"2026-11-15T16:21:10Z",
            }]
        }

    def __call__(self, request, timeout=30):
        url=request.full_url if hasattr(request,"full_url") else request
        if url.startswith("https://api.github.com/repos/nflverse/"):
            return BytesIO(json.dumps(self.meta).encode("utf-8"))
        if url==PUBLIC_URL:
            return BytesIO(self.raw)
        raise ValueError("UNEXPECTED_NETWORK_URL")


class PublicReleaseSmoke(unittest.TestCase):
    def test_actual_capture_contract_with_pinned_synthetic_digest(self):
        with TemporaryDirectory() as d:
            out=verify_weekly_public_archive(
                d,require_all_32_teams=False,opener=GitHubReleaseFixture())
            self.assertEqual(out["status"],
                "PUBLIC_SOURCE_HASH_AND_WEEKLY_SCHEMA_CHECKED_RESEARCH_ONLY")
            self.assertEqual(out["total_csv_rows"],3)
            self.assertEqual(out["eligible_regular_season_rows"],2)
            self.assertEqual(out["excluded_post_cutoff_rows"],1)
            self.assertEqual(out["teams_seen_before_cutoff"],1)
            self.assertFalse(out["historical_week9_pregame_reconstruction_certified"])
            self.assertFalse(out["player_td_probabilities_calibrated"])
            self.assertEqual((out["official_counted"],out["approved_stake_u"]),(0,0))
            files=list(Path(d).glob("*.csv.gz"))
            self.assertEqual(len(files),1)
            self.assertEqual(
                "sha256:"+sha256(files[0].read_bytes()).hexdigest(),
                out["source_original_sha256"])

    def test_real_mode_requires_all_32_teams(self):
        with TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"INCOMPLETE_NFL_TEAM_COVERAGE"):
                verify_weekly_public_archive(
                    d,require_all_32_teams=True,opener=GitHubReleaseFixture())

    def test_provider_digest_failure_blocks_before_audit(self):
        with TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"GITHUB_RELEASE_SHA256_MISMATCH"):
                verify_weekly_public_archive(
                    d,require_all_32_teams=False,
                    opener=GitHubReleaseFixture(corrupt_digest=True))
            self.assertFalse(list(Path(d).glob("*.csv.gz")))

    def test_unallowlisted_provider_asset_location_blocked(self):
        with self.assertRaisesRegex(ValueError,"PUBLIC_RELEASE_ASSET_URL_NOT_ALLOWLISTED"):
            get_release_asset_info("NFL_WEEKLY_2026",
                opener=GitHubReleaseFixture(wrong_url=True))

    def test_unregistered_release_is_not_fetched(self):
        with TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"UNREGISTERED_PUBLIC_RELEASE_ASSET"):
                capture_public_release("NFL2026_NOT_APPROVED",d,
                    opener=GitHubReleaseFixture())
            self.assertFalse(list(Path(d).glob("*.csv.gz")))


if __name__=="__main__":
    unittest.main()
