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
from datetime import datetime, timezone

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


# ---------------------------------------------------------------- CFB / NFL adapters
def _z(ts):
    """ISO UTC (offset or Z) -> canonical Z string, or None."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        d = datetime.fromisoformat(ts[:-1] + "+00:00" if ts.endswith("Z") else ts)
    except ValueError:
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pairs(rows, key):
    """Map id(row) -> opposite row for two-way markets (exactly two priced sides per key)."""
    groups = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    opp = {}
    for g in groups.values():
        if len(g) == 2 and all(isinstance(x.get("odds"), int) for x in g):
            opp[id(g[0])], opp[id(g[1])] = g[1], g[0]
    return opp


def _priced_or_withheld(base, state, reason, opp, capture):
    """Schema requires both DK prices + capture time for a priced row; otherwise keep the
    model values but log WITHHELD with the original card state in the reason."""
    if opp is None:
        return "WITHHELD", f"ONE_SIDED_QUOTE_NO_OPPOSITE_PRICE (card_state={state}{':' + reason if reason else ''})"
    if capture is None:
        return "WITHHELD", f"QUOTE_CAPTURE_TIME_MISSING (card_state={state}{':' + reason if reason else ''})"
    return state, reason


def _cfb_canon(r, home_away):
    """CFB card row -> (market, period, selection, team, player) in settle() vocabulary."""
    home, away = home_away
    m, pick = r["market"], r["pick"]
    period = "H1" if m.startswith("1H") else "FG"
    base = m[3:] if m.startswith("1H ") else m
    if m.startswith("Prop "):
        stat = m[5:]
        for word, side in ((" Over ", "over"), (" Under ", "under")):
            if word in pick:
                return stat, "FG", side, None, pick.split(word, 1)[0]
        return None, None, None, None, None
    if base == "ML":
        if pick == home: return "moneyline", period, "home", None, None
        if pick == away: return "moneyline", period, "away", None, None
    if base == "Spread":
        if home and pick.startswith(home + " "): return "spread", period, "home", None, None
        if away and pick.startswith(away + " "): return "spread", period, "away", None, None
    if base == "Total":
        return "total", period, "over" if pick.startswith("Over") else "under", None, None
    if base.endswith(" TT"):
        t = base[:-3]
        team = "home" if t == home else "away" if t == away else None
        if team:
            return "team_total", period, "over" if pick.startswith("Over") else "under", team, None
    return None, None, None, None, None


def rows_from_cfb_run(card, projs, withheld, ctx, intake, now_utc, model_code_sha256, commit_sha=None):
    """Every evaluated CFB selection. Returns (rows, unloggable). Reads frozen run values only.

    Game markets use the legacy normal with a ZERO-push assumption (recorded in distribution_id).
    CFB legacy props are MARKET-ANCHORED (mean = 0.7 model + 0.3 market-implied) and are labelled so.
    """
    import sportsedge_cfb_model as M
    kick = {str(p["game"]["id"]): _z(p.get("kickoff_utc")) for p in projs}
    sides = {str(p["game"]["id"]): (p["home"], p["away"]) for p in projs}
    cap = _z(intake.get("captured_utc"))
    pred = _z(now_utc.isoformat())
    selected = {id(r) for r in card}
    allrows = ctx.get("priced_rows_all", [])
    opp = _pairs([r for r in allrows if not r["market"].startswith("Prop")],
                 lambda r: (r["gameId"], r["market"], None if r["line"] is None else abs(float(r["line"]))))
    cfg = {"P_BLEND_MODEL": M.P_BLEND_MODEL, "PROP_MODEL_W": M.PROP_MODEL_W,
           "SD_MARGIN": M.SD_MARGIN, "SD_TOTAL": M.SD_TOTAL, "SD_TT": M.SD_TT,
           "PROP_SD_FRAC": M.PROP_SD_FRAC}
    base = {"sport": "CFB", "team": None, "player_id": None, "player_name": None, "period": "FG",
            "prediction_utc": pred, "book": "DraftKings", "model_version": "cfb-run-it-legacy",
            "model_commit_sha": commit_sha or _commit_sha(), "model_code_sha256": model_code_sha256,
            "config_sha256": sha256_of(cfg),
            "source_provenance": {"lines_captured": str(intake.get("captured")), "captured_utc": cap},
            "adj_ev": None, "adj_ev_method": "NOT_COMPUTED"}
    out, unl = [], []
    for r in allrows:
        gid = str(r["gameId"])
        start = kick.get(gid)
        if start is None:
            unl.append((gid, r["market"], r["pick"], "NO_KICKOFF_TIME")); continue
        prop = r["market"].startswith("Prop")
        if id(r) in selected:
            st, why = "SELECTED", None
        else:
            st, why = "REJECTED", ("CONTRADICTS_PROJECTION" if M.contradicts(r) else "NONPOSITIVE_BLENDED_EV")
        o = None if prop else opp.get(id(r))
        st, why = _priced_or_withheld(base, st, why, o, cap)
        dist = ("MARKET_ANCHORED_PROP_NORMAL(mean=0.7model+0.3market;sd_frac=PROP_SD_FRAC)" if prop
                else f"LEGACY_GAME_NORMAL_ZERO_PUSH(sd_margin={M.SD_MARGIN},sd_total={M.SD_TOTAL},sd_tt={M.SD_TT})")
        mkt, period, sel, team, player = _cfb_canon(r, sides.get(gid, (None, None)))
        if mkt is None:
            unl.append((gid, r["market"], r["pick"], "UNMAPPED_MARKET")); continue
        out.append({**base, "event_id": gid, "player_name": player, "market": mkt, "period": period,
                    "team": team, "player_id": str(r["player_id"]) if prop and r.get("player_id") is not None else None,
                    "selection": sel, "quote_captured_utc": cap, "game_start_utc": start,
                    "line": r["line"], "price": r["odds"] if st != "WITHHELD" else None,
                    "opp_price": o["odds"] if (o and st != "WITHHELD") else None,
                    "novig_p": r["p_market"] if st != "WITHHELD" else None, "projection": r.get("proj"),
                    "distribution_id": dist, "win_p": r["p_model"], "push_p": 0.0,
                    "loss_p": max(0.0, 1.0 - r["p_model"]), "raw_ev": r["ev_raw"] if st != "WITHHELD" else None,
                    "selection_state": st, "rejection_reason": why,
                    "source_provenance": {**base["source_provenance"],
                                          "projection_mode": "MARKET_ANCHORED_RESEARCH" if prop else "LEGACY_GAME_RESEARCH",
                                          "price_as_quoted": r["odds"], "pick_text": r["pick"],
                                          "market_text": r["market"]}})
    lab = ctx.get("label_to_gid", {})
    for k, (label, reason) in enumerate(withheld):
        gid = lab.get(label)
        if gid is None or kick.get(gid) is None:
            unl.append((label, None, None, reason)); continue
        out.append({**base, "event_id": gid, "market": "UNPRICED", "selection": f"withheld#{k}",
                    "quote_captured_utc": cap, "game_start_utc": kick[gid], "line": None, "price": None,
                    "opp_price": None, "novig_p": None, "projection": None, "distribution_id": "NONE",
                    "win_p": None, "push_p": None, "loss_p": None, "raw_ev": None,
                    "selection_state": "WITHHELD", "rejection_reason": str(reason)[:400]})
    return out, unl


def _nfl_canon(r):
    """NFL v3 ledger row -> (market, period, side) in settle() vocabulary, or Nones."""
    m, sel, game = str(r.get("market") or ""), str(r.get("selection") or ""), str(r.get("game") or "")
    if r.get("kind") == "prop":
        return None, "FG", None
    period = "H1" if m.startswith("1H") else "FG"
    base = m[3:] if m.startswith("1H ") else m
    away, _, home = game.partition("@")
    if base in ("Spread", "ML", "Moneyline"):
        mk = "spread" if base == "Spread" else "moneyline"
        if home and sel.startswith(home + " "): return mk, period, "home"
        if away and sel.startswith(away + " "): return mk, period, "away"
        return None, period, None
    if base == "Total":
        return "total", period, "over" if "Over" in sel else "under" if "Under" in sel else None
    return None, period, None


def rows_from_nfl_ledger(ledger_rows, meta, commit_sha=None):
    """Every NFL v3 ledger row (complete denominator) -> pregame-log rows. Returns (rows, unloggable).

    meta: {"kickoff_utc": {game: iso}, "quote_captured_utc": iso, "prediction_utc": iso,
           "model_version": str, "model_code_sha256": str, "config": dict, "provenance": dict}.
    NFL props are priced from a one-sided quote against the market line scaled by the model
    total, so they are logged MARKET_ANCHORED and WITHHELD (no opposite price)."""
    import re
    kick = {g: _z(t) for g, t in (meta.get("kickoff_utc") or {}).items()}
    cap = _z(meta.get("quote_captured_utc"))
    pred = _z(meta.get("prediction_utc"))
    games = [r for r in ledger_rows if r.get("kind") == "game"]
    opp = _pairs(games, lambda r: (r["game"], r["market"]))
    base = {"sport": "NFL", "team": None, "player_id": None, "player_name": None,
            "prediction_utc": pred, "book": "DraftKings", "model_version": meta.get("model_version") or "nfl-run-it-v3",
            "model_commit_sha": commit_sha or _commit_sha(),
            "model_code_sha256": meta.get("model_code_sha256") or "UNAVAILABLE",
            "config_sha256": sha256_of(meta.get("config") or {}),
            "source_provenance": dict(meta.get("provenance") or {"source": "UNSPECIFIED"}),
            "adj_ev": None, "adj_ev_method": "NOT_COMPUTED"}
    out, unl = [], []
    for i, r in enumerate(ledger_rows):
        start = kick.get(r.get("game"))
        if start is None or pred is None:
            unl.append((r.get("game"), r.get("market"), r.get("selection"), "NO_KICKOFF_OR_PREDICTION_TIME")); continue
        status, reason = r.get("status"), r.get("reject_reason") or None
        if status == "rejected_input":
            st, why = "WITHHELD", str(reason or "rejected_input")
        elif status == "on_card":
            st, why = "SELECTED", None
        else:
            st, why = "REJECTED", str(status or "NOT_QUALIFIED")
        prop = r.get("kind") == "prop"
        o = opp.get(id(r)) if not prop else None
        if st != "WITHHELD":
            st, why = _priced_or_withheld(base, st, why, o, cap)
        mkt_text = str(r.get("market") or "UNKNOWN")
        mkt, period, sel_side = _nfl_canon(r)
        line = r.get("line")
        if line is None and r.get("selection"):
            m = re.search(r"([+-]\d+(?:\.\d+)?)$", str(r["selection"]).replace(" ML", ""))
            line = float(m.group(1)) if m and "Spread" in mkt_text else None
        priced = st != "WITHHELD"
        pw, pp = r.get("model_p"), r.get("p_push") or 0.0
        if mkt is None and st != "WITHHELD":
            st, why = "WITHHELD", f"UNMAPPED_MARKET (card_state={st})"
        priced = st != "WITHHELD"
        out.append({**base, "event_id": str(r.get("game")), "period": period,
                    "player_name": r.get("player") if prop else None, "market": mkt or mkt_text,
                    "selection": sel_side or str(r.get("selection") or f"row#{i}"), "quote_captured_utc": cap,
                    "game_start_utc": start, "line": line,
                    "price": r["odds"] if priced else None, "opp_price": o["odds"] if (o and priced) else None,
                    "novig_p": r.get("market_p") if priced else None, "projection": r.get("proj_value"),
                    "distribution_id": ("MARKET_ANCHORED_PROP(one_sided_vig=1.045)" if prop
                                        else "V3_NORMAL(sd_margin=13.5,sd_total=13.0,sd_1h=9.5;integer_push)"),
                    "win_p": pw, "push_p": pp if pw is not None else None,
                    "loss_p": max(0.0, 1 - pw - pp) if pw is not None else None,
                    "raw_ev": r.get("raw_ev") if priced else None,
                    "selection_state": st, "rejection_reason": why,
                    "source_provenance": {**base["source_provenance"],
                                          "projection_mode": "MARKET_ANCHORED_RESEARCH" if prop else "V3_GAME_RESEARCH",
                                          "price_as_quoted": r.get("odds"), "selection_text": r.get("selection"),
                                          "market_text": mkt_text}})
    return out, unl
