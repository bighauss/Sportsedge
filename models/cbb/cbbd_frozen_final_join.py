"""CBB PRIVATE offline join: original frozen board + first-local-observation CBBD finals.

Joins only exact CBBD IDs, season and team IDs. ALL duplicates quarantine,
including blocked source rows. Never reconstruct forecasts or source timestamps.
Produces a complete research-only row ledger accepted by the separate
point_in_time_score_walkforward.audit; never odds, units or +EV.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from cbbd_prospective_capture import Hold, _unique_pairs, _bad_constant, utc
from torvik_cbbd_pregame_bridge import safe_path, _private_directory, _private_create
from point_in_time_score_walkforward import (
    Blocked, _hash, _parse_prediction, _parse_final
)

BOARD_STATUS = "CBB_POINT_IN_TIME_RESEARCH_ONLY_UNAUTHENTICATED_PAPER_0U"
FINALS_STATUS = "PAPER_0U_SOURCE_NOT_INDEPENDENTLY_ATTESTED"
FINAL_ROW_STATUS = "FINAL_RECEIPT_LOCAL_CAPTURE_UNAUTHENTICATED"
PUBLICATION_BASIS = "UPPER_BOUND_LOCAL_OBSERVATION_NOT_PROVIDER_PUBLICATION"


def _canonical_id(x):
    if not isinstance(x, str) or not x.isascii() or not x.isdecimal() or \
            not x or x[0] == "0" or int(x) <= 0:
        return None
    return x


def _container_checks(board, finals):
    if not isinstance(board, dict) or board.get("status") != BOARD_STATUS or \
       board.get("official") is not False or board.get("stake_u") != 0:
        raise Hold("ORIGINAL_BOARD_UNRECOGNIZED_OR_NON_PAPER")
    br = board.get("results")
    if not isinstance(br, list) or type(board.get("input_rows")) is not int or \
       board["input_rows"] != len(br):
        raise Hold("ORIGINAL_BOARD_ROW_CENSUS_MISMATCH")
    if type(board.get("season")) is not int or not 2000 <= board["season"] <= 2100:
        raise Hold("ORIGINAL_BOARD_SEASON_INVALID")
    freeze = utc(board.get("freeze_utc"), "board.freeze_utc")
    for label in ("schedule", "torvik", "crosswalk", "hca"):
        sources = board.get("source_sha256")
        if not isinstance(sources, dict):
            raise Hold("BOARD_ORIGINAL_SOURCE_DIGESTS_REQUIRED")
        try:
            _hash(sources.get(label), "board." + label)
        except Blocked as exc:
            raise Hold("BOARD_ORIGINAL_SOURCE_DIGEST_INVALID:" + label) from exc
    if type(board.get("projected_rows")) is not int or \
       board["projected_rows"] != sum(
           isinstance(r, dict) and r.get("status") == "PAPER_NON_COUNTED_UNCALIBRATED"
           for r in br):
        raise Hold("BOARD_PROJECTED_ROW_CENSUS_MISMATCH")
    for i, r in enumerate(br):
        if not isinstance(r, dict) or type(r.get("input_index")) is not int or \
           r["input_index"] != i or r.get("official") is not False or r.get("stake_u") != 0:
            raise Hold("BOARD_ROW_INDEX_OR_ADMISSION_INCONSISTENT")
        if r.get("status") not in ("BLOCKED", "PAPER_NON_COUNTED_UNCALIBRATED"):
            raise Hold("BOARD_ROW_STATUS_UNKNOWN")
    if not isinstance(finals, dict) or finals.get("format") != "CBBD_LOCAL_FINAL_RECEIPTS_V1" or \
       finals.get("status") != FINALS_STATUS or \
       finals.get("official") is not False or finals.get("stake_u") != 0:
        raise Hold("ORIGINAL_FINALS_REPORT_UNRECOGNIZED_OR_NON_PAPER")
    fr = finals.get("rows")
    if not isinstance(fr, list) or type(finals.get("row_count")) is not int or \
       finals["row_count"] != len(fr):
        raise Hold("FINALS_ROW_CENSUS_MISMATCH")
    try:
        _hash(finals.get("source_sha256"), "finals.source_sha256")
    except Blocked as exc:
        raise Hold("FINALS_SOURCE_SHA256_INVALID") from exc
    observed = utc(finals.get("local_observed_utc"), "finals.local_observed_utc")
    for i, r in enumerate(fr):
        if not isinstance(r, dict) or type(r.get("input_index")) is not int or \
           r.get("input_index") != i or r.get("official") is not False or r.get("stake_u") != 0:
            raise Hold("FINALS_ROW_INDEX_OR_ADMISSION_INCONSISTENT")
        if r.get("status") not in (FINAL_ROW_STATUS, "NOT_FINAL_OR_FUTURE_EVENT", "BLOCKED"):
            raise Hold("FINALS_ROW_STATUS_UNKNOWN")
    return br, fr, freeze, observed


def _final_verified(row, source_hash, observation):
    """Only self-consistent LOCAL normalized receipt, NOT provider attestation."""
    if row.get("status") != FINAL_ROW_STATUS:
        return None, "FINALS_SOURCE_" + row.get("status", "UNKNOWN")
    f = row.get("final")
    if not isinstance(f, dict):
        return None, "FINAL_RECEIPT_OBJECT_REQUIRED"
    if f.get("sha256") != source_hash:
        return None, "FINAL_SOURCE_DIGEST_MISMATCH"
    if f.get("publication_basis") != PUBLICATION_BASIS or \
       f.get("published_utc") != f.get("captured_utc") or \
       f.get("captured_utc") != observation:
        return None, "FINAL_LOCAL_OBSERVATION_CLOCK_MISMATCH"
    if f.get("game_id") != row.get("game_id"):
        return None, "FINAL_ROW_EVENT_ID_MISMATCH"
    return f, "FINAL_LOCALLY_OBSERVED_UNAUTHENTICATED"


def reconcile(board, finals):
    """Retain exactly one output for every original board input, no cherry-picking."""
    br, fr, freeze, observed = _container_checks(board, finals)
    raw_board_ids = [_canonical_id(x.get("game_id")) for x in br]
    duplicate_board = Counter(x for x in raw_board_ids if x is not None)
    final_rows = defaultdict(list)
    orphan_invalid = 0
    for row in fr:
        ident = _canonical_id(row.get("game_id"))
        if ident is None:
            orphan_invalid += 1
        else:
            final_rows[ident].append(row)
    original_ids = set(x for x in raw_board_ids if x is not None)
    unmatched_final_rows = sum(len(items) for k,items in final_rows.items() if k not in original_ids)
    out, details = [], []
    for idx, orig in enumerate(br):
        gid = raw_board_ids[idx]
        status = "BLOCKED_ORIGINAL_ROW"
        reason = orig.get("reason", "ORIGINAL_BOARD_BLOCKED")
        final = None
        if gid is None:
            status, reason = "INVALID_BOARD_EVENT_ID", "ORIGINAL_GAME_ID_MISSING_OR_NONCANONICAL"
        elif duplicate_board[gid] > 1:
            status, reason = "DUPLICATE_ORIGINAL_BOARD_ALL_COPIES", "DUPLICATE_GAME_ID"
        elif orig.get("status") == "PAPER_NON_COUNTED_UNCALIBRATED":
            # Verify arithmetic and chronology using the SAME guard as evaluator.
            try:
                p = _parse_prediction(orig)
                if p["season"] != board["season"] or p["freeze"] != freeze:
                    raise Blocked("BOARD_SEASON_OR_FREEZE_INCONSISTENT")
            except (Blocked, TypeError, ValueError, KeyError, AttributeError) as exc:
                status, reason = "INVALID_ORIGINAL_PREDICTION", str(exc)
            else:
                matched = final_rows.get(gid, ())
                if not matched:
                    status, reason = "MISSING_FINAL_RECEIPT", "PENDING_SOURCE_EVIDENCE"
                elif len(matched) > 1:
                    status, reason = "DUPLICATE_FINAL_RECEIPT_ALL_COPIES", "NON_UNIQUE_PROVIDER_EVENT"
                else:
                    f, verification = _final_verified(
                        matched[0], finals["source_sha256"], finals["local_observed_utc"]
                    )
                    if f is None:
                        status, reason = "UNAVAILABLE_OR_INVALID_FINAL", verification
                    else:
                        try:
                            _parse_final(f, p)
                            if not (p["freeze"] < p["tip"] < observed):
                                raise Blocked("FINAL_ORIGINAL_FORECAST_CLOCK_CONFLICT")
                        except (Blocked, ValueError, KeyError, TypeError) as exc:
                            status, reason = "FINAL_IDENTITY_OR_CLOCK_BLOCKED", str(exc)
                        else:
                            final = f
                            status, reason = "MATCHED_EXACT_PRIVATE_RESEARCH", "LOCAL_CLOCK_NOT_PROVIDER_ATTESTED"
        # No synthetic market quote is inserted, even for scored rows.
        out.append({"prediction": orig, "final": final, "quote": None})
        details.append({"input_index": idx, "game_id": gid, "join_status": status, "reason": reason})
    summary = {
        "status": "CBB_STRICT_FINAL_JOIN_PAPER_0U_UNAUTHENTICATED",
        "official": False, "stake_u": 0,
        "original_board_input_rows": len(br),
        "ledger_rows": len(out),
        "original_board_projected_rows": board["projected_rows"],
        "matched_rows": sum(x["join_status"] == "MATCHED_EXACT_PRIVATE_RESEARCH" for x in details),
        "join_status_counts": dict(sorted(Counter(x["join_status"] for x in details).items())),
        "unmatched_final_source_rows": unmatched_final_rows,
        "unidentified_final_source_rows": orphan_invalid,
        "final_source_rows": len(fr),
        "rows": details,
        "warnings": [
            "THIS_LEDGER_IS_SCORES_ONLY_NOT_AN_ODDS_OR_EV_LEDGER",
            "ORIGINAL_PROVIDER_BYTES_AND_EXTERNAL_PUBLISH_TIMES_NOT_INDEPENDENTLY_ATTESTED",
            "FINAL_PUBLICATION_IS_CONSERVATIVE_LOCAL_OBSERVATION_ONLY",
            "BLOCKED_AND_MISSING_SOURCE_ROWS_RETAINED; NO_AUTOMATIC_PROMOTION",
            "QUOTE_ALWAYS_NULL_UNTIL_SEPARATELY_AUTHENTICATED_SOURCE_JOIN",
        ],
    }
    return out, summary


def _load(path):
    raw = safe_path(path).read_bytes()
    try:
        obj = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs,
                         parse_constant=_bad_constant)
    except (UnicodeError, ValueError) as exc:
        raise Hold("INVALID_OR_DUPLICATE_JSON_SOURCE") from exc
    return obj, hashlib.sha256(raw).hexdigest()


def run(board_path, final_path, *, ledger_path, audit_path):
    src_paths = [safe_path(board_path), safe_path(final_path)]
    out_paths = [safe_path(ledger_path), safe_path(audit_path)]
    if len(set(src_paths + out_paths)) != 4:
        raise Hold("SOURCE_OR_OUTPUT_PATH_COLLISION")
    if any(x.exists() for x in out_paths):
        raise FileExistsError("CREATE_ONLY_OUTPUT_EXISTS")
    # Shared private directory; one finished pair or neither output. No writes
    # to historical board, original finals, or captured provider response.
    if out_paths[0].parent != out_paths[1].parent:
        raise Hold("OUTPUTS_MUST_SHARE_PRIVATE_DIRECTORY")
    _private_directory(out_paths[0].parent)
    b, bsha = _load(src_paths[0])
    f, fsha = _load(src_paths[1])
    ledger, report = reconcile(b, f)
    report["original_frozen_board_file_sha256"] = bsha
    report["original_final_receipt_file_sha256"] = fsha
    ledger_bytes = (json.dumps(ledger, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    report["ledger_sha256"] = hashlib.sha256(ledger_bytes).hexdigest()
    report_bytes = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    _private_create(out_paths[0], ledger_bytes)
    try:
        _private_create(out_paths[1], report_bytes)
    except BaseException:
        out_paths[0].unlink(missing_ok=True)
        raise
    return {"status": report["status"], "ledger_path": str(out_paths[0]),
            "audit_path": str(out_paths[1]), "matched_rows": report["matched_rows"],
            "total_rows": report["ledger_rows"], "approved_stake_u": 0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frozen-board", required=True)
    p.add_argument("--finals", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--audit", required=True)
    args = p.parse_args(argv)
    print(json.dumps(run(args.frozen_board, args.finals,
                         ledger_path=args.ledger, audit_path=args.audit),
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
