#!/usr/bin/env python3
"""SportsEdge Stage 2: read-only integrity audit of exported CSV tab snapshots.

This tool cannot authenticate bookmaker receipts or turn historical offers into bets.
It never edits inputs, model weights, frozen files or existing reports.
Export individual tabs as UTF-8 CSV, place them in a private local folder, then run:
    python sportsedge_stage2_readonly_audit.py --folder /private/exported_tabs
Optional: --output /private/new_stage2_report.json (create-only; fails if it exists)

No external packages needed. All user-specific data stays in your local runtime.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

TABS = (
    "ACTUAL_LEDGER", "MODEL_OUTPUTS", "GAMES", "PITCHERS", "LINEUPS",
    "ODDS", "Odds_Flat", "ODDS_RAW", "SHADOW_LEDGER", "CANDIDATE_AUDIT",
    "PICKS_DERIVED",
)
ERROR_TOKENS = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#ERROR!"}


def clean(value: object) -> str:
    return str(value if value is not None else "").strip()


def strict_csv(path: Path) -> dict:
    """Preserve raw bytes and embedded newlines; refuse ambiguous CSV structure."""
    raw = path.read_bytes()
    meta = {"name": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    try:
        text = raw.decode("utf-8-sig", errors="strict")
        import io
        with io.StringIO(text, newline="") as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, [])
            if not header:
                raise ValueError("NO_HEADER")
            normalized = [x.strip().casefold() for x in header]
            if any(not v for v in normalized):
                raise ValueError("BLANK_HEADER")
            if len(set(normalized)) != len(normalized):
                raise ValueError("DUPLICATE_NORMALIZED_HEADER")
            rows = []
            for record in reader:
                # No silent drop of empty, short or excess records.
                if not any(v.strip() for v in record):
                    raise ValueError("BLANK_LOGICAL_RECORD")
                if len(record) != len(header):
                    raise ValueError(f"RAGGED_RECORD:logical_row={len(rows)+2}:width={len(record)}:expected={len(header)}")
                rows.append(dict(zip(header, record)))
        return {**meta, "status": "PARSED", "headers": header, "row_count": len(rows), "rows": rows}
    except (UnicodeDecodeError, ValueError, csv.Error) as exc:
        return {**meta, "status": "AMBIGUOUS_CSV", "reason": str(exc)}


def _decimal(value: str) -> Decimal | None:
    try:
        number = Decimal(clean(value))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def audit_ledger(rows: list[dict]) -> dict:
    ctr = Counter()
    fields = ("BetID", "Placed CDT", "Sport", "Event", "Market", "Selection", "Book", "Bet Price",
              "Stake", "Close Price", "CLV", "Result", "Profit", "Model Prob", "Fair Price", "Edge")
    missing = {key: sum(not clean(r.get(key)) for r in rows) for key in fields}
    bet_ids = Counter(clean(r.get("BetID")) for r in rows if clean(r.get("BetID")))
    stake = Decimal("0")
    profit = Decimal("0")
    arithmetic_issues = []
    nonstandard_prices = 0
    invalid_money = 0
    for i, r in enumerate(rows, 2):
        outcome = clean(r.get("Result")).upper()
        ctr[outcome] += 1
        s, p = _decimal(r.get("Stake", "")), _decimal(r.get("Profit", ""))
        if s is None or s <= 0 or p is None:
            invalid_money += 1
            arithmetic_issues.append({"row": i, "code": "INVALID_STAKE_OR_PROFIT"})
            continue
        stake += s
        profit += p
        price = clean(r.get("Bet Price"))
        if not (len(price) >= 4 and price[0] in "+-" and price[1:].isdigit()):
            nonstandard_prices += 1
        expected = None
        if outcome in ("L", "LOSS"):
            expected = -s
        elif outcome in ("P", "PUSH"):
            expected = Decimal("0")
        elif outcome in ("W", "WIN") and price[0] in "+-" and price[1:].isdigit():
            odds = int(price)
            if abs(odds) >= 100:
                expected = (s * Decimal(odds) / Decimal(100) if odds > 0
                            else s * Decimal(100) / Decimal(-odds))
        if expected is not None and abs(expected - p) > Decimal("0.011"):
            arithmetic_issues.append({"row": i, "code": "PAYOUT_INCONSISTENT"})
    return {
        "wager_rows": len(rows), "result_counts": dict(ctr),
        "unique_bet_ids": len(bet_ids), "duplicate_bet_id_groups": sum(v > 1 for v in bet_ids.values()),
        "missing_fields": missing,
        "recorded_stakes": str(stake.quantize(Decimal("0.01"))),
        "recorded_profit": str(profit.quantize(Decimal("0.01"))),
        "recorded_roi_percent": float((profit / stake * 100).quantize(Decimal("0.01"))) if stake else None,
        "noncanonical_american_odds": nonstandard_prices,
        "invalid_monetary_rows": invalid_money,
        "arithmetic_issues": arithmetic_issues,
        "limitations": "Descriptive wager ledger only. No independent bookmaker authentication, prospective model proof or CLV can be inferred.",
    }


def audit_models(rows: list[dict]) -> dict:
    statuses = Counter(clean(r.get("Grade")) for r in rows)
    prices = sum(bool(clean(r.get("DK_Odds"))) for r in rows)
    prob = sum(bool(clean(r.get("Model_P"))) for r in rows)
    active = sum(bool(clean(r.get("GameID"))) and bool(clean(r.get("Market"))) and bool(clean(r.get("Model_P"))) for r in rows)
    return {"rows": len(rows), "grade_counts": dict(statuses), "model_p_nonempty": prob,
            "book_price_nonempty": prices, "complete_price_and_probability": active,
            "zero_stake_rows": sum(clean(r.get("Stake_u")) in ("0", "0.0") for r in rows),
            "error_tokens": Counter(v for r in rows for v in r.values() if clean(v) in ERROR_TOKENS)}


def audit_other(tab: str, rows: list[dict]) -> dict:
    report = {"rows": len(rows)}
    if tab == "GAMES":
        report["valid_id_and_team_rows"] = sum(
            clean(r.get("GameID")) not in ("", *ERROR_TOKENS)
            and bool(clean(r.get("AwayTeam"))) and bool(clean(r.get("HomeTeam"))) for r in rows
        )
    elif tab == "PITCHERS":
        metrics = ("KRate", "BBRate", "HR9", "SwStr", "CSW", "xFIP", "PitchCountProjection")
        report["metrics_coverage"] = {k: sum(bool(clean(r.get(k))) for r in rows) for k in metrics}
        report["input_statuses"] = dict(Counter(clean(r.get("InputStatus")) for r in rows))
    elif tab == "LINEUPS":
        report["bound_player_rows"] = sum(bool(clean(r.get("PlayerID"))) for r in rows)
        report["batting_order_rows"] = sum(bool(clean(r.get("BatOrder"))) for r in rows)
        report["statuses"] = dict(Counter(clean(r.get("LineupStatus")) for r in rows))
    elif tab == "PICKS_DERIVED":
        report["unique_games"] = len({clean(r.get("game")) for r in rows})
        report["games"] = dict(Counter(clean(r.get("game")) for r in rows))
        report["same_game_pick_duplicates"] = sum(n > 1 for n in Counter((clean(r.get("game")), clean(r.get("pick"))) for r in rows).values())
        report["classification"] = "DERIVED_TWO_SIDED_PRICE_ROWS_NOT_INDEPENDENT_BETS"
    return report


def audit_folder(folder: Path) -> dict:
    found = {}
    for tab in TABS:
        path = folder / (tab + ".csv")
        if not path.is_file():
            found[tab] = {"status": "NOT_SUPPLIED"}
            continue
        result = strict_csv(path)
        if result["status"] != "PARSED":
            found[tab] = result
            continue
        rows = result.pop("rows")
        if tab == "ACTUAL_LEDGER":
            stats = audit_ledger(rows)
        elif tab == "MODEL_OUTPUTS":
            stats = audit_models(rows)
        else:
            stats = audit_other(tab, rows)
        found[tab] = {**result, "audit": stats}
    return {"mode": "READ_ONLY_NO_PROMOTION", "sources": found,
            "note": "A CSV export is not provider-authenticated point-in-time evidence. Empty or missing sources are reported, never imputed."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="new JSON path; never overwrite")
    args = parser.parse_args()
    result = audit_folder(args.folder)
    payload = json.dumps(result, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    else:
        print(payload, end="")

if __name__ == "__main__":
    main()