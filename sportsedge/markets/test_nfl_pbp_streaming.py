"""Bounded nflverse PBP source validation; synthetic bytes, no network calls."""
from __future__ import annotations

import csv
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from sportsedge.markets.nfl_pbp_streaming import scan_pbp_gzip
from sportsedge.markets.public_release_capture import capture_public_release

FIELDS = (
    "game_id", "week", "posteam", "defteam", "epa", "wp", "pass",
    "rush", "description",
)


def source_csv(rows=None, fields=FIELDS):
    if rows is None:
        rows = [
            ["2026_01_CHI_GB","1","CHI","GB","0.31","0.58","1","0","pass play"],
            ["2026_01_CHI_GB","1","","GB","","0.23","0","0","kickoff"],
        ]
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def source_gzip(rows=None, fields=FIELDS):
    return gzip.compress(source_csv(rows, fields), mtime=0)


class PublicPBPStreamingScanTests(unittest.TestCase):
    def test_valid_pbp_schema_and_all_rows_counted(self):
        header, count = scan_pbp_gzip(source_gzip())
        self.assertEqual(count, 2)
        self.assertTrue({"game_id", "epa", "pass", "rush"}.issubset(header))

    def test_embedded_newline_in_quoted_text_does_not_split_records(self):
        rows = [
            ["2026_01_CHI_GB","1","CHI","GB","0.2","0.5","1","0","pass\ncompleted"],
        ]
        _, count = scan_pbp_gzip(source_gzip(rows))
        self.assertEqual(count, 1)

    def test_missing_mandatory_column_rejected_not_inferred(self):
        fields = tuple(x for x in FIELDS if x!="epa")
        rows = [["2026_01_CHI_GB","1","CHI","GB","0.5","1","0","pass"]]
        with self.assertRaisesRegex(ValueError, "PBP_MISSING_EPA_REQUIRED_COLUMNS"):
            scan_pbp_gzip(source_gzip(rows, fields))

    def test_duplicate_csv_headers_rejected_including_case(self):
        fields = list(FIELDS)
        fields[-1] = "Game_ID"
        with self.assertRaisesRegex(ValueError, "PBP_EMPTY_OR_DUPLICATE_CSV_HEADER"):
            scan_pbp_gzip(source_gzip(fields=fields))

    def test_broken_ragged_rows_block(self):
        rows = [
            ["2026_01_CHI_GB","1","CHI","GB","0.2","0.5","1","0"],
        ]
        with self.assertRaisesRegex(ValueError,"PBP_RAGGED_CSV_ROW"):
            scan_pbp_gzip(source_gzip(rows))
        extra = [
            ["2026_01_CHI_GB","1","CHI","GB","0.2","0.5","1","0","a","unexpected"],
        ]
        with self.assertRaisesRegex(ValueError,"PBP_RAGGED_CSV_ROW"):
            scan_pbp_gzip(source_gzip(extra))

    def test_blank_game_or_week_rejected(self):
        for game, week in (("", "1"), ("2026_01_CHI_GB", ""), ("2026_01_CHI_GB", "NaN")):
            rows = [[game,week,"CHI","GB","0.1","0.4","1","0","pass"]]
            with self.subTest((game,week)),self.assertRaisesRegex(ValueError,"PBP_MISSING_EVENT_OR_WEEK"):
                scan_pbp_gzip(source_gzip(rows))

    def test_no_data_records_refused(self):
        with self.assertRaisesRegex(ValueError, "PBP_NO_CSV_RECORDS"):
            scan_pbp_gzip(source_gzip(rows=[]))

    def test_gzip_crc_truncation_rejected(self):
        with self.assertRaisesRegex(ValueError,"PBP_GZIP_OR_CSV_DECODE_FAILED"):
            scan_pbp_gzip(source_gzip()[:-5])

    def test_bad_utf8_refused_without_dumping_raw_bytes(self):
        raw = source_csv() + b"\xff"
        with self.assertRaisesRegex(ValueError,"PBP_GZIP_OR_CSV_DECODE_FAILED"):
            scan_pbp_gzip(gzip.compress(raw,mtime=0))

    def test_record_count_and_decoded_byte_caps(self):
        raw = source_gzip()
        with self.assertRaisesRegex(ValueError,"PBP_RECORD_COUNT_EXCEEDS_CAP"):
            scan_pbp_gzip(raw,max_rows=1)
        huge = [["2026_01_CHI_GB","1","CHI","GB","0.2","0.5","1","0","x"*3000]]
        with self.assertRaisesRegex(ValueError,"PBP_DECOMPRESSED_BYTES_EXCEED_LIMIT"):
            scan_pbp_gzip(source_gzip(huge),max_decoded_bytes=1024)

    def test_physical_line_cap_prevents_memory_attack(self):
        huge = [["2026_01_CHI_GB","1","CHI","GB","0.2","0.5","1","0","x"*500]]
        with self.assertRaisesRegex(ValueError,"PBP_CSV_PHYSICAL_LINE_TOO_LONG"):
            scan_pbp_gzip(source_gzip(huge),max_line_bytes=128)

    def test_plain_csv_or_invalid_limits_refused(self):
        with self.assertRaisesRegex(ValueError,"PBP_GZIP_RAW_BYTES_REQUIRED"):
            scan_pbp_gzip(source_csv())
        with self.assertRaisesRegex(ValueError,"INVALID_PBP_SCAN_CAP"):
            scan_pbp_gzip(source_gzip(),max_rows=0)

    def test_real_capture_path_uses_streaming_and_keeps_original_digest(self):
        raw = source_gzip()
        expected_sha = "sha256:"+sha256(raw).hexdigest()
        metadata = {
            "asset_id": "NFL_PBP_2026",
            "name": "play_by_play_2026.csv.gz",
            "source_id": "NFLVERSE_PBP",
            "url": ("https://github.com/nflverse/nflverse-data/releases/download/"
                    "pbp/play_by_play_2026.csv.gz"),
            "provider_digest": expected_sha,
            "updated_at": "2026-11-15T12:00:00Z",
            "bytes_expected": len(raw),
            "release_id": 777,
        }
        with tempfile.TemporaryDirectory(prefix="sportsedge-nfl-pbp-") as temp:
            with patch(
                "sportsedge.markets.public_release_capture.get_release_asset_info",
                return_value=metadata,
            ):
                result = capture_public_release(
                    "NFL_PBP_2026", Path(temp),
                    opener=lambda *_args, **_kwargs: io.BytesIO(raw),
                )
            self.assertEqual(result["rows"],2)
            self.assertEqual(result["provider_digest"],expected_sha)
            self.assertEqual(result["original_bytes_sha256"],expected_sha)
            self.assertEqual(result["source_schema_scan_mode"],"BOUNDED_STREAMING_GZIP_CSV")
            self.assertFalse(result["point_in_time_feature_admissible"])
            self.assertFalse(result["source_authentication_verified"])
            original=list(Path(temp).glob("NFL_PBP_2026_*.csv.gz"))
            self.assertEqual(len(original),1)
            self.assertEqual(original[0].read_bytes(),raw)
            self.assertEqual(stat.S_IMODE(original[0].stat().st_mode),0o600)

    def test_provider_digest_mismatch_blocks_before_source_write(self):
        raw = source_gzip()
        metadata = {
            "asset_id": "NFL_PBP_2026",
            "name": "play_by_play_2026.csv.gz",
            "source_id": "NFLVERSE_PBP",
            "url": ("https://github.com/nflverse/nflverse-data/releases/download/"
                    "pbp/play_by_play_2026.csv.gz"),
            "provider_digest": "sha256:"+"a"*64,
            "updated_at": "2026-11-15T12:00:00Z",
            "bytes_expected": len(raw),
            "release_id": 777,
        }
        with tempfile.TemporaryDirectory(prefix="sportsedge-nfl-pbp-") as temp:
            with patch(
                "sportsedge.markets.public_release_capture.get_release_asset_info",
                return_value=metadata,
            ):
                with self.assertRaisesRegex(ValueError,"GITHUB_RELEASE_SHA256_MISMATCH"):
                    capture_public_release(
                        "NFL_PBP_2026", Path(temp),
                        opener=lambda *_args, **_kwargs: io.BytesIO(raw),
                    )
            self.assertFalse(list(Path(temp).glob("*.csv.gz")))


if __name__ == "__main__":
    unittest.main()
