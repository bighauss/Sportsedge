#!/usr/bin/env python3
"""Exact-byte Torvik CSV candidate capture. Never backfill historical PIT data.

This is a research-only raw response archiver. A local SHA-256 authenticates
the captured bytes, NOT provider publication time or a complete D-I census.
If Torvik rejects the HTTP request, fail; do not substitute a web summary.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_URL = "https://barttorvik.com/2027_team_results.csv"
ALIAS = {
    "team": ("team", "team_name", "teamname"),
    "adjoe": ("adjoe", "adjo", "adj_o", "adj. off."),
    "adjde": ("adjde", "adjd", "adj_d", "adj. def."),
    "adj_t": ("adj_t", "adjt", "tempo", "adj tempo", "adj. tempo")
}


class Reject(ValueError):
    pass


def clock(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError) as e:
        raise Reject("INVALID_CAPTURE_CLOCK") from e
    if d.tzinfo is None or d.utcoffset() is None:
        raise Reject("CAPTURE_CLOCK_NEEDS_OFFSET")
    return d.astimezone(timezone.utc)


def extract(raw, min_count=350, max_count=420):
    if not isinstance(raw, bytes) or not raw or len(raw) > 4_000_000:
        raise Reject("EMPTY_OR_OVERSIZE_RESPONSE")
    try:
        text = raw.decode("utf-8-sig", "strict")
        f = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = [x.strip().lower() for x in next(f, [])]
    except (UnicodeError, csv.Error) as e:
        raise Reject("INVALID_CSV") from e
    if not header or len(header) != len(set(header)) or not all(header):
        raise Reject("AMBIGUOUS_HEADER")
    chosen = {}
    for key, aliases in ALIAS.items():
        hits = [header.index(name) for name in aliases if name in header]
        if len(hits) != 1:
            raise Reject("MISSING_OR_AMBIGUOUS_FIELD:" + key)
        chosen[key] = hits[0]
    teams = set()
    rows = []
    try:
        for number, cols in enumerate(f, 2):
            if len(cols) != len(header) or not any(s.strip() for s in cols):
                raise Reject(f"BAD_CSV_ROW:{number}")
            name = cols[chosen["team"]].strip()
            if not name or name in teams:
                raise Reject("DUPLICATE_OR_BLANK_TEAM")
            teams.add(name)
            rec = {"team": name}
            for field in ("adjoe", "adjde", "adj_t"):
                try:
                    value = float(cols[chosen[field]])
                except (ValueError, TypeError) as e:
                    raise Reject("MISSING_NUMERIC:" + field) from e
                if not math.isfinite(value):
                    raise Reject("NONFINITE:" + field)
                rec[field] = value
            if not (65 <= rec["adjoe"] <= 160 and 65 <= rec["adjde"] <= 160 and
                    45 <= rec["adj_t"] <= 90):
                raise Reject("IMPLAUSIBLE_TORVIK_UNITS")
            rows.append(rec)
    except csv.Error as e:
        raise Reject("BAD_CSV_BODY") from e
    if not (min_count <= len(rows) <= max_count):
        raise Reject(f"NOT_FULL_D1_CANDIDATE:{len(rows)}")
    return {
        "n_teams": len(rows),
        "arithmetic_mean_oe": sum((r["adjoe"] + r["adjde"]) / 2 for r in rows) / len(rows),
        "arithmetic_mean_tempo": sum(r["adj_t"] for r in rows) / len(rows),
        "season_census_verified": False,
        "source_publication_verified": False,
        "no_historical_pit_claim": True,
    }


def download(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("barttorvik.com", "www.barttorvik.com") or not parsed.path.endswith("_team_results.csv"):
        raise Reject("URL_NOT_ALLOWED_TORVIK_RAW_CSV")
    r = Request(url, headers={"User-Agent": "SportsEdge-Research-Raw-Capture/1.0",
                              "Accept": "text/csv,*/*;q=0.5",
                              "Accept-Encoding": "identity"})
    with urlopen(r, timeout=15) as response:
        if response.status != 200:
            raise Reject("TORVIK_RESPONSE_NOT_200")
        actual = urlparse(response.geturl())
        if actual.hostname not in ("barttorvik.com", "www.barttorvik.com"):
            raise Reject("TORVIK_REDIRECT_TO_OTHER_HOST")
        raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise Reject("RESPONSE_TOO_LARGE")
        return raw


def persist(raw, output, source_url, captured_utc):
    stamp = clock(captured_utc)
    summary = extract(raw)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "original_response.csv").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    receipt = {"source_url": source_url, "captured_utc": stamp.isoformat(),
               "original_bytes_sha256": digest, "original_bytes_size": len(raw),
               "response_preserved_unmodified": True,
               "scale_candidate": summary,
               "status": "UNVALIDATED_FULL_CENSUS_CANDIDATE",
               "official_projection_parameters_adopted": False}
    (output / "capture_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if hashlib.sha256((output / "original_response.csv").read_bytes()).hexdigest() != digest:
        raise Reject("RAW_FILE_CHANGED_AFTER_WRITE")
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--out-dir", required=True)
    a = p.parse_args()
    # Fail loudly on HTTP 403 / DNS / HTML / wrong CSV shape. Do not pretend success.
    raw = download(a.url)
    # The CLI stamps its own UTC acquisition clock; never accept backdated user input.
    report = persist(raw, a.out_dir, a.url, datetime.now(timezone.utc).isoformat())
    print(f"RAW_BYTES={report['original_bytes_size']} SHA256={report['original_bytes_sha256']} "
          f"TEAMS={report['scale_candidate']['n_teams']} PAPER/0u")


if __name__ == "__main__":
    main()
