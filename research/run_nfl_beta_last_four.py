"""Offline NFL beta runner: never places bets or changes production cards.

Input JSON:
{"decision_utc":"...Z","scenarios":[{"event_id":"...", "players": {...},
"ordered_touchdowns":[...]}], "offers":[{"event_id":"...", "quote_id":"...",
"book":"DraftKings","kind":"XPLUS", ...}]}
All samples must originate from one independent, timestamped pregame model.
"""
import argparse
import json
from pathlib import Path
from nfl_beta_last_four import price_beta


def main():
    parser = argparse.ArgumentParser(description="NFL last-four PAPER beta")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-scenarios", type=int, default=1000)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if set(data) != {"decision_utc", "scenarios", "offers"}:
        raise ValueError("INPUT_SCHEMA_MUST_BE_EXACT")
    result = price_beta(data["scenarios"], data["offers"],
                        decision_utc=data["decision_utc"],
                        min_scenarios=args.min_scenarios)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
