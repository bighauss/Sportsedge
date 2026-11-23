"""Read-only, fail-closed source-text identity audit for mislabelled CBB rows.

Does not verify original PDFs or recover missing pregame predictions. Reports
candidate 1:1 event-label corrections only; leave all original exports untouched.
Never promote candidate quotes into bet settlement or official ROI.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


def _letters(s):
    return re.sub(r"[^a-z]", "", str(s).casefold())


def _teams(event):
    parts = re.split(r"\s+AT\s+", event, flags=re.IGNORECASE)
    if len(parts) != 2 or not all(_letters(x) for x in parts):
        raise ValueError("INVALID_EVENT_IDENTITY")
    return parts[0], parts[1]


def _source_names_match(raw, event):
    """Require full away name plus home name/prefix visible in OCR source text.

    The OCR prefix fallback remains unverified; it can never authenticate
    original capture bytes and only works for unique, bijective groups.
    """
    away, home = _teams(event)
    norm = _letters(raw)
    a, h = _letters(away), _letters(home)
    if a not in norm:
        return False
    return h in norm or (len(h) >= 12 and h[:9] in norm)


def reconcile(rows):
    """Map extracted text to event labels only within the same capture/period.

    Any ambiguous, duplicate, or incomplete group is quarantined all-copy.
    """
    if not isinstance(rows, list):
        raise ValueError("ROW_LIST_REQUIRED")
    flagged = [dict(r) for r in rows if r.get("identity_status") != "OK"]
    groups = defaultdict(list)
    for n, r in enumerate(flagged, 1):
        if not all(isinstance(r.get(k), str) and r[k].strip() for k in (
            "event", "market", "start", "source_file", "raw_source_text")):
            raise ValueError("CONFLICT_ROW_MISSING_SOURCE_FIELDS")
        _teams(r["event"])
        groups[(r["market"], r["start"], r["source_file"])].append((n, r))

    proposed, blocked, census = [], [], Counter()
    for group, entries in sorted(groups.items()):
        expected = {r["event"] for _, r in entries}
        label_counts = Counter(r["event"] for _, r in entries)
        options = []
        for n, r in entries:
            matches = sorted(event for event in expected
                             if _source_names_match(r["raw_source_text"], event))
            options.append((n, r, matches))
        unique = [hits[0] for _, _, hits in options if len(hits) == 1]
        bijection = (len(expected) == len(entries)
                     and all(v == 1 for v in label_counts.values())
                     and len(unique) == len(entries)
                     and len(set(unique)) == len(entries)
                     and set(unique) == expected)
        if not bijection:
            for n, r, matches in options:
                blocked.append({"source_row_ordinal_within_disputes": n,
                                "original_event": r["event"], "market": group[0],
                                "reason": "AMBIGUOUS_OR_NONBIJECTIVE_SOURCE_IDENTITY",
                                "candidate_count": len(matches)})
            census["blocked_rows"] += len(entries)
            continue

        for n, r, matches in options:
            raw = r["raw_source_text"]
            proposed.append({
                "source_row_ordinal_within_disputes": n,
                "stored_event_label": r["event"],
                "extracted_text_event_candidate": matches[0],
                "market": r["market"], "start": r["start"],
                "source_file": r["source_file"],
                "source_pdf_sha256_claimed": r.get("source_pdf_sha256", ""),
                "raw_text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "quote_fields_preserved": {
                    k: r.get(k, "") for k in (
                        "away_spread", "home_spread", "total", "away_ml",
                        "away_sp_odds", "over_odds", "home_ml", "home_sp_odds",
                        "under_odds")},
                "status": "CANDIDATE_LABEL_REASSIGNMENT_UNVERIFIED_ORIGINAL"})
        census["candidate_rows"] += len(entries)
    return {
        "schema": "sportsedge-cbb-extraction-identity-audit-v1",
        "input_rows": len(rows), "disputed_rows": len(flagged),
        "candidate_reassignments": proposed, "blocked": blocked,
        "census": dict(sorted(census.items())),
        "original_pdf_authenticated": False,
        "model_probabilities_recovered": False,
        "official_counted": 0, "approved_stake_u": 0,
        "warning": "OCR text is not an original PDF. Do not overwrite frozen records, approve prices, grade candidates or count wagers."}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_reextracted_csv")
    p.add_argument("--out", required=True, help="create-only owner-private JSON output")
    args = p.parse_args(argv)
    with open(args.private_reextracted_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, strict=True))
    report = reconcile(rows)
    with Path(args.out).open("x", encoding="utf-8") as out:
        json.dump(report, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    print(json.dumps({
        "input_rows": report["input_rows"],
        "disputed_rows": report["disputed_rows"],
        "census": report["census"],
        "original_pdf_authenticated": False}, sort_keys=True))
    return 0 if not report["blocked"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
