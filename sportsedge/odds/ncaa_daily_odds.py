"""One private NCAA (CBB/CFB) featured-market odds snapshot, dry-run by default.

PAPER / 0u research intake. Never emits picks, edges, EV, CLV or stakes.

Sports (exact The Odds API v4 keys, re-verified against
https://the-odds-api.com/sports-odds-data/sports-apis.html):
  ncaab -> ``basketball_ncaab``        (manifest sport ``CBB``)
  ncaaf -> ``americanfootball_ncaaf``  (manifest sport ``CFB``)

Snapshots:
  pregame -- morning quote for the pre-freeze paper card;
  close   -- dispatched shortly before start so graders can measure CLV.

Billing contract (https://the-odds-api.com/liveapi/guides/v4/):
  ``/v4/sports/{sport}/odds`` costs ``[markets] x [regions]``; when
  ``bookmakers`` is given every group of 10 books counts as 1 region.
  ``/v4/sports`` and ``/v4/sports/{sport}/events`` do not count against quota.
  If no events are returned the odds call is not charged.

Per run: 1 Central-date claim (made by the workflow BEFORE any request),
1 free ``/sports`` preflight (remaining-credit and in-season check), 1 free
``/events`` window check, and at most 1 paid ``/odds`` call whose budget is
computed before the request.  No retries, no redirects, keys never printed.

The paid call is delegated unchanged to
``sportsedge.odds.free_odds_aggregator_intake.capture`` so the raw bytes and
``sportsedge-oddsapi-aggregator-raw-v1`` manifest are exactly what the CBB
(``models/cbb/cbbd_paper_card.py --odds-api-raw/--odds-api-manifest``) and CFB
(``models/cfb/cfb_paper_card.py --odds-archive RAW SUMMARY CROSSWALK``) paper
card Odds API archive loaders consume.  A separate pairs sidecar lists only
complete two-sided per-book pairs for graders; it never replaces the raw file.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request
from zoneinfo import ZoneInfo

from sportsedge.odds.free_odds_aggregator_intake import (
    BASE,
    KEY_RE,
    SPORTS,
    _secure_open,
    capture,
    private_archive_root,
    strict_json,
    utc,
)
from sportsedge.odds.the_odds_api_clv_export import _write_private

CENTRAL = ZoneInfo("America/Chicago")
SPORT_CODES = {"ncaab": "CBB", "ncaaf": "CFB"}
SNAPSHOTS = ("pregame", "close")
MARKETS = ("h2h", "spreads", "totals")
# All four are documented Odds API bookmaker keys; <=10 books == 1 region.
BOOKS = ("draftkings", "fanduel", "betmgm", "pinnacle")
# Do not spend the final credits of the monthly quota on a research snapshot.
RESERVE_CREDITS = 50
# Window (minutes from capture) whose events make a paid call worthwhile.
WINDOWS_MINUTES = {"pregame": 36 * 60, "close": 90}
PREFLIGHT_MAX_BYTES = 2_000_000
PAIRS_SCHEMA = "sportsedge-ncaa-odds-pairs-v1"
RESULT_SCHEMA = "sportsedge-ncaa-daily-odds-v1"
HOLD_FILENAME = "ncaa-daily-odds.quota-hold.json"
ARCHIVE_FIELDS = (
    "schema", "sport", "raw_filename", "original_raw_sha256", "original_bytes",
    "captured_utc", "events_returned", "book_entries", "outcomes_returned",
    "live_poststart_outcomes_blocked",
    "stale_or_missing_aggregator_market_timestamp_outcomes",
    "provider_request_credits_last", "provider_remaining_credits",
    "missing_requested_market_keys_unverified",
)
PAPER = {"official_counted": 0, "approved_stake_u": 0, "edge_verified": False,
         "source_upstream_book_authenticated": False}
SUCCESS_STATES = {
    "DRY_RUN", "SKIPPED_ALREADY_ATTEMPTED", "SKIPPED_SPORT_NOT_IN_SEASON",
    "SKIPPED_NO_EVENTS_IN_WINDOW", "ARCHIVED_PROVIDER_RESPONSE",
    "ARCHIVED_NO_QUOTED_OUTCOMES",
}


def credit_budget(markets=MARKETS, books=BOOKS) -> int:
    """Documented maximum charge for one /odds call, computed BEFORE it."""
    if not markets or not books or len(books) > 10 * 10:
        raise ValueError("BUDGET_INPUT_INVALID")
    return len(markets) * math.ceil(len(books) / 10)


MAX_CREDITS = credit_budget()


def _save(path: Path, document: dict) -> None:
    _write_private(path, (json.dumps(document, sort_keys=True, allow_nan=False) + "\n").encode())


def _credits(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 8:
        return int(value)
    return None


def _stamp(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_key(env=None):
    """Primary key, else (only if primary is absent) the backup; never both."""
    env = os.environ if env is None else env
    for slot, name in (("primary", "SPORTSEDGE_ODDS_API_KEY"), ("primary", "ODDS_API_KEY"),
                       ("backup", "ODDS_API_KEY_BACKUP")):
        value = env.get(name)
        if value:
            if not KEY_RE.fullmatch(value):
                raise ValueError("USER_API_KEY_UNSAFE")
            return value, slot
    raise ValueError("USER_API_KEY_MISSING")


def _free_get(path, params, key, opener):
    """One free GET; refuses redirects/non-200; never echoes the key."""
    # BASE is ".../v4/sports/"; path "" -> /v4/sports, "/{key}/events" -> events.
    url = BASE.rstrip("/") + path
    req = Request(url + "?" + urlencode({"apiKey": key, **params}), headers={
        "Accept": "application/json", "User-Agent": "SportsEdge-UserAuthorized-Research/1.0"})
    try:
        with (opener or _secure_open)(req, timeout=15) as response:
            if hasattr(response, "geturl") and response.geturl() != req.full_url:
                raise ValueError("PREFLIGHT_REDIRECT_REFUSED")
            if hasattr(response, "status") and response.status != 200:
                raise ValueError("PREFLIGHT_UNEXPECTED_HTTP_STATUS")
            raw = response.read(PREFLIGHT_MAX_BYTES + 1)
            headers = response.headers
    except HTTPError as err:
        raise ValueError("PREFLIGHT_HTTP_ERROR_CODE:" + str(err.code)) from None
    except (URLError, OSError):
        raise ValueError("PREFLIGHT_TRANSPORT_FAILED") from None
    if not raw or len(raw) > PREFLIGHT_MAX_BYTES:
        raise ValueError("PREFLIGHT_RESPONSE_EMPTY_OR_OVERSIZE")
    if key.encode("utf-8") in raw:
        raise ValueError("PREFLIGHT_ECHOED_SECRET")
    try:
        return strict_json(raw), headers
    except (UnicodeError, ValueError):
        raise ValueError("PREFLIGHT_JSON_INVALID") from None


def preflight(sport_key, snapshot, key, now, opener=None):
    """Free /sports + /events checks. Returns (state_or_None, facts)."""
    sports, headers = _free_get("", {}, key, opener)
    remaining = _credits(headers.get("x-requests-remaining") if headers else None)
    charged = _credits(headers.get("x-requests-last") if headers else None)
    facts = {"preflight_remaining_credits": remaining, "preflight_credits_last": charged}
    if charged != 0:
        return "PREFLIGHT_UNEXPECTEDLY_CHARGED_PAUSE", facts
    if remaining is None:
        return "BLOCKED_PREFLIGHT_QUOTA_UNVERIFIED", facts
    if remaining < MAX_CREDITS + RESERVE_CREDITS:
        return "BLOCKED_REMAINING_CREDITS_TOO_LOW", facts
    if not isinstance(sports, list) or any(not isinstance(s, dict) for s in sports):
        raise ValueError("PREFLIGHT_SPORTS_NOT_LIST")
    if not any(s.get("key") == sport_key and s.get("active") is True for s in sports):
        return "SKIPPED_SPORT_NOT_IN_SEASON", facts
    window_end = now + timedelta(minutes=WINDOWS_MINUTES[snapshot])
    events, event_headers = _free_get("/" + sport_key + "/events", {
        "dateFormat": "iso", "commenceTimeFrom": _stamp(now),
        "commenceTimeTo": _stamp(window_end)}, key, opener)
    event_charge = _credits(event_headers.get("x-requests-last"))
    event_remaining = _credits(event_headers.get("x-requests-remaining"))
    facts["events_credits_last"] = event_charge
    facts["events_remaining_credits"] = event_remaining
    if event_charge != 0 or event_remaining is None:
        return "PREFLIGHT_EVENTS_QUOTA_UNVERIFIED_PAUSE", facts
    if event_remaining < MAX_CREDITS + RESERVE_CREDITS:
        return "BLOCKED_REMAINING_CREDITS_TOO_LOW", facts
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        raise ValueError("PREFLIGHT_EVENTS_NOT_LIST")
    upcoming = 0
    for ev in events:
        if ev.get("sport_key") != sport_key:
            raise ValueError("PREFLIGHT_EVENT_SPORT_MISMATCH")
        if now < utc(ev.get("commence_time")) <= window_end:
            upcoming += 1
    facts["window_events"] = upcoming
    if not upcoming:
        return "SKIPPED_NO_EVENTS_IN_WINDOW", facts
    return None, facts


def two_sided_pairs(raw: bytes, manifest: dict, snapshot: str):
    """Complete per-book two-sided pairs from the exact archived bytes.

    Pairing matches the paper-card loaders: h2h/spreads by exact provider
    home/away names (spread points must be exact negatives), totals by
    Over/Under with equal points; exactly one outcome per side.  Anything
    else is counted and excluded, never repaired.
    """
    digest = "sha256:" + sha256(raw).hexdigest()
    if manifest.get("original_raw_sha256") != digest:
        raise ValueError("PAIRS_RAW_HASH_MISMATCH")
    captured = datetime.fromisoformat(manifest["captured_utc"]).astimezone(timezone.utc)
    events = strict_json(raw)
    census = {"partial_or_inconsistent_pairs": 0, "poststart_events_excluded": 0,
              "events_outside_window": 0, "UNEXPECTED_EXTRA_OUTCOME": 0}
    rows, listing = [], []
    for ev in events:
        start = utc(ev["commence_time"])
        minutes = (start - captured).total_seconds() / 60
        listing.append({"odds_event_id": ev["id"], "commence_time": ev["commence_time"],
                        "home_team": ev["home_team"], "away_team": ev["away_team"]})
        if minutes <= 0:
            census["poststart_events_excluded"] += 1
            continue
        in_window = minutes <= WINDOWS_MINUTES[snapshot]
        if not in_window:
            census["events_outside_window"] += 1
        home, away = ev["home_team"], ev["away_team"]
        for book in ev["bookmakers"]:
            for m in book["markets"]:
                if len(m["outcomes"]) > 2:
                    census["UNEXPECTED_EXTRA_OUTCOME"] += 1
                    census["partial_or_inconsistent_pairs"] += 1
                    continue
                by = {}
                for o in m["outcomes"]:
                    by.setdefault(o["name"], []).append(o)
                key = m["key"]
                sides = (home, away) if key in ("h2h", "spreads") else ("Over", "Under")
                a, b = by.get(sides[0], []), by.get(sides[1], [])
                ok = len(a) == 1 and len(b) == 1 and len(by) == 2
                line = None
                if ok and key == "h2h":
                    ok = a[0].get("point") is None and b[0].get("point") is None
                elif ok and key == "spreads":
                    line = a[0].get("point")
                    ok = line is not None and b[0].get("point") == -line
                elif ok and key == "totals":
                    line = a[0].get("point")
                    ok = line is not None and b[0].get("point") == line
                if not ok:
                    census["partial_or_inconsistent_pairs"] += 1
                    continue
                rows.append({
                    "odds_event_id": ev["id"], "commence_time": ev["commence_time"],
                    "home_team": home, "away_team": away, "book": book["key"],
                    "market": key, "line": line,
                    "side_a": sides[0], "price_a": a[0]["price"],
                    "side_b": sides[1], "price_b": b[0]["price"],
                    "provider_last_update_utc": m.get("last_update") or book.get("last_update"),
                    "minutes_before_start": round(minutes, 2),
                    "in_snapshot_window": in_window,
                })
    return {"schema": PAIRS_SCHEMA, "snapshot": snapshot, "sport": manifest["sport"],
            "captured_utc": manifest["captured_utc"], "raw_sha256": digest,
            "raw_filename": manifest["raw_filename"],
            "line_convention": "spreads: line = home point; totals: line = total; "
                               "price_a = home/Over, price_b = away/Under",
            "close_semantics": ("closing quote only for rows with in_snapshot_window=true "
                                "(<= %d min before start)" % WINDOWS_MINUTES["close"]
                                if snapshot == "close" else "pregame quote, not a close"),
            "events": listing, "rows": rows, "census": census, **PAPER}


def run_snapshot(sport: str, snapshot: str, destination: Path, *, execute=False,
                 now: datetime | None = None, opener=None, env=None) -> dict:
    """Claim sport+snapshot+Central date before HTTP; never retries."""
    if sport not in SPORT_CODES or snapshot not in SNAPSHOTS:
        raise ValueError("NCAA_SPORT_OR_SNAPSHOT_INVALID")
    code = SPORT_CODES[sport]
    sport_key = SPORTS[code]
    clock = datetime.now(timezone.utc) if now is None else now
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("PILOT_CLOCK_NEEDS_UTC_OFFSET")
    clock = clock.astimezone(timezone.utc)
    day = clock.astimezone(CENTRAL).date().isoformat()
    environ = os.environ if env is None else env
    claimed = environ.get("SPORTSEDGE_DAILY_CLAIM_DATE_CT")
    if claimed and claimed != day:
        raise ValueError("PILOT_CENTRAL_DATE_CHANGED_AFTER_CLAIM")
    if destination.is_symlink():
        raise ValueError("PILOT_ARCHIVE_MUST_NOT_BE_SYMLINK")
    root = private_archive_root(destination)
    base = {
        "schema": RESULT_SCHEMA, "sport": sport, "manifest_sport": code,
        "sport_key": sport_key, "snapshot": snapshot, "date_ct": day,
        "attempt_clock_utc": clock.isoformat(), "markets": list(MARKETS),
        "bookmakers": list(BOOKS), "regions_equivalent": math.ceil(len(BOOKS) / 10),
        "maximum_credits_this_attempt": MAX_CREDITS,
        "reserve_credits_floor": RESERVE_CREDITS,
        "snapshot_window_minutes": WINDOWS_MINUTES[snapshot],
        "credits_used": 0, **PAPER,
    }
    if not execute:
        return {**base, "state": "DRY_RUN"}
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("PILOT_ARCHIVE_MUST_BE_OWNER_ONLY")
    halt = root / HOLD_FILENAME
    if os.path.lexists(halt):
        return {**base, "state": "BLOCKED_PRIOR_QUOTA_REVIEW"}
    stem = root / f"ncaa-{sport}-{snapshot}-{day}"
    try:
        _save(stem.with_suffix(".attempt.json"), {**base, "state": "ATTEMPT_CLAIMED"})
    except FileExistsError:
        return {**base, "state": "SKIPPED_ALREADY_ATTEMPTED"}

    def hold(reason):
        try:
            _save(halt, {"reason": reason, "date_ct": day, "sport": sport, "snapshot": snapshot})
        except FileExistsError:
            pass

    try:
        key, slot = resolve_key(environ)
    except ValueError:
        result = {**base, "state": "BLOCKED_SOURCE_AUTH"}
        _save(stem.with_suffix(".result.json"), result)
        return result
    base["api_key_slot"] = slot
    try:
        state, facts = preflight(sport_key, snapshot, key, clock, opener)
    except (ValueError, TypeError, KeyError, OSError):
        state, facts = "BLOCKED_PREFLIGHT_FAILED", {}
    base.update(facts)
    if state is not None:
        if state.endswith("_PAUSE"):
            hold(state)
        result = {**base, "state": state, "archive": None}
        _save(stem.with_suffix(".result.json"), result)
        return result
    try:
        summary = capture(code, root, key=key, markets=MARKETS, bookmakers=BOOKS, opener=opener, audit_only=True)
    except (ValueError, TypeError, ArithmeticError, OSError, KeyError):
        # Provider may have charged even if parsing/archiving failed.
        hold("CAPTURE_FAILED_REVIEW_PRIVATELY")
        result = {**base, "state": "CAPTURE_FAILED_REVIEW_PRIVATELY", "archive": None,
                  "credits_used": None}
        _save(stem.with_suffix(".result.json"), result)
        return result
    charge = _credits(summary.get("provider_request_credits_last"))
    remaining = _credits(summary.get("provider_remaining_credits"))
    pairs = None
    try:
        raw = (root / summary["raw_filename"]).read_bytes()
        pairs = two_sided_pairs(raw, {**summary, "sport": code}, snapshot)
    except (ValueError, TypeError, KeyError, OSError):
        pairs = None
    if charge is None or remaining is None:
        state = "ARCHIVED_QUOTA_UNCONFIRMED_REVIEW"
    elif charge > MAX_CREDITS:
        state = "ARCHIVED_UNEXPECTED_QUOTA_COST_PAUSE"
    elif remaining < MAX_CREDITS + RESERVE_CREDITS:
        state = "ARCHIVED_LOW_REMAINING_QUOTA_PAUSE"
    elif summary.get("stale_or_missing_aggregator_market_timestamp_outcomes"):
        state = "ARCHIVED_QUOTE_CLOCK_REVIEW"
    elif pairs is None:
        state = "ARCHIVED_PAIRS_SIDECAR_FAILED_REVIEW"
    elif not summary.get("outcomes_returned") or not any(r["in_snapshot_window"] for r in pairs["rows"]):
        state = "ARCHIVED_NO_QUOTED_OUTCOMES"
    else:
        state = "ARCHIVED_PROVIDER_RESPONSE"
    if state != "ARCHIVED_PROVIDER_RESPONSE":
        pairs = None
    if pairs is not None:
        _save(stem.with_suffix(".pairs.json"), pairs)
    audit_filename = Path(summary["raw_filename"]).stem + ".manifest.json"
    manifest_filename = None
    if state == "ARCHIVED_PROVIDER_RESPONSE" and snapshot == "pregame" and pairs["rows"]:
        # Preserve the original audit manifest. Only this new receipt carries
        # the card-loader sport/schema, and the digest binds the raw bytes.
        manifest_filename = stem.with_suffix(".accepted.json").name
        _save(root / manifest_filename, {
            **summary, "schema": "sportsedge-oddsapi-aggregator-raw-v1", "sport": code,
            "acceptance_state": state, "snapshot": snapshot, "audit_manifest": audit_filename,
        })
    result = {**base, "state": state, "credits_used": charge,
              "archive": {k: summary.get(k) for k in ARCHIVE_FIELDS},
              "audit_manifest_filename": audit_filename, "manifest_filename": manifest_filename,
              "pairs_filename": stem.with_suffix(".pairs.json").name if pairs else None,
              "two_sided_pairs": len(pairs["rows"]) if pairs else 0,
              "two_sided_pairs_in_window": (sum(r["in_snapshot_window"] for r in pairs["rows"])
                                            if pairs else 0),
              "pairs_census": pairs["census"] if pairs else None}
    if state.endswith(("_PAUSE", "_REVIEW")):
        hold(state)
    _save(stem.with_suffix(".result.json"), result)
    return result


LOG_FIELDS = ("state", "sport", "snapshot", "date_ct", "maximum_credits_this_attempt",
              "credits_used", "window_events", "two_sided_pairs",
              "two_sided_pairs_in_window", "api_key_slot", "official_counted",
              "approved_stake_u")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("private_archive", type=Path)
    parser.add_argument("--sport", choices=sorted(SPORT_CODES), required=True)
    parser.add_argument("--snapshot", choices=SNAPSHOTS, required=True)
    parser.add_argument("--execute", action="store_true", help="permit one live provider request")
    args = parser.parse_args(argv)
    try:
        report = run_snapshot(args.sport, args.snapshot, args.private_archive, execute=args.execute)
    except (OSError, ValueError, RuntimeError):
        print("NCAA_ODDS_LOCAL_ARCHIVE_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps({k: report.get(k) for k in LOG_FIELDS}, sort_keys=True))
    return 0 if report["state"] in SUCCESS_STATES else 2


if __name__ == "__main__":
    raise SystemExit(main())
