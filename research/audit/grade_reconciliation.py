"""Read-only, fail-closed audit of already-selected paper or wager grade rows.

This program never reconstructs an original sportsbook quote, authenticates a
capture, changes an archived grade, or reports a validated betting edge.
Each CSV record is one original *selection decision*, NOT one priced side.
Required columns: bet_id, event_id, price_american, stake_u, outcome.
Outcome: W, L, P, or PENDING. Stake_u=0 is explicit research-only.
"""
import argparse
import csv
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path


def _decimal(value, label):
    try:
        d = Decimal(str(value).strip())
        if not d.is_finite():
            raise InvalidOperation
        return d
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("INVALID_" + label)


def profit_per_unit(american):
    value = _decimal(american, "ODDS")
    if value != int(value) or value == 0 or abs(value) < 100 or abs(value) > 100000:
        raise ValueError("INVALID_AMERICAN_ODDS")
    return value / Decimal(100) if value > 0 else Decimal(100) / -value


def reconcile(rows, claimed_net_u=None):
    """Recompute realized W/L/P accounting, rejecting every duplicate bet ID."""
    original = list(rows)
    ids = Counter(str(r.get("bet_id") or "").strip() for r in original)
    accepted, blocked, pending = [], [], []
    net = Decimal(0)
    risk = Decimal(0)
    counts = Counter()
    for ix, row in enumerate(original, 2):
        bet_id = str(row.get("bet_id") or "").strip()
        event_id = str(row.get("event_id") or "").strip()
        reasons = []
        if not bet_id or not event_id:
            reasons.append("MISSING_IDENTITY")
        if bet_id and ids[bet_id] > 1:
            reasons.append("DUPLICATE_BET_ID")
        outcome = str(row.get("outcome") or "").strip().upper()
        if outcome not in ("W", "L", "P", "PENDING"):
            reasons.append("INVALID_OUTCOME")
        try:
            unit_profit = profit_per_unit(row.get("price_american"))
        except ValueError as e:
            reasons.append(str(e))
            unit_profit = None
        try:
            stake = _decimal(row.get("stake_u"), "STAKE")
            if stake < 0:
                raise ValueError("NEGATIVE_STAKE")
        except ValueError as e:
            reasons.append(str(e))
            stake = None
        if reasons:
            blocked.append({"csv_row": ix, "bet_id": bet_id, "reasons": sorted(set(reasons))})
            continue
        if outcome == "PENDING":
            pending.append({"csv_row": ix, "bet_id": bet_id, "stake_u": str(stake)})
            continue
        gain = (stake * unit_profit if outcome == "W"
                else -stake if outcome == "L" else Decimal(0))
        net += gain
        risk += stake
        if stake:
            counts[outcome] += 1
        else:
            counts["PAPER_0U"] += 1
        accepted.append({"csv_row": ix, "bet_id": bet_id, "event_id": event_id,
                         "outcome": outcome, "stake_u": str(stake),
                         "realized_units": str(gain)})
    summary = {"accepted_settled_rows": len(accepted),
               "actual_staked_decisions": sum(counts[k] for k in ("W", "L", "P")),
               "wins": counts["W"], "losses": counts["L"], "pushes": counts["P"],
               "paper_0u_rows": counts["PAPER_0U"],
               "net_units": str(net), "risk_units": str(risk),
               "roi_on_risk": str(net / risk) if risk else None,
               "unique_events": len({r["event_id"] for r in accepted if Decimal(r["stake_u"]) > 0})}
    comparison = None
    if claimed_net_u is not None:
        declared = _decimal(claimed_net_u, "CLAIMED_NET")
        diff = net - declared
        comparison = {"claimed_net_units": str(declared),
                      "computed_minus_claimed_units": str(diff),
                      "matches_within_0_01u": abs(diff) <= Decimal("0.01")}
    return {"status": "READ_ONLY_ACCOUNTING_DIAGNOSTIC_NOT_SOURCE_AUTHENTICATION",
            "total_input_rows": len(original), "summary": summary,
            "reported_comparison": comparison, "settled": accepted,
            "blocked": blocked, "pending": pending}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_file", type=Path)
    p.add_argument("--claimed-net-u", default=None)
    args = p.parse_args(argv)
    with args.csv_file.open(newline="", encoding="utf-8-sig") as f:
        report = reconcile(csv.DictReader(f), args.claimed_net_u)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not report["blocked"] and not (report["reported_comparison"] and
                      not report["reported_comparison"]["matches_within_0_01u"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
