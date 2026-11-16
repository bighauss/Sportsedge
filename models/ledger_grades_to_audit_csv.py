"""Convert historical markdown grade tables into *blocked* G2/G3 intake CSV.

This is a bookkeeping bridge, NOT a reconstruction of historical probabilities,
pregame odds receipts, sportsbook snapshots or event-level settlement evidence.
Outputs retain original odds and explicit W/L text, but leave missing inputs
as NOT_CAPTURED so the audit will fail closed. Do not use this to certify EV.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import re

from audit_disagreement_calibration import FIELDS

EXTRAS = ("ledger_section", "ledger_row", "ledger_markdown_sha256", "settlement_note")
COLUMNS = (*FIELDS, *EXTRAS)
ODDS = re.compile(r"^[+-][0-9]{3,6}$")
UNRELIABLE = re.compile(r"\b(inferred|likely|assum(?:e|es|ed|ing))\b", re.I)


def convert(markdown: str, *, filename: str = "ledger.md") -> list[dict]:
    source_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    records = []
    section = "UNSPECIFIED"
    for line_number, line in enumerate(markdown.splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [x.strip() for x in line[1:-1].split("|")]
        if len(cells) != 3 or cells[0].lower() == "play":
            continue
        if all(re.fullmatch(r"[-: ]+", x) for x in cells):
            continue
        play, odds_text, result_text = cells
        if not play:
            continue
        price = odds_text.replace("−", "-").replace("–", "-")
        if not ODDS.fullmatch(price):
            price = "NOT_CAPTURED"
        # Explicit W/L is still merely a markdown assertion. "Inferred" and
        # "likely" outcomes must never be silently classified as settled.
        match = re.match(r"^(WIN|LOSS)\b", result_text, re.I)
        outcome = ("1" if match.group(1).upper() == "WIN" else "0") if (
            match and not UNRELIABLE.search(result_text)
        ) else "UNVERIFIED"
        records.append({
            "event_id": f"LEDGER_ROW_{len(records)+1:05d}_UNMAPPED",
            "market": "UNCLASSIFIED",
            "selection": play,
            "model_p": "NOT_CAPTURED",
            "market_p": "NOT_CAPTURED",
            "outcome": outcome,
            "snapshot_utc": "NOT_CAPTURED",
            "kickoff_utc": "NOT_CAPTURED",
            "final_utc": "NOT_CAPTURED",
            "model_sha256": "NOT_CAPTURED",
            "source_sha256": "NOT_CAPTURED",
            "odds": price,
            "ledger_section": section,
            "ledger_row": str(line_number),
            "ledger_markdown_sha256": source_hash,
            "settlement_note": result_text,
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.markdown.read_text(encoding="utf-8")
    rows = convert(raw, filename=args.markdown.name)
    if not rows:
        raise SystemExit("No ledger grade rows found; no output written")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Prevent overwriting saved intake by accident.
    with args.output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"BLOCKED_RESEARCH: wrote {len(rows)} unverified grade rows to {args.output}")
    print("Missing model/market probabilities, trusted snapshots and timestamps MUST be supplied from their actual pregame records.")


if __name__ == "__main__":
    main()
