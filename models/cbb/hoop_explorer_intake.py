"""Inspect a manually exported Hoop-Explorer CSV/JSON without publishing data.

Generates a SHA-256 and an UNVERIFIED manifest DRAFT. No network, provider
login, scraping, predictions, odds or sensitive user data output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

try:
    from .hoop_explorer_research import (Blocked, MAX_BYTES, REQUIRED, OPTIONAL,
                                        read_rows)
except ImportError:
    from hoop_explorer_research import (Blocked, MAX_BYTES, REQUIRED, OPTIONAL,
                                       read_rows)


def inspect_export(path, kind, export_format=None):
    if kind not in REQUIRED:
        raise Blocked("UNKNOWN_EXPORT_KIND")
    file = Path(path)
    raw = file.read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise Blocked("EXPORT_EMPTY_OR_TOO_LARGE")
    fmt = export_format or file.suffix.lower().lstrip(".")
    if fmt not in ("csv", "json"):
        raise Blocked("CSV_OR_JSON_FORMAT_REQUIRED")
    rows, headers = read_rows(raw, fmt)
    if not rows:
        raise Blocked("EMPTY_EXPORT_ROWS")
    if any(not isinstance(k, str) or not k.strip() for k in headers):
        raise Blocked("INVALID_EXPORT_COLUMNS")
    headers = sorted(headers)
    digest = hashlib.sha256(raw).hexdigest()
    draft = {
        "provider": "hoop_explorer",
        "kind": kind,
        "format": fmt,
        "source_url": None,
        "access_basis": None,
        "scope_id": None,
        "season": None,
        "sha256": digest,
        "data_through_utc": None,
        "published_utc": None,
        "captured_utc": None,
        "columns": {key: None for key in sorted(REQUIRED[kind])},
    }
    if kind == "lineup":
        draft["disjoint_partition"] = False
    return {
        "status": "INSPECTED_ONLY_NOT_ADMITTED",
        "source_authenticated": False,
        "pregame_eligible": False,
        "official": False,
        "stake_u": 0,
        "data_values_included": False,
        "kind": kind,
        "rows": len(rows),
        "bytes": len(raw),
        "sha256": digest,
        "observed_headers": headers,
        "required_canonical_fields": sorted(REQUIRED[kind]),
        "optional_canonical_fields": sorted(OPTIONAL[kind]),
        "draft_manifest": draft,
        "warnings": [
            "Fill exact source header mappings; no name-based player identity guesses.",
            "If site does not publish timestamp history, use exploratory-only research.",
            "Do not invent release or data-through timestamps.",
            "Do not commit raw exports, secret API keys or private player files to public GitHub.",
        ]
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="local export file")
    p.add_argument("--kind", choices=sorted(REQUIRED), required=True)
    p.add_argument("--format", choices=("csv", "json"), dest="fmt")
    p.add_argument("--out", help="write inspector JSON to local path")
    args = p.parse_args(argv)
    report = inspect_export(args.input, args.kind, args.fmt)
    result = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(result, encoding="utf-8")
        print(f"INSPECTED_ONLY / 0u: {dest}")
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
