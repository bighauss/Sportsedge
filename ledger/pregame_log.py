"""Shared append-only PREGAME prediction log, schema v2 (hash-chained JSONL). PAPER / 0u.

Schema-first so CBB, CFB and NFL runners plug in the same way. One row per EVALUATED
selection -- SELECTED, REJECTED (with reason) and WITHHELD (with reason) -- so the full
denominator survives, not just +EV plays. Rows are frozen before game start and never
edited. Outcomes go to a SEPARATE append-only results log via grade_log(), which calls
sportsedge.grading.settlement.settle(); pregame rows are never mutated.

Validation on append (all-or-nothing): prediction or quote capture at/after game start,
duplicate selection ids, malformed probabilities (win+push+loss must be 1), prices, lines
or timestamps. read() re-verifies every hash link, so tampering or deleted rows raise.

export_harness() joins pregame rows to results and writes the exact CSV consumed by
research/backtest_harness/harness.py.
"""
from __future__ import annotations
import csv, hashlib, json, math, os
from datetime import datetime

SCHEMA = "sportsedge-pregame-prediction-log-v2"
RESULTS_SCHEMA = "sportsedge-pregame-results-v1"
GENESIS = "0" * 64
STATES = ("SELECTED", "REJECTED", "WITHHELD")
FIELDS = (
    # identity
    "sport", "event_id", "team", "player_id", "player_name", "market", "period", "selection",
    # timing
    "quote_captured_utc", "prediction_utc", "game_start_utc",
    # DraftKings
    "book", "line", "price", "opp_price", "novig_p",
    # model
    "projection", "distribution_id", "win_p", "push_p", "loss_p", "raw_ev", "adj_ev", "adj_ev_method",
    # versioning
    "model_version", "model_commit_sha", "model_code_sha256", "config_sha256", "source_provenance",
    # selection
    "selection_state", "rejection_reason",
)
ID_FIELDS = ("sport", "event_id", "team", "player_id", "market", "period", "selection", "line", "model_version")
HARNESS_COLUMNS = ["event_id", "date", "market", "selection", "line", "model_p", "push_p",
                   "price", "opp_price", "outcome"]


class LogError(ValueError):
    pass


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_of(obj):
    return hashlib.sha256(canon(obj).encode()).hexdigest()


def _utc(s, f):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise LogError("BAD_UTC:" + f)
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError as e:
        raise LogError("BAD_UTC:" + f) from e


def _text(v, f, optional=False):
    if v is None and optional:
        return
    if not isinstance(v, str) or not v.strip():
        raise LogError("BAD_TEXT:" + f)


def _real(v, f, optional=False, lo=None, hi=None):
    if v is None and optional:
        return
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise LogError("BAD_NUMBER:" + f)
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise LogError("OUT_OF_RANGE:" + f)


def selection_id(r):
    return sha256_of([r.get(k) if k != "line" or r.get(k) is None else float(r[k]) for k in ID_FIELDS])[:32]


def validate(r):
    if not isinstance(r, dict) or set(r) != set(FIELDS):
        raise LogError("FIELDS_MISMATCH")
    for f in ("sport", "event_id", "market", "period", "selection", "book", "model_version",
              "model_commit_sha", "model_code_sha256", "config_sha256", "distribution_id", "adj_ev_method"):
        _text(r[f], f)
    for f in ("team", "player_id", "player_name"):
        _text(r[f], f, optional=True)
    if not isinstance(r["source_provenance"], dict) or not r["source_provenance"]:
        raise LogError("SOURCE_PROVENANCE_REQUIRED")
    canon(r["source_provenance"])
    if r["selection_state"] not in STATES:
        raise LogError("BAD_SELECTION_STATE")
    if r["selection_state"] == "SELECTED":
        if r["rejection_reason"] is not None:
            raise LogError("SELECTED_WITH_REJECTION_REASON")
    else:
        _text(r["rejection_reason"], "rejection_reason")
    start = _utc(r["game_start_utc"], "game_start_utc")
    if _utc(r["prediction_utc"], "prediction_utc") >= start:
        raise LogError("PREDICTION_NOT_PREGAME")
    _real(r["line"], "line", optional=True)
    _real(r["projection"], "projection", optional=True)
    priced = r["selection_state"] != "WITHHELD"
    if r["quote_captured_utc"] is not None and _utc(r["quote_captured_utc"], "quote_captured_utc") >= start:
        raise LogError("QUOTE_NOT_PREGAME")
    if not priced:
        for f in ("win_p", "push_p", "loss_p", "novig_p"):
            _real(r[f], f, optional=True, lo=0, hi=1)
        return r
    if r["quote_captured_utc"] is None:
        raise LogError("QUOTE_CAPTURE_REQUIRED")
    for f in ("win_p", "push_p", "loss_p", "novig_p"):
        _real(r[f], f, lo=0, hi=1)
    if abs(r["win_p"] + r["push_p"] + r["loss_p"] - 1) > 1e-9:
        raise LogError("PROBABILITIES_MUST_SUM_TO_ONE")
    for f in ("price", "opp_price"):
        v = r[f]
        if isinstance(v, bool) or not isinstance(v, int) or abs(v) < 100:
            raise LogError("BAD_AMERICAN_PRICE:" + f)
    _real(r["raw_ev"], "raw_ev")
    _real(r["adj_ev"], "adj_ev", optional=True)
    if r["adj_ev"] is None and r["adj_ev_method"] != "NOT_COMPUTED":
        raise LogError("ADJ_EV_METHOD_MUST_SAY_NOT_COMPUTED")
    return r


def _read_chain(path, schema, check_row):
    out, prev = [], GENESIS
    if not os.path.exists(path):
        return out, prev
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            try:
                e = json.loads(line)
            except ValueError as ex:
                raise LogError(f"MALFORMED_LINE:{n}") from ex
            if not isinstance(e, dict) or set(e) != {"schema", "seq", "prev_sha256", "row", "sha256"} \
                    or e["schema"] != schema:
                raise LogError(f"BAD_ENTRY:{n}")
            if e["seq"] != n or e["prev_sha256"] != prev:
                raise LogError(f"CHAIN_BROKEN:{n}")
            if sha256_of({k: e[k] for k in ("schema", "seq", "prev_sha256", "row")}) != e["sha256"]:
                raise LogError(f"TAMPERED:{n}")
            check_row(e["row"]); out.append(e["row"]); prev = e["sha256"]
    return out, prev


def _append_chain(path, schema, prev, seq, rows):
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            seq += 1
            body = {"schema": schema, "seq": seq, "prev_sha256": prev, "row": r}
            prev = sha256_of(body)
            f.write(canon({**body, "sha256": prev}) + "\n")
    return seq, prev


def read(path):
    return _read_chain(path, SCHEMA, validate)[0]


def append(path, rows):
    existing, prev = _read_chain(path, SCHEMA, validate)
    seen = {selection_id(r) for r in existing}
    batch = []
    for r in rows:
        validate(r)
        sid = selection_id(r)
        if sid in seen:
            raise LogError("DUPLICATE_SELECTION:" + sid)
        seen.add(sid); batch.append(r)
    seq, head = _append_chain(path, SCHEMA, prev, len(existing), batch)
    return {"appended": len(batch), "total": seq, "head_sha256": head}


# ---------------------------------------------------------------- results (separate file)
def _check_result(r):
    if not isinstance(r, dict) or set(r) != {"selection_id", "outcome", "settlement_reason",
                                             "research_pnl_units", "graded_value", "grade_selection_sha256",
                                             "event_result_sha256", "settled_utc", "state"}:
        raise LogError("RESULT_FIELDS_MISMATCH")
    if r["outcome"] not in ("W", "L", "P", "VOID", "UNGRADED") or r["state"] != "PAPER_0U_NON_COUNTED":
        raise LogError("BAD_RESULT")


def read_results(path):
    return _read_chain(path, RESULTS_SCHEMA, _check_result)[0]


def grade_log(log_path, results_path, events, players=None, settled_utc=None):
    """Settle every not-yet-final pregame row via settlement.settle(); append results only.

    events: {event_id: event dict for settle()}. players: {event_id: players dict}.
    UNGRADED rows may be re-graded later; a final outcome (W/L/P/VOID) is written once.
    """
    from sportsedge.grading.settlement import settle
    rows = read(log_path)
    prior, prev = _read_chain(results_path, RESULTS_SCHEMA, _check_result)
    final = {r["selection_id"] for r in prior if r["outcome"] != "UNGRADED"}
    new = []
    census = {"graded": 0, "ungraded": 0, "already_final": 0, "no_event": 0, "withheld_skipped": 0}
    for r in rows:
        sid = selection_id(r)
        if r["selection_state"] == "WITHHELD":
            census["withheld_skipped"] += 1; continue
        if sid in final:
            census["already_final"] += 1; continue
        ev = events.get(r["event_id"])
        if ev is None:
            census["no_event"] += 1; continue
        sel = {"event_id": r["event_id"], "market": r["market"], "period": r["period"],
               "side": r["selection"], "line": r["line"], "price": r["price"],
               "team": r["team"], "player_id": r["player_id"]}
        g = settle(sel, ev, (players or {}).get(r["event_id"]))
        new.append({"selection_id": sid, "outcome": g.result, "settlement_reason": g.reason,
                    "research_pnl_units": g.profit_units, "graded_value": g.graded_value,
                    "grade_selection_sha256": g.selection_sha256,
                    "event_result_sha256": sha256_of(json.loads(json.dumps(ev, default=str))),
                    "settled_utc": settled_utc, "state": "PAPER_0U_NON_COUNTED"})
        census["graded" if g.result != "UNGRADED" else "ungraded"] += 1
    for r in new:
        _check_result(r)
    _append_chain(results_path, RESULTS_SCHEMA, prev, len(prior), new)
    return census


def export_harness(log_path, results_path, out_csv):
    """Latest final result per selection, joined to its pregame row. VOID is passed as V."""
    rows = read(log_path)
    latest = {}
    for r in read_results(results_path):
        latest[r["selection_id"]] = r["outcome"]
    census = {"exported": 0, "withheld_not_exported": 0, "ungraded": 0}
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, HARNESS_COLUMNS); w.writeheader()
        for r in rows:
            if r["selection_state"] == "WITHHELD":
                census["withheld_not_exported"] += 1; continue
            o = latest.get(selection_id(r))
            if o not in ("W", "L", "P", "VOID"):
                census["ungraded"] += 1; continue
            w.writerow({"event_id": r["event_id"], "date": r["game_start_utc"][:10],
                        "market": f'{r["sport"]}:{r["market"]}:{r["period"]}',
                        "selection": r["selection"] if r["player_id"] is None else f'{r["player_id"]}:{r["selection"]}',
                        "line": "" if r["line"] is None else r["line"], "model_p": r["win_p"],
                        "push_p": r["push_p"], "price": r["price"], "opp_price": r["opp_price"],
                        "outcome": "V" if o == "VOID" else o})
            census["exported"] += 1
    return census


# ---------------------------------------------------------------- CBB adapter
def _commit_sha():
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    try:
        import subprocess
        return subprocess.check_output(["git", "-C", os.path.dirname(os.path.abspath(__file__)), "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip() or "UNAVAILABLE"
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def rows_from_cbb_card(card, names, extra=None, commit_sha=None):
    """Every CBB market on the frozen card (priced, rejected or withheld). Reads frozen values only."""
    extra = extra or {}
    cfg = extra.get("config") or {}
    cfg_sha = sha256_of(json.loads(json.dumps(cfg, default=str)))
    rr = card.get("ratings_receipt") or {}
    prov = {"card_sha256": card.get("card_sha256"), "input_sha256": card.get("input_sha256"),
            "ratings_receipt_sha256": rr.get("sha256") if isinstance(rr, dict) else None}
    base = {"sport": "CBB", "team": None, "player_id": None, "player_name": None, "period": "FG",
            "prediction_utc": card["freeze_utc"], "model_version": card["model_version"],
            "model_commit_sha": commit_sha or _commit_sha(),
            "model_code_sha256": card.get("model_code_sha256") or "UNAVAILABLE",
            "config_sha256": cfg_sha, "source_provenance": prov,
            "adj_ev": None, "adj_ev_method": "NOT_COMPUTED"}
    out = []

    def state(ev, excluded):
        if excluded:
            return "REJECTED", "BLOWOUT_EXCLUDED"
        return ("SELECTED", None) if ev > 0 else ("REJECTED", "NONPOSITIVE_RAW_EV")

    for r in card["rows"]:
        start = r.get("tipoff_utc") or names.get(r["game_id"], (None, None, None))[2]
        pj = r.get("projection") or {}
        dist = (f"normal(margin_sd={pj.get('sd_margin')},total_sd={pj.get('sd_total')},"
                f"basis={pj.get('sd_basis')})") if pj else "NONE"
        for m in r["markets"]:
            proj = pj.get("total") if m["market"] == "total" else pj.get("margin")
            if m["status"] != "PRICED_PAPER":
                q = m.get("quote") or {}
                for side in (("over", "under") if m["market"] == "total" else ("home", "away")):
                    out.append({**base, "event_id": str(r["game_id"]), "market": m["market"], "selection": side,
                                "quote_captured_utc": q.get("captured_utc"), "game_start_utc": start,
                                "book": q.get("book") or "DraftKings", "line": q.get("line"),
                                "price": None, "opp_price": None, "novig_p": None, "projection": proj,
                                "distribution_id": dist, "win_p": None, "push_p": None, "loss_p": None,
                                "raw_ev": None, "selection_state": "WITHHELD",
                                "rejection_reason": str(m.get("pass_reason") or m["status"])})
                continue
            q = m["quote"]; prices = (int(q["price_a"]), int(q["price_b"]))
            for i, side in enumerate(m["sides"]):
                other = m["sides"][1 - i]
                line = q["line"]
                if line is not None and m["market"] == "spread" and side == "away":
                    line = -line
                ev = m["paper_ev_per_1u_at_price"][side]
                st, why = state(ev, m.get("blowout_excluded"))
                out.append({**base, "event_id": str(r["game_id"]), "market": m["market"], "selection": side,
                            "quote_captured_utc": q["captured_utc"], "game_start_utc": start,
                            "book": q["book"], "line": line, "price": prices[i], "opp_price": prices[1 - i],
                            "novig_p": m["market_novig_prob"][side], "projection": proj,
                            "distribution_id": dist, "win_p": m["model_prob"][side],
                            "push_p": m["model_prob"]["push"], "loss_p": m["model_prob"][other],
                            "raw_ev": ev, "selection_state": st, "rejection_reason": why})
    for m in extra.get("ladders", []):
        start = names.get(m["game_id"], (None, None, None))[2]
        for i, side in enumerate(m["sides"]):
            line = -m["line"] if m["kind"] == "alt_spread" and side == "away" else m["line"]
            st, why = state(m["paper_ev"][i], m["blowout_excluded"])
            win, push = m["model_prob"][i], m["push"]
            out.append({**base, "event_id": str(m["game_id"]), "market": m["kind"], "selection": side,
                        "quote_captured_utc": m["captured_utc"], "game_start_utc": start, "book": "DraftKings",
                        "line": line, "price": int(m["price"][i]), "opp_price": int(m["price"][1 - i]),
                        "novig_p": m["market_novig"][i], "projection": None, "distribution_id": "ladder",
                        "win_p": win, "push_p": push, "loss_p": max(0.0, 1 - win - push),
                        "raw_ev": m["paper_ev"][i], "selection_state": st, "rejection_reason": why})
    return out
