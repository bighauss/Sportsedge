"""Research-only census; no inferred neutral flags or Division I membership."""
import argparse
import json
from collections import Counter
import pyarrow.parquet as pq

def audit(path):
    table = pq.read_table(path)
    required = ("game_id", "game_date", "completed", "home_team_id",
                "away_team_id", "home_score", "away_score", "neutral_site")
    missing = sorted(set(required) - set(table.column_names))
    if missing:
        raise ValueError(f"missing columns: {missing}")
    rows = table.select(required).to_pylist()
    ids = Counter(r["game_id"] for r in rows if r["game_id"] is not None)
    finals = [r for r in rows if r["completed"] is True]
    valid = [r for r in finals if all(type(r[k]) is int and r[k] >= 0
             for k in ("home_score", "away_score"))]
    return {
        "rows": len(rows), "completed": len(finals),
        "valid_score_finals": len(valid),
        "duplicate_id_excess": sum(n-1 for n in ids.values()),
        "nulls": {k: sum(r[k] is None for r in rows) for k in required},
        "final_neutral": sum(r["neutral_site"] is True for r in valid),
        "final_non_neutral": sum(r["neutral_site"] is False for r in valid),
        "final_unknown_neutral": sum(r["neutral_site"] is None for r in valid),
        "same_team_finals": sum(r["home_team_id"] == r["away_team_id"] for r in valid),
        "schema": str(table.schema),
        "release_state": "PAPER_0U_NON_COUNTED",
    }

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("asset")
    print(json.dumps(audit(p.parse_args().asset), sort_keys=True))
