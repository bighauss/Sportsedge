"""PAPER-only R4 paired-quote structural audit.

This detects malformed and unmatched bookmaker offers. It does NOT establish
bookmaker authenticity, real-time freshness, positive EV or release eligibility.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import re

ASCII_DECIMAL = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?\Z")
NUMERIC = {"SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"}
CATEGORICAL = {"ML", "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "NRFI", "YRFI"}
TWO_SIDED = {"ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"}
MARKET_ALIAS = {"MONEYLINE": "ML", "MONEY_LINE": "ML",
                "PLAYERPROP": "PLAYER_PROP", "PROP": "PLAYER_PROP",
                "TEAMTOTAL": "TEAM_TOTAL"}
PERIOD_ALIAS = {"FULL_GAME": "FG", "FULLGAME": "FG", "H1": "1H",
                "H2": "2H", "FIRST_HALF": "1H",
                "SECOND_HALF": "2H", "FIRST_FIVE": "F5"}
BOOK_ALIAS = {"dk": "draftkings", "draftkings.com": "draftkings",
              "draftkings": "draftkings"}


def normalize_line(value, market):
    if not isinstance(value, str):
        raise ValueError("NON_STRING_LINE")
    value = value.strip()
    market = MARKET_ALIAS.get(market.upper(), market.upper())
    if market in CATEGORICAL:
        if market == "ML" and (not value or (
                ASCII_DECIMAL.fullmatch(value) and Decimal(value) == 0)):
            return ""
        if not value:
            return ""
        raise ValueError("CATEGORICAL_MARKET_HAS_LINE")
    if market not in NUMERIC:
        raise ValueError("UNKNOWN_MARKET")
    if not ASCII_DECIMAL.fullmatch(value):
        raise ValueError("NON_ASCII_OR_INVALID_NUMERIC_LINE")
    number = Decimal(value)
    if number == 0:
        return "0"
    if market in {"TOTAL", "TEAM_TOTAL", "PLAYER_PROP"} and number < 0:
        raise ValueError("NEGATIVE_NON_SPREAD_LINE")
    if abs(number) > 10000:
        raise ValueError("OUT_OF_RANGE_LINE")
    return str(number.normalize())


def _utc(raw):
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def _american(raw):
    if not re.fullmatch(r"[+-][0-9]{3,7}", raw):
        return None
    n = int(raw)
    if abs(n) < 100 or abs(n) > 1000000:
        return None
    return 100 / (100 + n) if n > 0 else -n / (-n + 100)


def audit_rows(rows):
    """Return zero-based-file-row issue objects, with 1-indexed header counted.

    A quote with one side missing is NOT made complete by another book.
    Periods, participants and alternate rungs are matched separately.
    """
    issues = defaultdict(set)
    groups = defaultdict(list)
    seen = set()
    starts = {}
    quote_ids = set()
    for index, row in enumerate(rows, 2):
        get = lambda k: (row.get(k) or "").strip()
        market0 = get("market").upper()
        market = MARKET_ALIAS.get(market0, market0)
        period0 = get("period").upper()
        period = PERIOD_ALIAS.get(period0, period0)
        side = get("side").upper()
        try:
            line = normalize_line(get("line"), market)
        except ValueError as exc:
            issues[index].add(str(exc))
            continue
        sport = get("sport").upper()
        event = get("event_id").casefold()
        book = BOOK_ALIAS.get(get("book").casefold(), get("book").casefold())
        player = get("player_id").casefold()
        team = get("team_id").casefold()
        stat = get("stat").casefold()
        offered_id = get("provider_market_id").casefold()
        try:
            stamp = _utc(get("captured_utc"))
            starts_at = _utc(get("event_start_utc"))
            timestamp = stamp.isoformat()
            evkey = (sport, event)
            if evkey in starts and starts[evkey] != starts_at:
                issues[index].add("CONFLICTING_CANONICAL_EVENT_START")
            starts.setdefault(evkey, starts_at)
        except ValueError:
            timestamp = get("captured_utc")
            issues[index].add("INVALID_TIMESTAMP")
            stamp = None
        quote_id = get("provider_quote_id").casefold()
        qkey = (book, quote_id)
        if qkey in quote_ids:
            issues[index].add("REUSED_CANONICAL_BOOK_QUOTE_ID")
        quote_ids.add(qkey)
        # The HOME/AWAY ML and spread use different team IDs on opposite sides;
        # the team ID must not split one game into two separate quote pairs.
        # Team totals, in contrast, must be grouped by the selected team.
        party = ((team,) if market == "TEAM_TOTAL" else
                 (player, stat) if market == "PLAYER_PROP" else ())
        identity = (sport, event, book, market, period, party, side, line,
                    timestamp, offered_id)
        if identity in seen:
            issues[index].add("CANONICAL_DUPLICATE_SELECTION")
        seen.add(identity)
        if market not in TWO_SIDED:
            continue  # First TD etc. are not necessarily two-way book markets.
        # Group spread legs by absolute rung; totals/props by signed threshold.
        ladder = str(abs(Decimal(line))) if market == "SPREAD" else line
        group = (sport, event, book, market, period, party, offered_id, ladder)
        groups[group].append((index, side, line, stamp, get("price_american")))

    for group, entries in groups.items():
        market = group[3]
        allowed = {"HOME", "AWAY"} if market in ("ML", "SPREAD") else {"OVER", "UNDER"}
        if len(entries) != 2 or {x[1] for x in entries} != allowed:
            for index, *_ in entries:
                issues[index].add("UNMATCHED_TWO_SIDED_BOOK_OFFER")
            continue
        (_, side1, line1, stamp1, price1), (_, side2, line2, stamp2, price2) = entries
        if market == "SPREAD" and Decimal(line1) != -Decimal(line2):
            for index, *_ in entries:
                issues[index].add("OPPOSING_SPREAD_SIGN_MISMATCH")
        if stamp1 is not None and stamp2 is not None:
            if abs((stamp1 - stamp2).total_seconds()) > 30:
                for index, *_ in entries:
                    issues[index].add("OPPOSITE_SNAPSHOT_SKEW_GT_30_SECONDS")
        p1, p2 = _american(price1), _american(price2)
        if p1 is not None and p2 is not None:
            hold = p1 + p2
            # Not a proof of bad quotes: unusual same-book hold needs manual
            # examination; keep flagged, never promote automatically.
            if hold < 0.995 or hold > 1.15:
                for index, *_ in entries:
                    issues[index].add("SUSPICIOUS_SAME_BOOK_OVERROUND_REVIEW")
    return [{"row": idx, "reasons": sorted(reasons)}
            for idx, reasons in sorted(issues.items())]
