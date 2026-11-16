"""Offline, research-only CLV bridge for authorized price-history exports.

NO unauthorized API or scraper. Quote clocks and event mapping are unverified,
so output is always PAPER/0u, even when a two-sided numeric match is possible.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCES = frozenset({"BESTBOOK", "ACTION_NETWORK", "COVERS", "SCORES_AND_ODDS", "DIRECT_BOOK", "THE_ODDS_API", "ODDS_GAP"})
KINDS = frozenset({"MONEYLINE", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP", "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "NRFI", "YRFI", "OTHER"})
SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"})
OPPOSITE_SIDES = {
    "MONEYLINE": frozenset({"HOME", "AWAY"}),
    "SPREAD": frozenset({"HOME", "AWAY"}),
    "TOTAL": frozenset({"OVER", "UNDER"}),
    "TEAM_TOTAL": frozenset({"OVER", "UNDER"}),
    "PLAYER_PROP": frozenset({"OVER", "UNDER"}),
    "ATTD": frozenset({"YES", "NO"}),
    "FIRST_TD": frozenset({"YES", "NO"}),
    "TD_2PLUS": frozenset({"YES", "NO"}),
    "FIRST_BASKET": frozenset({"YES", "NO"}),
    "NRFI": frozenset({"YES", "NO"}),
    "YRFI": frozenset({"YES", "NO"}),
}
FIELDS = ("source", "source_url", "sport", "event_id", "source_event_id", "source_market_id", "mapping_version", "book", "market_kind", "period", "settlement", "selection_id", "opposite_selection_id", "line", "opposite_line", "player_id", "team_id", "stat", "price_american", "opposite_price_american", "observed_at_utc", "captured_at_utc", "kickoff_utc")
REQUIRED = set(FIELDS) - {"line", "opposite_line", "player_id", "team_id", "stat", "source_market_id"}
REPO_ROOT = Path(__file__).resolve().parent.parent

class Blocked(ValueError):
    pass

def utc(raw: str) -> datetime:
    if not isinstance(raw, str) or not raw:
        raise Blocked("MISSING_UTC_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Blocked("INVALID_UTC_TIMESTAMP") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise Blocked("NON_UTC_TIMESTAMP")
    return parsed.astimezone(timezone.utc)

def odds(raw: str) -> int:
    try:
        d = Decimal(str(raw))
    except (ValueError, InvalidOperation) as exc:
        raise Blocked("INVALID_AMERICAN_PRICE") from exc
    if not d.is_finite() or d != d.to_integral_value() or not 100 <= abs(d) <= 100000:
        raise Blocked("INVALID_AMERICAN_PRICE")
    return int(d)

def implied(price: int) -> Decimal:
    x = Decimal(price)
    return Decimal(100) / (x + 100) if x > 0 else -x / (Decimal(100) - x)

def clean_book(book: str) -> str:
    aliases = {"dk": "draftkings", "draft kings": "draftkings", "fd": "fanduel", "fan duel": "fanduel"}
    key = " ".join(book.strip().casefold().split())
    return aliases.get(key, key)

def normalize_line(raw: str) -> str:
    if raw == "":
        return ""
    try:
        d = Decimal(raw)
    except InvalidOperation as exc:
        raise Blocked("INVALID_NUMERIC_LINE") from exc
    if not d.is_finite():
        raise Blocked("INVALID_NUMERIC_LINE")
    return str(d.normalize()) if d != 0 else "0"

@dataclass(frozen=True)
class Quote:
    source: str
    source_url: str
    sport: str
    event_id: str
    source_event_id: str
    source_market_id: str
    mapping_version: str
    book: str
    kind: str
    period: str
    settlement: str
    selection_id: str
    opposite_selection_id: str
    line: str
    opposite_line: str
    player_id: str
    team_id: str
    stat: str
    price: int
    opposite_price: int
    observed: datetime
    captured: datetime
    kickoff: datetime

    @property
    def identity(self):
        return (self.sport, self.event_id, self.kind, self.period, self.settlement,
                self.selection_id, self.opposite_selection_id, self.line, self.opposite_line,
                self.player_id, self.team_id, self.stat, clean_book(self.book), self.kickoff)

    @property
    def no_vig_probability(self) -> Decimal:
        own, other = implied(self.price), implied(self.opposite_price)
        return own / (own + other)

def parse_quote(row: dict[str, str], role: str) -> Quote:
    if role not in ("TAKE", "HISTORY"):
        raise Blocked("UNKNOWN_ROLE")
    if any(k not in row for k in FIELDS):
        raise Blocked("MISSING_COLUMNS")
    r = {k: (row[k] or "").strip() for k in FIELDS}
    if any(not r[k] for k in REQUIRED):
        raise Blocked("MISSING_REQUIRED_EVIDENCE")
    if r["source"] not in SOURCES or r["sport"] not in SPORTS or r["market_kind"] not in KINDS:
        raise Blocked("UNSUPPORTED_SOURCE_SPORT_OR_MARKET")
    if not r["source_url"].startswith("https://") or " " in r["source_url"]:
        raise Blocked("SOURCE_PAGE_URL_REQUIRED")
    if r["mapping_version"] in ("UNVERSIONED", "UNKNOWN", "NONE"):
        raise Blocked("CANONICAL_CROSSWALK_VERSION_REQUIRED")
    if r["selection_id"] == r["opposite_selection_id"]:
        raise Blocked("IDENTICAL_OPPOSING_SELECTIONS")
    expected = OPPOSITE_SIDES.get(r["market_kind"])
    if expected is not None and {r["selection_id"], r["opposite_selection_id"]} != expected:
        raise Blocked("INVALID_OPPOSITE_MARKET_SIDES")
    if r["market_kind"] == "MONEYLINE" and (r["line"] not in ("", "0") or r["opposite_line"] not in ("", "0")):
        raise Blocked("MONEYLINE_HAS_HANDICAP")
    if r["market_kind"] in {"ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "NRFI", "YRFI"} and (r["line"] or r["opposite_line"]):
        raise Blocked("CATEGORICAL_MARKET_HAS_LINE")
    if r["market_kind"] in {"SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"} and (not r["line"] or not r["opposite_line"]):
        raise Blocked("BOTH_MARKET_LINES_REQUIRED")
    # Some exports use moneyline 0 and others blank; those are one market.
    line, other_line = ("", "") if r["market_kind"] == "MONEYLINE" else (
        normalize_line(r["line"]), normalize_line(r["opposite_line"]))
    if r["market_kind"] == "SPREAD" and Decimal(line) != -Decimal(other_line):
        raise Blocked("SPREAD_OPPOSITE_SIGN_ERROR")
    if r["market_kind"] in {"TOTAL", "TEAM_TOTAL", "PLAYER_PROP"} and line != other_line:
        raise Blocked("TOTAL_OPPOSITE_LINE_ERROR")
    if r["market_kind"] == "PLAYER_PROP" and (not r["player_id"] or not r["stat"]):
        raise Blocked("UNBOUND_PLAYER_PROP")
    if r["market_kind"] == "TEAM_TOTAL" and not r["team_id"]:
        raise Blocked("UNBOUND_TEAM_TOTAL")
    observed, captured, kickoff = (utc(r[k]) for k in ("observed_at_utc", "captured_at_utc", "kickoff_utc"))
    if not observed <= captured or not observed < kickoff:
        raise Blocked("HISTORICAL_QUOTE_CHRONOLOGY_INVALID")
    if role == "TAKE" and not captured < kickoff:
        raise Blocked("TAKE_NOT_ACTUALLY_CAPTURED_PREGAME")
    return Quote(r["source"], r["source_url"], r["sport"], r["event_id"],
                 r["source_event_id"], r["source_market_id"], r["mapping_version"],
                 r["book"], r["market_kind"], r["period"], r["settlement"],
                 r["selection_id"], r["opposite_selection_id"], line, other_line,
                 r["player_id"], r["team_id"], r["stat"], odds(r["price_american"]),
                 odds(r["opposite_price_american"]), observed, captured, kickoff)

def load_csv(path: Path, role: str) -> tuple[list[Quote], str]:
    raw = path.read_bytes()
    if len(raw) > 20_000_000 or not raw:
        raise Blocked("EMPTY_OR_OVERSIZE_CSV")
    try:
        from io import StringIO
        content = raw.decode("utf-8-sig")
        # The header/record count must not be changed by silent treatment of
        # blank records. A blank line can hide a lost quoted selection.
        physical_records = list(csv.reader(StringIO(content, newline=""), strict=True))
        if any(not record for record in physical_records):
            raise Blocked("EMPTY_CSV_RECORD")
        reader = csv.DictReader(StringIO(content, newline=""),
                                restkey="__UNEXPECTED_CSV_EXTRA__", strict=True)
        if (not reader.fieldnames or
            len(reader.fieldnames) != len(set(reader.fieldnames)) or
            not set(FIELDS).issubset(reader.fieldnames)):
            raise Blocked("MISSING_OR_DUPLICATE_CSV_HEADERS")
        parsed = []
        for line, row in enumerate(reader, 2):
            if "__UNEXPECTED_CSV_EXTRA__" in row or None in row:
                raise Blocked("CSV_EXTRA_FIELDS_ROW_" + str(line))
            if any(v is None for v in row.values()):
                raise Blocked("CSV_TRUNCATED_ROW_" + str(line))
            parsed.append(parse_quote(row, role))
    except UnicodeError as exc:
        raise Blocked("NON_UTF8_CSV") from exc
    except csv.Error as exc:
        raise Blocked("MALFORMED_CSV_RECORD") from exc
    if not parsed:
        raise Blocked("NO_QUOTE_ROWS")
    seen = set()
    for q in parsed:
        key = (q.source, q.source_event_id, q.source_market_id, q.identity, q.observed)
        if key in seen:
            raise Blocked("DUPLICATE_SOURCE_QUOTE_AT_SAME_TIME")
        seen.add(key)
    return parsed, hashlib.sha256(raw).hexdigest()

def compare(takes: list[Quote], history: list[Quote], max_close_seconds: int = 600) -> list[dict]:
    if not 1 <= max_close_seconds <= 3600:
        raise Blocked("INVALID_CLOSE_WINDOW")
    # Index once: a complete multi-sport history can contain many thousands of
    # quotes and scanning the entire history for every TAKE is unnecessarily slow.
    indexed = {}
    for quote in history:
        indexed.setdefault(quote.identity, []).append(quote)
    seen_takes, out = set(), []
    for taken in takes:
        if taken.identity in seen_takes:
            raise Blocked("DUPLICATE_CANONICAL_TAKE")
        seen_takes.add(taken.identity)
        exact = [q for q in indexed.get(taken.identity, ()) if
                 taken.observed < q.observed < taken.kickoff and
                 0 < (taken.kickoff - q.observed).total_seconds() <= max_close_seconds]
        # A later price from a *different* capture chain is a reference, not the
        # closing snapshot of the TAKE source. Prefer that source's latest quote.
        # If that latest same-source quote fails integrity, DO NOT cherry-pick an
        # older same-source price or cross-source substitute to manufacture CLV.
        same_source = [q for q in exact if q.source == taken.source]
        eligible_pool = same_source if same_source else exact
        latest = max((q.observed for q in eligible_pool), default=None)
        candidates = [q for q in eligible_pool if q.observed == latest]
        if len(candidates) > 1:
            status, close = "AMBIGUOUS_LAST_CLOSE", None
        elif not candidates:
            status, close = "NO_EXACT_MATCHED_CLOSE", None
        else:
            close = candidates[0]
            if close.source != taken.source:
                status = "CROSS_SOURCE_REFERENCE_ONLY"
            elif (not taken.source_market_id or not close.source_market_id or
                  close.source_event_id != taken.source_event_id or close.source_market_id != taken.source_market_id
                  or close.mapping_version != taken.mapping_version):
                status = "PROVIDER_MARKET_CROSSWALK_UNVERIFIED"
            elif close.captured >= close.kickoff:
                status = "RETROSPECTIVE_HISTORY_UNVERIFIED"
            elif not (taken.captured < close.captured):
                status = "CLOSE_ARCHIVED_BEFORE_TAKE"
            # The observed TAKE price must still have been fresh when it was
            # actually archived. Otherwise a stale quote can create false CLV.
            elif (taken.captured - taken.observed).total_seconds() > 300:
                status = "TAKE_QUOTE_STALE_AT_CAPTURE"
            # An observation captured later can still describe market prices
            # that existed before the actual TAKE archival time.
            elif close.observed <= taken.captured:
                status = "CLOSE_OBSERVED_BEFORE_TAKE_CAPTURE"
            elif (close.captured - close.observed).total_seconds() > 300:
                status = "CLOSE_QUOTE_STALE_AT_CAPTURE"
            else:
                status = "SAME_SOURCE_STRUCTURAL_PAPER"
        # Research-only reference delta is available for rejected provenance
        # states, but the dedicated CLV field is NULL unless the source path,
        # original pregame archive and exact source market agree.
        delta = str((close.no_vig_probability - taken.no_vig_probability) * 100) if close else None
        valid_structural_close = status == "SAME_SOURCE_STRUCTURAL_PAPER"
        out.append({
            "status": status, "sport": taken.sport, "event_id": taken.event_id,
            "book": clean_book(taken.book), "market_kind": taken.kind,
            "period": taken.period, "selection_id": taken.selection_id,
            "line": taken.line, "player_id": taken.player_id,
            "taken_source": taken.source, "taken_observed_utc": taken.observed.isoformat(),
            "taken_price_american": taken.price,
            "taken_opposite_price_american": taken.opposite_price,
            "taken_novig_probability": str(taken.no_vig_probability),
            "closing_source": close.source if close else None,
            "close_observed_utc": close.observed.isoformat() if close else None,
            "close_price_american": close.price if close else None,
            "close_opposite_price_american": close.opposite_price if close else None,
            "close_novig_probability": str(close.no_vig_probability) if close else None,
            "clv_probability_points": delta if valid_structural_close else None,
            "reference_delta_probability_points": delta if close and not valid_structural_close else None,
            "captured_close_post_kickoff": close.captured >= close.kickoff if close else None,
            "source_authenticated": False, "official_counted": 0, "approved_stake_u": 0,
            "warning": "Provider timestamps, market mapping and original sportsbook quote authenticity are unverified",
        })
    return out

def run(taken_path: Path, history_paths: list[Path]) -> dict:
    takes, taken_sha = load_csv(taken_path, "TAKE")
    all_history, manifests = [], []
    for path in history_paths:
        rows, digest = load_csv(path, "HISTORY")
        all_history.extend(rows)
        manifests.append({"file_name": path.name, "sha256": digest, "rows": len(rows)})
    matches = compare(takes, all_history)
    counts = {status: sum(r["status"] == status for r in matches) for status in sorted({r["status"] for r in matches})}
    return {
        "schema": "sportsedge-historical-clv-reference-v2",
        "state": "PAPER_0U_UNAUTHENTICATED",
        "taken_sha256": taken_sha, "history_files": manifests,
        "take_rows": len(takes), "history_rows": len(all_history),
        "comparable_rows": sum(r["clv_probability_points"] is not None for r in matches),
        "reference_only_rows": sum(r["reference_delta_probability_points"] is not None for r in matches),
        "status_counts": counts,
        "official_counted": 0, "approved_stake_u": 0, "matches": matches,
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taken", type=Path, required=True)
    parser.add_argument("--history", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output == REPO_ROOT or REPO_ROOT in output.parents:
        raise Blocked("PRIVATE_CLV_OUTPUT_MUST_BE_OUTSIDE_PUBLIC_REPO")
    if output.exists():
        raise Blocked("CREATE_ONLY_OUTPUT_REFUSES_OVERWRITE")
    for inp in [args.taken, *args.history]:
        resolved = inp.resolve()
        if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
            raise Blocked("PRIVATE_CLV_INPUT_MUST_BE_OUTSIDE_PUBLIC_REPO")
    result = run(args.taken, args.history)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(output, flags, 0o600), "w", encoding="utf-8") as fd:
        json.dump(result, fd, indent=2, sort_keys=True, allow_nan=False)
        fd.write("\n")
    print(json.dumps({k: result[k] for k in ("state", "take_rows", "history_rows", "comparable_rows", "official_counted")}, sort_keys=True))

if __name__ == "__main__":
    main()
