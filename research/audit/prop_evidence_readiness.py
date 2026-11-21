"""Read-only, fail-closed readiness census for private original prop captures.

This tool never grades, backfills player IDs, computes Brier/correlation,
authenticates a provider, or changes original bytes. Every count is a
readiness count, NEVER proof of an exploitable betting edge.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import math

BASE_COLUMNS = {
    "sport", "market", "period", "side", "player_id", "player",
    "line", "price_american", "grade", "actual", "data_quality",
    "source_file_sha256", "source", "book",
}
TD_MARKETS = {"attd", "first_td", "td_2plus", "td2plus", "firsttd"}
INDEPENDENT_MODES = {"PROJECTION", "INDEPENDENT_MODEL", "FROZEN_PROJECTION"}
MAX_BYTES = 12_000_000


def strict_rows(raw: bytes) -> list[dict[str, str]]:
    """Reject ambiguous headers, ragged/empty logical records and malformed UTF-8.

    Actual physical empty lines inside properly quoted multiline CSV fields
    are retained. No row or field is silently deleted or normalized.
    """
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        raise ValueError("EMPTY_NONBYTES_OR_OVERSIZE_SOURCE")
    try:
        txt = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(txt, newline=""), strict=True)
        fields = next(reader, None)
        if not fields or any(not c or c != c.strip() for c in fields):
            raise ValueError("INVALID_HEADER")
        if len(set(c.casefold() for c in fields)) != len(fields):
            raise ValueError("DUPLICATE_CASEFOLD_HEADER")
        if not BASE_COLUMNS.issubset(fields):
            raise ValueError("MISSING_CAPTURE_SCHEMA")
        rows = []
        for cells in reader:
            if not cells or all(not c.strip() for c in cells):
                raise ValueError("BLANK_LOGICAL_RECORD")
            if len(cells) != len(fields):
                raise ValueError("RAGGED_CSV_RECORD")
            rows.append(dict(zip(fields, cells)))
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("MALFORMED_CSV") from exc


def prop_family(market: str) -> str | None:
    m = market.strip().lower()
    if m.startswith("player_prop"):
        return "PLAYER_STAT_THRESHOLD"
    if m in TD_MARKETS:
        return "TOUCHDOWN_EVENT"
    return None


def _utc(raw: str):
    if not raw or len(raw) > 70:
        return None
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if not t.tzinfo or t.utcoffset().total_seconds() != 0:
        return None
    return t.astimezone(timezone.utc)


def evidence_gaps(row: dict[str, str]) -> list[str]:
    """Return *all* missing requirements, never infer missing observations."""
    missing = []
    def exists(key):
        return bool(str(row.get(key, "")).strip())

    if not exists("event_id"):
        missing.append("EVENT_ID_UNBOUND")
    if not exists("player_id"):
        missing.append("PLAYER_ID_UNBOUND")
    if not exists("price_american") or (prop_family(row["market"]) == "PLAYER_STAT_THRESHOLD" and not exists("line")):
        missing.append("OFFER_PRICE_OR_STAT_LINE_MISSING")

    # A screenshot filename or its hash is not a signed provider quote.
    if not all(exists(k) for k in (
        "provider_receipt_id", "provider_observed_utc",
        "provider_captured_utc", "original_quote_sha256",
    )):
        missing.append("ORIGINAL_PROVIDER_QUOTE_PROOF_MISSING")

    try:
        p = float(str(row.get("p_model", "")).strip())
    except (ValueError, TypeError):
        p = math.nan
    if not math.isfinite(p) or not 0 < p < 1:
        missing.append("FROZEN_MODEL_PROBABILITY_MISSING_OR_INVALID")
    if str(row.get("model_mode", "")).strip().upper() not in INDEPENDENT_MODES:
        missing.append("INDEPENDENT_MODEL_MODE_UNVERIFIED")

    model_asof = _utc(row.get("model_asof_utc", ""))
    published = _utc(row.get("features_published_utc", ""))
    start = _utc(row.get("game_start_utc", ""))
    if not model_asof or not published or not start:
        missing.append("POINT_IN_TIME_MODEL_CLOCKS_MISSING")
    elif not published <= model_asof < start:
        missing.append("MODEL_OR_FEATURE_LOOKAHEAD")
    if not exists("model_sha256") or not exists("feature_snapshot_sha256"):
        missing.append("FROZEN_MODEL_SOURCE_HASH_MISSING")
    if not exists("grade") or not exists("actual") or not exists("result_source"):
        missing.append("GRADED_OFFICIAL_RESULT_MISSING")
    settled = _utc(row.get("settled_utc", ""))
    if not settled or not start or settled <= start:
        missing.append("SETTLEMENT_PROVENANCE_CLOCK_MISSING_OR_INVALID")
    return missing


def audit_capture(raw: bytes) -> dict:
    rows = strict_rows(raw)
    families = Counter()
    market_counts = Counter()
    gaps = Counter()
    player_related = 0
    row_ready = 0
    for row in rows:
        market = row["market"].strip().lower()
        market_counts[market] += 1
        family = prop_family(market)
        if family is None:
            families["NON_PLAYER_GAME_MARKET"] += 1
            continue
        families[family] += 1
        player_related += 1
        defects = evidence_gaps(row)
        gaps.update(defects)
        if not defects:
            row_ready += 1
    # A complete self-declared CSV is only structurally ready.
    # This program has no access to independently authenticated upstream logs.
    return {
        "schema": "sportsedge-private-prop-evidence-readiness-v1",
        "source_rows": len(rows),
        "player_related_rows": player_related,
        "market_counts": dict(sorted(market_counts.items())),
        "market_family_counts": dict(sorted(families.items())),
        "prop_rows_structurally_complete_unverified": row_ready,
        "prop_rows_provider_authenticated": 0,
        "prop_rows_eligible_for_verified_joint_metrics": 0,
        "gap_counts_nonexclusive": dict(sorted(gaps.items())),
        "model_or_history_mutated": False,
        "state": "PAPER_0U_MISSING_EXTERNAL_SOURCE_PROOF",
        "note": "No joint hit rates, Brier scores, profits or player identities may be inferred from this readiness census.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_capture_csv", type=Path)
    args = parser.parse_args(argv)
    # Only aggregate counts go to stdout; never echo names, prices or source rows.
    result = audit_capture(args.private_capture_csv.read_bytes())
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
