"""SportsEdge pre-game prediction log + calibration audit.

Logging/audit only. Does NOT change any model formula, weight, threshold or rule.

Every "run it" logs one row per priced side (see log_picks.py).
Row fields: ts_utc, sport, game, start_utc, market, pick, price_american, model_p, market_p_novig
Later: grade(game, pick, result) with result in {W, L, P}.
Audit: python ledger/prediction_log.py audit   (uses only rows logged before start_utc)
CLV is intentionally not used (Isaac removed it).
"""
import csv, math, os, sys
from datetime import datetime, timezone

PATH = os.path.join(os.path.dirname(__file__), "prediction_log.csv")
FIELDS = ["ts_utc", "sport", "game", "start_utc", "market", "pick",
          "price_american", "model_p", "market_p_novig", "result"]


def _read():
    if not os.path.exists(PATH):
        return []
    with open(PATH, newline="") as f:
        return list(csv.DictReader(f))


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


def grade(game, pick, result, market=None):
    rows = _read()
    n = 0
    for r in rows:
        if r["game"] == game and r["pick"] == pick and (market is None or r["market"] == market):
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


def audit(rows=None, edges=(-1.0, 0.0, 0.02, 0.05, 0.10, 1.0)):
    rows = rows if rows is not None else _read()
    clean = [r for r in rows if r["result"] in ("W", "L") and r["market_p_novig"]
             and r["start_utc"] and r["ts_utc"] < r["start_utc"]]  # pre-game, two-sided only
    print(f"graded pre-game two-sided rows: {len(clean)}")
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
