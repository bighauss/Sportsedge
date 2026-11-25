"""Guarded NBA RUN IT entry point (research only, PAPER_0U, NON_COUNTED).

Use this CLI, never `python sportsedge_nba_model.py`, so invalid contracts cannot reach the frozen pricer.
Source kinds: dk_capture, pdf, screenshot, csv, manual, replay. PDF and screenshot captures need extracted
structured rows (--odds/--props CSV); the raw file is not parsed.

Exit status: 0 = priced, 3 = no eligible contracts (nothing priced), 4 = frozen model changed, 2 = usage/input error.
Every run writes a unique workspace under <out>/runs/<run_id>/ with the rejection ledger, accepted inputs,
run_manifest.json (sha256 of every file) and labelled outputs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from market_contract import SOURCE_KINDS, run_guarded  # noqa: E402

INPUT_NAMES = ("teams", "games", "injuries", "players", "positional_defense", "odds", "props")
EXIT = {"PRICED": 0, "NO_ELIGIBLE_CONTRACTS": 3, "FROZEN_MODEL_CHANGED": 4}


def run_from_inputs(inputs: dict, out_dir: str = ".", *, source_kind: str = "csv", as_of=None):
    return run_guarded(inputs, out_dir, source_kind=source_kind, as_of=as_of)


def _dir_inputs(folder: str) -> dict:
    paths = {n: os.path.join(folder, n + ".csv") for n in INPUT_NAMES}
    return {k: v for k, v in paths.items() if os.path.exists(v)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source-kind", required=True, choices=sorted(SOURCE_KINDS))
    p.add_argument("--inputs", default="sample", help="Directory of input CSVs")
    p.add_argument("--odds", default="")
    p.add_argument("--props", default="")
    p.add_argument("--games", default="")
    p.add_argument("--capture-id", default="", help="Board-level capture id (used only when a row has none)")
    p.add_argument("--captured-at", default="", help="Board-level tz-aware ISO timestamp (used only when a row has none)")
    p.add_argument("--as-of", default="", help="tz-aware ISO run time; default now")
    p.add_argument("--capture-path", default="", help="Original PDF/screenshot/DK artifact path (not parsed)")
    p.add_argument("--out", default="out")
    args = p.parse_args(argv)
    inputs = _dir_inputs(args.inputs)
    for k in ("odds", "props", "games"):
        if getattr(args, k):
            inputs[k] = getattr(args, k)
    inputs.update(capture_id=args.capture_id, captured_at=args.captured_at, capture_path=args.capture_path)
    as_of = None
    if args.as_of:
        from market_contract import parse_ts
        as_of = parse_ts(args.as_of)
        if as_of is None:
            print(json.dumps({"status": "INPUT_ERROR", "error": "--as-of must be tz-aware ISO-8601"}))
            return 2
    result = run_from_inputs(inputs, args.out, source_kind=args.source_kind, as_of=as_of)
    print(json.dumps({"status": result["status"], "run_id": result["run_id"], "run_dir": result["run_dir"],
                      "source_kind": result["source_kind"], "accepted_odds": len(result["accepted"]),
                      "accepted_props": len(result["props_accepted"]), "rejected": len(result["rejected"]),
                      "picks": len(result["picks"]), "ledger": result["ledger"], "csv": result["csv"],
                      "official_counted": 0, "approved_stake_u": 0, "release": "PAPER_0U",
                      "status_label": "NON_COUNTED"}, sort_keys=True))
    return EXIT.get(result["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
