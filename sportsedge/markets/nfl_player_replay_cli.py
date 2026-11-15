"""Run historical NFL player forecast study against real GitHub-digested releases.

WARNING: this is a *retrospective* study of today's PUBLIC revised release
with prior-week numerical partitioning; NOT authenticated 2026 historic PIT.

Usage:
  python -m sportsedge.markets.nfl_player_replay_cli /private/source-archive

Capture to private nonrepo directory only. The command never contacts any
bookmaker, never writes a player price and emits aggregated error metrics only.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from hashlib import sha256
import json
import sys

from .public_release_capture import capture_public_release
from .nfl_player_walkforward_research import (
    NGS_ASSETS, parse_source_archive, historical_player_walkforward,
)


def capture_and_evaluate(
    destination: str|Path, *,
    season:int=2026, first_test_week:int=5, through_week:int=9,
    opener=None,
) -> dict:
    kwargs={} if opener is None else {"opener":opener}
    root=Path(destination).resolve()
    archives={}
    for asset in ("NFL_WEEKLY_2026",)+NGS_ASSETS:
        result=capture_public_release(asset,root,**kwargs)
        digest=result["original_bytes_sha256"]
        files=list(root.glob(f"{asset}_{digest[7:23]}.csv.gz"))
        if len(files)!=1:
            raise ValueError("PLAYER_RESEARCH_ARCHIVE_MISSING_OR_AMBIGUOUS:"+asset)
        raw=files[0].read_bytes()
        if digest != "sha256:"+sha256(raw).hexdigest():
            raise ValueError("PLAYER_RESEARCH_ORIGINAL_ARCHIVE_MODIFIED:"+asset)
        observed=datetime.fromisoformat(
            result["provider_updated_at_claim"].replace("Z","+00:00"))
        fetched=datetime.fromisoformat(result["retrieved_at_utc"])
        source_id="NFLVERSE_WEEKLY" if asset=="NFL_WEEKLY_2026" else "NFLVERSE_NGS"
        rows,h=parse_source_archive(raw,source_id=source_id,
            expected_sha256=digest,
            observed_at_utc=observed,captured_at_utc=fetched)
        archives[asset]={"rows":rows,"hash":h,"fetched_at":result["retrieved_at_utc"],
                         "provider_updated_claim":result["provider_updated_at_claim"]}
    report=historical_player_walkforward(
        archives["NFL_WEEKLY_2026"]["rows"],
        {a:archives[a]["rows"] for a in NGS_ASSETS},
        season=season,first_test_week=first_test_week,
        through_week=through_week,
    )
    report["source_evidence"]={
        a:{"sha256":v["hash"],
           "retrieved_at_utc":v["fetched_at"],
           "provider_updated_claim":v["provider_updated_claim"],
           "original_file_stored_outside_repo":True,
           "historical_point_in_time_certified":False}
        for a,v in archives.items()
    }
    report["data_archive_not_retained_by_ci_after_job"]=True
    return report


def main(argv:list[str]|None=None)->int:
    argv=sys.argv[1:] if argv is None else argv
    if len(argv)!=1:
        raise SystemExit("Usage: python -m sportsedge.markets.nfl_player_replay_cli /private/archive")
    result=capture_and_evaluate(argv[0])
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
