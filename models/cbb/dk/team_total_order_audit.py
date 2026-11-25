"""Audit held CBB team totals; never mutate or release a runner board.

Equal-price contracts are mathematically invariant to swapping the two prices.
Unequal prices require explicit labels. Neither fact proves provider identity,
settlement, capture authenticity, or point-in-time availability.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path


def price(value):
    try:
        p = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError("INVALID_PRICE")
    if not p.is_finite() or p != p.to_integral_value() or abs(p) < 100:
        raise ValueError("INVALID_PRICE")
    return int(p)


def audit(raw):
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    seen = set()
    out = []
    for r in rows:
        if r.get("market") not in ("TT_HOME", "TT_AWAY"):
            continue
        key = r.get("row_key")
        if not key or key in seen:
            raise ValueError("MISSING_OR_DUPLICATE_ROW_KEY")
        seen.add(key)
        codes = set(filter(None, (r.get("reason_codes") or "").split(";")))
        state = "OTHER_HOLD_OR_REJECTION"
        options = []
        try:
            a, b = price(r["price_a"]), price(r["price_b"])
            if r.get("disposition") == "HELD" and codes == {"TOTALS_ORDER_UNVERIFIED"} and not r.get("totals_order"):
                options = [{"over": a, "under": b}]
                if a != b:
                    options.append({"over": b, "under": a})
                state = "ORDER_INVARIANT_DIAGNOSTIC_ONLY" if a == b else "EXPLICIT_LABEL_EVIDENCE_REQUIRED"
            elif r.get("disposition") == "ACCEPTED" and not codes and r.get("totals_order") in ("over_under", "under_over"):
                state = "UPSTREAM_EXPLICIT_ORDER"
        except (KeyError, ValueError):
            state = "INVALID_PRICE"
        out.append({"row_key": key, "period": r.get("period"), "market": r.get("market"),
                    "dk_event_id": r.get("dk_event_id"), "line": r.get("line"),
                    "tip_utc": r.get("tip_utc"), "captured_utc": r.get("captured_utc"),
                    "provenance": r.get("provenance"), "original_disposition": r.get("disposition"),
                    "state": state, "hypothetical_price_assignments": options,
                    "admission_changed": False, "approved_stake_u": 0})
    counts = Counter((r["period"], r["state"]) for r in out)
    return {"source_sha256": hashlib.sha256(raw).hexdigest(), "rows": out,
            "counts": {f"{p}:{s}": n for (p, s), n in sorted(counts.items())},
            "total": len(out), "released": 0, "label": "PAPER_0U_NON_COUNTED",
            "limitations": "Order invariance is arithmetic only. No held rows are released. Unequal-price rows need original labeled selections; retrospective identity and all other evidence gates remain."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--board", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = audit(args.board.read_bytes())
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, sort_keys=True))


if __name__ == "__main__":
    main()
