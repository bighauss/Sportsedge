"""SportsEdge prediction log + calibration audit (logging/audit only; touches no model logic).

Every "run it" appends one row per priced side to ledger/predictions.csv BEFORE the game:
  ts_utc, sport, game_id, game, market, pick, line, price, model_p, market_p_novig, result
result is filled later: W / L / P (push) / V (void).

CLI:
  python prediction_log.py log  --sport NFL --game-id ... --game "NE@DET" --market ML \
        --pick NE --price +120 --opp-price -140 --model-p 0.48
  python prediction_log.py grade --game-id ... --market ML --pick NE --result W
  python prediction_log.py audit           # calibration buckets by model-vs-market gap
CLV is intentionally not used (Isaac removed it).
"""
import argparse, csv, math, os, sys
from datetime import datetime, timezone

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.csv")
COLS = ["ts_utc", "sport", "game_id", "game", "market", "pick", "line", "price",
        "model_p", "market_p_novig", "result"]


def implied(american):
    a = float(american)
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def novig(price, opp_price):
    p, q = implied(price), implied(opp_price)
    return p / (p + q)


def payout(american):  # profit per 1u staked
    a = float(american)
    return a / 100 if a > 0 else 100 / -a


def read():
    if not os.path.exists(LOG):
        return []
    with open(LOG, newline="") as f:
        return list(csv.DictReader(f))


def write(rows):
    with open(LOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def log_row(a):
    mp = novig(a.price, a.opp_price) if a.opp_price else ""
    rows = read()
    rows.append({"ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "sport": a.sport, "game_id": a.game_id, "game": a.game, "market": a.market,
                 "pick": a.pick, "line": a.line or "", "price": a.price,
                 "model_p": f"{float(a.model_p):.4f}",
                 "market_p_novig": f"{mp:.4f}" if mp != "" else "", "result": ""})
    write(rows)


def grade(a):
    rows, n = read(), 0
    for r in rows:
        if r["game_id"] == a.game_id and r["market"] == a.market and r["pick"] == a.pick:
            r["result"] = a.result
            n += 1
    write(rows)
    print(f"graded {n} row(s)")


BUCKETS = [(0, .02), (.02, .05), (.05, .08), (.08, .12), (.12, 1.0)]


def audit(rows=None, out=sys.stdout):
    rows = rows if rows is not None else read()
    g = [r for r in rows if r["result"] in ("W", "L") and r["market_p_novig"]]
    print(f"graded W/L rows with no-vig market: {len(g)} (of {len(rows)} logged)", file=out)
    print("gap bucket | n | model% | mkt% | actual% | ROI | Brier mdl/mkt | LogL mdl/mkt", file=out)
    for lo, hi in BUCKETS:
        b = [r for r in g if lo <= float(r["model_p"]) - float(r["market_p_novig"]) < hi]
        if not b:
            print(f"{lo:.0%}-{hi:.0%} | 0", file=out)
            continue
        y = [1.0 if r["result"] == "W" else 0.0 for r in b]
        m = [min(max(float(r["model_p"]), 1e-6), 1 - 1e-6) for r in b]
        k = [min(max(float(r["market_p_novig"]), 1e-6), 1 - 1e-6) for r in b]
        n = len(b)
        roi = sum(payout(r["price"]) if yy else -1 for r, yy in zip(b, y)) / n
        bs = lambda p: sum((pp - yy) ** 2 for pp, yy in zip(p, y)) / n
        ll = lambda p: -sum(yy * math.log(pp) + (1 - yy) * math.log(1 - pp) for pp, yy in zip(p, y)) / n
        flag = " SMALL n" if n < 50 else ""
        print(f"{lo:.0%}-{hi:.0%} | {n}{flag} | {sum(m)/n:.1%} | {sum(k)/n:.1%} | {sum(y)/n:.1%} | "
              f"{roi:+.1%} | {bs(m):.3f}/{bs(k):.3f} | {ll(m):.3f}/{ll(k):.3f}", file=out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    l = sp.add_parser("log")
    for f in ["sport", "game-id", "game", "market", "pick", "price", "model-p"]:
        l.add_argument("--" + f, required=True)
    l.add_argument("--opp-price")
    l.add_argument("--line")
    gr = sp.add_parser("grade")
    for f in ["game-id", "market", "pick", "result"]:
        gr.add_argument("--" + f, required=True)
    sp.add_parser("audit")
    a = ap.parse_args()
    {"log": log_row, "grade": grade, "audit": lambda _: audit()}[a.cmd](a)
