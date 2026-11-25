"""Guarded NBA RUN IT entry point (research only, PAPER_0U).

Use this CLI, not python sportsedge_nba_model.py, so invalid market contracts
never reach the frozen pricer. Source kinds: dk_capture, pdf, screenshot, csv,
manual, replay. PDF and screenshot captures require extracted structured odds
rows (an odds CSV or --odds-rows); the raw file is not parsed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from market_contract import (  # noqa: E402
    SOURCE_KINDS, load_board, run_card_guarded,
)

INPUT_NAMES = ("teams", "games", "injuries", "players", "positional_defense", "odds", "props")


def run_from_inputs(inputs: dict, out_dir: str = ".", *, source_kind: str = "csv"):
    return run_card_guarded(inputs, out_dir, source_kind=source_kind)


def _dir_inputs(folder: str) -> dict:
    paths = {n: os.path.join(folder, n + ".csv") for n in INPUT_NAMES}
    return {k: v for k, v in paths.items() if os.path.exists(v)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-kind", required=True, choices=sorted(SOURCE_KINDS))
    p.add_argument("--inputs", default="sample", help="Directory of input CSVs")
    p.add_argument("--odds", default="", help="Odds CSV (extracted rows for any source kind)")
    p.add_argument("--games", default="", help="Games CSV used to bind team identities")
    p.add_argument("--capture-path", default="", help="Original PDF/screenshot/DK artifact path (not parsed)")
    p.add_argument("--out", default="out")
    args = p.parse_args(argv)
    inputs = _dir_inputs(args.inputs)
    if args.odds:
        inputs["odds"] = args.odds
    if args.games:
        inputs["games"] = args.games
    if args.capture_path:
        inputs["capture_path"] = args.capture_path
    result = run_from_inputs(inputs, args.out, source_kind=args.source_kind)
    summary = {
        "source_kind": result.get("source_kind"),
        "accepted": len(result.get("accepted") or []),
        "rejected": len(result.get("rejected") or []),
        "picks": len(result.get("picks") or []),
        "ledger": result.get("ledger"),
        "csv": result.get("csv"),
        "official_counted": 0,
        "approved_stake_u": 0,
        "release": "PAPER_0U",
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if result.get("accepted") is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
