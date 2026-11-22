"""Offline batch grading from private, archived picks and completed finals."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from sportsedge.markets.allmarkets_research import Market
from sportsedge.validation import paper_ledger as ledger


SCHEMA = "sportsedge-paper-grade-batch-v1"
MAX_PICKS = 500
BAD_INPUT = (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError, RecursionError)


def _pick(root, row, asof):
    if not isinstance(row, dict) or not {"kickoff_utc", "pick"}.issubset(row) or set(row) - {
        "kickoff_utc", "pick", "taken", "final"
    }:
        raise ledger.Blocked("INVALID_BATCH_ENTRY")
    kickoff = ledger.time_utc(row["kickoff_utc"])
    pick, pick_clock, pick_hash = ledger.source(root, row["pick"], kickoff, "pregame")
    decision = ledger.time_utc(pick["decision_at_utc"])
    if not decision <= pick_clock <= asof:
        raise ledger.Blocked("PICK_CLOCK_OUT_OF_ORDER")
    if ledger.time_utc(pick["kickoff_utc"]) != kickoff:
        raise ledger.Blocked("PICK_KICKOFF_MISMATCH")
    pid = pick["pick_id"]
    home, away = pick["home_id"], pick["away_id"]
    if (not isinstance(pid, str) or not pid.strip() or len(pid) > 128
            or any(not isinstance(x, str) or not x.strip() for x in (home, away)) or home == away):
        raise ledger.Blocked("PICK_ID_OR_TEAMS_INVALID")
    return Market(**pick["market"]), pick, kickoff, decision, pick_hash


def _price(root, row, market, kickoff, decision):
    if row.get("taken") is None:
        return "NO_SAVED_PRICE"
    try:
        quote, clock, _ = ledger.source(root, row["taken"], kickoff, "pregame")
        quoted_market, _ = ledger.novig_pair(quote)
        if clock > decision or quoted_market.identity() != market.identity():
            raise ledger.Blocked("PRICE_AFTER_DECISION_OR_MARKET_MISMATCH")
    except BAD_INPUT:
        return "PRICE_EVIDENCE_BLOCKED"
    return "EXACT_PRICE_EVIDENCE_UNAUTHENTICATED"


def _result(root, row, market, pick, kickoff, pick_hash, asof):
    if row.get("final") is None:
        return "PENDING_FINAL", None
    final, captured, final_hash = ledger.source(root, row["final"], kickoff, "postgame")
    if (captured > asof or final["event_id"] != market.event_id or final["sport"] != market.sport
            or (final["home_id"], final["away_id"]) != (pick["home_id"], pick["away_id"])):
        raise ledger.Blocked("FINAL_IDENTITY_OR_ASOF_MISMATCH")
    if final["final_status"] in ("SCHEDULED", "IN_PROGRESS", "POSTPONED", "SUSPENDED"):
        return "PENDING_FINAL", None
    available = ledger.time_utc(final["final_available_utc"])
    if not kickoff < available <= captured:
        raise ledger.Blocked("FINAL_AVAILABILITY_OUT_OF_ORDER")
    grade = ledger._settle_final(final, market)
    return "PAPER_RESULT_GRADED", {
        "pick_id": pick["pick_id"], "status": "PAPER_RESULT_ONLY_UNAUTHENTICATED",
        "selection_identity": list(market.identity()), "grade": grade,
        "pick_sha256": pick_hash, "final_sha256": final_hash,
        "official_counted": 0, "approved_stake_u": 0,
        "source_authentication_independent": False, "roi": "UNAVAILABLE_NO_AUTHORITATIVE_BET_LEDGER",
    }


def run_batch(manifest, *, database=None, now=None, rejected_final_indices=frozenset()):
    asof = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(asof, datetime) or asof.utcoffset() is None:
        raise ledger.Blocked("ASOF_REQUIRES_OFFSET")
    path = ledger.private_file(manifest, "GRADE_BATCH")
    if not 0 < path.stat().st_size <= ledger.MAX_EVIDENCE_BYTES:
        raise ledger.Blocked("GRADE_BATCH_SIZE_INVALID")
    doc = ledger.strict_json(path.read_bytes())
    if (not isinstance(doc, dict) or set(doc) != {"schema", "entries"} or doc["schema"] != SCHEMA
            or not isinstance(doc["entries"], list) or not 0 < len(doc["entries"]) <= MAX_PICKS):
        raise ledger.Blocked("INVALID_GRADE_BATCH_MANIFEST")
    rows, seen, duplicates = [], set(), set()
    picks, finals, prices, writes = Counter(), Counter(), Counter(), Counter()
    for index, row in enumerate(doc["entries"]):
        try:
            market, pick, kickoff, decision, pick_hash = _pick(path.parent, row, asof)
        except BAD_INPUT:
            picks["PICK_EVIDENCE_BLOCKED"] += 1
            continue
        keys = (("pick", pick["pick_id"]), ("market", market.identity()))
        duplicates.update(k for k in keys if k in seen)
        seen.update(keys)
        rows.append((index, row, market, pick, kickoff, decision, pick_hash, keys))
    for index, row, market, pick, kickoff, decision, pick_hash, keys in rows:
        if any(k in duplicates for k in keys):
            picks["DUPLICATE_PICK_OR_MARKET_BLOCKED"] += 1
            continue
        picks["PICK_ACCEPTED"] += 1
        prices[_price(path.parent, row, market, kickoff, decision)] += 1
        if index in rejected_final_indices:
            finals["FINAL_INPUT_BLOCKED"] += 1
            continue
        try:
            state, result = _result(path.parent, row, market, pick, kickoff, pick_hash, asof)
        except BAD_INPUT:
            finals["FINAL_OR_SETTLEMENT_BLOCKED"] += 1
            continue
        finals[state] += 1
        if result is not None:
            if database is None:
                writes["DRY_RUN"] += 1
            else:
                try:
                    writes[ledger.append_ledger(database, result)["status"]] += 1
                except (ledger.Blocked, sqlite3.Error, OSError):
                    writes["LEDGER_WRITE_BLOCKED"] += 1
    return {"picks": dict(picks), "results": dict(finals), "prices": dict(prices), "ledger": dict(writes),
            "official_counted": 0, "approved_stake_u": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database", type=Path, help="append to this private ledger; omit for dry run")
    args = parser.parse_args(argv)
    try:
        report = run_batch(args.manifest, database=args.database)
    except BAD_INPUT:
        print("GRADE_BATCH_BLOCKED")
        return 2
    print(json.dumps(report, sort_keys=True))
    if any("BLOCKED" in status for area in ("picks", "results", "prices", "ledger") for status in report[area]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
