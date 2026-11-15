"""Research-only adversarial pair audit layered on R4; never promotes a quote.

Run after R4's row validation. Incomplete book pairs are BLOCK, not imputed.
"""
import csv
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ASCII_DECIMAL = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?\Z")
OPPOSITE = {"HOME":"AWAY", "AWAY":"HOME", "OVER":"UNDER",
            "UNDER":"OVER", "YES":"NO", "NO":"YES"}
NUMERIC = {"SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"}
CATEGORICAL = {"ML", "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "NRFI", "YRFI"}

def normalize_line(value, market):
    value = value.strip()
    if market in CATEGORICAL:
        if market == "ML" and value in ("", "0", "+0", "-0", "0.0", "0.00", "00"):
            return ""
        if value == "":
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

def audit_rows(rows):
    """Return row-indexed fail-closed reasons. Input is private, output sanitized."""
    problems = defaultdict(set)
    groups = defaultdict(list)
    seen = set()
    for index, row in enumerate(rows, 2):
        get = lambda k: (row.get(k) or "").strip()
        market = get("market").upper()
        side = get("side").upper()
        try:
            line = normalize_line(get("line"), market)
        except ValueError as exc:
            problems[index].add(str(exc))
            continue
        event = get("event_id").casefold()
        book = get("book").casefold()
        player = get("player_id").casefold()
        team = get("team_id").casefold()
        stat = get("stat").casefold()
        period = get("period").upper()
        captured = get("captured_utc")
        identity = (get("sport").upper(), event, book, market, period,
                    player, team, stat, side, line, captured)
        if identity in seen:
            problems[index].add("CANONICAL_DUPLICATE_SELECTION")
        seen.add(identity)
        ladder = (str(abs(Decimal(line))) if market == "SPREAD"
                  else line if market in NUMERIC else "")
        group = (get("sport").upper(), event, book, market, period,
                 player, team, stat, captured, ladder)
        groups[group].append((index, side, line))
    for group, entries in groups.items():
        market = group[3]
        if len(entries) != 2 or set(x[1] for x in entries) not in (
                {"HOME", "AWAY"}, {"OVER", "UNDER"}, {"YES", "NO"}):
            for index, _, _ in entries:
                problems[index].add("UNMATCHED_TWO_SIDED_BOOK_OFFER")
            continue
        (_, side1, line1), (_, side2, line2) = entries
        if market == "SPREAD":
            valid = Decimal(line1) == -Decimal(line2)
        elif market in {"TOTAL", "TEAM_TOTAL", "PLAYER_PROP"}:
            valid = line1 == line2
        else:
            valid = line1 == line2
        if not valid:
            for index, _, _ in entries:
                problems[index].add("OPPOSING_LINE_MISMATCH")
    return [{"row": i, "reasons": sorted(v)} for i, v in sorted(problems.items())]

def audit_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return audit_rows(list(csv.DictReader(f)))
