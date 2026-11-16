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
    return values


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
        if not isinstance(catalog, list) or not catalog:
            failures.append({"event_id": eid, "reason": "OFFERED_MARKET_INVENTORY_MISSING"})
            continue
        if not isinstance(quotes, list) or not isinstance(exclusions, list):
            failures.append({"event_id": eid, "reason": "QUOTE_OR_EXCLUSION_LIST_MISSING"})
            continue
        keys, fulfilled = set(), set()
        for item in catalog:
            key = _key(item)
            if key in keys:
                failures.append({"event_id": eid, "market": key, "reason": "DUPLICATE_INVENTORY_MARKET"})
            keys.add(key)
        for q in quotes:
            key = _key(q)
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
            if key not in keys:
                failures.append({"event_id": eid, "market": key, "reason": "EXCLUSION_NOT_IN_INVENTORY"})
                continue
            if exclusion.get("reason") not in REASONS:
                failures.append({"event_id": eid, "market": key, "reason": "EXCLUSION_REASON_INVALID"})
                continue
            try:
                _utc(exclusion.get("noted_at_utc"))
            except CompletenessError:
                failures.append({"event_id": eid, "market": key, "reason": "EXCLUSION_TIMESTAMP_INVALID"})
                continue
            fulfilled.add(key)
        for key in sorted(keys - fulfilled):
            failures.append({"event_id": eid, "market": key, "reason": "OFFERED_MARKET_UNACCOUNTED_FOR"})
        for family in sorted(CORE):
            expected = ("HOME", "AWAY") if family in ("ML", "SPREAD") else ("OVER", "UNDER")
            for side in expected:
                if not any(k[0] == "DK" and k[2] == family and k[3] == "FG" and k[4] == side for k in keys):
                    failures.append({"event_id": eid, "market": ("DK", family, "FG", side),
                                     "reason": "CORE_SIDE_MISSING_WITHOUT_EXCLUSION"})
        checks.append({"event_id": eid, "sport": sport, "inventory_count": len(keys),
                       "accounted_count": len(keys & fulfilled), "quote_row_count": len(quotes),
                       "exclusion_count": len(exclusions)})
    return {"schema": "sportsedge-odds-completeness-result-v1",
            "status": "PAPER_0U_COMPLIANT_INVENTORY" if not failures else "PAPER_0U_INCOMPLETE",
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
