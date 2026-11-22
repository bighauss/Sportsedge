"""One command for every "run it": runs the engine of record, then logs every priced side.

    python ledger/run_it.py board.csv 2026-11-22T18:00:00+00:00

Second arg = earliest kickoff in the slate (UTC ISO). If omitted, rows are still logged
(picks are NEVER blocked) but are tagged start_utc="" and excluded from the pre-game audit.
Engine formulas untouched; this only calls engine.run() and saves its output.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
sys.path.insert(0, HERE)
import sportsedge_v5
from log_picks import log_out


def main(board="board.csv", start=""):
    out = sportsedge_v5.run(board)          # prints the card + writes picks.csv as always
    try:
        n = log_out(out, start)
        print(f"prediction log: {n} rows saved" + ("" if start else " (no kickoff time - not audit-eligible)"))
    except Exception as e:                  # logging must never stop the card
        print(f"prediction log FAILED (card unaffected): {e}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
