"""Read-only source-hashed Nov9 CBB printed-card ↔ ORIGINAL board audit.

Never uses final scores to join, infer probability, choose source revisions,
rewrite historical grades, authenticate a sportsbook, or count official wagers.

Input board bytes MUST be the selected Drive original revision, not today's
overwritten board. Original saved file hashes and event timing are required.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
from pathlib import Path
import re


class AuditBlocked(ValueError):
    pass


HASH = re.compile(r"[a-f0-9]{64}\Z")
CARD_ROW = re.compile(r"^\|\s*(\d+)\s*\|")
PERCENT = re.compile(r"^[+-]?(\d+(?:\.\d+)?)%\Z")
PRICE = re.compile(r"^[+-]?\d{3,7}\Z")
CARD_COUNT = re.compile(r"^CARD \((\d+)\)")
DOUBTED_COUNT = re.compile(r"^MODEL-DOUBTED \((\d+)\)")
FIELDS = ("sport", "home", "away", "market", "line", "price_a", "price_b")


def as_utc(value):
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("naive")
        return moment.astimezone(timezone.utc)
    except (AttributeError, ValueError) as ex:
        raise AuditBlocked("TIMESTAMP_INVALID_OR_NAIVE") from ex


def checked_sha(raw, expected, kind):
    if not isinstance(expected, str) or not HASH.fullmatch(expected):
        raise AuditBlocked(kind + "_EXPECTED_SHA_REQUIRED")
    digest = sha256(raw).hexdigest()
    if digest != expected:
        raise AuditBlocked(kind + "_SOURCE_SHA_MISMATCH")
    return digest


def amer(raw):
    if not isinstance(raw, str) or not PRICE.fullmatch(raw.strip()):
        raise AuditBlocked("INVALID_PRICE")
    v = int(raw)
    if not 100 <= abs(v) <= 1000000:
        raise AuditBlocked("INVALID_PRICE")
    return v


def dec_odds(v):
    return Decimal(1) + (
        Decimal(v) / Decimal(100) if v > 0 else Decimal(100) / Decimal(-v)
    )


def raw_implied(v):
    return Decimal(1) / dec_odds(v)


def d(raw, name):
    try:
        v = Decimal(str(raw))
    except (TypeError, InvalidOperation) as ex:
        raise AuditBlocked("INVALID_" + name) from ex
    if not v.is_finite():
        raise AuditBlocked("INVALID_" + name)
    return v


def board_rows(raw):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("ascii"), newline=""))
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not set(FIELDS).issubset(fields):
            raise AuditBlocked("ORIGINAL_BOARD_HEADER_MISSING_OR_DUPLICATE")
        rows = []
        for row_number, row in enumerate(reader, 2):
            if (None in row or any(v is None for v in row.values()) or
                    row["sport"] != "CBB" or
                    not row["home"] or not row["away"] or
                    row["home"] == row["away"]):
                raise AuditBlocked("BAD_BOARD_ROW_" + str(row_number))
            own, opp = amer(row["price_a"]), amer(row["price_b"])
            if row["market"] not in {
                "ML", "SPREAD", "TOTAL", "HOME_TT", "AWAY_TT",
                "1H_ML", "1H_SPREAD", "1H_TOTAL", "1H_HOME_TT", "1H_AWAY_TT"
            }:
                raise AuditBlocked("UNSUPPORTED_BOARD_MARKET")
            if row["market"].endswith("ML"):
                if row["line"] not in ("", "0", "0.0"):
                    raise AuditBlocked("ML_HAS_LINE")
            else:
                d(row["line"], "BOARD_LINE")
            rows.append({**row, "source_board_csv_row": row_number,
                         "american_a": own, "american_b": opp})
        if not rows:
            raise AuditBlocked("EMPTY_BOARD")
        return rows
    except (UnicodeError, csv.Error) as ex:
        raise AuditBlocked("INVALID_ASCII_BOARD") from ex


def original_card_rows(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeError as ex:
        raise AuditBlocked("INVALID_CARD_ENCODING") from ex
    rows = []
    section = "CARD"
    expected = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if m := CARD_COUNT.match(line):
            expected["CARD"] = int(m[1])
        if m := DOUBTED_COUNT.match(line):
            section = "MODEL-DOUBTED"
            expected["MODEL-DOUBTED"] = int(m[1])
            continue
        if not CARD_ROW.match(line):
            continue
        cells = [v.strip() for v in line.strip().strip("|").split("|")]
        if len(cells) != 9:
            raise AuditBlocked("BAD_CARD_COLUMN_COUNT_LINE_" + str(line_number))
        rank = int(cells[0])
        if not cells[1].startswith("CBB "):
            raise AuditBlocked("NOT_CBB_CARD_SELECTION")
        price = amer(cells[2])
        p_match = PERCENT.fullmatch(cells[3])
        ev_match = PERCENT.fullmatch(cells[6])
        if not p_match or not ev_match:
            raise AuditBlocked("INVALID_DISPLAYED_PROBABILITY_OR_EV")
        p = d(p_match[1], "MODEL_PERCENT")
        ev = d(ev_match[1], "EV_PERCENT")
        if not Decimal(0) < p < Decimal(100):
            raise AuditBlocked("OUT_OF_RANGE_MODEL_PROBABILITY")
        rows.append({
            "section": section, "card_rank": rank,
            "card_line_number": line_number,
            "printed_selection": cells[1],
            "model_percent": p, "printed_ev_percent": ev,
            "american_price": price,
            "model_percent_digits": len(p_match[1].partition(".")[2]),
            "ev_percent_digits": len(ev_match[1].partition(".")[2]),
        })
    for sec in ("CARD", "MODEL-DOUBTED"):
        part = [r["card_rank"] for r in rows if r["section"] == sec]
        if sec not in expected or len(part) != expected[sec] or part != list(range(1, len(part) + 1)):
            raise AuditBlocked("BAD_OR_INCOMPLETE_" + sec.replace("-", "_") + "_RANKING")
    return rows


def selection_shape(text):
    core = text.removeprefix("CBB ")
    half = core.startswith("1H ")
    if half:
        core = core[3:]
    prefix = "1H_" if half else ""
    if m := re.fullmatch(r"(.+?) ML", core):
        return (prefix + "ML", m[1], None, None)
    if m := re.fullmatch(r"(Over|Under) (\d+(?:\.\d+)?)", core):
        return (prefix + "TOTAL", None, m[1], d(m[2], "LINE"))
    if m := re.fullmatch(r"(.+?) (Over|Under) (\d+(?:\.\d+)?)", core):
        return (prefix + "TT", m[1], m[2], d(m[3], "LINE"))
    if m := re.fullmatch(r"(.+?) ([+-]\d+(?:\.\d+)?)", core):
        return (prefix + "SPREAD", m[1], None, d(m[2], "LINE"))
    raise AuditBlocked("UNPARSED_CARD_MARKET:" + text)


def match(pick, board):
    market, team, side, line = selection_shape(pick["printed_selection"])
    half = market.startswith("1H_")
    matches = []
    for row in board:
        if team is not None and team not in (row["home"], row["away"]):
            continue
        if market in ("TT", "1H_TT"):
            underlying = ("1H_" if half else "") + (
                "HOME_TT" if team == row["home"] else "AWAY_TT"
            )
        else:
            underlying = market
        if row["market"] != underlying:
            continue
        if market.endswith("ML"):
            take_a = team == row["home"]
        else:
            if market.endswith("SPREAD"):
                required_line = line if team == row["home"] else -line
                take_a = team == row["home"]
            else:
                required_line = line
                take_a = side == "Over"
            if d(row["line"], "BOARD_LINE") != required_line:
                continue
        if row["american_a" if take_a else "american_b"] == pick["american_price"]:
            matches.append((row, take_a))
    if len(matches) != 1:
        raise AuditBlocked(
            "CARD_ORIGINAL_SOURCE_MATCH_NOT_UNIQUE:"
            + pick["section"] + ":" + str(pick["card_rank"])
            + ":matches=" + str(len(matches))
        )
    return matches[0]


def audit(original_board_bytes, printed_card_bytes, *,
          expected_board_sha, expected_card_sha,
          original_board_saved_utc, printed_card_saved_utc, earliest_game_start_utc,
          expected_board_rows=None):
    board_sha = checked_sha(original_board_bytes, expected_board_sha, "BOARD")
    card_sha = checked_sha(printed_card_bytes, expected_card_sha, "CARD")
    tb, tc, tip = (
        as_utc(original_board_saved_utc),
        as_utc(printed_card_saved_utc),
        as_utc(earliest_game_start_utc)
    )
    if not tb < tc < tip:
        raise AuditBlocked("SOURCE_FILE_TIMES_NOT_PRETIP_OR_ORDERED")
    board = board_rows(original_board_bytes)
    if expected_board_rows is not None and len(board) != expected_board_rows:
        raise AuditBlocked("ORIGINAL_BOARD_ROW_COUNT_MISMATCH")
    card = original_card_rows(printed_card_bytes)
    matched = []
    for pick in card:
        row, take_a = match(pick, board)
        own = row["american_a" if take_a else "american_b"]
        other = row["american_b" if take_a else "american_a"]
        implied_a = raw_implied(row["american_a"])
        implied_b = raw_implied(row["american_b"])
        overround = implied_a + implied_b - 1
        if overround < 0:
            raise AuditBlocked("NEGATIVE_BOOK_OVERROUND")
        implied = raw_implied(own)
        devig = implied / (implied_a + implied_b)
        p = pick["model_percent"] / 100
        ev = (p * dec_odds(own) - 1) * 100
        # Displayed one-decimal p and EV were rounded separately; no
        # false-positive arithmetic failure due to truncation of model p.
        p_half = Decimal("0.5").scaleb(-pick["model_percent_digits"])
        ev_half = Decimal("0.5").scaleb(-pick["ev_percent_digits"])
        tolerance = p_half * dec_odds(own) + ev_half
        discrepancy = abs(ev - pick["printed_ev_percent"])
        matched.append({
            "section": pick["section"], "card_rank": pick["card_rank"],
            "printed_selection": pick["printed_selection"],
            "game": row["away"] + " @ " + row["home"],
            "board_market": row["market"], "board_line": row["line"],
            "board_csv_row": row["source_board_csv_row"],
            "matched_side": "A" if take_a else "B",
            "price_american": own, "opposing_price_american": other,
            "model_probability": float(p),
            "single_book_implied_probability": round(float(implied), 9),
            "two_sided_no_vig_probability": round(float(devig), 9),
            "model_minus_no_vig_pp": round(float((p - devig) * 100), 6),
            "bookmaker_margin_pp": round(float(overround * 100), 6),
            "ev_from_display_probability_pct": round(float(ev), 6),
            "printed_ev_pct": float(pick["printed_ev_percent"]),
            "display_rounding_tolerance_pp": round(float(tolerance), 6),
            "ev_arithmetic_consistent_with_display_rounding": discrepancy <= tolerance,
            "original_gate": "MODEL_DOUBTED" if pick["section"] == "MODEL-DOUBTED" else "PAPER_CARD",
            "quote_receipt": "MISSING_ORIGINAL_PROVIDER_BYTES_AND_OBSERVED_UTC",
            "model_feature_vintage": "NOT_INDEPENDENTLY_ATTESTED",
            "approved_stake_units": 0,
        })
    return {
        "status": "PAPER_0U_READ_ONLY_NOT_AUTHENTICATED_OR_SETTLED",
        "board_sha256": board_sha, "card_sha256": card_sha,
        "board_rows": len(board), "card_rows": len(card),
        "model_doubted": sum(r["section"] == "MODEL-DOUBTED" for r in matched),
        "unique_source_matches": len(matched),
        "arithmetic_discrepancies": sum(
            not r["ev_arithmetic_consistent_with_display_rounding"] for r in matched
        ),
        "source_file_timing_only": {
            "original_board_saved_utc": original_board_saved_utc,
            "printed_card_saved_utc": printed_card_saved_utc,
            "earliest_game_start_utc": earliest_game_start_utc,
        },
        "source_limits": [
            "This joins archived FILE bytes, not original sportsbook provider quote receipts.",
            "One-sided model EV is not calibrated EV or official wager ROI.",
            "No model-feature publication vintage, player injury vintage or quote observation UTC verified.",
            "A printed 209-row card is not the original complete 496-row picks.csv.",
            "No historical result, score, censor or wager entry used in this source join."
        ],
        "matches": matched,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_board", type=Path)
    p.add_argument("printed_card", type=Path)
    p.add_argument("--board-sha256", required=True)
    p.add_argument("--card-sha256", required=True)
    p.add_argument("--board-saved-utc", required=True)
    p.add_argument("--card-saved-utc", required=True)
    p.add_argument("--earliest-game-start-utc", required=True)
    p.add_argument("--expected-board-rows", type=int)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    report = audit(
        args.original_board.read_bytes(), args.printed_card.read_bytes(),
        expected_board_sha=args.board_sha256, expected_card_sha=args.card_sha256,
        original_board_saved_utc=args.board_saved_utc,
        printed_card_saved_utc=args.card_saved_utc,
        earliest_game_start_utc=args.earliest_game_start_utc,
        expected_board_rows=args.expected_board_rows
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"PAPER_0U: {report['unique_source_matches']}/{report['card_rows']} "
          f"exact pretip FILE joins; no authenticated sportsbook quotes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
