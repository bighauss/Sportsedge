"""Convert an already-authorized, privately archived Odds API v4 capture to CLV CSV.

No network, no vendor scraping, no credentials, no wagering. The CSV supplies
PAPER source observations only: upstream bookmaker quotes are NOT independently
authenticated. Supports exact FG two-sided h2h/spreads/totals; all other
market families are quarantined, never mapped to invented settlement IDs.

Original provider JSON + SHA manifest must live outside the public checkout.
Conflicting/duplicated source market groups are quarantined ALL-COPY, never
first-wins. CSV and .audit.json are private, exclusive-create 0600 outputs:
a failed write removes only files actually created by that invocation, and
never deletes previously existing originals. No user wager is inferred from
a price-board TAKE snapshot.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path

from ledger.historical_clv_bridge import FIELDS, Blocked, parse_quote
from sportsedge.odds.free_odds_aggregator_intake import SPORTS, BASE, strict_json, utc

BOOK_NAMES = {
    "draftkings": "DraftKings",
    "fanduel": "FanDuel",
    "betmgm": "BetMGM",
    "betrivers": "BetRivers",
    "pinnacle": "Pinnacle",
    "caesars": "Caesars",
}
REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPORT = {"h2h": "MONEYLINE", "spreads": "SPREAD", "totals": "TOTAL"}
MAPPING_VERSION = "the-odds-api-v4-native-event-market-v1"


def _private_path(path: Path) -> Path:
    # Checking only .resolve() lets a public checkout symlink mask its lexical
    # location; both the supplied name and resolved target must be private.
    lexical = Path(os.path.abspath(os.fspath(path)))
    resolved = lexical.resolve()
    if any(p == REPO_ROOT or REPO_ROOT in p.parents
           for p in (lexical, resolved)):
        raise Blocked("ODDS_SOURCE_OR_OUTPUT_IN_PUBLIC_REPO")
    return resolved


def load_evidence(manifest_path: Path):
    manifest_path = _private_path(manifest_path)
    base = manifest_path.parent
    # Reject last-key-wins tampering with saved source/timestamp/endpoint
    # metadata. These fields are caller claims, not provider attestations.
    try:
        manifest = strict_json(manifest_path.read_bytes())
    except (UnicodeError, json.JSONDecodeError, ValueError):
        raise Blocked("ORIGINAL_MANIFEST_DUPLICATE_OR_INVALID_JSON") from None
    if not isinstance(manifest, dict):
        raise Blocked("ORIGINAL_MANIFEST_OBJECT_REQUIRED")
    if manifest.get("schema") != "sportsedge-oddsapi-aggregator-raw-v1":
        raise Blocked("UNEXPECTED_ORIGINAL_ARCHIVE_MANIFEST")
    sport = manifest.get("sport")
    if sport not in SPORTS:
        raise Blocked("UNSUPPORTED_SPORT")
    read_endpoint = manifest.get("read_only_endpoint", "")
    allowed_prefix = BASE + SPORTS[sport]
    if read_endpoint != allowed_prefix + "/odds" and not (
        read_endpoint.startswith(allowed_prefix + "/events/") and
        read_endpoint.endswith("/odds") and "?" not in read_endpoint):
        raise Blocked("UNVERIFIED_SOURCE_ENDPOINT_OR_SECRET_QUERY")
    raw_name = manifest.get("raw_filename")
    if (not isinstance(raw_name, str) or not raw_name or
            raw_name != Path(raw_name).name or raw_name in (".", "..")):
        raise Blocked("ORIGINAL_RAW_PATH_INVALID")
    raw_path = _private_path(base / raw_name)
    if not raw_path.is_relative_to(base) or not raw_path.is_file():
        raise Blocked("ORIGINAL_RAW_MISSING_OR_PATH_ESCAPE")
    raw = raw_path.read_bytes()
    if not 0 < len(raw) <= 20_000_000:
        raise Blocked("ORIGINAL_RAW_EMPTY_OR_OVERSIZE")
    digest = sha256(raw).hexdigest()
    if manifest.get("original_raw_sha256") != "sha256:" + digest:
        raise Blocked("ORIGINAL_RAW_HASH_MISMATCH")
    captured = utc(manifest.get("captured_utc"))
    payload = strict_json(raw)
    events = [payload] if isinstance(payload, dict) else payload
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        raise Blocked("INVALID_RAW_EVENT_ARRAY")
    if len(events) != manifest.get("events_returned"):
        raise Blocked("MANIFEST_EVENT_COUNT_MISMATCH")
    return manifest, events, captured, digest


def _point(raw) -> str:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise Blocked("POINT_NOT_NUMERIC")
    try:
        d = Decimal(str(raw))
    except InvalidOperation as exc:
        raise Blocked("POINT_INVALID_DECIMAL") from exc
    if not d.is_finite():
        raise Blocked("POINT_NONFINITE")
    return str(d.normalize()) if d else "0"


def _pair(ev: dict, market: dict):
    kind = market["key"]
    results = market.get("outcomes")
    if not isinstance(results, list) or len(results) != 2 or any(not isinstance(o, dict) for o in results):
        raise Blocked("MARKET_NOT_TWO_SIDED")
    home, away = ev["home_team"], ev["away_team"]
    if kind in ("h2h", "spreads"):
        expected = {"HOME": home, "AWAY": away}
    elif kind == "totals":
        expected = {"OVER": "Over", "UNDER": "Under"}
    else:
        raise Blocked("MARKET_NOT_SUPPORTED")
    outcome = {}
    for o in results:
        sides = [side for side, name in expected.items() if o.get("name") == name]
        if len(sides) != 1 or sides[0] in outcome:
            raise Blocked("BOOK_OUTCOME_TEAM_SIDE_MISMATCH")
        outcome[sides[0]] = o
    if set(outcome) != set(expected):
        raise Blocked("BOOK_OUTCOME_PAIR_INCOMPLETE")
    for o in outcome.values():
        p = o.get("price")
        if isinstance(p, bool) or not isinstance(p, int) or abs(p) < 100 or abs(p) > 100000:
            raise Blocked("INVALID_BOOK_PRICE")
    if kind == "h2h":
        lines = {side: "" for side in expected}
    else:
        lines = {side: _point(o.get("point")) for side,o in outcome.items()}
    # parse_quote also checks opposite signed spread lines and equal total lines.
    return outcome, lines


def convert(manifest_path: Path, phase: str = "TAKE"):
    if phase not in ("TAKE", "HISTORY"):
        raise Blocked("INVALID_ARCHIVE_PHASE")
    manifest, events, captured, digest = load_evidence(manifest_path)
    counts = Counter()
    rows = []
    # Buffer all valid market groups. First-wins dedupe is selection bias:
    # a later duplicate or conflicting quote must quarantine *all* copies.
    buffered = []
    seen_groups = set()
    duplicate_groups = set()
    source_url = manifest["read_only_endpoint"]
    for ev in events:
        if (ev.get("sport_key") != SPORTS[manifest["sport"]] or
                not isinstance(ev.get("id"), str) or not ev["id"] or
                not isinstance(ev.get("home_team"), str) or
                not isinstance(ev.get("away_team"), str) or
                ev["home_team"] == ev["away_team"]):
            raise Blocked("PROVIDER_EVENT_IDENTITY_INVALID")
        kickoff = utc(ev.get("commence_time"))
        books = ev.get("bookmakers")
        if not isinstance(books, list):
            raise Blocked("BOOKMAKER_ARRAY_INVALID")
        for book in books:
            if not isinstance(book, dict) or not isinstance(book.get("markets"), list):
                raise Blocked("PROVIDER_BOOK_MARKET_SCHEMA_INVALID")
            label = BOOK_NAMES.get(book.get("key"))
            for market in book["markets"]:
                if not isinstance(market, dict):
                    raise Blocked("PROVIDER_MARKET_SCHEMA_INVALID")
                kind = market.get("key")
                if kind not in SUPPORT:
                    counts["MARKET_FAMILY_UNSUPPORTED"] += 1
                    continue
                if label is None:
                    counts["BOOK_NOT_ALLOWLISTED"] += 1
                    continue
                if captured >= kickoff:
                    counts["CAPTURE_NOT_PREGAME"] += 1
                    continue
                timestamp = market.get("last_update") or book.get("last_update")
                try:
                    observed = utc(timestamp)
                except (ValueError, TypeError):
                    counts["MISSING_OR_INVALID_MARKET_CLOCK"] += 1
                    continue
                if observed > captured or observed >= kickoff:
                    counts["PROVIDER_TIME_LOOKAHEAD"] += 1
                    continue
                if (captured-observed).total_seconds() > 300:
                    counts["STALE_QUOTE_OVER_FIVE_MINUTES"] += 1
                    continue
                try:
                    outcomes,lines = _pair(ev, market)
                    prepared = []
                    for side in outcomes:
                        other = next(t for t in outcomes if t != side)
                        row = {
                            "source": "THE_ODDS_API",
                            "source_url": source_url,
                            "sport": manifest["sport"],
                            # Provider-native ID: not a SportsEdge cross-provider ID.
                            "event_id": ev["id"],
                            "source_event_id": ev["id"],
                            "source_market_id": kind,
                            "mapping_version": MAPPING_VERSION,
                            "book": label,
                            "market_kind": SUPPORT[kind],
                            "period": "FG",
                            "settlement": "POSTED_RULES_UNVERIFIED",
                            "selection_id": side,
                            "opposite_selection_id": other,
                            "line": lines[side],
                            "opposite_line": lines[other],
                            "player_id": "",
                            "team_id": "",
                            "stat": "",
                            "price_american": str(outcomes[side]["price"]),
                            "opposite_price_american": str(outcomes[other]["price"]),
                            "observed_at_utc": observed.isoformat(),
                            "captured_at_utc": captured.isoformat(),
                            "kickoff_utc": kickoff.isoformat(),
                        }
                        parse_quote(row, phase)
                        dedupe_key = (ev["id"], label, kind, side, lines[side], observed)
                        prepared.append((dedupe_key, row))
                except Blocked as exc:
                    counts[str(exc)] += 1
                    continue
                group_key = frozenset(key for key, _ in prepared)
                if group_key in seen_groups:
                    duplicate_groups.add(group_key)
                seen_groups.add(group_key)
                buffered.append((group_key, [row for _, row in prepared]))
    for group_key, market_rows in buffered:
        if group_key in duplicate_groups:
            counts["DUPLICATE_CANONICAL_MARKET_ALL_COPIES_QUARANTINED"] += 1
            continue
        rows.extend(market_rows)
        counts["ACCEPTED_TWO_SIDED_MARKET"] += 1
    return rows, {
        "schema": "sportsedge-oddsapi-to-clv-archive-v1",
        "state": "PAPER_0U_SOURCE_RELAY_NOT_BOOK_AUTHENTICATED" if rows else "BLOCK_NO_VALID_TWO_SIDED_QUOTES",
        "sport": manifest["sport"],
        "phase": phase,
        "original_raw_sha256": "sha256:" + digest,
        "original_manifest_filename": Path(manifest_path).name,
        "provider": "the-odds-api.com",
        "mapping_version": MAPPING_VERSION,
        "rows_generated": len(rows),
        "market_groups_quarantined_by_reason": dict(sorted(counts.items())),
        "bookmakers_independently_authenticated": False,
        "claimed_market_clocks_externally_verified": False,
        "source_native_event_ids_not_cross_provider": True,
        "official_counted": 0,
        "approved_stake_u": 0,
    }


def _remove_owned(path: Path, identity: tuple[int, int]) -> None:
    """Never unlink a pre-existing or concurrently replaced evidence file."""
    try:
        current = os.stat(path, follow_symlinks=False)
        if (current.st_dev, current.st_ino) == identity:
            os.unlink(path)
    except FileNotFoundError:
        pass


def _write_private(path: Path, content: bytes) -> tuple[Path, tuple[int, int]]:
    path = Path(path)
    if path.is_symlink():
        raise Blocked("OUTPUT_SYMLINK_REFUSED")
    path = _private_path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    created = os.fstat(descriptor)
    identity = (created.st_dev, created.st_ino)
    try:
        with os.fdopen(descriptor, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        _remove_owned(path, identity)
        raise
    return path, identity


def write_export(manifest: Path, output: Path, phase: str = "TAKE"):
    output = Path(output)
    if output.suffix.lower() != ".csv":
        raise Blocked("OUTPUT_MUST_BE_CSV")
    if output.exists():
        raise Blocked("CREATE_ONLY_REFUSES_OVERWRITE")
    audit = output.with_name(output.name + ".audit.json")
    if audit.exists():
        raise Blocked("AUDIT_OUTPUT_ALREADY_EXISTS")
    rows, info = convert(manifest, phase)
    from io import StringIO
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    encoded = buf.getvalue().encode("utf-8")
    info["normalized_csv_sha256"] = "sha256:" + sha256(encoded).hexdigest()
    created = []
    try:
        created.append(_write_private(output, encoded))
        created.append(_write_private(
            audit, (json.dumps(info, sort_keys=True, indent=2) + "\n").encode("utf-8")))
    except BaseException:
        for path, identity in reversed(created):
            _remove_owned(path, identity)
        raise
    return info


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_original_manifest", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", choices=("TAKE", "HISTORY"), default="TAKE")
    a = p.parse_args(argv)
    out = write_export(a.private_original_manifest, a.output, a.phase)
    print(json.dumps({k:out[k] for k in (
        "state", "sport", "rows_generated", "official_counted", "approved_stake_u")},
        sort_keys=True))


if __name__ == "__main__":
    main()
