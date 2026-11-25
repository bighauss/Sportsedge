"""Coverage census for CBB RUN IT (PAPER / 0u).

Every (period, market) family in contracts.MARKET_CATALOG must appear in the
inventory with either a priced row or an explicit reason code. Nothing is
silently omitted. Used by the shared runner and audit stage.

No probabilities, prices, or grades are invented here.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Iterable, Mapping

try:
    from . import contracts as C
except ImportError:  # running as script
    import contracts as C  # type: ignore


def census(priced: Iterable[Mapping], rejections: Iterable[Mapping]) -> dict:
    """Return { (period, market): {"status": ..., "reason_code": ..., "n": ...} }
    covering the full MARKET_CATALOG.
    """
    by = defaultdict(lambda: {"status": "NO_QUOTE", "reason_code": "NO_QUOTE", "n": 0,
                              "priced": 0, "rejected": 0})
    for r in priced:
        key = (r.get("period"), r.get("market"))
        if key[0] and key[1]:
            by[key]["priced"] += 1
            by[key]["n"] += 1
            by[key]["status"] = r.get("status") or "PRICED_PAPER"
            by[key]["reason_code"] = r.get("reason_code")
    for r in rejections:
        key = (r.get("period"), r.get("market"))
        if key[0] and key[1]:
            by[key]["rejected"] += 1
            by[key]["n"] += 1
            if by[key]["priced"] == 0:
                by[key]["status"] = "REJECTED"
                by[key]["reason_code"] = r.get("reason_code") or "REJECTED"

    out = {}
    for period, market in C.MARKET_CATALOG:
        key = (period, market)
        info = by[key]
        if info["n"] == 0:
            info = {"status": "NOT_IMPLEMENTED", "reason_code": "ADAPTER_NOT_LANDED",
                    "n": 0, "priced": 0, "rejected": 0}
        out[f"{period}/{market}"] = info
    return out


def summary(census_dict: dict) -> dict:
    counts = defaultdict(int)
    for v in census_dict.values():
        counts[v["status"]] += 1
    return {"families": len(census_dict), "by_status": dict(counts)}


if __name__ == "__main__":
    print(summary(census([], [])))
