"""Optional, allowlisted nflverse release capture with GitHub asset digest validation.

NO automatic sportsbook capture. NO scraping. Operator must explicitly run;
not called from cards or CI. Raw original gz bytes saved to a private directory.
GitHub release updated_at is NOT proof of original PIT publication time.
Examples:
 python -m sportsedge.markets.public_release_capture NFL_WEEKLY_2026 /private/archives
 python -m sportsedge.markets.public_release_capture NFL_NGS_PASS /private/archives
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
import json
import os
import re
import sys

from .source_ingestion import parse_snapshot_bytes, SourceReceipt
from .nfl_pbp_streaming import scan_pbp_gzip

REPO="nflverse/nflverse-data"
REPOSITORY_ROOT=Path(__file__).resolve().parents[2]


def require_private_archive_path(destination):
    """Reject every path inside the repository, independently of process CWD.

    This is a local filesystem guard, not cryptographic evidence of a
    privately hosted or immutable archive. Resolving paths catches symlinks.
    """
    resolved=Path(destination).resolve()
    if resolved==REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents:
        raise ValueError("RECEIPT_ARCHIVE_MUST_BE_OUTSIDE_PUBLIC_REPOSITORY")
    return resolved

ASSETS={
    "NFL_WEEKLY_2026":("stats_player","stats_player_week_2026.csv.gz","NFLVERSE_WEEKLY"),
    "NFL_PBP_2026":("pbp","play_by_play_2026.csv.gz","NFLVERSE_PBP"),
    "NFL_NGS_PASS":("nextgen_stats","ngs_passing.csv.gz","NFLVERSE_NGS"),
    "NFL_NGS_RUSH":("nextgen_stats","ngs_rushing.csv.gz","NFLVERSE_NGS"),
    "NFL_NGS_RECEIVE":("nextgen_stats","ngs_receiving.csv.gz","NFLVERSE_NGS"),
}


def allowed_asset_url(tag: str, name: str, url: str) -> bool:
    """Require exact documented GitHub release URL, not arbitrary caller URL."""
    return url==f"https://github.com/{REPO}/releases/download/{tag}/{name}"


def get_release_asset_info(asset_id: str, opener=urlopen) -> dict:
    if asset_id not in ASSETS:
        raise ValueError("UNREGISTERED_PUBLIC_RELEASE_ASSET")
    tag,name,source_id=ASSETS[asset_id]
    endpoint=f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"
    with opener(Request(endpoint,headers={"Accept":"application/vnd.github+json",
                "User-Agent":"SportsEdge-Research-SourceAudit"}),timeout=30) as response:
        release=json.load(response)
    matches=[a for a in release.get("assets",[]) if a.get("name")==name]
    if len(matches)!=1:
        raise ValueError("PUBLIC_RELEASE_ASSET_NOT_FOUND_OR_DUPLICATED")
    asset=matches[0]
    if not allowed_asset_url(tag,name,asset.get("browser_download_url","")):
        raise ValueError("PUBLIC_RELEASE_ASSET_URL_NOT_ALLOWLISTED")
    digest=asset.get("digest","")
    if not isinstance(digest,str) or not re.fullmatch(r"sha256:[0-9a-f]{64}",digest):
        raise ValueError("PROVIDER_DIGEST_MISSING_OR_INVALID")
    return {"asset_id":asset_id,"name":name,"source_id":source_id,
            "url":asset["browser_download_url"],"provider_digest":digest,
            "updated_at":asset.get("updated_at"),"bytes_expected":asset.get("size"),
            "release_id":release.get("id")}


def capture_public_release(asset_id:str, destination:Path | str, *,
                           max_download_bytes:int=95_000_000,
                           opener=urlopen) -> dict:
    # Validate destination BEFORE any outbound provider call or source write.
    dest=require_private_archive_path(destination)
    metadata=get_release_asset_info(asset_id,opener=opener)
    with opener(Request(metadata["url"],headers={
                "User-Agent":"SportsEdge-Research-SourceAudit"}),timeout=60) as response:
        raw=response.read(max_download_bytes+1)
    if not raw or len(raw)>max_download_bytes:
        raise ValueError("PUBLIC_RELEASE_DOWNLOAD_EMPTY_OR_EXCESSIVE")
    digest="sha256:"+sha256(raw).hexdigest()
    if digest!=metadata["provider_digest"]:
        raise ValueError("GITHUB_RELEASE_SHA256_MISMATCH")
    if len(raw)!=metadata["bytes_expected"]:
        raise ValueError("GITHUB_RELEASE_SIZE_MISMATCH")
    now=datetime.now(timezone.utc)
    try:
        claimed_updated=datetime.fromisoformat(metadata["updated_at"].replace("Z","+00:00"))
    except (AttributeError,ValueError) as exc:
        raise ValueError("PROVIDER_RELEASE_DATE_MISSING") from exc
    if claimed_updated>now:
        raise ValueError("FUTURE_DATED_PROVIDER_RELEASE")
    if asset_id == "NFL_PBP_2026":
        # Large PBP CSV is validated as a bounded gzip stream. Do not
        # materialize tens of thousands of 372-column rows or assume the
        # generic small-CSV 80MB decompressed budget covers the full season.
        header, row_count = scan_pbp_gzip(raw)
        receipt = SourceReceipt(
            metadata["source_id"], now, claimed_updated, digest,
            len(raw), row_count, header,
        )
        scan_mode = "BOUNDED_STREAMING_GZIP_CSV"
    else:
        receipt, _ = parse_snapshot_bytes(
            metadata["source_id"], raw, claimed_updated, now,
        )
        scan_mode = "GENERIC_CSV_OR_GZIP"
    dest.mkdir(mode=0o700,parents=True,exist_ok=True)
    final=dest / (metadata["asset_id"]+"_"+digest.split(":")[1][:16]+".csv.gz")
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(final,flags,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        final.unlink(missing_ok=True)
        raise
    manifest={
        "state":"RAW_PUBLIC_SOURCE_ARCHIVED_RESEARCH_ONLY",
        "sport":"NFL","asset":asset_id,"origin":metadata["url"],
        "original_bytes_sha256":receipt.sha256_raw,
        "provider_digest":metadata["provider_digest"],
        "size":receipt.bytes_length,"rows":receipt.record_count,
        "source_schema_scan_mode":scan_mode,
        "provider_updated_at_claim":metadata["updated_at"],
        "retrieved_at_utc":now.isoformat(),
        "actual_data_coverage_checked":False,
        "source_authentication_verified":False,
        "point_in_time_feature_admissible":False,
        "official_counted":0,"approved_stake_u":0,
    }
    mpath=final.with_suffix(final.suffix+".manifest.json")
    with mpath.open("x",encoding="utf-8") as f:
        json.dump(manifest,f,indent=2,sort_keys=True)
    return manifest


if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("Usage: python -m sportsedge.markets.public_release_capture <asset_id> <private_archivedir>")
    print(json.dumps(capture_public_release(sys.argv[1],sys.argv[2]),indent=2))
