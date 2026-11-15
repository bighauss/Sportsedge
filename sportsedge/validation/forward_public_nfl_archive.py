"""Prospective, create-only nflverse PUBLIC asset capture for forward research.

No sportsbook collection, no signed provider transport, and NO official betting
admission. GitHub Actions artifact timestamps are independent evidence of the
CI run occurring, not a cryptographic certificate of source publication.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from sportsedge.markets.public_release_capture import ASSETS, capture_public_release

ALLOWED = ("NFL_WEEKLY_2026", "NFL_NGS_PASS", "NFL_NGS_RUSH", "NFL_NGS_RECEIVE")
EVENT_ID_RE = re.compile(r"[a-zA-Z0-9_.:-]{1,96}\Z")
RUN_RE = re.compile(r"[0-9a-zA-Z_-]{1,64}\Z")


def utc(raw):
    try:
        date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as e:
        raise ValueError("INVALID_TARGET_KICKOFF_UTC") from e
    if date.tzinfo is None or date.utcoffset().total_seconds() != 0:
        raise ValueError("TARGET_KICKOFF_MUST_BE_UTC")
    return date.astimezone(timezone.utc)


def _digest(path):
    return "sha256:" + sha256(Path(path).read_bytes()).hexdigest()


def prospective_archive(private_parent, *, assets=ALLOWED, event_id=None,
                        event_start_utc=None, run_id=None, now_utc=None,
                        capture=capture_public_release):
    now = datetime.now(timezone.utc) if now_utc is None else now_utc
    if now.tzinfo is None or now.utcoffset().total_seconds() != 0:
        raise ValueError("CLOCK_MUST_BE_UTC")
    if (not assets or len(set(assets)) != len(assets) or
            any(asset not in ALLOWED or asset not in ASSETS for asset in assets)):
        raise ValueError("UNREGISTERED_OR_DUPLICATE_PUBLIC_ASSET")
    if (event_id is None) != (event_start_utc is None):
        raise ValueError("EVENT_AND_KICKOFF_MUST_BOTH_BE_SUPPLIED")
    if event_id is not None and not EVENT_ID_RE.fullmatch(event_id):
        raise ValueError("INVALID_EVENT_ID")
    start = utc(event_start_utc) if event_start_utc is not None else None
    if run_id is not None and not RUN_RE.fullmatch(run_id):
        raise ValueError("INVALID_RUN_ID")
    parent = Path(private_parent).resolve()
    cwd = Path.cwd().resolve()
    if parent == cwd or cwd in parent.parents:
        raise ValueError("ARCHIVE_MUST_BE_OUTSIDE_PUBLIC_REPOSITORY")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    slug = now.strftime("%Y%m%dT%H%M%S%fZ") + ("_" + run_id if run_id else "")
    dest = parent / ("forward_nfl_" + slug)
    dest.mkdir(mode=0o700, exist_ok=False)
    observations = []
    failure = None
    try:
        for asset in assets:
            raw_manifest = capture(asset, dest)
            if raw_manifest.get("asset") != asset or raw_manifest.get("state") != "RAW_PUBLIC_SOURCE_ARCHIVED_RESEARCH_ONLY":
                raise ValueError("UNEXPECTED_CAPTURE_STATUS")
            digest = raw_manifest.get("original_bytes_sha256")
            if (not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)):
                raise ValueError("MALFORMED_RAW_DIGEST")
            archives = list(dest.glob(asset + "_" + digest[7:23] + ".csv.gz"))
            if len(archives) != 1 or _digest(archives[0]) != digest:
                raise ValueError("ORIGINAL_RAW_NOT_STORED_OR_MUTATED")
            if archives[0].stat().st_size != raw_manifest.get("size"):
                raise ValueError("ORIGINAL_SIZE_MISMATCH")
            if not raw_manifest.get("retrieved_at_utc"):
                raise ValueError("CAPTURE_TIMESTAMP_MISSING")
            observed = utc(raw_manifest["retrieved_at_utc"])
            # A real download finishes after run start. Injected test clocks remain
            # deterministic; production checks against the actual completion clock.
            observation_clock = now if now_utc is not None else datetime.now(timezone.utc)
            if observed > observation_clock:
                raise ValueError("FUTURE_CAPTURE_TIMESTAMP")
            observations.append({
                "asset_id": asset, "source_id": ASSETS[asset][2],
                "raw_sha256": digest, "raw_bytes": archives[0].stat().st_size,
                "source_rows": raw_manifest.get("rows"),
                "provider_updated_claim": raw_manifest.get("provider_updated_at_claim"),
                "retrieved_at_utc": raw_manifest["retrieved_at_utc"],
                "original_filename": archives[0].name,
                "publisher_publication_authenticated": False,
            })
    except Exception as exc:
        # The caller must receive a failed run; no incomplete collection can
        # look like a complete, valid prospective archive.
        failure = type(exc).__name__ + ":" + str(exc)
    all_before_event = (start is not None and failure is None and now < start and
        all(utc(o["retrieved_at_utc"]) < start for o in observations))
    manifest = {
        "schema": "sportsedge-public-nfl-forward-capture-v1",
        "state": "PAPER_0U_RAW_PUBLIC_SOURCE_CAPTURE" if failure is None else "BLOCK_INCOMPLETE_PUBLIC_CAPTURE",
        "collected_run_start_utc": now.isoformat(),
        "github_run_id_claim": run_id,
        "github_sha_claim": os.environ.get("GITHUB_SHA") or None,
        "github_ref_claim": os.environ.get("GITHUB_REF") or None,
        "event_id_declared": event_id,
        "event_start_utc_declared": start.isoformat() if start else None,
        "collected_before_declared_event": all_before_event,
        "event_identity_source_authenticated": False,
        "sport": "NFL", "captured_asset_count": len(observations),
        "requested_assets": list(assets), "asset_receipts": observations,
        "error": failure,
        "independent_original_source_authentication": False,
        "licensed_sportsbook_quote_captured": False,
        "player_lineup_confirmed": False,
        "real_slate_card_accepted": False,
        "point_in_time_feature_admissible_for_betting": False,
        "official_counted": 0, "approved_stake_u": 0,
    }
    # One manifest, create-only, no tokens / sportsbook data. Stored with the
    # raw public input artifacts and later exposed as a CI run attachment.
    target = dest / "capture_manifest.json"
    with target.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    if failure is not None:
        raise RuntimeError("FORWARD_PUBLIC_CAPTURE_FAILED:" + failure)
    return dest, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_archive_parent")
    parser.add_argument("--event-id")
    parser.add_argument("--event-start-utc")
    parser.add_argument("--assets", nargs="+", choices=ALLOWED, default=list(ALLOWED))
    args = parser.parse_args(argv)
    dest, result = prospective_archive(
        args.private_archive_parent,
        event_id=args.event_id or None,
        event_start_utc=args.event_start_utc or None,
        assets=tuple(args.assets),
        run_id=os.environ.get("GITHUB_RUN_ID") or None,
    )
    # Public/sanitized status only; original payloads are archived, not printed.
    print(json.dumps({"archive_dir": str(dest), "state": result["state"],
        "assets": result["captured_asset_count"],
        "pre_event": result["collected_before_declared_event"],
        "official_counted": 0, "approved_stake_u": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
