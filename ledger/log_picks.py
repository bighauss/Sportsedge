"""Append the engine's priced sides to ledger/prediction_log.csv.

Preferred: python ledger/run_it.py board.csv <start_utc>   (runs engine + logs)
Manual:    python ledger/log_picks.py picks.csv <start_utc>

Each row gets bet_key = sport|game|market|side|player|pick (pick text carries the line),
so grading matches exactly one side. Logging only.
"""
import csv, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from prediction_log import log_run


def bet_key(p):
    market, side = (str(p.get("bet_type", "")).split("|") + ["", ""])[:2]
    return "|".join([p["sport"], p["game"], market, side, p.get("player", "") or "", p["pick"]])


def to_rows(picks, start):
    rows = []
    for p in picks:
        if p.get("model_p") in (None, ""):
            continue
        mp = p.get("market_p")
        rows.append(dict(sport=p["sport"], game=p["game"], start_utc=start,
                         market=str(p.get("bet_type", "")).split("|")[0],
                         player=p.get("player", "") or "", pick=p["pick"], bet_key=bet_key(p),
                         price_american=p["price"], model_p=p["model_p"],
                         market_p_novig="" if mp in (None, "") else mp))
    return rows


def log_out(out, start=""):
    rows = to_rows(out, start)
    log_run(rows)
    return len(rows)


def main(path="picks.csv", start=""):
    with open(path, newline="") as f:
        print(f"logged {log_out(list(csv.DictReader(f)), start)} priced sides")


if __name__ == "__main__":
    main(*sys.argv[1:3])
