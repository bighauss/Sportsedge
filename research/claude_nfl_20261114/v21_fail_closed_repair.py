#!/usr/bin/env python3
"""SportsEdge v2.1: read-only, fail-closed diagnostic repair for legacy R2 rows.

No wager sizing or actionability is authorized by this module. The v5 engine,
legacy R2 calculations, and historical decisions remain untouched.

Input: legacy v5/R2 rows (model_p, market_p, price, bet_type, game, pick, ...).
Output: each input row with SEPARATE v21_* diagnostic fields, never R2 fields.
Unverifiable inputs and missing evidence remain explicit flags; zero rows are
silently dropped. The report is an audit, not a card.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

MODEL_WEIGHT = Decimal("0.30")
MARKET_WEIGHT = Decimal("0.70")
GAP_REVIEW = Decimal("0.15")
EIGHT_DP = Decimal("0.00000001")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
ALLOWED_SPORTS = {"NFL", "CFB", "CBB", "NBA", "MLB", "NHL"}
OUTPUT_FIELDS = (
    "v21_source_row", "v21_status", "v21_reasons", "v21_linear_win_p",
    "v21_linear_push_p", "v21_binary_ev_illustrative", "v21_push_aware_ev",
    "v21_gap_pp", "v21_approved_stake_u",
)


def number(value: object, *, probability: bool = False) -> Decimal:
    """Strict numerical parser: reject blanks, NaN, infinity, and out-of-domain."""
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        raise ValueError("missing numeric input")
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError("malformed numeric input") from exc
    if not d.is_finite() or (probability and not (Decimal(0) < d < Decimal(1))):
        raise ValueError("nonfinite or out-of-range numeric input")
    return d


def odds_payout(value: object) -> Decimal:
    """Return NET profit per $1 risked for an integer American price."""
    raw = str(value or "").strip().replace("−", "-").replace("＋", "+")
    if not re.fullmatch(r"[+-]?[0-9]+", raw):
        raise ValueError("invalid American-odds notation")
    price = int(raw)
    if -100 < price < 100:
        raise ValueError("invalid American odds: absolute value below 100")
    return Decimal(price) / 100 if price > 0 else 100 / Decimal(-price)


def instant(raw: str) -> datetime:
    if not raw or not str(raw).strip():
        raise ValueError("missing time")
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if value.utcoffset() is None:
        raise ValueError("naive time")
    return value.astimezone(timezone.utc)


def market_family(bet_type: str) -> str:
    return str(bet_type).strip().split("|", 1)[0].upper()


def canonical_key(row: Mapping[str, str]) -> tuple[str, ...]:
    """Avoid conflating markets/lines while detecting duplicate selection labels.

    A missing event ID is separately flagged: a game label alone can be repeated
    on different dates and is not a production-grade unique event identifier.
    """
    def value(key: str) -> str:
        return str(row.get(key) or "").strip().casefold()
    return (
        value("sport"), value("event_id") or value("game"),
        value("game_start_utc"), market_family(value("bet_type")),
        value("bet_type"), value("pick"), value("player_id") or value("player"),
    )


def fmt(value: Decimal) -> str:
    return str(value.quantize(EIGHT_DP))


def audit_one(row: Mapping[str, str], *, line: int, duplicate: bool) -> dict[str, str]:
    """Return an auditable row; every unavailable element fails closed."""
    original = dict(row)
    flags: set[str] = set()
    family = market_family(row.get("bet_type") or "")
    if duplicate:
        flags.add("DUPLICATE_SELECTION")
    if str(row.get("sport") or "").strip().upper() not in ALLOWED_SPORTS:
        flags.add("UNKNOWN_SPORT")
    if not family or not row.get("game") or not row.get("pick"):
        flags.add("MISSING_MARKET_EVENT_OR_SIDE")
    if not (row.get("event_id") or "").strip():
        flags.add("EVENT_ID_UNVERIFIED")
    if (row.get("player") or "").strip() and not (row.get("player_id") or "").strip():
        flags.add("PLAYER_ID_UNVERIFIED")
    if str(row.get("mode") or "").strip().upper() != "PROJECTION":
        flags.add("NO_INDEPENDENT_PROJECTION")
    if family.startswith(("1H_", "2H_", "1Q_", "2Q_", "3Q_", "4Q_")) and str(row.get("mode") or "").strip().upper() == "ANCHOR":
        flags.add("PERIOD_DERIVED_ANCHOR")
    if (row.get("book") or "").strip().upper() != "DK":
        flags.add("DK_BOOK_NOT_VERIFIED")
    # A well-formed file hash alone does not prove the sportsbook published a price.
    if not SHA256.fullmatch((row.get("quote_sha256") or "").strip()):
        flags.add("QUOTE_HASH_MISSING_OR_INVALID")
    if (row.get("source_authenticated") or "").strip().lower() != "true":
        flags.add("QUOTE_NOT_AUTHENTICATED")
    if (row.get("no_vig_source_verified") or "").strip().lower() != "true":
        flags.add("NO_VIG_SOURCE_UNVERIFIED")
    if (row.get("model_version_verified") or "").strip().lower() != "true":
        flags.add("MODEL_VERSION_UNVERIFIED")
    try:
        quoted = instant(row.get("captured_utc") or "")
        start = instant(row.get("game_start_utc") or "")
        modeled = instant(row.get("model_asof_utc") or "")
        if not (modeled <= quoted < start):
            flags.add("ASOF_OR_PREGAME_TIME_VIOLATION")
    except (ValueError, TypeError, OverflowError):
        flags.add("PREGAME_TIMESTAMPS_UNVERIFIED")

    win = push = binary_ev = actual_ev = gap = ""
    try:
        model = number(row.get("model_p"), probability=True)
    except ValueError:
        flags.add("MODEL_PROBABILITY_INVALID")
        model = None
    try:
        market = number(row.get("market_p"), probability=True)
    except ValueError:
        flags.add("MARKET_PROBABILITY_MISSING_OR_INVALID")
        market = None
    try:
        payout = odds_payout(row.get("price"))
    except ValueError:
        flags.add("AMERICAN_ODDS_INVALID")
        payout = None

    if model is not None and market is not None:
        blended = MODEL_WEIGHT * model + MARKET_WEIGHT * market
        win = fmt(blended)
        gap = fmt(abs(model - market) * 100)
        if abs(model - market) > GAP_REVIEW:
            flags.add("MODEL_MARKET_GAP_GT15PP")
        if payout is not None:
            # Only a binary what-if: never present as an actionable EV.
            binary_ev = fmt(blended * payout - (1 - blended))
            settlement = (row.get("settlement_kind") or "").strip().upper()
            if settlement == "BINARY_NO_PUSH":
                push = fmt(Decimal(0))
                actual_ev = binary_ev
            elif settlement == "WIN_LOSS_PUSH":
                try:
                    model_push = number(row.get("model_push_p"))
                    market_push = number(row.get("market_push_p"))
                    if not (0 <= model_push < 1 - model and 0 <= market_push < 1 - market):
                        raise ValueError("invalid push masses")
                    blended_push = MODEL_WEIGHT * model_push + MARKET_WEIGHT * market_push
                    push = fmt(blended_push)
                    actual_ev = fmt(blended * payout - (1 - blended - blended_push))
                except ValueError:
                    flags.add("PUSH_PROBABILITY_MISSING_OR_INVALID")
            else:
                flags.add("SETTLEMENT_UNVERIFIED")
    if not flags:
        # Never promote automatically: caller-provided booleans are NOT independent proof.
        flags.add("NO_INDEPENDENT_MARKET_PROMOTION")
    original.update({
        "v21_source_row": str(line),
        "v21_status": "PAPER_HOLD_0U",
        "v21_reasons": ";".join(sorted(flags)),
        "v21_linear_win_p": win,
        "v21_linear_push_p": push,
        "v21_binary_ev_illustrative": binary_ev,
        "v21_push_aware_ev": actual_ev,
        "v21_gap_pp": gap,
        "v21_approved_stake_u": "0",
    })
    return original


def repair_rows(rows: Sequence[Mapping[str, str]]) -> tuple[list[dict[str, str]], dict]:
    checked: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for line, row in enumerate(rows, start=2):
        key = canonical_key(row)
        checked.append(audit_one(row, line=line, duplicate=key in seen))
        seen.add(key)
    issues = Counter(flag for row in checked for flag in row["v21_reasons"].split(";") if flag)
    return checked, {
        "status": "RESEARCH_ONLY_PAPER_0U", "source_rows": len(rows),
        "output_rows": len(checked), "actionable_rows": 0,
        "rows_with_binary_illustration": sum(bool(row["v21_binary_ev_illustrative"]) for row in checked),
        "rows_with_complete_push_aware_ev": sum(bool(row["v21_push_aware_ev"]) for row in checked),
        "issues": dict(sorted(issues.items())),
        "warning": "No provider authentication, calibrated win probabilities, CLV, or wagering approval is implied.",
    }


def run(input_file: str, output_csv: str, output_report: str) -> dict:
    raw = Path(input_file).read_bytes()
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
    columns = reader.fieldnames
    if not columns:
        raise ValueError("no CSV header")
    if len(set(columns)) != len(columns):
        raise ValueError("duplicate CSV field names")
    if any(k in columns for k in OUTPUT_FIELDS):
        raise ValueError("input already has v21 output fields")
    rows = list(reader)
    checked, report = repair_rows(rows)
    report["source_sha256"] = hashlib.sha256(raw).hexdigest()
    out = Path(output_csv)
    rpt = Path(output_report)
    if out.resolve() == rpt.resolve() or out.resolve() == Path(input_file).resolve() or rpt.resolve() == Path(input_file).resolve():
        raise ValueError("outputs must differ from source and each other")
    if out.exists() or rpt.exists():
        raise FileExistsError("create-only reports: destination exists")
    # Open BOTH outputs with exclusive-create semantics before writing either.
    # If a later open/write fails, remove only the new outputs we created.
    created: list[Path] = []
    try:
        with ExitStack() as stack:
            f = stack.enter_context(out.open("x", newline="", encoding="utf-8"))
            created.append(out)
            g = stack.enter_context(rpt.open("x", encoding="utf-8"))
            created.append(rpt)
            writer = csv.DictWriter(f, fieldnames=columns + list(OUTPUT_FIELDS), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(checked)
            json.dump(report, g, indent=2, sort_keys=True)
            g.write("\n")
    except Exception:
        for created_path in created:
            created_path.unlink(missing_ok=True)
        raise
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_csv")
    parser.add_argument("--out", required=True, help="new, create-only annotated CSV")
    parser.add_argument("--report", required=True, help="new, create-only JSON census")
    args = parser.parse_args(argv)
    report = run(args.source_csv, args.out, args.report)
    print(json.dumps({k: report[k] for k in ("status", "source_rows", "output_rows", "actionable_rows")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
