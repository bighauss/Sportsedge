"""Read-only forensic top-edge census. NEVER promotes, bets, trains or rewrites.

Input two PRIVATE original-compatible JSON files outside the Git checkout:
  claims: {"schema": CLAIM_SCHEMA, "rows": [{... original saved claim ...}]}
  finals: {"schema": FINAL_SCHEMA, "rows": [{... independently collected final ...}]}
Every claim is counted even when it fails evidence verification. Ranking uses
ONLY the pregame SAVED claimed EV (never actual results or postgame refits).
Local SHA paths and user-supplied timestamps are NOT sportsbook attestation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat

CLAIM_SCHEMA = "sportsedge-original-claim-census-v1"
FINAL_SCHEMA = "sportsedge-independent-final-overlay-v1"
REPORT_SCHEMA = "sportsedge-top20-forensic-evidence-v1"
ROOT = Path(__file__).resolve().parents[2]
HASH = re.compile(r"^[a-f0-9]{64}$")
SPORTS = {"NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"}
MARKETS = {"ML", "SPREAD", "TOTAL", "TEAM_TOTAL"}
PERIODS = {"FG", "1H", "2H", "1Q", "2Q", "3Q", "4Q"}
MAX_BYTES = 12 * 1024 * 1024
MAX_ROWS = 100000

class EvidenceError(ValueError):
    pass


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def _finite_json_float(s):
    f = float(s)
    if not math.isfinite(f):
        raise EvidenceError("NONFINITE_JSON_NUMBER")
    return f


def _parse(raw, schema):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise EvidenceError("INVALID_OR_OVERSIZED_ORIGINAL_BYTES")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                            parse_constant=lambda x: (_ for _ in ()).throw(EvidenceError("NONFINITE_JSON_LITERAL")),
                            parse_float=_finite_json_float)
    except EvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise EvidenceError("INVALID_ORIGINAL_JSON") from exc
    if not isinstance(result, dict) or set(result) != {"schema", "rows"} or result["schema"] != schema:
        raise EvidenceError("INVALID_SOURCE_SCHEMA")
    if not isinstance(result["rows"], list) or len(result["rows"]) > MAX_ROWS:
        raise EvidenceError("INVALID_ORIGINAL_ROW_POPULATION")
    return result["rows"]


def _time(v):
    if not isinstance(v, str) or not v or not (v.endswith("Z") or v.endswith("+00:00")):
        return None
    try:
        x = datetime.fromisoformat(v[:-1] + "+00:00" if v.endswith("Z") else v)
    except ValueError:
        return None
    return x if x.utcoffset() == timezone.utc.utcoffset(x) else None


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    if len(str(v)) > 64:
        return None
    try:
        x = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return x if x.is_finite() else None


def _hash_ok(v):
    return isinstance(v, str) and bool(HASH.fullmatch(v))


def _price(v):
    if type(v) is not int or not 100 <= abs(v) <= 100000:
        return None
    return Decimal(1) + (Decimal(v) / 100 if v > 0 else Decimal(100) / abs(v))


def _key(v):
    if not isinstance(v, str) or not v.strip() or len(v) > 128:
        return None
    return v.strip()


def _safe(v):
    return str(v).strip() if v is not None else ""


def _selection_id(row):
    """Keep team/participant/period/line; 1H and FG or two TT teams differ."""
    market = _safe(row.get("market")).upper()
    line = _num(row.get("line")) if market != "ML" else Decimal(0)
    if line is not None:
        line = format(line.normalize(), "f")
    return (
        _safe(row.get("sport")).upper(), _safe(row.get("event_id")),
        _safe(row.get("period")).upper(), market, _safe(row.get("side")).upper(),
        line, _safe(row.get("team_id")), _safe(row.get("player_id")),
    )


def _finals_index(rows):
    out, duplicate = {}, set()
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError("MALFORMED_FINAL_ROW")
        key = (_safe(row.get("sport")).upper(), _safe(row.get("event_id")))
        if not all(key):
            raise EvidenceError("MISSING_FINAL_EVENT_IDENTITY")
        if key in out:
            duplicate.add(key)
        out[key] = row
    return out, duplicate


def _score(final, field, flags):
    n = final.get(field)
    if type(n) is not int or not 0 <= n <= 500:
        flags.append("MISSING_OR_INVALID_RESULT:" + field)
        return None
    return Decimal(n)


def _settlement(row, final, flags):
    """Independent overlay. Results do not enter ranking or model p."""
    if final is None:
        flags.append("FINAL_NOT_SUPPLIED")
        return None
    if _safe(final.get("home_team_id")) != _safe(row.get("home_team_id")) or \
       _safe(final.get("away_team_id")) != _safe(row.get("away_team_id")) or \
       not _key(row.get("home_team_id")) or not _key(row.get("away_team_id")):
        flags.append("UNVERIFIED_TEAM_FINAL_BINDING")
        return None
    if _time(final.get("event_start_utc")) != _time(row.get("event_start_utc")):
        flags.append("FINAL_EVENT_START_MISMATCH")
        return None
    start, settled = _time(row.get("event_start_utc")), _time(final.get("settled_utc"))
    if not start or not settled or settled <= start:
        flags.append("FINAL_PUBLISHED_BEFORE_END_OR_BAD_CLOCK")
        return None
    if not _hash_ok(final.get("source_sha256")):
        flags.append("FINAL_SOURCE_HASH_MISSING")
    period = _safe(row.get("period")).upper()
    if period not in ("FG", "1H"):
        flags.append("PERIOD_RESULT_SCORES_UNAVAILABLE")
        return None
    hs = _score(final, "home_score" if period == "FG" else "home_1h", flags)
    as_ = _score(final, "away_score" if period == "FG" else "away_1h", flags)
    if hs is None or as_ is None:
        return None
    market = _safe(row.get("market")).upper()
    side = _safe(row.get("side")).upper()
    line = _num(row.get("line")) if market != "ML" else None
    if market == "ML":
        if side not in ("HOME", "AWAY"):
            flags.append("INVALID_SIDE_FOR_MONEYLINE")
            return None
        cmp = hs-as_ if side == "HOME" else as_-hs
    elif market == "SPREAD":
        if side not in ("HOME", "AWAY") or line is None:
            flags.append("INVALID_SIDE_OR_SPREAD_LINE")
            return None
        cmp = (hs-as_ if side == "HOME" else as_-hs) + line
    elif market == "TOTAL":
        if side not in ("OVER", "UNDER") or line is None:
            flags.append("INVALID_TOTAL_SIDE_OR_LINE")
            return None
        cmp = (hs+as_)-line
        if side == "UNDER":
            cmp = -cmp
    elif market == "TEAM_TOTAL":
        if side not in ("OVER", "UNDER") or line is None:
            flags.append("INVALID_TEAM_TOTAL_SIDE_OR_LINE")
            return None
        team = _safe(row.get("team_id"))
        if team not in (row.get("home_team_id"), row.get("away_team_id")):
            flags.append("TEAM_TOTAL_TEAM_ID_NOT_BOUND_TO_EVENT")
            return None
        score = hs if team == row.get("home_team_id") else as_
        cmp = score-line
        if side == "UNDER":
            cmp = -cmp
    else:
        flags.append("MARKET_SETTLEMENT_UNSUPPORTED")
        return None
    return "W" if cmp > 0 else ("L" if cmp < 0 else "P")


def _claimed_ev_math(row, flags):
    odds = _price(row.get("price_american"))
    p = _num(row.get("p_model"))
    claimed = _num(row.get("saved_claimed_ev"))
    if odds is None:
        flags.append("INVALID_AMERICAN_ODDS")
    if p is None or not Decimal(0) < p < Decimal(1):
        flags.append("INVALID_OR_MISSING_PREMATCH_MODEL_PROBABILITY")
    if claimed is None:
        flags.append("MISSING_ORIGINAL_SAVED_CLAIMED_EV")
    elif not Decimal("-1") <= claimed <= Decimal("1000"):
        flags.append("SAVED_CLAIMED_EV_OUT_OF_RANGE")
        claimed = None
    if odds is None or p is None or not Decimal(0) < p < Decimal(1):
        return claimed, None, None
    implied = Decimal(1)/odds
    return claimed, p * odds - 1, implied


def _validate_claim(row, finals, *, max_quote_age_seconds, disagreement_points):
    flags = []
    if not isinstance(row, dict):
        return {"flags": ["INVALID_CLAIM_TYPE"], "reported_ev": None,
                "raw_implied_probability": None, "raw_binary_ev": None,
                "corrected_grade": None, "event_key": None, "identity": None}
    sport = _safe(row.get("sport")).upper()
    if sport not in SPORTS:
        flags.append("UNKNOWN_SPORT")
    event_id = _key(row.get("event_id"))
    if not event_id:
        flags.append("MISSING_EVENT_ID")
    market = _safe(row.get("market")).upper()
    period = _safe(row.get("period")).upper()
    if market not in MARKETS:
        flags.append("UNSUPPORTED_MARKET_SETTLEMENT")
    if period not in PERIODS:
        flags.append("UNSUPPORTED_PERIOD")
    if not _key(row.get("book")):
        flags.append("BOOK_ID_MISSING")
    if not _key(row.get("provider_market_id")):
        flags.append("PROVIDER_MARKET_ID_MISSING")
    if not _key(row.get("provider_event_id")):
        flags.append("PROVIDER_EVENT_ID_MISSING")
    if market == "TEAM_TOTAL" and not _key(row.get("team_id")):
        flags.append("TEAM_TOTAL_TEAM_ID_MISSING")
    if market not in MARKETS and not _key(row.get("player_id")):
        flags.append("UNSUPPORTED_PROP_OR_PLAYER_MAPPING")
    if not _hash_ok(row.get("model_sha256")):
        flags.append("FROZEN_MODEL_HASH_MISSING")
    if not _hash_ok(row.get("model_input_sha256")):
        flags.append("FROZEN_MODEL_INPUT_HASH_MISSING")
    if not _hash_ok(row.get("original_quote_sha256")):
        flags.append("ORIGINAL_BOOK_QUOTE_BYTES_HASH_MISSING")
    if not _key(row.get("upstream_book_id")) or not _key(row.get("source_transport_id")):
        flags.append("UPSTREAM_BOOK_OR_TRANSPORT_LINEAGE_MISSING")
    # Original receipt hash / self-reported timestamps are evidence of LOCAL
    # data integrity only, not third-party signed market attestation.
    flags.append("ORIGINAL_PROVIDER_BOOK_ATTESTATION_UNVERIFIED")
    times = {k: _time(row.get(k)) for k in (
        "event_start_utc", "model_frozen_utc", "quote_captured_utc",
        "quote_published_utc", "selected_utc", "model_features_published_utc",
        "model_features_available_utc", "fitted_until_utc")}
    for name, value in times.items():
        if value is None:
            flags.append("MISSING_OR_INVALID_UTC:" + name)
    start, frozen, captured, published, selected, features_pub, features_avail, fitted = (
        times[k] for k in (
            "event_start_utc", "model_frozen_utc", "quote_captured_utc",
            "quote_published_utc", "selected_utc", "model_features_published_utc",
            "model_features_available_utc", "fitted_until_utc"))
    if start and frozen and frozen >= start:
        flags.append("MODEL_NOT_FROZEN_BEFORE_EVENT")
    if start and captured and captured >= start:
        flags.append("QUOTE_CAPTURE_NOT_PREGAME")
    if start and selected and selected >= start:
        flags.append("PICK_SELECTED_AFTER_START")
    if published and captured and published > captured:
        flags.append("BOOK_QUOTE_PUBLICATION_AFTER_CAPTURE")
    if captured and selected:
        if captured > selected:
            flags.append("QUOTE_CAPTURE_AFTER_PICK")
        elif (selected-captured).total_seconds() > max_quote_age_seconds:
            flags.append("QUOTE_STALE_AT_DECISION")
    if frozen and selected and frozen > selected:
        flags.append("MODEL_FROZEN_AFTER_PICK")
    if frozen and features_pub and features_pub > frozen:
        flags.append("FEATURE_PUBLISHED_AFTER_FORECAST_FREEZE")
    if frozen and features_avail and features_avail > frozen:
        flags.append("FEATURE_AVAILABLE_AFTER_FORECAST_FREEZE")
    if frozen and fitted and fitted >= frozen:
        flags.append("MODEL_FIT_NOT_BEFORE_FREEZE")
    claimed, binary_ev, implied = _claimed_ev_math(row, flags)
    line = _num(row.get("line"))
    if market == "ML" and line not in (None, Decimal(0)):
        flags.append("MONEYLINE_CANNOT_HAVE_POINT_LINE")
    if market in ("TOTAL", "TEAM_TOTAL") and line is not None and line < 0:
        flags.append("IMPOSSIBLE_NEGATIVE_SCORE_TOTAL_LINE")
    if market != "ML" and line is None:
        flags.append("MISSING_MARKET_LINE")
    if market == "ML" and period != "FG" or (market != "ML" and line is not None and line % 1 == 0):
        # Conditional P(win|not push) cannot verify unconditional EV. The
        # original win/loss/tie masses must be saved. Don't misdiagnose.
        pw, pl = _num(row.get("p_win_unconditional")), _num(row.get("p_loss_unconditional"))
        if pw is None or pl is None or pw < 0 or pl < 0 or pw+pl > 1:
            flags.append("PUSH_AWARE_ORIGINAL_WIN_LOSS_MASSES_MISSING")
        elif binary_ev is not None and claimed is not None:
            actual_ev = pw * (_price(row.get("price_american"))-1) - pl
            if abs(actual_ev-claimed) > Decimal("0.015"):
                flags.append("PUSH_AWARE_CLAIMED_EV_MISMATCH")
    elif binary_ev is not None and claimed is not None and abs(binary_ev-claimed) > Decimal("0.015"):
        flags.append("CLAIMED_EV_BINARY_ARITHMETIC_MISMATCH")
    for a, b, tag in (("model_home_margin", "book_home_main_spread", "MARGIN"),
                      ("model_game_total", "book_game_main_total", "GAME_TOTAL"),
                      ("model_team_total", "book_team_main_total", "TEAM_TOTAL")):
        aa, bb = _num(row.get(a)), _num(row.get(b))
        if aa is not None and bb is not None:
            # Home favorite spread -11.5 corresponds to home margin +11.5.
            gap = aa+bb if tag == "MARGIN" else aa-bb
            if abs(gap) >= Decimal(str(disagreement_points)):
                flags.append("SAVED_MODEL_MARKET_6PT_DISAGREEMENT:" + tag)
        elif a in row or b in row:
            flags.append("MISSING_PAIRED_MARKET_ANCHOR:" + tag)
    event_key = (sport, event_id) if event_id else None
    corrected = _settlement(row, finals.get(event_key), flags) if event_key else None
    old = _safe(row.get("historical_grade")).upper()
    if old and old not in ("W", "L", "P", "UNSETTLED", "UNKNOWN"):
        flags.append("INVALID_HISTORICAL_GRADE")
    if corrected and old in ("W", "L", "P") and corrected != old:
        flags.append("HISTORICAL_GRADING_DISAGREEMENT_G18_OR_OTHER")
    # Never count this as certified—even complete text hashes cannot prove an
    # external quote originated from the claimed book.
    return {
        "event_key": event_key,
        "identity": _selection_id(row),
        "sport": sport, "event_id": event_id,
        "market": market, "period": period,
        "line": row.get("line"), "side": row.get("side"),
        "price_american": row.get("price_american"),
        "model_probability": float(_num(row.get("p_model"))) if _num(row.get("p_model")) is not None and 0 < _num(row.get("p_model")) < 1 else None,
        "reported_ev": float(claimed) if claimed is not None else None,
        "raw_implied_probability": float(implied) if implied is not None else None,
        "raw_binary_ev": float(binary_ev) if binary_ev is not None else None,
        "historical_grade": old or None, "corrected_grade": corrected,
        "flags": sorted(set(flags)), "official_counted": 0,
        "approved_stake_u": 0,
    }


def audit(claim_bytes, final_bytes, *, top_n=20, max_quote_age_seconds=300,
          disagreement_points=6):
    if not (isinstance(top_n, int) and not isinstance(top_n, bool) and 1 <= top_n <= 500):
        raise EvidenceError("INVALID_TOP_N")
    if not (isinstance(max_quote_age_seconds, int) and not isinstance(max_quote_age_seconds, bool)
            and 1 <= max_quote_age_seconds <= 86400):
        raise EvidenceError("INVALID_MAX_QUOTE_AGE")
    if not (type(disagreement_points) in (int, float) and 0 < disagreement_points <= 100):
        raise EvidenceError("INVALID_DISAGREEMENT_THRESHOLD")
    claims = _parse(claim_bytes, CLAIM_SCHEMA)
    final_rows = _parse(final_bytes, FINAL_SCHEMA)
    finals, duplicated_finals = _finals_index(final_rows)
    result = [_validate_claim(row, finals, max_quote_age_seconds=max_quote_age_seconds,
                              disagreement_points=disagreement_points)
              for row in claims]
    identities = Counter(_selection_id(row) for row in claims if isinstance(row, dict))
    flags = Counter()
    for r in result:
        if r["identity"] in identities and identities[r["identity"]] > 1:
            r["flags"] = sorted(set(r["flags"] + ["DUPLICATE_CLAIM_IDENTITY_ALL_COPIES_HELD"]))
        if r["event_key"] in duplicated_finals:
            r["flags"] = sorted(set(r["flags"] + ["DUPLICATE_FINALS_NOT_CANONICAL"]))
            r["corrected_grade"] = None
        flags.update(r["flags"])
    # The rank is the ORIGINAL saved claimed EV, not a new calibrated
    # probability, a corrected historical forecast or an outcome sort.
    rankable = [(i, r) for i, r in enumerate(result) if r["reported_ev"] is not None]
    rankable.sort(key=lambda t: (-t[1]["reported_ev"], t[0]))
    selected = [r for _, r in rankable[:top_n]]
    by_event = Counter(tuple(r["event_key"]) for r in selected if r["event_key"] is not None)
    for r in selected:
        r["correlated_claims_in_same_event_top_n"] = by_event.get(tuple(r["event_key"]), 0) if r["event_key"] else 0
    return {
        "schema": REPORT_SCHEMA,
        "status": "FORENSIC_RESEARCH_ONLY_UNVERIFIED_PAPER_0U",
        "claim_source_sha256": sha256(claim_bytes).hexdigest(),
        "final_source_sha256": sha256(final_bytes).hexdigest(),
        "claimed_rows_total": len(claims), "rankable_pregame_ev_claims": len(rankable),
        "missing_saved_ev_rows": len(claims)-len(rankable),
        "flagged_all_original_rows": sum(bool(r["flags"]) for r in result),
        "top_claims_count": len(selected), "top_distinct_events": len(by_event),
        "top_event_cluster_sizes": [{"sport": k[0], "event_id": k[1], "rows": n}
                                    for k, n in sorted(by_event.items())],
        "top_claims": selected,
        "flag_count_all_rows": dict(sorted(flags.items())),
        "all_original_claims_retained": result,
        "original_data_modified": False,
        "historical_grades_modified": False,
        "source_bookmaker_authentication_verified": False,
        "future_model_calibration_validated": False,
        "approved_stake_u": 0, "official_counted": 0,
        "note": "Row hashes and self-reported timestamps do not verify original book identity. Rankings include flagged rows; no retrospectively filtered profit claim.",
    }


def _private_path(path, *, source):
    lexical = Path(os.path.abspath(os.fspath(path)))
    resolved = lexical.resolve()
    for part in (lexical, resolved):
        if part == ROOT or ROOT in part.parents:
            raise EvidenceError("PRIVATE_AUDIT_FILES_REQUIRED_OUTSIDE_PUBLIC_REPO")
    if any(candidate.is_symlink() for candidate in (lexical, *lexical.parents)):
        raise EvidenceError("SYMLINK_AUDIT_PATH_FORBIDDEN")
    if not lexical.parent.is_dir() or lexical.parent.stat().st_mode & 0o077:
        raise EvidenceError("PRIVATE_PARENT_DIRECTORY_0700_REQUIRED")
    if source:
        if not lexical.is_file() or lexical.stat().st_mode & 0o077:
            raise EvidenceError("PRIVATE_ORIGINAL_FILE_0600_REQUIRED")
    elif lexical.exists():
        raise FileExistsError("CREATE_ONLY_AUDIT_REPORT_ALREADY_EXISTS")
    return lexical


def _read_private(path):
    p = _private_path(path, source=True)
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > MAX_BYTES:
            raise EvidenceError("ORIGINAL_SOURCE_FD_INVALID_OR_EXPOSED")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            data = f.read(MAX_BYTES+1)
        if not 0 < len(data) <= MAX_BYTES:
            raise EvidenceError("ORIGINAL_SOURCE_BYTES_OVERSIZED")
        return data
    finally:
        if fd >= 0:
            os.close(fd)


def audit_files(claims_path, finals_path, output_path, *, top_n=20):
    paths = [_private_path(p, source=k) for p, k in
             ((claims_path, True), (finals_path, True), (output_path, False))]
    if len({str(p.resolve()) for p in paths}) != 3:
        raise EvidenceError("SOURCE_AND_REPORT_PATHS_MUST_BE_DISTINCT")
    report = audit(_read_private(paths[0]), _read_private(paths[1]), top_n=top_n)
    raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    flags = os.O_WRONLY | os.O_EXCL | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(paths[2], flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            fd = -1
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        paths[2].unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_original_claims_json")
    parser.add_argument("private_separate_final_results_json")
    parser.add_argument("--private-report", required=True)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)
    r = audit_files(args.private_original_claims_json,
                    args.private_separate_final_results_json,
                    args.private_report, top_n=args.top)
    print(json.dumps({"status": r["status"], "total": r["claimed_rows_total"],
                      "top": r["top_claims_count"], "events": r["top_distinct_events"],
                      "approved_stake_u": 0}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())