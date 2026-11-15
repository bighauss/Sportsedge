"""Discover 2026 Next Gen Stats public CSV schema from verified GitHub releases.

Original bytes are digest-verified and kept only in private/temp archive.
No player rows or names are printed, no model moments fitted and no odds loaded.
Schema discovery is NOT validation of point-in-time pregame source availability.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from hashlib import sha256
import csv
import gzip
import io
import json
import sys

from .public_release_capture import capture_public_release
from .source_ingestion import parse_snapshot_bytes


NGS_ASSETS = ("NFL_NGS_PASS", "NFL_NGS_RUSH", "NFL_NGS_RECEIVE")


def inspect_ngs_assets(destination: Path | str, *, opener=None) -> list[dict]:
    result=[]
    kwargs={} if opener is None else {"opener":opener}
    for asset in NGS_ASSETS:
        m=capture_public_release(asset,destination,**kwargs)
        root=Path(destination).resolve()
        digest=m["original_bytes_sha256"]
        matches=list(root.glob(f"{asset}_{digest[7:23]}.csv.gz"))
        if len(matches)!=1:
            raise ValueError("NGS_ORIGINAL_ARCHIVE_NOT_FOUND")
        raw=matches[0].read_bytes()
        if "sha256:"+sha256(raw).hexdigest()!=digest:
            raise ValueError("NGS_ARCHIVE_RAW_HASH_CHANGED")
        observed=datetime.fromisoformat(m["provider_updated_at_claim"].replace("Z","+00:00"))
        captured=datetime.fromisoformat(m["retrieved_at_utc"])
        receipt,rows=parse_snapshot_bytes("NFLVERSE_NGS",raw,observed,captured)
        names=receipt.schema_columns
        season_field="season" if "season" in names else None
        if season_field is None:
            raise ValueError("NGS_SEASON_FIELD_NOT_FOUND")
        total_2026=0
        sample_weeks=set()
        for row in rows:
            if row["season"]!="2026":
                continue
            total_2026+=1
            if row.get("week"):
                sample_weeks.add(row["week"])
        result.append({
            "asset":asset,
            "original_bytes_sha256":digest,
            "provider_updated_claim":m["provider_updated_at_claim"],
            "total_csv_rows":len(rows),
            "season_2026_rows":total_2026,
            "season_2026_week_values":sorted(sample_weeks)[:30],
            "column_names":list(names),
            "raw_player_rows_emitted":False,
            "point_in_time_pre_game_validated":False,
            "player_moment_calibration_validated":False,
            "official_counted":0,"approved_stake_u":0,
            "status":"SCHEMA_DISCOVERY_RESEARCH_ONLY",
        })
    return result


def main(argv=None)->int:
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        raise SystemExit("Usage: python -m sportsedge.markets.ngs_public_research_smoke PRIVATE_ARCHIVE_DIR")
    results=inspect_ngs_assets(args[0])
    print(json.dumps(results,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
