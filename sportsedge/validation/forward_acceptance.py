"""Read-only structural progress audit for SportsEdge Issue #10 hard Gates A-E.

Self-reported manifests, dates, hashes and signed strings do NOT prove bookmaker
authenticity, real-slate completeness, independent review or positive EV.
ALWAYS returns PAPER/0u. This code does not make wagers or issue promotions.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import argparse
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def require_private_path(candidate, *, label):
    """Refuse source and report paths in this public checkout.

    Resolved paths also reject symlinks into the public source tree. This is
    a privacy boundary, not independent evidence authentication.
    """
    # Check both spellings: a public checkout symlink that *points out* to a
    # private file remains dangerous because the lexical public path may be
    # committed/exposed; a private symlink that points *in* is likewise refused.
    lexical = Path(os.path.abspath(candidate))
    resolved = lexical.resolve()
    if (lexical == REPOSITORY_ROOT or REPOSITORY_ROOT in lexical.parents
            or resolved == REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents):
        raise ValueError("PRIVATE_" + label + "_INSIDE_PUBLIC_REPOSITORY")
    return resolved

SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
CARD_FIELDS = {"card_id", "generated_utc", "price_rows", "missing_price_rows",
               "stale_quote_rows", "unauthenticated_quote_rows", "guard_bypasses",
               "pit_total", "pit_complete"}
CLOSE_FIELDS = {"bet_id", "event_start_utc", "open_observed_utc", "taken_observed_utc",
                "close_observed_utc", "settled_at_utc", "settlement",
                "market_identity_matched", "upstream_book_matched"}
CYCLE_FIELDS = {"cycle_id", "registered_utc", "window_start_utc", "window_end_utc",
                "leakage_findings", "report_sha256"}
ROOT_FIELDS = {"schema", "cards", "clv_triples", "calibration_cycles"}

def _keys(obj, allowed, label):
    if not isinstance(obj, dict) or set(obj) != allowed:
        raise ValueError("INVALID_FIELDS:" + label)
    return obj

def _stamp(raw, label):
    if not isinstance(raw, str):
        raise ValueError("INVALID_TIMESTAMP:" + label)
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP:" + label) from exc
    if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
        raise ValueError("UTC_TIMESTAMP_REQUIRED:" + label)
    return ts.astimezone(timezone.utc)

def _count(raw, label):
    if type(raw) is not int or raw < 0:
        raise ValueError("INVALID_COUNT:" + label)
    return raw

def _unique(items, field, label):
    values = [item[field] for item in items]
    if any(type(x) is not str or not x.strip() for x in values) or len(set(values)) != len(values):
        raise ValueError("EMPTY_OR_DUPLICATE_ID:" + label)

def _recent_clean_day_streak(cards):
    """Consecutive CLEAN reported CT dates ending on the latest reported date.

    Every run on a day must pass both price and guard checks. A failed run on
    the same date is not hidden by a second successful run that day. A clean
    five-day stretch in the distant past cannot cover a broken latest day.
    This is still just a self-reported calendar count, NOT verified slate uptime.
    """
    by_day = {}
    for when, _, price_clean, guard_clean in cards:
        day = when.astimezone(CT).date().toordinal()
        by_day[day] = by_day.get(day, True) and price_clean and guard_clean
    current = 0
    previous = None
    for day in sorted(by_day, reverse=True):
        if not by_day[day]:
            break
        if previous is not None and previous - day != 1:
            break
        current += 1
        previous = day
    return current

def _check_cards(data):
    cards = []
    for r in data:
        _keys(r, CARD_FIELDS, "card")
        r = dict(r)
        when = _stamp(r["generated_utc"], "card.generated_utc")
        for k in CARD_FIELDS - {"card_id", "generated_utc"}:
            _count(r[k], "card." + k)
        if not (r["price_rows"] > 0 and r["pit_complete"] <= r["pit_total"]
                and all(r[k] <= r["price_rows"] for k in
                        ("missing_price_rows", "stale_quote_rows", "unauthenticated_quote_rows"))):
            raise ValueError("INCONSISTENT_CARD_COUNTS")
        clean = not any(r[k] for k in ("missing_price_rows", "stale_quote_rows",
                                      "unauthenticated_quote_rows"))
        guard_clean = r["guard_bypasses"] == 0
        cards.append((when, r, clean, guard_clean))
    _unique([v[1] for v in cards], "card_id", "cards")
    cards.sort(key=lambda v: (v[0], v[1]["card_id"]))
    return cards

def _check_closes(data):
    structural = 0
    reasons = Counter()
    for row in data:
        _keys(row, CLOSE_FIELDS, "clv")
        _stamp(row["event_start_utc"], "clv.event_start")
        open_t = _stamp(row["open_observed_utc"], "clv.open")
        taken_t = _stamp(row["taken_observed_utc"], "clv.taken")
        close_t = _stamp(row["close_observed_utc"], "clv.close")
        settled_t = _stamp(row["settled_at_utc"], "clv.settled")
        event_t = _stamp(row["event_start_utc"], "clv.event_start")
        if type(row["market_identity_matched"]) is not bool or type(row["upstream_book_matched"]) is not bool:
            raise ValueError("INVALID_CLV_MATCH_FLAG")
        if row["settlement"] not in ("WIN", "LOSS", "PUSH"):
            reasons["UNSETTLED_OR_INVALID_RESULT"] += 1
        elif not (open_t <= taken_t < close_t < event_t < settled_t):
            reasons["CLOSE_CHRONOLOGY_NOT_VALID"] += 1
        elif not row["market_identity_matched"] or not row["upstream_book_matched"]:
            reasons["CLV_MARKET_OR_BOOK_UNMATCHED"] += 1
        else:
            structural += 1
    _unique(data, "bet_id", "clv_triples")
    return structural, dict(sorted(reasons.items()))

def _check_cycles(data):
    parsed = []
    for row in data:
        _keys(row, CYCLE_FIELDS, "cycle")
        registered = _stamp(row["registered_utc"], "cycle.registered")
        start = _stamp(row["window_start_utc"], "cycle.start")
        end = _stamp(row["window_end_utc"], "cycle.end")
        leak = _count(row["leakage_findings"], "cycle.leakage")
        if not isinstance(row["report_sha256"], str) or not SHA.fullmatch(row["report_sha256"]):
            raise ValueError("INVALID_CYCLE_REPORT_HASH")
        parsed.append((start, end, registered, leak, row))
    _unique(data, "cycle_id", "calibration_cycles")
    parsed.sort(key=lambda x: x[0])
    # Non-overlapping evaluation windows are necessary for independent folds.
    for i in range(1, len(parsed)):
        if parsed[i][0] < parsed[i-1][1]:
            raise ValueError("OVERLAPPING_CALIBRATION_EVALUATIONS")
    clean = [p for p in parsed if p[2] < p[0] < p[1] and p[3] == 0]
    # Issue #10 explicitly requires the LAST THREE registered cycles clean.
    # Counting any three clean cycles from old history would hide a new
    # leakage finding or an unregistered latest test.
    latest_clean_streak = 0
    for p in reversed(parsed):
        if p[2] < p[0] < p[1] and p[3] == 0:
            latest_clean_streak += 1
        else:
            break
    return len(clean), len(parsed), latest_clean_streak

def analyze(manifest):
    _keys(manifest, ROOT_FIELDS, "root")
    if manifest["schema"] != "sportsedge-issue10-structural-v1":
        raise ValueError("UNSUPPORTED_ACCEPTANCE_SCHEMA")
    for name, cap in (("cards", 100000), ("clv_triples", 200000), ("calibration_cycles", 10000)):
        if not isinstance(manifest[name], list) or len(manifest[name]) > cap:
            raise ValueError("INVALID_OR_UNBOUNDED_EVIDENCE_LIST:" + name)
    cards = _check_cards(manifest["cards"])
    matched_closes, excluded_closes = _check_closes(manifest["clv_triples"])
    clean_cycles, cycles, latest_clean_cycles = _check_cycles(manifest["calibration_cycles"])
    latest = cards[-100:]
    consecutive_clean = 0
    for _, r, clean, _ in reversed(cards):
        if not clean:
            break
        consecutive_clean += 1
    consecutive_guards = 0
    for _, r, _, guard_clean in reversed(cards):
        if not guard_clean:
            break
        consecutive_guards += 1
    total_pit = sum(row["pit_total"] for _, row, _, _ in latest)
    complete_pit = sum(row["pit_complete"] for _, row, _, _ in latest)
    # A price-bearing card with zero declared PIT packages is not evidence
    # that its event/market inputs were actually checked. Without this guard,
    # one large complete card can make 99 empty-package cards look 100% PIT.
    zero_pit_cards = sum(row["pit_total"] == 0 for _, row, _, _ in latest)
    ratio = complete_pit / total_pit if total_pit else 0.0
    # Latest self-reported daily streak, accounting for EVERY run on each day.
    # It still does not verify completeness against a true real-slate schedule.
    date_streak = _recent_clean_day_streak(cards)
    gates = {
        "A_prices": {"threshold_cards": 100, "reported_clean_recent_streak": consecutive_clean,
                     "structural_threshold_met": consecutive_clean >= 100,
                     "reported_remaining_to_100": max(0, 100 - consecutive_clean)},
        "B_PIT": {"minimum_fraction": 0.95, "reported_total_packages_last_100": total_pit,
                  "reported_complete_packages_last_100": complete_pit,
                  "reported_zero_pit_cards_last_100": zero_pit_cards,
                  "reported_fraction": ratio,
                  "reported_incomplete_packages_last_100": total_pit - complete_pit,
                  "reported_packages_short_of_95pct": max(0, (95 * total_pit + 99) // 100 - complete_pit),
                  "structural_threshold_met": total_pit > 0 and ratio >= 0.95
                      and zero_pit_cards == 0},
        "C_calibration": {"minimum_cycles": 3, "reported_cycles": cycles,
                          "reported_clean_registered_cycles": clean_cycles,
                          "reported_latest_clean_cycle_streak": latest_clean_cycles,
                          "structural_threshold_met": latest_clean_cycles >= 3,
                          "reported_remaining_to_3": max(0, 3 - latest_clean_cycles)},
        "D_CLV": {"minimum_settled_comparable": 200,
                   "reported_structurally_comparable_closes": matched_closes,
                   "reported_exclusion_reasons": excluded_closes,
                   "structural_threshold_met": matched_closes >= 200,
                   "reported_remaining_to_200": max(0, 200 - matched_closes)},
        "E_guard": {"threshold_cards": 100, "reported_no_bypass_recent_streak": consecutive_guards,
                     "structural_threshold_met": consecutive_guards >= 100,
                     "reported_remaining_to_100": max(0, 100 - consecutive_guards)},
        "five_days": {"minimum_reported_consecutive_dates": 5,
                      "reported_calendar_date_streak": date_streak,
                      "structural_threshold_met": date_streak >= 5,
                      "reported_remaining_to_5": max(0, 5 - date_streak)},
    }
    # No provider attestation, trusted wall-clock source, signed independent
    # calibration reviews, slate-completeness proof or owner promotion signature
    # is authenticated by arbitrary JSON input.
    for x in gates.values():
        x["externally_certified"] = False
    return {"state": "PAPER_0U_EXTERNAL_EVIDENCE_NOT_AUTHENTICATED",
            "official_counted": 0, "approved_stake_u": 0,
            "counts_provenance": "SELF_REPORTED_PRIVATE_MANIFEST_ONLY",
            "independently_verified_gate_counts": None,
            "input_cards": len(cards), "input_clv_triples": len(manifest["clv_triples"]),
            "input_calibration_cycles": cycles, "gates": gates,
            "reported_all_structural_thresholds_met":
                all(v["structural_threshold_met"] for v in gates.values()),
            "release_certified": False,
            "missing_external_proof": [
                "AUTHENTIC_BOOKMAKER_OBSERVATION_AND_INDEPENDENT_SOURCE_CHAIN",
                "REAL_SLATE_SCHEDULE_AND_POINT_IN_TIME_FEATURE_PUBLICATION",
                "INDEPENDENT_SIGNED_CHRONOLOGICAL_CALIBRATION_REVIEW",
                "AUTHENTIC_SAME_MARKET_SETTLEMENT_AND_CLOSING_RECEIPTS",
                "INDEPENDENT_POLICY_REVIEW_AND_EXPLICIT_OWNER_PROMOTION",
            ]}

def _unique_json_pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("DUPLICATE_JSON_KEY:" + k)
        result[k] = v
    return result

def report_file(source, destination):
    src = require_private_path(source, label="ACCEPTANCE_INPUT")
    dst = require_private_path(destination, label="ACCEPTANCE_REPORT")
    if src == dst:
        raise ValueError("SOURCE_AND_REPORT_MUST_DIFFER")
    raw = src.read_bytes()
    if not raw or len(raw) > 20_000_000:
        raise ValueError("MANIFEST_EMPTY_OR_TOO_LARGE")
    manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_pairs,
                          parse_constant=lambda token: (_ for _ in ()).throw(
                              ValueError("NONFINITE_MANIFEST_JSON:" + token)))
    report = analyze(manifest)
    report["input_sha256"] = "sha256:" + sha256(raw).hexdigest()
    # Validate and fully serialize before exclusive file creation: a failed
    # JSON encoding cannot strand a partial but credible-looking audit file.
    payload = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dst, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        # O_EXCL means the destination was created by this invocation.
        # Do not leave an incomplete report that could be treated as evidence.
        dst.unlink(missing_ok=True)
        raise
    return report

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_json")
    parser.add_argument("--report", required=True, help="create-only sanitized JSON report")
    args = parser.parse_args(argv)
    report = report_file(args.manifest_json, args.report)
    print(json.dumps({"state": report["state"], "release_certified": False,
                      "approved_stake_u": 0, "input_cards": report["input_cards"]}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
