#!/usr/bin/env python3
"""Daily fail-closed market release matrix sweep; no book authentication or bet placement."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

SPORTS = frozenset(("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"))
FAMILIES = frozenset(("FULL_GAME_ML_SPREAD_TOTAL", "TEAM_TOTALS", "PLAYER_PROPS",
                      "PERIODS", "SPECIALS", "ALTERNATES", "SGP_OR_CORRELATED"))
GATES = frozenset(("A", "B", "C", "D", "E"))
REPO = Path(__file__).resolve().parents[2]
DEFAULT = REPO / "research" / "freezes" / "market_release_matrix_20261115.json"


def inspect_matrix(matrix):
    problems = []
    if not isinstance(matrix, dict) or matrix.get("schema") != "sportsedge-market-release-matrix-v1":
        return {"status": "BLOCK", "issues": ["UNKNOWN_MATRIX_SCHEMA"]}
    markets = matrix.get("markets")
    if not isinstance(markets, list):
        return {"status": "BLOCK", "issues": ["MARKET_ROWS_MISSING"]}
    seen = set()
    for i, row in enumerate(markets):
        if not isinstance(row, dict):
            problems.append("NONOBJECT_ROW:" + str(i))
            continue
        sport, family = row.get("sport"), row.get("market_family")
        key = (sport, family)
        if sport not in SPORTS or family not in FAMILIES:
            problems.append("UNKNOWN_MARKET_FAMILY:" + str(i))
            continue
        if key in seen:
            problems.append("DUPLICATE_MARKET:" + sport + "/" + family)
        seen.add(key)
        gates = row.get("gates")
        if not isinstance(gates, dict) or set(gates) != GATES or any(type(gates[g]) is not bool for g in GATES):
            problems.append("MISSING_OR_INVALID_AE_FLAGS:" + sport + "/" + family)
        if row.get("release_state") != "PAPER_0U":
            # External provider receipt signature verification and independent release
            # attestation are not yet implemented: refuse even caller-declared A-E True.
            problems.append("UNSUPPORTED_OFFICIAL_RELEASE:" + sport + "/" + family)
        if type(row.get("approved_stake_u")) not in (int, float) or row.get("approved_stake_u") != 0:
            problems.append("NONZERO_STAKE_FORBIDDEN:" + sport + "/" + family)
        if row.get("official_counted") != 0 or type(row.get("official_counted")) is not int:
            problems.append("OFFICIAL_COUNT_FORBIDDEN:" + sport + "/" + family)
        if not isinstance(row.get("reasons"), list):
            problems.append("MISSING_REASON_CODES:" + sport + "/" + family)
    for sport in SPORTS:
        for family in FAMILIES:
            if (sport, family) not in seen:
                problems.append("MISSING_FAMILY:" + sport + "/" + family)
    return {"status": "PAPER_0U_SAFE_MATRIX" if not problems else "BLOCK",
            "issues": sorted(set(problems)), "checked": len(seen),
            "official_counted": 0, "approved_stake_u": 0}


def _unique_pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("DUPLICATE_JSON_KEY:" + k)
        d[k] = v
    return d


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--matrix", type=Path, default=DEFAULT)
    a = p.parse_args()
    data = json.loads(a.matrix.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs)
    result = inspect_matrix(data)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if not result["issues"] else 2)


if __name__ == "__main__":
    main()
