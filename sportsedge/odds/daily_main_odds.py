"""One private daily NFL featured-market capture, dry-run by default."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from sportsedge.odds.free_odds_aggregator_intake import (
    capture,
    private_archive_root,
)
from sportsedge.odds.the_odds_api_clv_export import _write_private


SPORT = "NFL"
MARKETS = ("h2h", "spreads", "totals")
BOOKS = ("draftkings", "fanduel")  # one provider quota group, not two source chains
MAX_CREDITS = len(MARKETS)
CENTRAL = ZoneInfo("America/Chicago")
ARCHIVE_FIELDS = (
    "state", "raw_filename", "original_raw_sha256", "captured_utc", "events_returned",
    "outcomes_returned", "live_poststart_outcomes_blocked",
    "stale_or_missing_aggregator_market_timestamp_outcomes",
    "provider_remaining_credits", "provider_request_credits_last",
    "missing_requested_market_keys_unverified",
)


def _save(path: Path, document: dict) -> None:
    _write_private(path, (json.dumps(document, sort_keys=True, allow_nan=False) + "\n").encode())


def _credits(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 8:
        return int(value)
    return None


def run_daily(destination: Path, *, execute: bool = False, now: datetime | None = None) -> dict:
    """Claim the Central date before HTTP; no automatic retry, even on failure."""
    clock = datetime.now(timezone.utc) if now is None else now
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("PILOT_CLOCK_NEEDS_UTC_OFFSET")
    day = clock.astimezone(CENTRAL).date().isoformat()
    root = private_archive_root(destination)
    if destination.is_symlink():
        raise ValueError("PILOT_ARCHIVE_MUST_NOT_BE_SYMLINK")
    base = {
        "schema": "sportsedge-daily-featured-odds-pilot-v1",
        "date_ct": day,
        "attempt_clock_utc": clock.astimezone(timezone.utc).isoformat(),
        "sport": SPORT,
        "markets": list(MARKETS),
        "bookmakers": list(BOOKS),
        "maximum_credits_this_attempt": MAX_CREDITS,
        "maximum_pilot_credits_per_31_central_dates": MAX_CREDITS * 31,
        "full_board": False,
        "close": False,
        "source_upstream_book_authenticated": False,
        "official_counted": 0,
        "approved_stake_u": 0,
    }
    if not execute:
        return {**base, "state": "DRY_RUN"}
    # A stable private destination is necessary for both access control and
    # idempotency. Use the same root for every run, never ephemeral storage.
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("PILOT_ARCHIVE_MUST_BE_OWNER_ONLY")
    halt = root / "daily-nfl-main.quota-hold.json"
    if os.path.lexists(halt):
        return {**base, "state": "BLOCKED_PRIOR_QUOTA_REVIEW"}
    stem = root / f"daily-nfl-main-{day}"
    try:
        _save(stem.with_suffix(".attempt.json"), {**base, "state": "ATTEMPT_CLAIMED"})
    except FileExistsError:
        return {**base, "state": "SKIPPED_ALREADY_ATTEMPTED"}
    try:
        summary = capture(SPORT, root, markets=MARKETS, bookmakers=BOOKS)
    except (ValueError, TypeError, ArithmeticError, OSError, KeyError):
        # Do not expose a provider response, credentials or a private path.
        result = {**base, "state": "CAPTURE_FAILED_REVIEW_PRIVATELY", "archive": None}
    else:
        charge = _credits(summary.get("provider_request_credits_last"))
        remaining = _credits(summary.get("provider_remaining_credits"))
        if charge is None or remaining is None:
            state = "ARCHIVED_QUOTA_UNCONFIRMED_REVIEW"
        elif charge > MAX_CREDITS:
            state = "ARCHIVED_UNEXPECTED_QUOTA_COST_PAUSE"
        elif remaining < MAX_CREDITS:
            state = "ARCHIVED_LOW_REMAINING_QUOTA_PAUSE"
        elif not summary["outcomes_returned"]:
            state = "ARCHIVED_NO_QUOTED_OUTCOMES"
        else:
            state = "ARCHIVED_PROVIDER_RESPONSE"
        result = {**base, "state": state, "archive": {k: summary.get(k) for k in ARCHIVE_FIELDS}}
        if state.endswith(("_PAUSE", "_REVIEW")):
            try:
                _save(halt, {"reason": state, "date_ct": day})
            except FileExistsError:
                pass
    _save(stem.with_suffix(".result.json"), result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_archive", type=Path)
    parser.add_argument("--execute", action="store_true", help="permit one live provider request")
    args = parser.parse_args(argv)
    try:
        report = run_daily(args.private_archive, execute=args.execute)
    except (OSError, ValueError, RuntimeError):
        print("PILOT_LOCAL_ARCHIVE_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps({k: report[k] for k in (
        "state", "date_ct", "maximum_credits_this_attempt",
        "maximum_pilot_credits_per_31_central_dates", "official_counted", "approved_stake_u",
    )}, sort_keys=True))
    return 0 if report["state"] in {
        "DRY_RUN", "SKIPPED_ALREADY_ATTEMPTED", "ARCHIVED_PROVIDER_RESPONSE",
        "ARCHIVED_NO_QUOTED_OUTCOMES",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
