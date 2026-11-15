"""nflverse offensive touchdown-share lineage builder (no probability pricing).

Input is the ORIGINAL weekly player stats CSV or gz bytes, with original SHA,
regular-season cutoff, stable IDs and team coverage. A historical share fraction
must never be passed directly as P(ATTD), P(first TD) or P(2+ TD).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json

from .source_ingestion import parse_snapshot_bytes

NFL32 = frozenset({
    "ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN","DET","GB",
    "HOU","IND","JAX","KC","LAC","LAR","LV","MIA","MIN","NE","NO","NYG",
    "NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS",
})


def numeric_count(v, label: str) -> Decimal:
    try:
        n=Decimal(str(v))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_WEEKLY_TD_COUNT:"+label) from None
    if not n.is_finite() or n<0 or n!=n.to_integral_value():
        raise ValueError("INVALID_WEEKLY_TD_COUNT:"+label)
    return n


def build_offensive_td_shares(
    raw_csv_or_gz: bytes, *,
    through_week: int,
    season: int,
    source_observed_at_utc: datetime,
    fetched_at_utc: datetime,
    expected_raw_sha256: str | None = None,
    require_all_32_teams: bool = True,
) -> dict:
    if type(through_week)!=int or not 1<=through_week<=22:
        raise ValueError("INVALID_WEEK_CUTOFF")
    if type(season)!=int or not 2000<=season<=2100:
        raise ValueError("INVALID_SEASON")
    receipt, rows = parse_snapshot_bytes(
        "NFLVERSE_WEEKLY", raw_csv_or_gz,
        source_observed_at_utc, fetched_at_utc)
    if expected_raw_sha256 is not None and receipt.sha256_raw!=expected_raw_sha256:
        raise ValueError("WEEKLY_SOURCE_SHA_MISMATCH")
    td_counts: dict[tuple[str,str],Decimal]={}
    seen:set[tuple[int,int,str,str]]=set()
    active_teams:set[str]=set()
    eligible_rows=0
    excluded_future=0
    for row in rows:
        if not row.get("season") or not row.get("week"):
            raise ValueError("SEASON_WEEK_MISSING")
        try:
            y=int(row["season"]);w=int(row["week"])
        except ValueError:
            raise ValueError("INVALID_SEASON_WEEK") from None
        if y!=season or row.get("season_type","").strip().upper() not in ("REG","REGULAR"):
            continue
        if w>through_week:
            excluded_future+=1
            continue
        if w<1:
            raise ValueError("INVALID_WEEK")
        pid=row.get("player_id","").strip()
        # 2026 nflverse weekly stats actually uses `team`; some older exports
        # use `recent_team`. If both exist, refuse conflicting identities.
        field_team=(row.get("team") or "").strip().upper()
        field_recent=(row.get("recent_team") or "").strip().upper()
        if field_team and field_recent and field_team != field_recent:
            raise ValueError("CONFLICTING_WEEKLY_TEAM_IDENTIFIERS")
        team=field_team or field_recent
        if not pid or not team or team not in NFL32:
            raise ValueError("UNKNOWN_OR_MISSING_PLAYER_TEAM_ID")
        key=(y,w,team,pid)
        if key in seen:
            raise ValueError("DUPLICATE_WEEKLY_PLAYER_TEAM_ENTRY")
        seen.add(key)
        eligible_rows+=1
        active_teams.add(team)
        rush=numeric_count(row["rushing_tds"],"rush")
        rec=numeric_count(row["receiving_tds"],"receiving")
        # Passing touchdowns THROWN by a quarterback are not player TD SCORED.
        td_counts[(team,pid)]=td_counts.get((team,pid),Decimal(0))+rush+rec
    if not eligible_rows:
        raise ValueError("NO_REGULAR_SEASON_ROWS_BEFORE_CUTOFF")
    missing=sorted(NFL32-active_teams)
    if require_all_32_teams and missing:
        raise ValueError("INCOMPLETE_NFL_TEAM_COVERAGE:"+",".join(missing))
    team_sum:dict[str,Decimal]={}
    for (team,pid),n in td_counts.items():
        team_sum[team]=team_sum.get(team,Decimal(0))+n
    entries=[]
    for (team,pid),td in sorted(td_counts.items()):
        if td==0:
            continue
        if team_sum[team]==0:
            raise ValueError("ZERO_OFFENSIVE_TEAM_TD_DENOMINATOR")
        entries.append({
            "team":team,"player_id":pid,
            "offensive_tds":int(td),
            "team_offensive_tds":int(team_sum[team]),
            "share":str(td/team_sum[team]),
            "share_is_probability":False,
        })
    return {
        "status":"HISTORICAL_SHARE_ONLY",
        "approved_stake_u":0,"official_counted":0,
        "p_anytime_td":None,"p_first_td":None,"p_2plus_td":None,
        "season":season,"through_week":through_week,
        "eligible_weekly_rows":eligible_rows,
        "excluded_future_weekly_rows":excluded_future,
        "teams_observed":len(active_teams),
        "missing_teams":missing,
        "input_sha256":receipt.sha256_raw,
        "source_record_count":receipt.record_count,
        "source_observed_at_utc":source_observed_at_utc.isoformat(),
        "fetched_at_utc":fetched_at_utc.isoformat(),
        "entries":entries,
        "warnings":[
            "HISTORICAL_TD_SHARE_IS_NOT_A_TD_BET_PROBABILITY",
            "REQUIRES_ROSTER_STATUS_OPPONENT_TEAM_TD_DISTRIBUTION_GAME_SCRIPT",
            "NO_NFLVERSE_POINT_IN_TIME_ATTESTATION_FROM_RAW_HASH_ALONE",
            "FIRST_TD_REQUIRES_ORDERED_ALL_TEAM_SCORE_EVENTS_INCLUDING_DEFENSE",
            "MULTI_TD_REQUIRES_COUNT_DISTRIBUTION_NOT_SINGLE_BERNOULLI",
        ],
    }
