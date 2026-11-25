"""NBA market-contract ingestion guard v2 (research only, PAPER_0U, NON_COUNTED).

Architecture (every source kind goes through the same pipeline):

    DraftKings | PDF | screenshot | CSV | manual | replay
        -> structured rows (this module never parses PDFs/images)
        -> universal contract validation:
             identity  (verified unique event -> home/away binding, roster/ratings present)
             odds      (whole-number American, |p| >= 100, coherent two-sided prices)
             period    (exact frozen spelling; 2H/2Q/3Q/4Q refused)
             selection (exact event teams, OVER/UNDER, no Tie/Draw in two-way)
             lines     (finite, 0.5 grid, ML none, spreads complementary, totals equal)
             chronology(capture id + tz-aware timestamp, <= tip and <= as_of; no cross-capture pairing)
        -> valid contracts   -> per-run immutable workspace -> frozen pricer
        -> invalid contracts -> persisted rejection ledger with reason codes

The frozen model file (blob b353de86) is never edited. The guard refuses to price if that blob changes.
Frozen functions stay callable for frozen-file regression tests only; operational code must call
run_guarded / run_it. Player props are validated here too and are withheld with reason codes when invalid.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN_MODEL = "models/nba/sportsedge_nba_model.py"
FROZEN_BLOB = "b353de86445188288cab4050f6cae13eee76bff6"

RELEASE = "PAPER_0U"
STATUS_LABEL = "NON_COUNTED"

SOURCE_KINDS = frozenset({"dk_capture", "pdf", "screenshot", "csv", "manual", "replay"})
PROP_STATS = frozenset({"PTS", "REB", "AST", "3PM", "PRA"})
TIE_SELECTIONS = frozenset({"TIE", "DRAW", "X"})
OU = frozenset({"OVER", "UNDER"})
TEAM_RE = re.compile(r"^[A-Z0-9]+$")
MARKET_RE = re.compile(r"^(?:(1H|1Q)_)?(ML|SPREAD|TOTAL|TT_([A-Z0-9]+))$")
UNSUPPORTED_PERIOD_RE = re.compile(r"^(2H|2Q|3Q|4Q)_")
MAX_HOLD = 1.5  # sum of implied probabilities above this is not a plausible two-way market

REASON = {
    "TIE_OR_DRAW_IN_TWO_WAY_ML": "Tie/Draw selection cannot be priced as a two-way moneyline",
    "THREE_WAY_ML_UNSUPPORTED": "Three-way moneyline (Tie/Draw offered) is not priced by the two-way model",
    "INCOMPLETE_TWO_WAY": "Two-way market is missing a complementary selection",
    "DUPLICATE_SELECTION": "Duplicate selection in the same market contract",
    "AMBIGUOUS_MARKET_CONTRACT": "Selections do not form a unique two-way contract (or a sibling quote failed)",
    "MIXED_PERIOD_CONTRACT": "Selections or fields from different periods were combined in one contract",
    "PERIOD_FIELD_CONFLICT": "Explicit period field disagrees with the market name",
    "UNSUPPORTED_PERIOD_MARKET": "Period is not priceable by the frozen model (no silent fallback to full-game)",
    "UNKNOWN_MARKET": "Market name is not an exact frozen NBA market spelling",
    "MISSING_REQUIRED_FIELD": "Required board field is missing",
    "SOURCE_KIND_INVALID": "Source kind is not a supported ingestion path",
    "SOURCE_ROWS_MISSING": "Capture has no extracted structured rows (PDF/screenshot are not parsed)",
    "ODDS_MALFORMED_OR_FRACTIONAL": "Price is not a whole-number American quote with |price| >= 100",
    "INVALID_LINE": "Line is missing, non-finite, malformed or present where none is allowed",
    "LINE_OFF_GRID": "Line is not on the 0.5 grid",
    "SPREAD_LINES_NOT_COMPLEMENTARY": "Spread lines must have opposite signs and equal magnitude",
    "TOTAL_LINES_MISMATCH": "Over/Under lines differ or are not positive",
    "INCOHERENT_TWO_SIDED_PRICES": "Two-sided prices imply no positive hold or an implausible hold",
    "UNKNOWN_EVENT": "game_id has no verified event identity",
    "INVALID_EVENT_IDENTITY": "Event home/away missing, equal, or not frozen-safe uppercase alphanumeric codes",
    "CONFLICTING_EVENT_BINDING": "game_id maps to conflicting event definitions",
    "EVENT_NOT_PRICEABLE": "Event lacks unique team ratings, so the frozen model cannot project it",
    "SELECTION_NOT_EVENT_TEAM": "Selection is not exactly one of the event's two teams",
    "UNKNOWN_TEAM_TOTAL_TEAM": "Team-total market team is not one of the event's two teams",
    "MISSING_CAPTURE_PROVENANCE": "capture_id and captured_at are required",
    "CHRONOLOGY_INVALID": "captured_at is not a timezone-aware ISO-8601 timestamp",
    "TIPOFF_UNVERIFIABLE": "Event tip-off time cannot be verified, so chronology cannot be checked",
    "QUOTE_AFTER_TIP": "Quote was captured at or after tip-off (pregame only)",
    "QUOTE_FROM_FUTURE": "Quote capture time is after the run's as-of time",
    "SUPERSEDED_BY_LATER_CAPTURE": "A later valid capture of the same contract exists; captures are never mixed",
    "AMBIGUOUS_CAPTURE_TIE": "Different captures with the same timestamp quote the same contract",
    "PROP_UNSUPPORTED_STAT": "Prop stat is not one of PTS, REB, AST, 3PM, PRA",
    "PROP_UNKNOWN_PLAYER": "Prop player/team/id does not resolve to exactly one roster row",
    "PROP_TEAM_NOT_EVENT_TEAM": "Prop team is missing or not one of the event's two teams",
    "PROP_DUPLICATE": "Duplicate prop quote in the same capture",
    "FROZEN_MODEL_CHANGED": "Frozen model blob differs from the pinned blob; refusing to price",
}

REJECT_FIELDS = ["record_type", "source_kind", "game_id", "market", "selection", "line", "price",
                 "player", "team", "stat", "over_price", "under_price", "capture_id", "captured_at",
                 "reason_code", "reason", "reason_detail"]
ODDS_FIELDS = ["game_id", "market", "selection", "line", "price", "capture_id", "captured_at", "source_kind"]
PROP_FIELDS = ["game_id", "player", "team", "player_id", "stat", "line", "over_price", "under_price",
               "capture_id", "captured_at", "source_kind"]


# ------------------------------------------------------------------ helpers
def _s(v) -> str:
    return "" if v is None else str(v).strip()


def blob_sha1(path: str) -> str:
    with open(path, "rb") as f:
        body = f.read()
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_american_price(value):
    """Whole-number American price or None (fractional, decimal, fraction, NaN/inf, bool, |p|<100)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(value) if isinstance(value, (int, float)) else float(str(value).strip().replace("\u2212", "-"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num != int(num) or abs(num) < 100:
        return None
    return int(num)


def implied(price: int) -> float:
    return 100.0 / (price + 100.0) if price > 0 else -price / (-price + 100.0)


def parse_line(value):
    """Finite float on the 0.5 grid, else (None, reason_code)."""
    if value is None or _s(value) == "":
        return None, "INVALID_LINE"
    try:
        f = float(_s(value))
    except ValueError:
        return None, "INVALID_LINE"
    if not math.isfinite(f):
        return None, "INVALID_LINE"
    if abs(f * 2 - round(f * 2)) > 1e-9:
        return None, "LINE_OFF_GRID"
    return f, None


def fmt_line(f: float) -> str:
    f = 0.0 if f == 0 else f
    return repr(float(f))


def parse_ts(value):
    """tz-aware datetime or None."""
    t = _s(value)
    if not t:
        return None
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None and dt.utcoffset() is not None else None


def atomic_write(path: str, text: str) -> str:
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def write_csv_atomic(path: str, rows: list[dict], fields: list[str]) -> str:
    import io
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return atomic_write(path, buf.getvalue())


def read_csv_rows(path: str) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _rej(row: dict, code: str, detail: str = "", record_type: str = "odds", source_kind: str = "") -> dict:
    rec = {k: _s(row.get(k)) for k in REJECT_FIELDS if k in row}
    rec.update(record_type=record_type, source_kind=source_kind or _s(row.get("source_kind")),
               reason_code=code, reason=REASON[code], reason_detail=detail)
    return rec


# ------------------------------------------------------------------ identity
def build_events(games: list[dict], teams: list[dict]):
    """Return (events, rejected). events[game_id] = dict(home, away, tip, ok, problem)."""
    from zoneinfo import ZoneInfo
    rejected: list[dict] = []
    team_count = defaultdict(int)
    for t in teams:
        team_count[_s(t.get("team"))] += 1
    by_gid = defaultdict(list)
    for g in games:
        by_gid[_s(g.get("game_id"))].append(g)
    events = {}
    for gid, rows in by_gid.items():
        if not gid:
            continue
        sigs = {(_s(r.get("home")), _s(r.get("away")), _s(r.get("date")), _s(r.get("tipoff_et"))) for r in rows}
        if len(sigs) > 1:
            events[gid] = dict(ok=False, problem="CONFLICTING_EVENT_BINDING")
            continue
        home, away, date, tip = next(iter(sigs))
        if not home or not away or home == away or not TEAM_RE.match(home) or not TEAM_RE.match(away):
            events[gid] = dict(ok=False, problem="INVALID_EVENT_IDENTITY", detail=f"{home!r}/{away!r}")
            continue
        if team_count[home] != 1 or team_count[away] != 1:
            events[gid] = dict(ok=False, problem="EVENT_NOT_PRICEABLE", detail=f"{home}/{away} ratings rows")
            continue
        tip_dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                tip_dt = datetime.strptime(f"{date} {tip}", fmt).replace(tzinfo=ZoneInfo("America/New_York"))
                break
            except ValueError:
                pass
        events[gid] = dict(ok=True, home=home, away=away, tip=tip_dt, game_row=rows[0])
    return events


# ------------------------------------------------------------------ odds validation
def _provenance(row: dict, board: dict, as_of, event) -> tuple:
    """Return (capture_id, captured_at_dt, code, detail)."""
    cid = _s(row.get("capture_id")) or _s(board.get("capture_id"))
    cat = _s(row.get("captured_at")) or _s(board.get("captured_at"))
    if not cid or not cat:
        return cid, None, "MISSING_CAPTURE_PROVENANCE", ""
    dt = parse_ts(cat)
    if dt is None:
        return cid, None, "CHRONOLOGY_INVALID", cat
    if event.get("tip") is None:
        return cid, dt, "TIPOFF_UNVERIFIABLE", ""
    if dt >= event["tip"]:
        return cid, dt, "QUOTE_AFTER_TIP", f"{dt.isoformat()} >= {event['tip'].isoformat()}"
    if as_of is not None and dt > as_of:
        return cid, dt, "QUOTE_FROM_FUTURE", dt.isoformat()
    return cid, dt, None, ""


def _group_odds(rows, board, as_of, events, kind):
    """Row-level checks. Returns (groups: key -> list[(row, parsed)]), rejected."""
    rejected = []
    groups = defaultdict(list)
    for r in rows:
        r = dict(r)
        missing = [k for k in ("game_id", "market", "selection", "price") if _s(r.get(k)) == ""]
        gid = _s(r.get("game_id"))
        market = _s(r.get("market")).upper()
        raw_line = _s(r.get("line"))
        try:
            lk = repr(abs(float(raw_line))) if raw_line else ""
        except ValueError:
            lk = "RAW:" + raw_line
        board_key = (_s(r.get("capture_id")) or _s(board.get("capture_id")),
                     _s(r.get("captured_at")) or _s(board.get("captured_at")), gid, market, lk)
        parsed = dict(row=r, market=market, error=None, detail="")
        if missing:
            parsed["error"], parsed["detail"] = "MISSING_REQUIRED_FIELD", ",".join(missing)
        else:
            ev = events.get(gid)
            if ev is None:
                parsed["error"] = "UNKNOWN_EVENT"
            elif not ev["ok"]:
                parsed["error"], parsed["detail"] = ev["problem"], ev.get("detail", "")
            else:
                parsed["event"] = ev
                cid, dt, code, detail = _provenance(r, board, as_of, ev)
                parsed["cid"], parsed["dt"] = cid, dt
                if code:
                    parsed["error"], parsed["detail"] = code, detail
        groups[board_key].append(parsed)
    return groups, rejected


def _classify_market(market: str):
    """Return (period, base, tt_team, error_code)."""
    if "/" in market:
        return None, None, None, "MIXED_PERIOD_CONTRACT"
    m = MARKET_RE.match(market)
    if m:
        period = m.group(1) or "FG"
        base = "TT" if m.group(2).startswith("TT_") else m.group(2)
        return period, base, m.group(3), None
    if UNSUPPORTED_PERIOD_RE.match(market):
        return None, None, None, "UNSUPPORTED_PERIOD_MARKET"
    if "3WAY" in market or "3-WAY" in market or market.endswith("1X2"):
        return None, None, None, "THREE_WAY_ML_UNSUPPORTED"
    return None, None, None, "UNKNOWN_MARKET"


def _check_group(key, items, kind):
    """Return (accepted_canonical_rows, rejected, contract_meta)."""
    rej = []

    def all_reject(code, detail=""):
        return [], rej + [_rej(p["row"], code, detail, source_kind=kind) for p in items if not p.get("_done")], None

    # row-level errors poison the whole group
    bad = [p for p in items if p["error"]]
    if bad:
        for p in bad:
            rej.append(_rej(p["row"], p["error"], p["detail"], source_kind=kind)); p["_done"] = True
        return [], rej + [_rej(p["row"], "AMBIGUOUS_MARKET_CONTRACT", "sibling_quote_rejected", source_kind=kind)
                          for p in items if not p.get("_done")], None
    market = items[0]["market"]
    period, base, tt_team, code = _classify_market(market)
    if code:
        return all_reject(code)
    explicit = {_s(p["row"].get("period")).upper() for p in items} - {""}
    if explicit:
        want = "" if period == "FG" else period
        if explicit - {want, "FG"} or (period != "FG" and explicit != {period}):
            return all_reject("PERIOD_FIELD_CONFLICT", ",".join(sorted(explicit)))
    ev = items[0]["event"]
    home, away = ev["home"], ev["away"]
    sels = [_s(p["row"]["selection"]).upper() for p in items]
    # prices first: strict integers
    prices = []
    for p in items:
        pr = parse_american_price(p["row"].get("price"))
        if pr is None:
            return all_reject("ODDS_MALFORMED_OR_FRACTIONAL", _s(p["row"].get("price")))
        prices.append(pr)
    cnt = defaultdict(int)
    for s in sels:
        cnt[s] += 1
    if any(c > 1 for c in cnt.values()):
        return all_reject("DUPLICATE_SELECTION")
    ties = [s for s in sels if s in TIE_SELECTIONS]
    teams = [s for s in sels if s not in TIE_SELECTIONS]
    if base == "ML":
        if ties:
            return all_reject("THREE_WAY_ML_UNSUPPORTED" if len(teams) >= 2 else "TIE_OR_DRAW_IN_TWO_WAY_ML")
        if len(sels) < 2:
            return all_reject("INCOMPLETE_TWO_WAY")
        if len(sels) > 2:
            return all_reject("AMBIGUOUS_MARKET_CONTRACT")
        if set(sels) != {home, away}:
            return all_reject("SELECTION_NOT_EVENT_TEAM", ",".join(sels))
        if any(_s(p["row"].get("line")) for p in items):
            return all_reject("INVALID_LINE", "moneyline must have no line")
        lines = ["", ""]
    else:
        parsed_lines = []
        for p in items:
            f, c = parse_line(p["row"].get("line"))
            if c:
                return all_reject(c, _s(p["row"].get("line")))
            parsed_lines.append(f)
        if base in ("TOTAL", "TT"):
            if base == "TT" and tt_team not in (home, away):
                return all_reject("UNKNOWN_TEAM_TOTAL_TEAM", tt_team)
            if ties or set(sels) - OU:
                return all_reject("AMBIGUOUS_MARKET_CONTRACT", "total selections must be OVER/UNDER")
            if len(sels) < 2:
                return all_reject("INCOMPLETE_TWO_WAY")
            if parsed_lines[0] != parsed_lines[1] or parsed_lines[0] <= 0:
                return all_reject("TOTAL_LINES_MISMATCH")
        else:  # SPREAD
            if ties:
                return all_reject("TIE_OR_DRAW_IN_TWO_WAY_ML" if len(teams) < 2 else "THREE_WAY_ML_UNSUPPORTED")
            if len(sels) < 2:
                return all_reject("INCOMPLETE_TWO_WAY")
            if len(sels) > 2:
                return all_reject("AMBIGUOUS_MARKET_CONTRACT")
            if set(sels) != {home, away}:
                return all_reject("SELECTION_NOT_EVENT_TEAM", ",".join(sels))
            if abs(parsed_lines[0] + parsed_lines[1]) > 1e-9 or (parsed_lines[0] == 0) != (parsed_lines[1] == 0):
                return all_reject("SPREAD_LINES_NOT_COMPLEMENTARY", f"{parsed_lines[0]},{parsed_lines[1]}")
        lines = [fmt_line(x) for x in parsed_lines]
    if not (1.0 + 1e-9 < implied(prices[0]) + implied(prices[1]) <= MAX_HOLD):
        return all_reject("INCOHERENT_TWO_SIDED_PRICES", f"{prices[0]},{prices[1]}")
    out = []
    for p, sel, pr, ln in zip(items, sels, prices, lines):
        out.append(dict(game_id=_s(p["row"]["game_id"]), market=market, selection=sel, line=ln, price=str(pr),
                        capture_id=p["cid"], captured_at=p["dt"].isoformat(), source_kind=kind))
    meta = dict(game_id=items[0]["row"]["game_id"].strip(), market=market, base=base,
                abs_line=abs(float(lines[0])) if lines[0] != "" else None, dt=items[0]["dt"], cid=items[0]["cid"])
    return out, rej, meta


def validate_odds(rows: Iterable[dict], events: dict, *, as_of=None, board=None, source_kind="csv") -> dict:
    kind = _s(source_kind).lower()
    board = board or {}
    rows = list(rows or [])
    if kind not in SOURCE_KINDS:
        return {"source_kind": source_kind, "accepted": [],
                "rejected": [_rej(r, "SOURCE_KIND_INVALID", _s(source_kind)) for r in rows]
                or [_rej({}, "SOURCE_KIND_INVALID", _s(source_kind))]}
    if not rows:
        return {"source_kind": kind, "accepted": [], "rejected": [_rej({}, "SOURCE_ROWS_MISSING", source_kind=kind)]}
    groups, rejected = _group_odds(rows, board, as_of, events, kind)
    valid = []
    for key, items in groups.items():
        out, rej, meta = _check_group(key, items, kind)
        rejected += rej
        if out:
            valid.append((out, meta))
    # never mix captures: one capture per (game, market, abs line)
    by_contract = defaultdict(list)
    for out, meta in valid:
        by_contract[(meta["game_id"], meta["market"], meta["abs_line"])].append((out, meta))
    accepted = []
    for ckey, cands in by_contract.items():
        newest = max(m["dt"] for _, m in cands)
        top = [(o, m) for o, m in cands if m["dt"] == newest]
        for o, m in cands:
            if m["dt"] != newest:
                rejected += [_rej(r, "SUPERSEDED_BY_LATER_CAPTURE", m["cid"], source_kind=kind) for r in o]
        if len({m["cid"] for _, m in top}) > 1 or len(top) > 1:
            for o, m in top:
                rejected += [_rej(r, "AMBIGUOUS_CAPTURE_TIE", m["cid"], source_kind=kind) for r in o]
            continue
        accepted.append(top[0])
    final = [r for o, _ in accepted for r in o]
    return {"source_kind": kind, "accepted": final, "rejected": rejected,
            "accepted_count": len(final), "rejected_count": len(rejected)}


# ------------------------------------------------------------------ props validation
def validate_props(rows: Iterable[dict], events: dict, players: list[dict], *, as_of=None, board=None,
                   source_kind="csv") -> dict:
    kind = _s(source_kind).lower()
    board = board or {}
    rows = list(rows or [])
    roster = defaultdict(list)
    for p in players:
        roster[(_s(p.get("team")), _s(p.get("player")))].append(p)
    rejected, valid, seen = [], [], defaultdict(list)
    for r in rows:
        r = dict(r)
        r["record_type"] = "prop"
        gid, stat = _s(r.get("game_id")), _s(r.get("stat")).upper()
        team, name, pid = _s(r.get("team")), _s(r.get("player")), _s(r.get("player_id"))
        code = detail = None
        ev = events.get(gid)
        if any(_s(r.get(k)) == "" for k in ("game_id", "player", "stat", "line", "over_price", "under_price")):
            code = "MISSING_REQUIRED_FIELD"
        elif ev is None:
            code = "UNKNOWN_EVENT"
        elif not ev["ok"]:
            code, detail = ev["problem"], ev.get("detail", "")
        elif kind not in SOURCE_KINDS:
            code = "SOURCE_KIND_INVALID"
        elif stat not in PROP_STATS:
            code = "PROP_UNSUPPORTED_STAT"
        elif team not in (ev["home"], ev["away"]):
            code = "PROP_TEAM_NOT_EVENT_TEAM"
        else:
            cid, dt, c, d = _provenance(r, board, as_of, ev)
            if c:
                code, detail = c, d
            else:
                line, lc = parse_line(r.get("line"))
                op, up = parse_american_price(r.get("over_price")), parse_american_price(r.get("under_price"))
                matches = roster.get((team, name), [])
                if lc or line is None or line <= 0:
                    code, detail = (lc or "INVALID_LINE"), _s(r.get("line"))
                elif op is None or up is None:
                    code, detail = "ODDS_MALFORMED_OR_FRACTIONAL", f"{r.get('over_price')},{r.get('under_price')}"
                elif not (1.0 + 1e-9 < implied(op) + implied(up) <= MAX_HOLD):
                    code, detail = "INCOHERENT_TWO_SIDED_PRICES", f"{op},{up}"
                elif len(matches) != 1 or (pid and _s(matches[0].get("player_id")) != pid):
                    code = "PROP_UNKNOWN_PLAYER"
                else:
                    rec = dict(game_id=gid, player=name, team=team, player_id=pid, stat=stat, line=fmt_line(line),
                               over_price=str(op), under_price=str(up), capture_id=cid,
                               captured_at=dt.isoformat(), source_kind=kind)
                    seen[(cid, dt, gid, team, name, pid, stat, line)].append(rec)
                    valid.append((rec, dt, cid, (gid, team, name, pid, stat, line)))
                    continue
        rejected.append(_rej(r, code, detail or "", record_type="prop", source_kind=kind))
    dup_ids = {id(rec) for v in seen.values() if len(v) > 1 for rec in v}
    by_contract = defaultdict(list)
    for rec, dt, cid, ckey in valid:
        if id(rec) in dup_ids:
            rejected.append(_rej(rec, "PROP_DUPLICATE", record_type="prop", source_kind=kind))
        else:
            by_contract[ckey].append((rec, dt, cid))
    accepted = []
    for ckey, cands in by_contract.items():
        newest = max(dt for _, dt, _ in cands)
        top = [c for c in cands if c[1] == newest]
        for rec, dt, cid in cands:
            if dt != newest:
                rejected.append(_rej(rec, "SUPERSEDED_BY_LATER_CAPTURE", cid, record_type="prop", source_kind=kind))
        if len(top) > 1:
            rejected += [_rej(rec, "AMBIGUOUS_CAPTURE_TIE", cid, record_type="prop", source_kind=kind)
                         for rec, _, cid in top]
        else:
            accepted.append(top[0][0])
    return {"source_kind": kind, "accepted": accepted, "rejected": rejected}


# ------------------------------------------------------------------ loading
def load_board(inputs: dict, *, source_kind: str = "csv", as_of=None) -> dict:
    """Load structured inputs and run universal validation for every source kind."""
    kind = _s(source_kind).lower()
    as_of = as_of or datetime.now(timezone.utc)
    board = {"capture_id": _s(inputs.get("capture_id")), "captured_at": _s(inputs.get("captured_at"))}
    games = list(inputs.get("games_rows") or read_csv_rows(inputs.get("games", "")))
    teams = list(inputs.get("teams_rows") or read_csv_rows(inputs.get("teams", "")))
    players = list(inputs.get("players_rows") or read_csv_rows(inputs.get("players", "")))
    events = build_events(games, teams)
    odds_rows = list(inputs.get("odds_rows") or read_csv_rows(inputs.get("odds", "")))
    prop_rows = list(inputs.get("props_rows") or read_csv_rows(inputs.get("props", "")))
    if not odds_rows and not prop_rows and kind in SOURCE_KINDS:
        miss = _rej({"capture_path": _s(inputs.get("capture_path"))}, "SOURCE_ROWS_MISSING",
                    "structured rows are required; PDF/screenshot files are not parsed", source_kind=kind)
        return {"source_kind": kind, "accepted": [], "rejected": [miss], "props_accepted": [],
                "props_rejected": [], "events": events, "as_of": as_of}
    o = validate_odds(odds_rows, events, as_of=as_of, board=board, source_kind=kind) if odds_rows or kind not in SOURCE_KINDS \
        else {"source_kind": kind, "accepted": [], "rejected": []}
    p = validate_props(prop_rows, events, players, as_of=as_of, board=board, source_kind=kind) if prop_rows \
        else {"accepted": [], "rejected": []}
    if kind not in SOURCE_KINDS:
        p = {"accepted": [], "rejected": []}
    return {"source_kind": o["source_kind"], "accepted": o["accepted"], "rejected": o["rejected"],
            "props_accepted": p["accepted"], "props_rejected": p["rejected"], "events": events, "as_of": as_of}


# Operational entry points. Every one validates before anything can reach the frozen pricer.
GUARDED_ENTRY_POINTS = (
    "models/nba/market_contract.py:load_board",
    "models/nba/market_contract.py:validate_odds",
    "models/nba/market_contract.py:validate_props",
    "models/nba/market_contract.py:run_guarded",
    "models/nba/run_it.py:main",
    "models/nba/run_it.py:run_from_inputs",
)
# Frozen callables: regression-test use only. The frozen __main__ cannot be guarded without editing the
# frozen blob, so operational code, workflows and CLIs are forbidden from reaching it (census test).
FROZEN_REGRESSION_ONLY = (
    "models/nba/sportsedge_nba_model.py:run_card",
    "models/nba/sportsedge_nba_model.py:price_games",
    "models/nba/sportsedge_nba_model.py:price_game_market",
    "models/nba/sportsedge_nba_model.py:price_props",
    "models/nba/sportsedge_nba_model.py:__main__",
)
_PRICING_HOOK = None  # tests only: called with each accepted odds/prop record just before pricing


def _label_outputs(run_dir: str, run_id: str, csv_path: str, md_path: str) -> None:
    rows = read_csv_rows(csv_path)
    fields = list(rows[0].keys()) if rows else []
    if not fields:
        with open(csv_path, newline="", encoding="utf-8") as f:
            fields = next(csv.reader(f), [])
    extra = dict(release=RELEASE, status=STATUS_LABEL, official_counted="0", approved_stake_u="0",
                 run_id=run_id, research_only="TRUE")
    for r in rows:
        r.update(extra)
    write_csv_atomic(csv_path, rows, fields + [k for k in extra if k not in fields])
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    banner = (f"> **{RELEASE} / {STATUS_LABEL} / official_counted=0 / approved_stake_u=0 / research only** "
              f"- guarded run `{run_id}`; invalid contracts are in nba_rejected_markets.csv.\n\n")
    atomic_write(md_path, banner + md)


def run_guarded(inputs: dict, out_dir: str = ".", *, source_kind: str = "csv", as_of=None, price: bool = True) -> dict:
    """Validate everything, persist the ledger, and price only valid contracts in a unique run workspace."""
    board = load_board(inputs, source_kind=source_kind, as_of=as_of)
    as_of = board["as_of"]
    frozen_path = os.path.join(HERE, "sportsedge_nba_model.py")
    frozen_ok = blob_sha1(frozen_path) == FROZEN_BLOB
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"{stamp}-{uuid.uuid4().hex[:12]}"
    run_dir = os.path.join(out_dir, "runs", run_id)
    os.makedirs(run_dir, exist_ok=False)  # unique per run; never shared between concurrent runs
    rejected = list(board["rejected"]) + list(board["props_rejected"])
    if not frozen_ok:
        rejected.append(_rej({}, "FROZEN_MODEL_CHANGED", blob_sha1(frozen_path), source_kind=board["source_kind"]))
    ledger = write_csv_atomic(os.path.join(run_dir, "nba_rejected_markets.csv"), rejected, REJECT_FIELDS)
    result = {"run_id": run_id, "run_dir": run_dir, "source_kind": board["source_kind"], "ledger": ledger,
              "accepted": board["accepted"], "props_accepted": board["props_accepted"], "rejected": rejected,
              "picks": [], "projections": {}, "csv": None, "md": None, "release": RELEASE,
              "status_label": STATUS_LABEL, "official_counted": 0, "approved_stake_u": 0}
    hashes = {"nba_rejected_markets.csv": sha256_file(ledger)}
    if not frozen_ok:
        result["status"] = "FROZEN_MODEL_CHANGED"
    elif not (board["accepted"] or board["props_accepted"]) or not price:
        result["status"] = "NO_ELIGIBLE_CONTRACTS"
    else:
        hook = _PRICING_HOOK
        if hook:
            for rec in board["accepted"] + board["props_accepted"]:
                hook(dict(rec))
        ok_games = [e["game_row"] for e in board["events"].values() if e["ok"]]
        game_fields = list(ok_games[0].keys()) if ok_games else ["game_id"]
        paths = {"games": write_csv_atomic(os.path.join(run_dir, "games.csv"), ok_games, game_fields),
                 "odds": write_csv_atomic(os.path.join(run_dir, "_accepted_odds.csv"), board["accepted"], ODDS_FIELDS),
                 "props": write_csv_atomic(os.path.join(run_dir, "_accepted_props.csv"), board["props_accepted"], PROP_FIELDS)}
        for name in ("teams", "injuries", "players", "positional_defense"):
            src = inputs.get(name, "")
            rows = list(inputs.get(name + "_rows") or read_csv_rows(src))
            fields = list(rows[0].keys()) if rows else ["team"]
            paths[name] = write_csv_atomic(os.path.join(run_dir, name + ".csv"), rows, fields)
        for name, p in paths.items():
            hashes[os.path.basename(p)] = sha256_file(p)
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import sportsedge_nba_model as frozen
        card = frozen.run_card(paths, out_dir=run_dir)
        _label_outputs(run_dir, run_id, card["csv"], card["md"])
        result.update(picks=card["picks"], projections=card["projections"], csv=card["csv"], md=card["md"])
        hashes["nba_card.csv"], hashes["nba_card.md"] = sha256_file(card["csv"]), sha256_file(card["md"])
        result["status"] = "PRICED"
    manifest = {"run_id": run_id, "status": result["status"], "source_kind": board["source_kind"],
                "as_of": as_of.isoformat(), "frozen_model_blob": blob_sha1(frozen_path),
                "frozen_model_blob_pinned": FROZEN_BLOB, "release": RELEASE, "status_label": STATUS_LABEL,
                "official_counted": 0, "approved_stake_u": 0, "research_only": True,
                "accepted_odds": len(board["accepted"]), "accepted_props": len(board["props_accepted"]),
                "rejected": len(rejected), "files_sha256": hashes}
    atomic_write(os.path.join(run_dir, "run_manifest.json"), json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    result["manifest"] = os.path.join(run_dir, "run_manifest.json")
    return result


run_card_guarded = run_guarded  # backwards-compatible alias
