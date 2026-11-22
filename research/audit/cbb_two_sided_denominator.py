"""Read-only CBB two-sided market/candidate denominator reconciliation.

Use this ONLY on owner-private, already-normalized inputs. A paired quote row
can never imply a model output exists. Do not invent its missing prediction.
No network, wager, live-source authentication, model edits or ledger writes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

MARKETS = frozenset(("ML", "SPREAD", "TOTAL", "1H_ML", "1H_SPREAD", "1H_TOTAL"))
BOARD = frozenset(("sport", "home", "away", "home_proj", "away_proj",
                   "market", "line", "price_a", "price_b"))
PICKS = frozenset(("sport", "game", "mode", "pick", "price", "model_p",
                   "fair_odds", "market_p", "edge", "ev", "score",
                   "stars", "player", "bet_type"))
SIDE = re.compile(r"^(ML|SPREAD|TOTAL|1H_ML|1H_SPREAD|1H_TOTAL)\|([01])\|$")


def _money(v):
    if type(v) is not str or not re.fullmatch(r"[+-]?[0-9]{3,6}", v):
        raise ValueError("INVALID_PRICE")
    n = int(v)
    if not 100 <= abs(n) <= 100000:
        raise ValueError("INVALID_PRICE")
    return n


def _unit(v, label):
    if type(v) is not str or not v:
        raise ValueError("INVALID_PROBABILITY:" + label)
    try:
        x = Decimal(v)
    except InvalidOperation as exc:
        raise ValueError("INVALID_PROBABILITY:" + label) from exc
    if not x.is_finite() or not 0 <= x <= 1:
        raise ValueError("INVALID_PROBABILITY:" + label)
    return x


def _rows(path):
    raw = Path(path).read_bytes()
    if not 0 < len(raw) <= 5_000_000:
        raise ValueError("CSV_EMPTY_OR_TOO_LARGE")
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, strict=True)
        header = tuple(reader.fieldnames or ())
        rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError("RAGGED_OR_EXTRA_CSV_FIELDS")
    return set(header), rows


def reconcile(board_rows, prediction_rows):
    """One expected pair per submitted 2-sided quote: both sides or explicit HOLD.

    This is a read-only audit of provided rows; a 2-sided board row itself is
    not an authenticated original sportsbook offer.
    """
    if type(board_rows) is not list or type(prediction_rows) is not list:
        raise ValueError("ROW_LISTS_REQUIRED")
    if len(board_rows) > 100000 or len(prediction_rows) > 200000:
        raise ValueError("ROW_LIMIT_EXCEEDED")
    expected = {}
    for row in board_rows:
        if type(row) is not dict or set(row) != BOARD:
            raise ValueError("BOARD_ROW_SCHEMA_INVALID")
        if row["sport"] != "CBB" or row["market"] not in MARKETS:
            raise ValueError("BOARD_SPORT_OR_MARKET_INVALID")
        game = row["away"] + " @ " + row["home"]
        if (not row["home"] or not row["away"] or
                row["home"].strip() != row["home"] or
                row["away"].strip() != row["away"]):
            raise ValueError("BOARD_TEAM_IDENTITY_INVALID")
        if row["market"] in ("ML", "1H_ML") and row["line"] not in ("",):
            raise ValueError("ML_LINE_MUST_BE_EMPTY")
        key = (game, row["market"])
        if key in expected:
            raise ValueError("DUPLICATE_BOARD_MARKET")
        price_a, price_b = _money(row["price_a"]), _money(row["price_b"])
        expected[(game, row["market"], 0)] = price_a
        expected[(game, row["market"], 1)] = price_b
    if not expected:
        raise ValueError("EMPTY_TWO_SIDED_BOARD")

    observed, duplicates, orphan, wrong_price = {}, [], [], []
    for i, row in enumerate(prediction_rows, 1):
        if type(row) is not dict or set(row) != PICKS:
            raise ValueError("PREDICTION_ROW_SCHEMA_INVALID")
        if row["sport"] != "CBB" or row["mode"] != "PROJECTION":
            raise ValueError("PREDICTION_NOT_CBB_PROJECTION")
        parsed = SIDE.fullmatch(row["bet_type"])
        if parsed is None:
            raise ValueError("UNRECOGNIZED_MARKET_SIDE")
        key = (row["game"], parsed.group(1), int(parsed.group(2)))
        if key in observed:
            duplicates.append({"row": i, "game": key[0],
                               "market": key[1], "side_index": key[2]})
            continue
        _unit(row["model_p"], "model_p")
        observed[key] = (i, _money(row["price"]))
        if key not in expected:
            orphan.append({"row": i, "game": key[0],
                           "market": key[1], "side_index": key[2]})
        elif observed[key][1] != expected[key]:
            wrong_price.append({"row": i, "game": key[0], "market": key[1],
                                "side_index": key[2], "reason": "PRICE_CHANGED"})

    missing = [
        {"game": game, "market": market, "side_index": side,
         "status": "BLOCKED_NO_RECORDED_PROJECTION"}
        for (game, market, side) in expected
        if (game, market, side) not in observed
    ]
    counts = Counter(row["market"] for row in board_rows)
    present = sum(k in observed for k in expected)
    assert len(expected) == present + len(missing)
    return {
        "schema": "sportsedge-cbb-two-sided-audit-v1",
        "state": "PAPER_0U_PRIVATE_RECONCILIATION_ONLY",
        "board_markets": len(board_rows),
        "expected_outcomes": len(expected),
        "supplied_predictions": len(prediction_rows),
        "matched_outcomes": present,
        "missing_outcomes": len(missing),
        "duplicated_prediction_rows": len(duplicates),
        "orphan_prediction_rows": len(orphan),
        "price_mismatch_rows": len(wrong_price),
        "market_counts": dict(sorted(counts.items())),
        "complete_denominator": (
            not missing and not duplicates and not orphan and not wrong_price and
            present == len(prediction_rows) == len(expected)
        ),
        "missing_details_PRIVATE": missing,
        "duplicate_details_PRIVATE": duplicates,
        "orphan_details_PRIVATE": orphan,
        "price_mismatch_details_PRIVATE": wrong_price,
        "source_authenticated": False,
        "model_calibration_verified": False,
        "official_counted": 0, "approved_stake_u": 0,
        "note": "A missing prediction must remain explicitly blocked; no second-side probability, EV, or model row may be inferred from the opposing side.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_board")
    p.add_argument("private_picks")
    p.add_argument("--out", required=True, help="create-only, owner-private JSON destination")
    args = p.parse_args(argv)
    header, board = _rows(args.private_board)
    if header != BOARD:
        raise ValueError("BOARD_HEADER_MISMATCH")
    header, picks = _rows(args.private_picks)
    if header != PICKS:
        raise ValueError("PICKS_HEADER_MISMATCH")
    result = reconcile(board, picks)
    with Path(args.out).open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(json.dumps({k:result[k] for k in (
        "board_markets", "expected_outcomes", "matched_outcomes",
        "missing_outcomes", "complete_denominator", "official_counted",
        "approved_stake_u"
    )}, sort_keys=True))
    return 0 if result["complete_denominator"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
