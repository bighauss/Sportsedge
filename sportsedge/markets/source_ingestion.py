"""Source registry and receipt-preserving *offline* sports data intake.

No paid/hidden scraping or fabricated sports data. Registered public repo URLs
are documentation pointers, not proof any API/CSV is live or licensed for reuse.
Raw bytes are hashed exactly as received. Proof of a hash is NOT a timestamp
attestation, source signature, feature quality, or sportsbook price receipt.

For actual provider access use the documented upstream API, obey its terms,
then archive raw bytes outside this public repository with an immutable manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import gzip
import io
import json
import re

SHA = re.compile(r"^sha256:[a-f0-9]{64}$")
SPORTS = frozenset({"NFL","CFB","CBB","NBA","MLB"})

@dataclass(frozen=True)
class Source:
    id: str
    sport: str
    upstream_repo: str
    scope: str
    access: str
    pit_warning: str
    required_columns: tuple[str, ...] = ()
    # A separate provider-specific versioned parser is required for most feeds.

SOURCES = {
    "NFLVERSE_WEEKLY": Source(
        "NFLVERSE_WEEKLY", "NFL", "https://github.com/nflverse/nflverse-data",
        "Weekly NFL player rushing/receiving/passing stats",
        "Public release; check release asset SHA-256 and date",
        "Published-after-game revision cannot be used to backfill pregame features",
        ("season","week","season_type","player_id","rushing_tds","receiving_tds")),
    "NFLVERSE_PBP": Source(
        "NFLVERSE_PBP","NFL","https://github.com/nflverse/nflverse-data",
        "Play-by-play scoring and game/drive outcomes",
        "Public release; archive original release bytes",
        "End-of-game results are targets, never pregame projection features",
        ("game_id","week")),
    "NFLVERSE_NGS": Source(
        "NFLVERSE_NGS","NFL","https://github.com/nflverse/nflreadpy",
        "Next Gen Stats passing, rushing and receiving",
        "Documented nflreadpy/nflverse loaders; check season/coverage",
        "NGS features must be published before market snapshot"),
    "CFB_DATA": Source(
        "CFB_DATA","CFB","https://github.com/sportsdataverse/sportsdataverse-py",
        "CFB public schedules, plays, teams, opponent adjustment",
        "Sport-specific Python/R release loaders; CFBD API may need free key",
        "Historical published/revised fields require PIT archive"),
    "CFB_FASTR": Source(
        "CFB_FASTR","CFB","https://github.com/sportsdataverse/cfbfastR",
        "CFB play by play and pregame team ratings features",
        "Public R package, release workflows; inspect metadata",
        "Postgame EPA is not same-game pregame information"),
    "CBB_HOOPR": Source(
        "CBB_HOOPR","CBB","https://github.com/sportsdataverse/hoopR",
        "College basketball NCAA/ESPN/Torvik team and player stats",
        "Public repo; free Torvik/ESPN/NCAA paths only, never paid KenPom",
        "Published season aggregate must be frozen before each game"),
    "NBA_STATS": Source(
        "NBA_STATS","NBA","https://github.com/swar/nba_api",
        "NBA game logs, advanced box stats, play by play",
        "Public nba_api wrapper; site may rate limit/deny requests",
        "Starter/injury/player-minute inputs require their own dated confirmations"),
    "NBA_HOOPR": Source(
        "NBA_HOOPR","NBA","https://github.com/sportsdataverse/hoopR",
        "NBA PBP/boxscore snapshots",
        "Public hoopR release assets; check output version",
        "Do not use postgame possessions as live pregame features"),
    "MLB_STATCAST": Source(
        "MLB_STATCAST","MLB","https://github.com/jldbc/pybaseball",
        "Statcast expected stats, batted balls and pitcher/batter matchups",
        "Free pybaseball Statcast wrapper; verify upstream terms and coverage",
        "Do not use current-game Statcast observations in pregame run"),
    "MLB_STATSAPI": Source(
        "MLB_STATSAPI","MLB","https://github.com/MLB-StatsAPI/MLB-StatsAPI",
        "MLB schedule, probable starters, box scores and results",
        "Documented community wrapper for public MLB StatsAPI",
        "Probable starter is not the same as confirmed lineup/starter"),
}


@dataclass(frozen=True)
class SourceReceipt:
    source_id: str
    capture_at_utc: datetime
    observed_at_utc: datetime
    sha256_raw: str
    bytes_length: int
    record_count: int
    schema_columns: tuple[str,...]
    status: str = "RESEARCH_UNAUTHENTICATED"

    def __post_init__(self):
        if self.source_id not in SOURCES:
            raise ValueError("UNKNOWN_SOURCE")
        if self.capture_at_utc.tzinfo is None or self.observed_at_utc.tzinfo is None:
            raise ValueError("UTC_TIMESTAMP_REQUIRED")
        for t in (self.capture_at_utc,self.observed_at_utc):
            if t.utcoffset().total_seconds()!=0:
                raise ValueError("NON_UTC_TIMESTAMP")
        if self.observed_at_utc>self.capture_at_utc:
            raise ValueError("SOURCE_OBSERVED_AFTER_CAPTURE")
        if not SHA.fullmatch(self.sha256_raw):
            raise ValueError("INVALID_RAW_SHA256")
        if self.status!="RESEARCH_UNAUTHENTICATED":
            raise ValueError("SOURCE_AUTHENTICATION_IS_NOT_PROVEN")


def parse_snapshot_bytes(
    source_id: str,
    raw: bytes,
    observed_at_utc: datetime,
    captured_at_utc: datetime,
    *,
    max_decompressed_bytes: int = 80_000_000,
) -> tuple[SourceReceipt,list[dict]]:
    """Validate exact bytes/columns and preserve the original SHA; no networking."""
    if source_id not in SOURCES or not isinstance(raw,bytes) or not raw:
        raise ValueError("SOURCE_OR_RAW_BYTES_MISSING")
    payload_hash="sha256:"+sha256(raw).hexdigest()
    if raw[:2]==b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
            data=gz.read(max_decompressed_bytes+1)
    else:
        data=raw
    if len(data)>max_decompressed_bytes:
        raise ValueError("SOURCE_PAYLOAD_TOO_LARGE")
    try:
        body=data.decode("utf-8-sig")
        reader=csv.DictReader(io.StringIO(body,newline=""),strict=True,restkey=None,restval=None)
        headers=reader.fieldnames or []
        if not headers or len(set(h.casefold().strip() for h in headers))!=len(headers):
            raise ValueError("SOURCE_DUPLICATE_OR_INVALID_HEADER")
        for required in SOURCES[source_id].required_columns:
            if required not in headers:
                raise ValueError("SOURCE_REQUIRED_COLUMN_MISSING:"+required)
        if source_id=="NFLVERSE_WEEKLY" and not ({"team","recent_team"} & set(headers)):
            raise ValueError("SOURCE_TEAM_ID_COLUMN_MISSING")
        rows=list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError("SOURCE_RAGGED_CSV_ROW")
    except (UnicodeError,csv.Error) as exc:
        raise ValueError("SOURCE_CSV_DECODE_OR_PARSE_FAILED") from exc
    receipt=SourceReceipt(source_id, captured_at_utc, observed_at_utc, payload_hash,
                          len(raw),len(rows),tuple(headers))
    return receipt,rows


def check_feature_cutoff(
    receipt: SourceReceipt, *,
    decision_at_utc: datetime, quote_observed_at_utc: datetime
) -> tuple[str,...]:
    """Only publication and capture times with defensible pregame chronology qualify."""
    problems=[]
    for t in (decision_at_utc,quote_observed_at_utc):
        if t.tzinfo is None or t.utcoffset().total_seconds()!=0:
            raise ValueError("UTC_TIMESTAMP_REQUIRED")
    if receipt.observed_at_utc>quote_observed_at_utc:
        problems.append("FEATURE_PUBLISHED_AFTER_ODDS")
    if receipt.capture_at_utc>quote_observed_at_utc:
        problems.append("FEATURE_COLLECTED_AFTER_ODDS")
    if receipt.capture_at_utc>decision_at_utc:
        problems.append("FEATURE_COLLECTED_AFTER_DECISION")
    problems.append("SOURCE_TRANSPORT_AND_PUBLISH_TIMESTAMP_NOT_INDEPENDENTLY_ATTESTED")
    return tuple(problems)


def source_inventory() -> list[dict]:
    return [
        {"id":s.id,"sport":s.sport,"upstream_repo":s.upstream_repo,
         "scope":s.scope,"access":s.access,"pit_warning":s.pit_warning}
        for s in SOURCES.values()
    ]
