"""Append the engine's picks.csv (every priced side) to ledger/prediction_log.csv.

Run right after the engine, before games start:
    python engine/sportsedge_v5.py board.csv
    python ledger/log_picks.py picks.csv [start_utc]

start_utc (ISO, e.g. 2026-11-22T18:00:00+00:00) is the slate's earliest kickoff; if given,
the audit can prove each row was saved pre-game. Engine untouched; logging only.
"""
import csv, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from prediction_log import log_run


def main(path="picks.csv", start=""):
    with open(path, newline="") as f:
        picks = list(csv.DictReader(f))
    rows = [dict(sport=p["sport"], game=p["game"], start_utc=start,
                 market=p.get("bet_type", "").split("|")[0], pick=p["pick"],
                 price_american=p["price"], model_p=p["model_p"],
                 market_p_novig=p.get("market_p") or "")
            for p in picks if p.get("model_p")]
    log_run(rows)
    print(f"logged {len(rows)} priced sides")


if __name__ == "__main__":
    main(*sys.argv[1:3])
