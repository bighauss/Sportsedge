#!/usr/bin/env python3
"""Private, point-in-time-constrained archived nflverse PBP -> NFL EPA features.

Consumes the original five-source ZIP captured by GitHub Actions, validates
original PBP bytes and one independent *operator-supplied* per-game availability
manifest, then calls the unchanged EPA ridge research feature builder.

No bookmaker quotes, score betting probabilities, live model promotion or
wagers. All timestamps and source availability are still unauthenticated
until an independent source/clock process verifies them. PAPER / 0u.
"""
from __future__ import annotations

import argparse
import csv
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import zipfile

from epa_ridge_pit import build_ratings, utc
from feature_snapshot_bridge_pit import strict_original_json
from score_walkforward_pit import private_evidence_path, create_private_output
from sportsedge.markets.nfl_pbp_streaming import scan_pbp_gzip

ZIP_BYTES_MAX = 160_000_000
ZIP_ENTRY_COUNT_MAX = 100
ZIP_UNCOMPRESSED_MAX = 250_000_000
PBP_BYTES_MAX = 95_000_000
HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
RATING_COLUMNS = frozenset({
    "game_id", "drive", "play_id", "posteam", "defteam", "pass", "rush",
    "epa", "wp",
})


def _check_hash(value, label):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("INVALID_SOURCE_HASH:" + label)
    return value


def _zip_members(archive):
    infos = archive.infolist()
    if not infos or len(infos) > ZIP_ENTRY_COUNT_MAX:
        raise ValueError("INVALID_ARCHIVE_ENTRY_COUNT")
    names = [i.filename for i in infos]
    if len(set(names)) != len(names):
        raise ValueError("DUPLICATE_ZIP_ARCHIVE_MEMBER")
    for name in names:
        obj = PurePosixPath(name)
        if (obj.is_absolute() or
            any(part in ("..", ".", "") for part in name.split("/")) or
            "\\" in name or ":" in name):
            raise ValueError("ZIP_PATH_TRAVERSAL_OR_NONCANONICAL_MEMBER")
    if sum(i.file_size for i in infos) > ZIP_UNCOMPRESSED_MAX:
        raise ValueError("ZIP_DECLARED_SIZE_EXCEEDS_CAP")
    return names


def _one_json(archive, name, max_bytes=100_000):
    info = archive.getinfo(name)
    if info.file_size > max_bytes:
        raise ValueError("OVERSIZED_ARCHIVED_MANIFEST")
    raw = archive.read(name)
    if len(raw) != info.file_size:
        raise ValueError("TRUNCATED_ARCHIVED_MANIFEST")
    return strict_original_json(raw), raw


def _inspect_archive(archive_bytes, expected_archive_hash, asof_utc):
    _check_hash(expected_archive_hash, "EXPECTED_ARCHIVE")
    if len(archive_bytes) > ZIP_BYTES_MAX or not archive_bytes:
        raise ValueError("ORIGINAL_ARCHIVE_TOO_LARGE_OR_EMPTY")
    original_zip_hash = "sha256:" + sha256(archive_bytes).hexdigest()
    if original_zip_hash != expected_archive_hash:
        raise ValueError("ARCHIVED_GITHUB_ZIP_SHA_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
            members = _zip_members(z)
            manifests = [
                m for m in members if m.endswith("/capture_manifest.json")
            ]
            if len(manifests) != 1:
                raise ValueError("EXACTLY_ONE_ARCHIVED_CAPTURE_MANIFEST_REQUIRED")
            meta_name = manifests[0]
            root = meta_name[: -len("capture_manifest.json")]
            meta, meta_raw = _one_json(z, meta_name)
            if not isinstance(meta, dict) or meta.get("state") != (
                "PAPER_0U_RAW_PUBLIC_SOURCE_CAPTURE"
            ) or meta.get("sport") != "NFL":
                raise ValueError("SOURCE_CAPTURE_NOT_COMPLETE_RESEARCH_ARCHIVE")
            receipts = meta.get("asset_receipts")
            requested = meta.get("requested_assets")
            if not isinstance(receipts, list) or not isinstance(requested, list):
                raise ValueError("SOURCE_ASSET_RECEIPTS_MISSING")
            if (len(receipts) != len(requested) or
                len(receipts) != meta.get("captured_asset_count") or
                len({x.get("asset_id") for x in receipts if isinstance(x, dict)}) != len(receipts) or
                set(requested) != {x.get("asset_id") for x in receipts if isinstance(x, dict)}):
                raise ValueError("SOURCE_ASSET_CENSUS_MISMATCH")
            if requested.count("NFL_PBP_2026") != 1:
                raise ValueError("PBP_ASSET_MISSING_OR_DUPLICATED")
            pbp = next(x for x in receipts if x["asset_id"] == "NFL_PBP_2026")
            if pbp.get("source_id") != "NFLVERSE_PBP":
                raise ValueError("SOURCE_PBP_IDENTITY_MISMATCH")
            basename = pbp.get("original_filename")
            if (not isinstance(basename, str) or
                not re.fullmatch(r"^NFL_PBP_2026_[0-9a-f]{16}\.csv\.gz$", basename)):
                raise ValueError("SOURCE_PBP_BASENAME_INVALID")
            raw_path = root + basename
            sidecar_path = raw_path + ".manifest.json"
            if raw_path not in members or sidecar_path not in members:
                raise ValueError("PBP_OR_SOURCE_RECEIPT_NOT_ARCHIVED")
            file_info = z.getinfo(raw_path)
            if file_info.file_size > PBP_BYTES_MAX or file_info.file_size == 0:
                raise ValueError("ARCHIVED_PBP_COMPRESSED_SIZE_INVALID")
            raw_pbp = z.read(raw_path)
            if len(raw_pbp) != file_info.file_size:
                raise ValueError("ARCHIVED_PBP_TRUNCATED")
            pbp_sha = "sha256:" + sha256(raw_pbp).hexdigest()
            if (_check_hash(pbp.get("raw_sha256"), "PBP_RAW") != pbp_sha or
                pbp.get("raw_bytes") != len(raw_pbp) or
                basename != f"NFL_PBP_2026_{pbp_sha[7:23]}.csv.gz"):
                raise ValueError("ARCHIVED_PBP_HASH_OR_SIZE_MISMATCH")
            sidecar, _ = _one_json(z, sidecar_path)
            if (sidecar.get("original_bytes_sha256") != pbp_sha or
                sidecar.get("provider_digest") != pbp_sha or
                sidecar.get("source_schema_scan_mode") != "BOUNDED_STREAMING_GZIP_CSV" or
                sidecar.get("rows") != pbp.get("source_rows") or
                sidecar.get("retrieved_at_utc") != pbp.get("retrieved_at_utc")):
                raise ValueError("PBP_SIDECAR_SOURCE_IDENTITY_MISMATCH")
            retrieved = utc(pbp["retrieved_at_utc"])
            observed_run_start = utc(meta["collected_run_start_utc"])
            provider_update = utc(sidecar["provider_updated_at_claim"])
            if not (provider_update <= retrieved and
                    observed_run_start <= retrieved <= utc(asof_utc)):
                raise ValueError("PUBLIC_PBP_CAPTURE_AFTER_FORECAST_OR_BAD_CLOCK")
            columns, source_rows = scan_pbp_gzip(raw_pbp)
            if not RATING_COLUMNS.issubset(columns):
                raise ValueError("PBP_RIDGE_PLAY_AND_DRIVE_ID_COLUMNS_MISSING")
            if source_rows != pbp.get("source_rows"):
                raise ValueError("SOURCE_PBP_RECORD_CENSUS_CHANGED")
            return {
                "source_raw_gzip": raw_pbp,
                "original_archive_sha256": original_zip_hash,
                "source_raw_sha256": pbp_sha,
                "original_capture_manifest_sha256": (
                    "sha256:" + sha256(meta_raw).hexdigest()),
                "source_rows": source_rows,
                "source_captured_at_utc": retrieved.isoformat(),
                "provider_release_updated_at_claim": provider_update.isoformat(),
                "collected_before_declared_event_claim": (
                    meta.get("collected_before_declared_event") is True),
                "event_identity_source_authenticated": False,
                "original_source_publication_authenticated": False,
            }
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("INVALID_OR_TRUNCATED_GITHUB_ARCHIVE_ZIP") from exc


def _pbp_rows(raw_gzip):
    with gzip.GzipFile(fileobj=io.BytesIO(raw_gzip), mode="rb") as gz:
        with io.TextIOWrapper(gz, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, restkey="__overflow__", restval=None, strict=True)
            if not RATING_COLUMNS.issubset(reader.fieldnames or []):
                raise ValueError("PBP_MODEL_REQUIRED_COLUMNS_MISSING")
            for row in reader:
                if "__overflow__" in row or any(v is None for v in row.values()):
                    raise ValueError("PBP_MODEL_RAGGED_SOURCE_RECORD")
                yield row


def build_from_archive(
    archive_bytes,
    *,
    expected_archive_sha256,
    game_manifest,
    game_manifest_sha256,
    asof_utc,
    half_life_days=21.0,
    ridge=30.0,
    wp_limits=None,
):
    """No invented game completion or provider data-available timestamps."""
    _check_hash(game_manifest_sha256, "EXPECTED_GAME_MANIFEST")
    if not isinstance(game_manifest, dict) or not game_manifest:
        raise ValueError("SOURCE_GAME_AVAILABILITY_MANIFEST_REQUIRED")
    # JSON actual file hash is checked by the CLI and carried through unchanged.
    upstream = _inspect_archive(archive_bytes, expected_archive_sha256, asof_utc)
    original = upstream.pop("source_raw_gzip")
    scores = build_ratings(
        _pbp_rows(original), game_manifest,
        asof_utc=asof_utc,
        source_observed_utc=upstream["source_captured_at_utc"],
        half_life_days=half_life_days,
        ridge=ridge,
        wp_limits=wp_limits,
    )
    if scores["census"]["source_rows"] != upstream["source_rows"]:
        raise ValueError("PBP_RIDGE_ROW_CENSUS_CHANGED")
    scores["archive_provenance"] = {
        **upstream,
        "operator_game_manifest_sha256": game_manifest_sha256,
        "game_completion_and_availability_independently_attested": False,
        "public_release_original_does_not_authenticate_historical_cutoffs": True,
    }
    scores["official_counted"] = 0
    scores["approved_stake_u"] = 0
    scores["status"] = "PAPER_HOLD_0U"
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", required=True,
                        help="complete original 5-source GitHub Actions ZIP")
    parser.add_argument("--expected-archive-sha256", required=True,
                        help="trusted separately recorded original ZIP SHA256")
    parser.add_argument("--game-manifest", required=True,
                        help="independently maintained game final/availability JSON")
    parser.add_argument("--expected-game-manifest-sha256", required=True)
    parser.add_argument("--asof-utc", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ridge", type=float, default=30.0)
    parser.add_argument("--half-life-days", type=float, default=21.0)
    parser.add_argument("--wp-filter", action="store_true")
    args = parser.parse_args()

    # Validate every private location before reading any source bytes.
    archive_path = private_evidence_path(args.source_archive)
    manifest_path = private_evidence_path(args.game_manifest)
    private_evidence_path(args.out)
    archive_bytes = archive_path.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    manifest_hash = "sha256:" + sha256(manifest_bytes).hexdigest()
    if manifest_hash != _check_hash(
        args.expected_game_manifest_sha256, "GAME_MANIFEST"
    ):
        raise ValueError("GAME_MANIFEST_ORIGINAL_BYTES_HASH_MISMATCH")
    manifest = strict_original_json(manifest_bytes)
    result = build_from_archive(
        archive_bytes,
        expected_archive_sha256=args.expected_archive_sha256,
        game_manifest=manifest,
        game_manifest_sha256=manifest_hash,
        asof_utc=args.asof_utc,
        half_life_days=args.half_life_days,
        ridge=args.ridge,
        wp_limits=(0.1, 0.9) if args.wp_filter else None,
    )
    payload = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) +
               "\n").encode("utf-8")
    create_private_output(args.out, payload)
    print(json.dumps({
        "status": result["status"],
        "out": args.out,
        "source_rows": result["census"]["source_rows"],
        "used_games": result["games_used"],
        "approved_stake_u": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
