"""Fail-closed CBB card-to-grade reconciliation (paper-only diagnostic).

Adapter for card-visible rows, not the private operative grader. It never edits
archived cards, authenticates a final, or promotes a wager. Team names are
matched whole; never strip arbitrary uppercase tokens such as VMI/NJIT/UNC.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from decimal import Decimal, InvalidOperation
import json
import re


class GradeIntegrityError(ValueError):
    pass


def game_key(text: str) -> str:
    """Remove only explicitly-known sport label, never uppercase team tokens."""
    if not isinstance(text, str) or not text.strip():
        raise GradeIntegrityError("MISSING_GAME")
    value = " ".join(text.split())
    value = re.sub(r"^CBB\s+", "", value, flags=re.IGNORECASE)
    if value.count("@") != 1:
        raise GradeIntegrityError("GAME_AWAY_AT_HOME_REQUIRED")
    away, home = (" ".join(x.split()).casefold() for x in value.split("@"))
    if not away or not home or away == home:
        raise GradeIntegrityError("INVALID_GAME_TEAMS")
    return away + " @ " + home


def _dec(value, label):
    try:
        d = Decimal(str(value).strip())
        if not d.is_finite():
            raise InvalidOperation
        return d
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise GradeIntegrityError("INVALID_" + label) from exc


def _payout(odds):
    price = _dec(odds, "PRICE")
    if price != int(price) or not (100 <= abs(price) <= 100000):
        raise GradeIntegrityError("INVALID_AMERICAN_PRICE")
    return price / 100 if price > 0 else 100 / -price


def match_card_games(card_games: list[str], verified_final_games: list[str]) -> dict:
    """Never silently drop team names; unmatched finals and pending explicit."""
    final_keys = [game_key(s) for s in verified_final_games]
    if len(set(final_keys)) != len(final_keys):
        raise GradeIntegrityError("DUPLICATE_VERIFIED_FINAL_GAME")
    keys = {game_key(s) for s in card_games}
    return {"matched": sorted(keys.intersection(final_keys)),
            "pending": sorted(keys.difference(final_keys)),
            "unmatched_finals": sorted(set(final_keys).difference(keys))}


def summarize_delivered(rows: list[dict], *, expected_rows: int | None = None) -> dict:
    """Derive all per-game splits from the delivered rows, not summary prose.

    Required fields: bet_id, game, price_american, result, role. role=CARD
    only; doubted rows stay separate. W/L/P/PENDING are exact. Units are
    hypothetical equal-stake paper units, not official or wagered funds.
    """
    if expected_rows is not None and len(rows) != expected_rows:
        raise GradeIntegrityError("DELIVERED_ROW_COUNT_MISMATCH")
    seen = set()
    grouped = defaultdict(lambda: {"wins": 0, "losses": 0, "pushes": 0,
                                   "pending": 0, "flat_1u_paper_net": Decimal(0),
                                   "gross_flat_1u_wins": Decimal(0),
                                   "plus_money_win_gross": Decimal(0),
                                   "plus_money_wins": 0})
    for row in rows:
        if row.get("role") != "CARD":
            raise GradeIntegrityError("NON_CARD_ROW_IN_DELIVERED_SET")
        bet_id = str(row.get("bet_id") or "").strip()
        if not bet_id or bet_id in seen:
            raise GradeIntegrityError("MISSING_OR_DUPLICATE_BET_ID")
        seen.add(bet_id)
        game = game_key(row.get("game"))
        result = str(row.get("result") or "").upper().strip()
        if result not in ("W", "L", "P", "PENDING"):
            raise GradeIntegrityError("UNKNOWN_OR_MISSING_RESULT")
        odds = _dec(row.get("price_american"), "PRICE")
        payoff = _payout(odds)
        group = grouped[game]
        if result == "PENDING":
            group["pending"] += 1
        elif result == "W":
            group["wins"] += 1
            group["flat_1u_paper_net"] += payoff
            group["gross_flat_1u_wins"] += payoff
            if odds > 0:
                group["plus_money_wins"] += 1
                group["plus_money_win_gross"] += payoff
        elif result == "L":
            group["losses"] += 1
            group["flat_1u_paper_net"] -= 1
        else:
            group["pushes"] += 1
    empty = {"wins": 0, "losses": 0, "pushes": 0, "pending": 0,
             "flat_1u_paper_net": Decimal(0), "gross_flat_1u_wins": Decimal(0),
             "plus_money_win_gross": Decimal(0), "plus_money_wins": 0}
    totals = {k: sum((g[k] for g in grouped.values()),
                 Decimal(0) if isinstance(v, Decimal) else 0)
              for k, v in empty.items()}
    if sum(totals[k] for k in ("wins", "losses", "pushes", "pending")) != len(rows):
        raise GradeIntegrityError("GRADE_ROW_CONSERVATION_FAILED")
    def clean(obj):
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in obj.items()}
    return {"status": "PAPER_0U_UNVALIDATED_RECONCILIATION",
            "delivered_rows": len(rows), "unique_games": len(grouped),
            "totals": clean(totals),
            "by_game": {game: clean(g) for game, g in sorted(grouped.items())},
            "official_counted": 0, "approved_stake_u": 0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("card_rows_csv")
    p.add_argument("--expected-rows", type=int, required=True)
    args = p.parse_args(argv)
    with open(args.card_rows_csv, newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    try:
        report = summarize_delivered(rows, expected_rows=args.expected_rows)
    except GradeIntegrityError as exc:
        p.exit(2, "GRADE_RECONCILIATION_BLOCKED:" + str(exc) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
