"""Seven-sport offline authorized-export capture audit (research / 0u).

Accepts only files already lawfully acquired and stored in private directories.
Never calls DK, BestBook, DataGolf or any network/API endpoint. A source hash,
source label, claimed permission or converted JSON cannot authenticate a book.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path

from sportsedge.validation.seven_sport_pit_freeze import (
    SPORTS, FAMILIES, _artifact, _private_path, _raw_file, _utc, _unique_json,
)

REQUEST_FIELDS = frozenset({
    "schema", "sport", "provider", "upstream_book",
    "upstream_provider", "collection_path_id", "source_mapping_version",
    "permission_reference_claim", "source_observed_utc",
    "source_captured_utc", "original_provider_file",
    "converted_quote_file", "events",
})
EVENT_FIELDS = frozenset({"event_id", "start_utc", "market_inventory"})
INVENTORY_FIELDS = frozenset({"market_family", "status"})
QUOTE_FIELDS = frozenset({
    "event_id", "market_family", "period", "selection",
    "selection_id", "participant_id", "stat", "line",
    "price_american", "provider_quote_id", "provider_market_id",
    "observed_utc",
})
STATES = frozenset({"CAPTURED", "NOT_CAPTURED", "OFFER_UNKNOWN", "UNSUPPORTED"})


def _parse(raw, schema):
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json,
                     parse_constant=lambda v: (_ for _ in ()).throw(
                         ValueError("NONFINITE_JSON:" + v)))
    if not isinstance(obj, dict) or obj.get("schema") != schema:
        raise ValueError("INVALID_EXPORT_SCHEMA:" + schema)
    return obj


def _text(v, label):
    if not isinstance(v, str) or not v.strip() or v != v.strip() or len(v) > 200:
        raise ValueError("INVALID_IDENTIFIER:" + label)
    return v


def _price(v):
    if isinstance(v, bool):
        raise ValueError("INVALID_AMERICAN_ODDS")
    try:
        n = Decimal(str(v).replace("−", "-").replace("＋", "+"))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_AMERICAN_ODDS") from None
    if not n.is_finite() or n != n.to_integral_value() or abs(n) < 100 or abs(n) > 100000:
        raise ValueError("INVALID_AMERICAN_ODDS")
    return int(n)


def _line(v):
    if not isinstance(v, str) or len(v) > 32:
        raise ValueError("INVALID_LINE")
    if v == "":
        return ""
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ValueError("INVALID_LINE") from None
    if not d.is_finite():
        raise ValueError("INVALID_LINE")
    return str(d.normalize())


def audit(request, converted, *, actual_now=None):
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        raise ValueError("INVALID_CAPTURE_REQUEST_FIELDS")
    if request["schema"] != "sportsedge-seven-sport-offline-export-request-v1":
        raise ValueError("INVALID_CAPTURE_SCHEMA")
    if request["sport"] not in SPORTS:
        raise ValueError("UNKNOWN_SPORT")
    for f in ("provider", "upstream_book", "upstream_provider",
              "collection_path_id", "source_mapping_version",
              "permission_reference_claim"):
        _text(request[f], f)
    if request["source_mapping_version"] == "UNVERSIONED":
        raise ValueError("VERSIONED_SOURCE_MAPPING_REQUIRED")
    observed = _utc(request["source_observed_utc"], "source_observed")
    captured = _utc(request["source_captured_utc"], "source_captured")
    now = datetime.now(timezone.utc) if actual_now is None else actual_now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("ACTUAL_NOW_MUST_BE_UTC")
    if not observed <= captured <= now:
        raise ValueError("SOURCE_CAPTURE_CHRONOLOGY")
    original = _artifact(request["original_provider_file"], "provider_raw")
    normalized = _artifact(request["converted_quote_file"], "converted_quotes")
    if not isinstance(converted, dict) or set(converted) != {"schema", "quotes"}:
        raise ValueError("INVALID_CONVERTED_EXPORT_FIELDS")
    if converted["schema"] != "sportsedge-seven-sport-converted-quotes-v1":
        raise ValueError("INVALID_CONVERTED_EXPORT_SCHEMA")
    if not isinstance(converted["quotes"], list) or len(converted["quotes"]) > 100000:
        raise ValueError("INVALID_QUOTE_POPULATION")
    events = request["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= 1000:
        raise ValueError("NONEMPTY_EVENT_CENSUS_REQUIRED")
    known = {}
    statuses = {}
    for entry in events:
        if not isinstance(entry, dict) or set(entry) != EVENT_FIELDS:
            raise ValueError("INVALID_EVENT_ENTRY")
        eid = _text(entry["event_id"], "event_id")
        if eid in known:
            raise ValueError("DUPLICATE_EVENT_ID")
        start = _utc(entry["start_utc"], "event_start")
        if not captured < start:
            raise ValueError("SOURCE_CAPTURE_NOT_PREGAME")
        inventory = entry["market_inventory"]
        if not isinstance(inventory, list) or len(inventory) != len(FAMILIES):
            raise ValueError("INCOMPLETE_MARKET_FAMILY_CENSUS")
        by_family = {}
        for item in inventory:
            if not isinstance(item, dict) or set(item) != INVENTORY_FIELDS:
                raise ValueError("INVALID_INVENTORY_ENTRY")
            family = item["market_family"]
            if family not in FAMILIES or family in by_family or item["status"] not in STATES:
                raise ValueError("INVALID_OR_DUPLICATE_MARKET_FAMILY")
            by_family[family] = item["status"]
        if set(by_family) != FAMILIES:
            raise ValueError("INCOMPLETE_MARKET_FAMILY_CENSUS")
        known[eid] = start
        statuses[eid] = by_family
    quote_counts = Counter()
    identifiers = set()
    original_quote_ids = set()
    for row in converted["quotes"]:
        if not isinstance(row, dict) or set(row) != QUOTE_FIELDS:
            raise ValueError("INVALID_CONVERTED_QUOTE_FIELDS")
        event = row["event_id"]
        if event not in known:
            raise ValueError("QUOTE_EVENT_NOT_IN_CENSUS")
        family = row["market_family"]
        if family not in FAMILIES or statuses[event][family] != "CAPTURED":
            raise ValueError("QUOTE_FAMILY_NOT_DECLARED_CAPTURED")
        period = _text(row["period"], "period")
        selection = _text(row["selection"], "selection")
        selection_id = _text(row["selection_id"], "selection_id")
        ident = (
            event, family, period, selection, selection_id,
            str(row["participant_id"]), str(row["stat"]), _line(row["line"]),
        )
        if ident in identifiers:
            raise ValueError("DUPLICATE_EXACT_MARKET_OUTCOME")
        identifiers.add(ident)
        quote_id = _text(row["provider_quote_id"], "provider_quote_id")
        market_id = _text(row["provider_market_id"], "provider_market_id")
        if (event, quote_id) in original_quote_ids:
            raise ValueError("REUSED_PROVIDER_QUOTE_ID")
        original_quote_ids.add((event, quote_id))
        if not isinstance(row["participant_id"], str) or not isinstance(row["stat"], str):
            raise ValueError("INVALID_PLAYER_STAT_ID")
        if family == "PLAYER_PROP" and (not row["participant_id"] or not row["stat"]):
            raise ValueError("PLAYER_PROP_ID_AND_STAT_REQUIRED")
        _price(row["price_american"])
        when = _utc(row["observed_utc"], "quote_observed")
        if when > captured or when >= known[event]:
            raise ValueError("FUTURE_OR_POST_START_QUOTE")
        quote_counts[(event, family)] += 1
    declared_captured = 0
    status_tally = Counter()
    for eid, inventory in statuses.items():
        for family, status in inventory.items():
            count = quote_counts[(eid, family)]
            if (status == "CAPTURED") != (count > 0):
                raise ValueError("INVENTORY_QUOTE_POPULATION_DISAGREES")
            declared_captured += status == "CAPTURED"
            status_tally[status] += 1
    return {
        "schema": "sportsedge-seven-sport-offline-export-report-v1",
        "state": "PAPER_0U_OFFLINE_EXPORT_UNAUTHENTICATED",
        "sport": request["sport"],
        "source_claim": {
            "provider": request["provider"],
            "upstream_book": request["upstream_book"],
            "upstream_provider": request["upstream_provider"],
            "collection_path_id": request["collection_path_id"],
            "source_mapping_version": request["source_mapping_version"],
        },
        "raw_provider_file": original,
        "converted_quote_file": normalized,
        "source_observed_utc_claimed": observed.isoformat(),
        "source_captured_utc_claimed": captured.isoformat(),
        "events_declared": len(known),
        "market_family_slots_declared": len(known)*len(FAMILIES),
        "families_with_claimed_quotes": declared_captured,
        "quote_rows_claimed": len(converted["quotes"]),
        "market_family_status_counts": dict(sorted(status_tally.items())),
        "provider_authenticity_verified": False,
        "provider_to_converted_row_mapping_verified": False,
        "independent_second_source_verified": False,
        "complete_real_slate_verified": False,
        "release_certified": False,
        "approved_stake_u": 0,
        "official_counted": 0,
    }


def report_file(request_file, destination, *, actual_now=None):
    src = _private_path(request_file, "capture_request")
    dst = _private_path(destination, "capture_report", output=True)
    if src == dst:
        raise ValueError("REQUEST_AND_REPORT_SAME_PATH")
    raw = _raw_file(src, "capture_request")
    request = _parse(raw, "sportsedge-seven-sport-offline-export-request-v1")
    quote_source = request.get("converted_quote_file")
    if not isinstance(quote_source, dict) or "path" not in quote_source:
        raise ValueError("NORMALIZED_EXPORT_FILE_MISSING")
    converted_raw = _raw_file(quote_source["path"], "converted_quotes")
    converted = _parse(converted_raw, "sportsedge-seven-sport-converted-quotes-v1")
    result = audit(request, converted, actual_now=actual_now)
    result["request_sha256"] = "sha256:" + sha256(raw).hexdigest()
    payload = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dst, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            dst.unlink()
        except OSError:
            pass
        raise
    return result


def main():
    p = argparse.ArgumentParser(description="Inspect permitted private original odds exports; never authenticates or bets")
    p.add_argument("request")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    report = report_file(args.request, args.out)
    print(json.dumps({"state": report["state"], "sport": report["sport"],
                      "events_declared": report["events_declared"],
                      "quote_rows_claimed": report["quote_rows_claimed"],
                      "official_counted": 0, "approved_stake_u": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
