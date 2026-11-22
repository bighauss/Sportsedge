"""SportsEdge pre-game prediction log + calibration audit.

Logging/audit only. Does NOT change any model formula, weight, threshold or rule.

Every "run it" logs one row per priced side (ledger/run_it.py does it automatically).
Grade:  grade(bet_key, "W"|"L"|"P")   - matches exactly one side via bet_key
Audit:  python ledger/prediction_log.py audit
        only rows saved before kickoff, two-sided (has no-vig price), latest pre-game row per bet_key.
CLV is intentionally not used (Isaac removed it).
"""
import csv, math, os, sys
from datetime import datetime, timezone

PATH = os.path.join(os.path.dirname(__file__), "prediction_log.csv")
FIELDS = ["ts_utc", "sport", "game", "start_utc", "market", "player", "pick", "bet_key",
          "price_american", "model_p", "market_p_novig", "result"]


def _read():
    if not os.path.exists(PATH):
        return []
    with open(PATH, newline="") as f:
        return [{k: r.get(k, "") for k in FIELDS} for r in csv.DictReader(f)]


def _write(rows):
    with open(PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def log_run(new_rows):
    rows = _read()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in new_rows:
        r = {k: r.get(k, "") for k in FIELDS}
        r["ts_utc"] = r["ts_utc"] or now
        r["result"] = ""
        rows.append(r)
    _write(rows)


def grade(bet_key, result):
    """Set result on every logged row with this exact bet_key. Returns rows updated."""
    assert result in ("W", "L", "P")
    rows = _read()
    n = 0
    for r in rows:
        if r["bet_key"] == bet_key:
            r["result"] = result
            n += 1
    _write(rows)
    return n


def _profit(price, res):
    p = float(price)
    if res == "P":
        return 0.0
    if res == "L":
        return -1.0
    return p / 100 if p > 0 else 100 / -p


def _ts(s):
    return datetime.fromisoformat(s)


def audit(rows=None, edges=(-1.0, 0.0, 0.02, 0.05, 0.10, 1.0)):
    rows = rows if rows is not None else _read()
    latest = {}
    for r in rows:
        if r["result"] not in ("W", "L") or not r["market_p_novig"] or not r["start_utc"]:
            continue
        if _ts(r["ts_utc"]) >= _ts(r["start_utc"]):
            continue                                   # saved after kickoff -> not pre-game
        k = r["bet_key"] or r["pick"]
        if k not in latest or r["ts_utc"] > latest[k]["ts_utc"]:
            latest[k] = r
    clean = list(latest.values())
    print(f"graded pre-game two-sided sides: {len(clean)}")
    for lo, hi in zip(edges, edges[1:]):
        b = [r for r in clean if lo <= float(r["model_p"]) - float(r["market_p_novig"]) < hi]
        if not b:
            continue
        n = len(b)
        y = [1.0 if r["result"] == "W" else 0.0 for r in b]
        mp = [float(r["model_p"]) for r in b]
        kp = [float(r["market_p_novig"]) for r in b]
        brier = lambda ps: sum((p - o) ** 2 for p, o in zip(ps, y)) / n
        ll = lambda ps: -sum(o * math.log(max(p, 1e-6)) + (1 - o) * math.log(max(1 - p, 1e-6))
                             for p, o in zip(ps, y)) / n
        roi = sum(_profit(r["price_american"], r["result"]) for r in b) / n
        flag = "  SMALL SAMPLE" if n < 50 else ""
        print(f"edge {lo:+.0%}..{hi:+.0%}: n={n} model={sum(mp)/n:.3f} actual={sum(y)/n:.3f} "
              f"mkt={sum(kp)/n:.3f} ROI={roi:+.1%} Brier m/k={brier(mp):.4f}/{brier(kp):.4f} "
              f"LL m/k={ll(mp):.4f}/{ll(kp):.4f}{flag}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        audit()
    else:
        print(__doc__)
