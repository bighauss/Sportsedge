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

# Validate the actual columns observed from the November 15, 2026
# GitHub-hosted nflverse Next Gen Stats release. Never infer IDs from names.
CORE_STATS={
    "NFL_NGS_PASS":("attempts","completions","pass_yards","pass_touchdowns"),
    "NFL_NGS_RUSH":("rush_attempts","rush_yards","rush_touchdowns"),
    "NFL_NGS_RECEIVE":("targets","receptions","yards","rec_touchdowns"),
}
NFL_TEAMS=frozenset((
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC "
    "LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS"
).split())
EXACT_NGS_ALIASES={"LA":"LAR"}


def _metric(row: dict, name: str, *, may_be_negative: bool=False) -> float:
    import math
    try:
        if not row.get(name) or str(row[name]).strip() in ("NA","NaN","null"):
            raise ValueError
        n=float(row[name])
    except (TypeError,ValueError) as exc:
        raise ValueError("NGS_REQUIRED_STAT_MISSING_OR_INVALID:"+name) from exc
    if not math.isfinite(n) or (n<0 and not may_be_negative):
        raise ValueError("NGS_REQUIRED_STAT_INVALID:"+name)
    return n


def audit_ngs_weekly_rows(
    asset: str,
    columns: tuple[str,...],
    rows: list[dict],
    *,
    season: int=2026,
    through_week: int=9,
) -> dict:
    if asset not in CORE_STATS or type(season)!=int or type(through_week)!=int or not 1<=through_week<=22:
        raise ValueError("NGS_UNREGISTERED_ASSET_OR_CUTOFF")
    required={"season","season_type","week","player_gsis_id","team_abbr"}
    required.update(CORE_STATS[asset])
    if not required.issubset(columns):
        raise ValueError("NGS_REQUIRED_SCHEMA_MISSING:"+",".join(sorted(required-set(columns))))
    accepted=0
    dropped_aggregate=0
    dropped_after=0
    skipped_other=0
    seen=set()
    teams=set()
    for row in rows:
        if row["season"]!=str(season) or row["season_type"]!="REG":
            skipped_other+=1
            continue
        try:
            week=int(row["week"])
        except (TypeError,ValueError) as exc:
            raise ValueError("NGS_WEEK_MISSING_OR_INVALID") from exc
        if week==0:
            # NGS uses week=0 for season-to-date aggregate: never double count.
            dropped_aggregate+=1
            continue
        if week>through_week:
            dropped_after+=1
            continue
        if week<1:
            raise ValueError("NGS_NEGATIVE_WEEK")
        team=row["team_abbr"].strip().upper()
        team=EXACT_NGS_ALIASES.get(team,team)
        player=row["player_gsis_id"].strip()
        if team not in NFL_TEAMS:
            raise ValueError("NGS_UNKNOWN_TEAM_ID:"+team)
        if not player:
            raise ValueError("NGS_PLAYER_GSIS_ID_MISSING")
        key=(season,week,team,player)
        if key in seen:
            raise ValueError("NGS_DUPLICATED_WEEKLY_PLAYER_TEAM_ROW")
        seen.add(key)
        for stat in CORE_STATS[asset]:
            _metric(row,stat,may_be_negative=stat in ("rush_yards","yards","pass_yards"))
        if asset=="NFL_NGS_PASS":
            if _metric(row,"completions")>_metric(row,"attempts"):
                raise ValueError("NGS_PASS_COMPLETIONS_EXCEED_ATTEMPTS")
        if asset=="NFL_NGS_RECEIVE":
            if _metric(row,"receptions")>_metric(row,"targets"):
                raise ValueError("NGS_RECEIVING_CATCHES_EXCEED_TARGETS")
        teams.add(team)
        accepted+=1
    if accepted==0:
        raise ValueError("NGS_NO_VALID_WEEKLY_2026_ROWS")
    if len(teams)!=32:
        raise ValueError("NGS_32_TEAM_COVERAGE_INCOMPLETE:"+str(len(teams)))
    return {
        "accepted_regular_season_player_week_rows":accepted,
        "excluded_week_zero_aggregate_rows":dropped_aggregate,
        "excluded_post_cutoff_rows":dropped_after,
        "other_seasons_or_game_types":skipped_other,
        "accepted_team_count":len(teams),
        "requires_fitted_player_variance_before_prop_pricing":True,
    }


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
        total_2026=sum(row["season"]=="2026" for row in rows)
        sample_weeks={row["week"] for row in rows
                      if row["season"]=="2026" and row.get("week")}
        weekly=audit_ngs_weekly_rows(asset,names,rows)
        result.append({
            "asset":asset,
            "original_bytes_sha256":digest,
            "provider_updated_claim":m["provider_updated_at_claim"],
            "total_csv_rows":len(rows),
            "season_2026_rows":total_2026,
            "season_2026_week_values":sorted(sample_weeks)[:30],
            "required_metric_columns":list(CORE_STATS[asset]),
            "weekly_filter_audit":weekly,
            "raw_player_rows_emitted":False,
            "point_in_time_pre_game_validated":False,
            "player_moment_calibration_validated":False,
            "official_counted":0,"approved_stake_u":0,
            "status":"CURRENT_RELEASE_WEEKLY_INTEGRITY_VALIDATED_RESEARCH_ONLY",
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
