#!/usr/bin/env python3
"""Fail-closed offered-market and DK core-market completeness audit.

Accepts PRIVATE operator-supplied authorized-provider archive manifests only.
This never fetches books, authenticates a provider, prices selections or promotes wagers.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat

REPO = Path(__file__).resolve().parents[2]
CORE = frozenset(("ML", "SPREAD", "TOTAL"))
SPORTS = frozenset(("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"))
REASONS = frozenset(("NOT_OFFERED", "NOT_CAPTURED", "NO_AUTHORIZED_ACCESS",
                     "NO_PRICE", "UNSUPPORTED", "STALE", "AFTER_START",
                     "IDENTITY_UNMATCHED", "PROVIDER_ERROR"))
# An absent core outcome is not an offered market; never fabricate a provider
# market ID or a quote to make an inventory check pass. In particular,
# NOT_OFFERED requires upstream authentication that this offline tool lacks.
CORE_ABSENCE_REASONS = REASONS - {"NOT_OFFERED", "AFTER_START"}


class CompletenessError(ValueError):
    pass


def _utc(value):
    if not isinstance(value, str) or not value:
        raise CompletenessError("UTC_TIMESTAMP_REQUIRED")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CompletenessError("INVALID_ISO_TIMESTAMP") from exc
    if d.utcoffset() is None or d.utcoffset().total_seconds() != 0:
        raise CompletenessError("UTC_OFFSET_REQUIRED")
    return d.astimezone(timezone.utc)


def _private_path(value):
    lexical = Path(os.path.abspath(os.fspath(value)))
    resolved = lexical.resolve()
    if lexical == REPO or REPO in lexical.parents or resolved == REPO or REPO in resolved.parents:
        raise CompletenessError("PRIVATE_ARCHIVE_OR_REPORT_REQUIRED")
    if lexical.is_symlink() or any(a.is_symlink() for a in lexical.parents):
        raise CompletenessError("SYMLINK_ARCHIVE_OR_REPORT_REFUSED")
    return lexical


def _unique_pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise CompletenessError("DUPLICATE_ARCHIVE_FIELD:" + k)
        d[k] = v
    return d


def _bad_constant(v):
    raise CompletenessError("NONFINITE_ARCHIVE_NUMBER")


def _key(row):
    if not isinstance(row, dict):
        raise CompletenessError("NONOBJECT_MARKET_ROW")
    fields = ("book", "provider_market_id", "family", "period", "side", "line")
    values = tuple(row.get(k) for k in fields)
    if not all(isinstance(v, str) and v.strip() for v in values[:5]) or not isinstance(values[5], str):
        raise CompletenessError("MARKET_IDENTITY_MISSING")
    # A provider_market_id may cover multiple players/teams or alternate rungs.
    # Retain participant and settlement identity rather than collapsing them.
    extras = ("team_id", "player_id", "stat", "settlement")
    identifiers = tuple(row.get(k, "") for k in extras)
    if any(not isinstance(v, str) for v in identifiers):
        raise CompletenessError("MARKET_PARTICIPANT_IDENTITY_INVALID")
    family = values[2].upper()
    if "PLAYER_PROP" in family and (not identifiers[1] or not identifiers[2]):
        raise CompletenessError("PLAYER_AND_STAT_IDENTITY_REQUIRED")
    if "TEAM_TOTAL" in family and not identifiers[0]:
        raise CompletenessError("TEAM_TOTAL_IDENTITY_REQUIRED")
    return values + identifiers


def _core_absence(row, start):
    """Record a missing DK core *slot*, not an invented offered outcome."""
    if not isinstance(row, dict):
        raise CompletenessError("CORE_ABSENCE_NOT_OBJECT")
    expected = {"book", "family", "period", "side", "reason", "noted_at_utc"}
    if set(row) != expected:
        raise CompletenessError("CORE_ABSENCE_SCHEMA_INVALID")
    book, family, period, side = (row[k] for k in
                                  ("book", "family", "period", "side"))
    if book != "DK" or family not in CORE or period != "FG":
        raise CompletenessError("CORE_ABSENCE_NOT_DK_FULL_GAME")
    sides = ("HOME", "AWAY") if family in ("ML", "SPREAD") else ("OVER", "UNDER")
    if side not in sides:
        raise CompletenessError("CORE_ABSENCE_WRONG_SIDE")
    if not isinstance(row["reason"], str) or row["reason"] not in CORE_ABSENCE_REASONS:
        raise CompletenessError("CORE_ABSENCE_REASON_UNVERIFIED_OR_INVALID")
    if _utc(row["noted_at_utc"]) >= start:
        raise CompletenessError("CORE_ABSENCE_NOTED_AFTER_START")
    return (book, family, period, side)


def _recorded_quote(row, start):
    mandatory = ("line", "price_american", "original_observed_utc", "captured_utc")
    if any(k not in row for k in mandatory):
        raise CompletenessError("ORIGINAL_QUOTE_FIELDS_MISSING")
    if not isinstance(row["line"], str):
        raise CompletenessError("QUOTE_LINE_MISSING")
    if type(row["price_american"]) is not int or not (100 <= abs(row["price_american"]) <= 100000):
        raise CompletenessError("PRICE_NOT_VALID_AMERICAN_INT")
    observed = _utc(row["original_observed_utc"])
    captured = _utc(row["captured_utc"])
    if observed > captured:
        raise CompletenessError("ORIGINAL_TIMESTAMP_AFTER_CAPTURE")
    if (captured - observed).total_seconds() > 300:
        raise CompletenessError("STALE_ORIGINAL_QUOTE_GT_300S")
    if observed >= start or captured >= start:
        raise CompletenessError("POST_START_QUOTE")
    h = row.get("source_receipt_sha256")
    if h is not None and (not isinstance(h, str) or not re.fullmatch(r"[a-f0-9]{64}", h)):
        raise CompletenessError("INVALID_SOURCE_RECEIPT_HASH")


def evaluate(archive):
    if not isinstance(archive, dict) or archive.get("schema") != "sportsedge-odds-completeness-v1":
        raise CompletenessError("INVALID_ARCHIVE_SCHEMA")
    events = archive.get("events")
    if not isinstance(events, list) or not events:
        raise CompletenessError("NO_EVENTS_IN_ARCHIVE")
    failures, checks = [], []
    seen_events = set()
    for event in events:
        if not isinstance(event, dict):
            raise CompletenessError("EVENT_NOT_OBJECT")
        eid, sport = event.get("event_id"), event.get("sport")
        if not isinstance(eid, str) or not eid or eid in seen_events:
            raise CompletenessError("INVALID_OR_DUPLICATE_EVENT")
        seen_events.add(eid)
        if sport not in SPORTS:
            raise CompletenessError("SPORT_NOT_SUPPORTED")
        start = _utc(event.get("kickoff_utc"))
        catalog, quotes, exclusions = (event.get(k) for k in ("market_inventory", "quotes", "exclusions"))
        # This list explicitly accounts for core slots NOT present in an upstream
        # market inventory, without inventing a provider_market_id or price.
        missing_core = event.get("core_absences", [])
        if not isinstance(catalog, list) or not catalog:
            failures.append({"event_id": eid, "reason": "OFFERED_MARKET_INVENTORY_MISSING"})
            continue
        if not isinstance(quotes, list) or not isinstance(exclusions, list) or not isinstance(missing_core, list):
            failures.append({"event_id": eid, "reason": "QUOTE_OR_EXCLUSION_LIST_MISSING"})
            continue
        keys, fulfilled = set(), set()
        seen_core_absences = set()
        for record in missing_core:
            try:
                missing_slot = _core_absence(record, start)
            except CompletenessError as exc:
                failures.append({"event_id": eid, "reason": str(exc)})
                continue
            if missing_slot in seen_core_absences:
                failures.append({"event_id": eid, "market": missing_slot,
                                 "reason": "DUPLICATE_CORE_ABSENCE"})
            seen_core_absences.add(missing_slot)
        # Preserve the full original offered-outcome census. One source
        # disposition per exact book/market/period/side/line is mandatory:
        # accepting the first of two prices or a price plus NOT_OFFERED
        # makes coverage depend on input order and silently hides conflicts.
        original_disposition_counts = Counter()
        for item in catalog:
            key = _key(item)
            if key in keys:
                failures.append({"event_id": eid, "market": key, "reason": "DUPLICATE_INVENTORY_MARKET"})
            keys.add(key)
        for q in quotes:
            key = _key(q)
            if key in keys:
                original_disposition_counts[key] += 1
            if key not in keys:
                failures.append({"event_id": eid, "market": key, "reason": "QUOTE_NOT_IN_INVENTORY"})
                continue
            try:
                _recorded_quote(q, start)
                fulfilled.add(key)
            except CompletenessError as exc:
                failures.append({"event_id": eid, "market": key, "reason": str(exc)})
        for exclusion in exclusions:
            key = _key(exclusion)
            if key in keys:
                original_disposition_counts[key] += 1
            if key not in keys:
                failures.append({"event_id": eid, "market": key, "reason": "EXCLUSION_NOT_IN_INVENTORY"})
                continue
            if exclusion.get("reason") not in REASONS:
                failures.append({"event_id": eid, "market": key, "reason": "EXCLUSION_REASON_INVALID"})
                continue
            try:
                if _utc(exclusion.get("noted_at_utc")) >= start:
                    raise CompletenessError("EXCLUSION_NOTED_AFTER_START")
            except CompletenessError as exc:
                failures.append({"event_id": eid, "market": key, "reason": str(exc)})
                continue
            fulfilled.add(key)
        for key in sorted(original_disposition_counts):
            if original_disposition_counts[key] > 1:
                failures.append({
                    "event_id": eid, "market": key,
                    "reason": "DUPLICATE_OR_CONFLICTING_SOURCE_DISPOSITION",
                    "original_disposition_rows": original_disposition_counts[key],
                })
                # Do not count any of the conflicting copies as accounting for
                # this market, even if one valid row was processed first.
                fulfilled.discard(key)
        for key in sorted(keys - fulfilled):
            failures.append({"event_id": eid, "market": key, "reason": "OFFERED_MARKET_UNACCOUNTED_FOR"})
        for family in sorted(CORE):
            expected = ("HOME", "AWAY") if family in ("ML", "SPREAD") else ("OVER", "UNDER")
            for side in expected:
                present = any(k[0] == "DK" and k[2] == family and k[3] == "FG" and k[4] == side for k in keys)
                if present and ("DK", family, "FG", side) in seen_core_absences:
                    failures.append({"event_id": eid, "market": ("DK", family, "FG", side),
                                     "reason": "CORE_SLOT_PRESENT_AND_ABSENT_CONFLICT"})
                if not present and ("DK", family, "FG", side) not in seen_core_absences:
                    failures.append({"event_id": eid, "market": ("DK", family, "FG", side),
                                     "reason": "CORE_SIDE_MISSING_WITHOUT_EXCLUSION"})
        checks.append({"event_id": eid, "sport": sport, "inventory_count": len(keys),
                       "accounted_count": len(keys & fulfilled), "quote_row_count": len(quotes),
                       "exclusion_count": len(exclusions),
                       "core_absence_count": len(seen_core_absences)})
    absent_any_core = any(c["core_absence_count"] for c in checks)
    status = ("PAPER_0U_INCOMPLETE" if failures else
              "PAPER_0U_DECLARED_CORE_GAPS" if absent_any_core else
              "PAPER_0U_COMPLIANT_INVENTORY")
    return {"schema": "sportsedge-odds-completeness-result-v1",
            "status": status,
            "checks": checks, "failures": failures, "gate_a_authenticated": False,
            "official_counted": 0, "approved_stake_u": 0,
            "note": "Local completeness does not verify upstream book permission, offer truth, timestamps or independent source paths."}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    path, out = _private_path(a.archive), _private_path(a.report)
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise CompletenessError("PRIVATE_MODE_0600_ARCHIVE_REQUIRED")
    if not out.parent.is_dir() or stat.S_IMODE(out.parent.stat().st_mode) & 0o077:
        raise CompletenessError("PRIVATE_MODE_0700_REPORT_DIRECTORY_REQUIRED")
    raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs,
                     parse_constant=_bad_constant)
    result = evaluate(raw)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(out, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(result, file, indent=2, sort_keys=True, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    print(result["status"] + " failures=" + str(len(result["failures"])))
    raise SystemExit(0 if not result["failures"] else 2)


if __name__ == "__main__":
    main()
