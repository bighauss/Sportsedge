"""Permissioned offline parser for The Odds Gap historical long-form CSV.

No live fetch, undocumented API, credentials, bet execution, wager inference,
or first-party bookmaker attestation. Only HISTORY rows are emitted. Source
timestamps are vendor claims; a retrospectively downloaded file cannot prove
that an earlier trade/selection actually occurred at that price.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import csv
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

from ledger.historical_clv_bridge import (
    Blocked, FIELDS, REPO_ROOT, normalize_line, odds, parse_quote, utc,
)

SPORT_KEYS = {
    "americanfootball_nfl": "NFL",
    "americanfootball_ncaaf": "CFB",
    "basketball_ncaab": "CBB",
    "basketball_nba": "NBA",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
}
BOOKS = {
    "draftkings": "DraftKings",
    "fanduel": "FanDuel",
    "betmgm": "BetMGM",
    "betrivers": "BetRivers",
    "caesars": "Caesars",
    "fanatics": "Fanatics",
    "pinnacle": "Pinnacle",
    "hardrockbet": "Hard Rock Bet",
    "ballybet": "Bally Bet",
    "betparx": "BetParx",
    "thescorebet": "theScore Bet",
}
EXCHANGES = {"kalshi", "polymarket", "polymarket_us", "prophetx", "novig"}
MARKETS = {"ml": "MONEYLINE", "spread": "SPREAD", "total": "TOTAL"}
SIDE_PAIRS = {
    "ml": ("home", "away"),
    "spread": ("home", "away"),
    "total": ("over", "under"),
}
REQUIRED = (
    "snapshot_ts", "sport", "away", "home", "commence_time", "market",
    "side", "line", "book", "american_odds", "game_id",
)
SCHEMA = "sportsedge-oddsgap-history-import-v1"


def private_path(p: Path) -> Path:
    resolved = Path(p).resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise Blocked("PRIVATE_DATA_MUST_STAY_OUTSIDE_PUBLIC_REPO")
    return resolved


def _source_page(url: str) -> str:
    if not isinstance(url, str):
        raise Blocked("INVALID_APPROVED_EXPORT_URL")
    u = urlsplit(url)
    if (u.scheme != "https" or u.hostname != "theoddsgap.com" or
        u.port not in (None, 443) or u.username or u.password or
        u.path != "/api/odds-export.csv" or u.fragment):
        raise Blocked("UNRECOGNIZED_OR_UNAUTHORIZED_SOURCE_ENDPOINT")
    allowed = {"sport", "market", "start", "end"}
    params = parse_qsl(u.query, keep_blank_values=True)
    if len(params) != len(set(k for k, _ in params)) or any(k not in allowed for k, _ in params):
        raise Blocked("UNSAFE_SOURCE_QUERY_OR_SECRET")
    # Never record source URLs with user-supplied credentials or tokens.
    return "https://theoddsgap.com/data"


def source(manifest_file: Path):
    manifest_file = private_path(manifest_file)
    root = manifest_file.parent
    meta = json.loads(manifest_file.read_text(encoding="utf-8"))
    if meta.get("schema") != SCHEMA:
        raise Blocked("ORIGINAL_CSV_MANIFEST_SCHEMA_REQUIRED")
    _source_page(meta.get("source_url"))
    name = meta.get("source_path")
    if (not isinstance(name, str) or not name or name in (".", "..") or
        Path(name).name != name or "\\" in name):
        raise Blocked("RAW_SOURCE_PATH_ESCAPE")
    raw_path = private_path(root / name)
    if not raw_path.is_relative_to(root) or not raw_path.is_file():
        raise Blocked("RAW_SOURCE_MISSING")
    raw = raw_path.read_bytes()
    if not 0 < len(raw) <= 100_000_000:
        raise Blocked("RAW_SOURCE_EMPTY_OR_OVERSIZE")
    digest = sha256(raw).hexdigest()
    if meta.get("source_sha256") != digest:
        raise Blocked("RAW_SOURCE_SHA256_MISMATCH")
    downloaded = utc(meta.get("downloaded_at_utc"))
    return meta, raw, digest, downloaded


def _line(market: str, value: str) -> str:
    if market == "ml":
        if value.strip() not in ("", "0"):
            raise Blocked("ML_LINE_MUST_BE_EMPTY")
        return ""
    if not value.strip():
        raise Blocked("MISSING_HANDICAP_OR_TOTAL_LINE")
    return normalize_line(value.strip())


def ingest(manifest_file: Path):
    meta, raw, digest, downloaded = source(manifest_file)
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Blocked("RAW_NON_UTF8_CSV") from exc
    reader = csv.DictReader(StringIO(decoded))
    if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or
        not set(REQUIRED).issubset(reader.fieldnames)):
        raise Blocked("MISSING_OR_DUPLICATED_SOURCE_HEADERS")
    groups = defaultdict(list)
    blocked = Counter()
    total = 0
    for row in reader:
        total += 1
        if total > 1_000_000:
            raise Blocked("EXCESSIVE_CSV_ROWS")
        if None in row or any(row.get(k) is None for k in REQUIRED):
            blocked["CSV_ROW_SHAPE_INVALID"] += 1
            continue
        try:
            sport = SPORT_KEYS.get(row["sport"].strip())
            market = row["market"].strip().lower()
            book = row["book"].strip().lower()
            side = row["side"].strip().lower()
            if sport is None:
                raise Blocked("SPORT_NOT_IN_SIX_SPORT_KERNEL")
            if market not in MARKETS:
                raise Blocked("MARKET_FAMILY_UNSUPPORTED")
            if book in EXCHANGES:
                raise Blocked("EXCHANGE_NOT_ORIGINAL_SPORTSBOOK")
            if book not in BOOKS:
                raise Blocked("BOOK_NOT_ALLOWLISTED")
            if side not in SIDE_PAIRS[market]:
                raise Blocked("SIDE_UNSUPPORTED_OR_THREE_WAY")
            observed, kickoff = utc(row["snapshot_ts"].strip()), utc(row["commence_time"].strip())
            if observed >= kickoff:
                raise Blocked("POST_KICKOFF_QUOTE")
            if observed > downloaded:
                raise Blocked("SOURCE_QUOTE_AFTER_DOWNLOAD")
            line = _line(market, row["line"])
            odds(row["american_odds"].strip())
            game_id = row["game_id"].strip()
            home, away = row["home"].strip(), row["away"].strip()
            if not game_id or not home or not away or home == away:
                raise Blocked("GAME_ID_OR_TEAMS_MISSING")
            handicap_key = abs(Decimal(line)) if market == "spread" else line
            key = (sport, game_id, kickoff.isoformat(), book, market,
                   observed.isoformat(), handicap_key)
            groups[key].append((side, line, row["american_odds"].strip(), home, away))
        except (Blocked, ValueError, TypeError, InvalidOperation) as exc:
            blocked[str(exc) if isinstance(exc, Blocked) else "UNPARSEABLE_SOURCE_ROW"] += 1
    rows = []
    for key in sorted(groups, key=str):
        sport, game_id, kickoff, book, market, observed, _ = key
        entries = groups[key]
        sides = {side: (line, price, home, away) for side,line,price,home,away in entries}
        if len(entries) != 2 or set(sides) != set(SIDE_PAIRS[market]):
            blocked["INCOMPLETE_OR_DUPLICATED_TWO_SIDED_GROUP"] += 1
            continue
        names = {(e[2], e[3]) for e in sides.values()}
        if len(names) != 1:
            blocked["TEAM_IDENTITY_DRIFT_AT_SNAPSHOT"] += 1
            continue
        a,b = SIDE_PAIRS[market]
        if market == "spread" and Decimal(sides[a][0]) != -Decimal(sides[b][0]):
            blocked["OPPOSITE_SPREAD_SIGN_ERROR"] += 1
            continue
        if market == "total" and sides[a][0] != sides[b][0]:
            blocked["OPPOSITE_TOTAL_LINE_ERROR"] += 1
            continue
        prepared = []
        try:
            for side,other in ((a,b),(b,a)):
                line,price,_,_ = sides[side]
                row = {
                    "source":"ODDS_GAP",
                    "source_url":"https://theoddsgap.com/data",
                    "sport":sport,
                    "event_id":game_id,  # Source-native, NOT a mapped SportsEdge event ID
                    "source_event_id":game_id,
                    "source_market_id":market,  # Market label, NOT bookmaker receipt ID
                    "mapping_version":"theoddsgap-long-v1-source-native",
                    "book":BOOKS[book],
                    "market_kind":MARKETS[market],
                    "period":"FG",
                    "settlement":"POSTED_RULES_UNVERIFIED",
                    "selection_id":side.upper(),
                    "opposite_selection_id":other.upper(),
                    "line":line,
                    "opposite_line":sides[other][0],
                    "player_id":"",
                    "team_id":"",
                    "stat":"",
                    "price_american":price,
                    "opposite_price_american":sides[other][1],
                    "observed_at_utc":observed,
                    "captured_at_utc":downloaded.isoformat(),
                    "kickoff_utc":kickoff,
                }
                parse_quote(row, "HISTORY")
                prepared.append(row)
        except Blocked as exc:
            blocked[str(exc)] += 1
            continue
        rows.extend(prepared)
    report = {
        "schema": SCHEMA,
        "state": "PAPER_RETROSPECTIVE_VENDOR_CLAIMS_ONLY" if rows else "BLOCK_NO_USABLE_TWO_SIDED_QUOTES",
        "source": "THE_ODDS_GAP",
        "source_url": "https://theoddsgap.com/data",
        "original_csv_sha256": digest,
        "source_file_name": Path(meta["source_path"]).name,
        "downloaded_at_utc": downloaded.isoformat(),
        "vendor_sample_flag_claim": meta.get("x_data_sample", "UNKNOWN"),
        "raw_source_rows": total,
        "market_groups_seen": len(groups),
        "two_sided_quotes_written": len(rows),
        "blocked_rows_or_groups_by_reason": dict(sorted(blocked.items())),
        "source_native_event_ids_not_cross_provider": True,
        "provider_quoted_snapshots_not_independently_attested": True,
        "licensed_sportsbook_source_chains_not_independently_authenticated": True,
        "official_counted": 0,
        "approved_stake_u": 0,
    }
    return rows, report


def export(manifest: Path, destination: Path):
    destination = private_path(destination)
    if destination.suffix.lower() != ".csv":
        raise Blocked("OUTPUT_MUST_BE_CSV")
    audit = destination.with_name(destination.name + ".audit.json")
    if destination.exists() or audit.exists():
        raise Blocked("CREATE_ONLY_EXPORT_REFUSES_OVERWRITE")
    rows, report = ingest(manifest)
    buff = StringIO()
    writer = csv.DictWriter(buff, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = buff.getvalue().encode("utf-8")
    report["normalized_csv_sha256"] = sha256(raw).hexdigest()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    created = []
    try:
        for path, payload in ((destination, raw), (audit, (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "wb") as fd:
                fd.write(payload)
                fd.flush()
                os.fsync(fd.fileno())
    except BaseException:
        # Never leave an orphan usable CSV if its audit sidecar cannot be saved.
        # Only unlink files this invocation created, never pre-existing evidence.
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = export(args.private_manifest, args.output)
    print(json.dumps({key:result[key] for key in (
        "state","raw_source_rows","two_sided_quotes_written",
        "official_counted","approved_stake_u")},sort_keys=True))


if __name__ == "__main__":
    main()
