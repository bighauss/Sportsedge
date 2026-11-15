"""Verified-shape, *unverified-origin* five-sport independent player projection intake.

Reads pregame model forecast CSV, NOT a bookmaker board and NOT market-implied
player means. Enforces source lineage/time, stable IDs, complete sport-specific
variance and active/volume gates before handing PlayerMoment to scenarios.

Original file hash is exact, but does not prove source truth. All outputs
PAPER / 0u and no wager authorization. No guessing a player ID from a label.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import csv
import io
import math
import re

from .projection_distribution import PlayerMoment
from .allmarkets_research import STAT_NAMES, _time, _hash
from .source_ingestion import SOURCES

REQUIRED = frozenset({
    "sport","event_id","player_id","team_id","stat","mean","sd",
    "asof_utc","trained_until_utc","source_snapshot_sha256","source_id",
    "confirmed_active","projected_targets","projected_rush_attempts",
    "projected_minutes","confirmed_pitcher","confirmed_batting_lineup",
})
FORBIDDEN = frozenset({
    "book_price","price","odds","dk_price","market_implied_mean",
    "no_vig_probability","blended_ev","book","source_auth_claim",
})


def _datetime(s:str)->datetime:
    if not isinstance(s,str) or not s:
        raise ValueError("PLAYER_FORECAST_ASOF_MISSING")
    try:
        d=datetime.fromisoformat(s.replace("Z","+00:00"))
        return _time(d)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("PLAYER_FORECAST_INVALID_TIMESTAMP") from exc


def _numeric(s:str, label:str, *, optional:bool=False)->float|None:
    if s in ("",None):
        if optional:return None
        raise ValueError("PLAYER_FORECAST_NUMERIC_MISSING:"+label)
    try:
        f=float(s)
    except (ValueError,TypeError) as exc:
        raise ValueError("PLAYER_FORECAST_INVALID_NUMBER:"+label) from exc
    if not math.isfinite(f) or f<0:
        raise ValueError("PLAYER_FORECAST_NONFINITE_OR_NEGATIVE:"+label)
    return f


def _bool(s:str,label:str)->bool:
    if s not in ("0","1"):
        raise ValueError("PLAYER_FORECAST_UNCONFIRMED_BOOLEAN:"+label)
    return s=="1"


@dataclass(frozen=True)
class PlayerForecastIntake:
    file_sha256: str
    event_id: str
    sport: str
    player_count: int
    moments: tuple[PlayerMoment,...]
    status: str = "RESEARCH_INPUT_ONLY"
    official_counted: int = 0
    approved_stake_u: int = 0


def ingest_player_forecast_csv(
    raw:bytes,
    *,
    sport:str,
    event_id:str,
    game_roster_ids:frozenset[str],
    event_team_ids:frozenset[str],
    forecast_freeze_utc:datetime,
    odds_observed_at_utc:datetime,
    expected_file_sha256:str | None = None,
) -> PlayerForecastIntake:
    if sport not in STAT_NAMES:
        raise ValueError("UNKNOWN_SPORT")
    if not event_id or len(event_team_ids)!=2 or not game_roster_ids:
        raise ValueError("MISSING_EVENT_TEAM_OR_ROSTER_IDENTITIES")
    freeze=_time(forecast_freeze_utc)
    quote_time=_time(odds_observed_at_utc)
    if freeze>quote_time:
        raise ValueError("PLAYER_FEATURES_FROZEN_AFTER_ODDS")
    if not isinstance(raw,bytes) or not raw:
        raise ValueError("EMPTY_PLAYER_FORECAST")
    digest="sha256:"+sha256(raw).hexdigest()
    if expected_file_sha256 is None:
        # An original-data hash must be retained outside the model's own output.
        raise ValueError("EXPECTED_ORIGINAL_FORECAST_HASH_REQUIRED")
    _hash(expected_file_sha256)
    if digest!=expected_file_sha256:
        raise ValueError("PLAYER_FORECAST_FILE_HASH_MISMATCH")
    try:
        doc=raw.decode("utf-8-sig")
        reader=csv.DictReader(io.StringIO(doc,newline=""),restkey=None,
                              restval=None,strict=True)
        columns=reader.fieldnames or []
        if not columns or len(set(k.casefold().strip() for k in columns))!=len(columns):
            raise ValueError("DUPLICATE_OR_INVALID_PLAYER_FORECAST_HEADERS")
        missing=REQUIRED-set(columns)
        if missing:
            raise ValueError("PLAYER_FORECAST_SCHEMA_MISSING:"+",".join(sorted(missing)))
        if FORBIDDEN & set(columns):
            raise ValueError("PLAYER_FORECAST_CONTAINS_BOOKMAKER_DERIVED_INPUT")
        rows=list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("PLAYER_FORECAST_RAGGED_CSV")
    except (UnicodeError,csv.Error) as exc:
        raise ValueError("PLAYER_FORECAST_INVALID_CSV") from exc
    if not rows:
        raise ValueError("PLAYER_FORECAST_EMPTY_ROWS")
    result=[]
    seen=set()
    for i,row in enumerate(rows,2):
        if row["sport"]!=sport or row["event_id"]!=event_id:
            raise ValueError("PLAYER_FORECAST_EVENT_SCOPE_MISMATCH")
        player=row["player_id"].strip()
        team=row["team_id"].strip()
        stat=row["stat"].strip().upper()
        if not player or player not in game_roster_ids or team not in event_team_ids:
            raise ValueError("UNBOUND_ROSTER_OR_TEAM_ID")
        if stat not in STAT_NAMES[sport]:
            raise ValueError("UNSUPPORTED_PROP_STAT:"+stat)
        key=(player,stat)
        if key in seen:
            raise ValueError("DUPLICATED_PLAYER_STAT_PROJECTION")
        seen.add(key)
        if row["source_id"] not in SOURCES or SOURCES[row["source_id"]].sport!=sport:
            raise ValueError("UNAPPROVED_PLAYER_FEATURE_SOURCE")
        snapshot_hash=row["source_snapshot_sha256"]
        _hash(snapshot_hash)
        asof=_datetime(row["asof_utc"])
        trained=_datetime(row["trained_until_utc"])
        if not (trained<asof<=freeze<=quote_time):
            raise ValueError("PLAYER_FORECAST_CHRONOLOGY_OR_LOOKAHEAD")
        moment=PlayerMoment(
            player_id=player,team_id=team,stat=stat,
            projected_mean=_numeric(row["mean"],"mean"),
            standard_deviation=_numeric(row["sd"],"sd"),
            raw_features_sha256=snapshot_hash,
            trained_until_utc=trained,
            projection_asof_utc=asof,
            confirmed_active=_bool(row["confirmed_active"],"active"),
            projected_targets=_numeric(row["projected_targets"],"targets",optional=True),
            projected_rush_attempts=_numeric(row["projected_rush_attempts"],"rush_attempts",optional=True),
            projected_minutes=_numeric(row["projected_minutes"],"minutes",optional=True),
            confirmed_pitcher=_bool(row["confirmed_pitcher"],"pitcher"),
            confirmed_batting_lineup=_bool(row["confirmed_batting_lineup"],"batting_lineup"),
        )
        moment.validate(sport,freeze)
        result.append(moment)
    return PlayerForecastIntake(
        file_sha256=digest,event_id=event_id,sport=sport,
        player_count=len({m.player_id for m in result}),
        moments=tuple(result),
    )
