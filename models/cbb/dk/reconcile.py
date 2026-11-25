"""Reconcile DraftKings board captures into a validated derived board + rejection ledger.

Pure functions over files already on disk. Original boards are only read.
Contract: docs/cbb/dk_interface.md. Everything stays PAPER_0U / NON_COUNTED.
"""
from __future__ import annotations
import csv, io, json, re, unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import evidence as EV
from . import schema as S

CT = ZoneInfo("America/Chicago")
TIP_TOLERANCE = timedelta(minutes=15)
TT_TOLERANCE = 4.0
SUPPORTED = {"SPREAD", "TOTAL", "ML", "TT_HOME", "TT_AWAY", "ALT_SPREAD", "ALT_TOTAL"}
TOTAL_LIKE = {"TOTAL", "ALT_TOTAL", "TT_HOME", "TT_AWAY"}
LINE_RANGES = {("FG", "TOTAL"): (80, 220), ("FG", "ALT_TOTAL"): (80, 220), ("1H", "TOTAL"): (30, 120),
               ("1H", "ALT_TOTAL"): (30, 120), ("FG", "TT_HOME"): (30, 130), ("FG", "TT_AWAY"): (30, 130),
               ("1H", "TT_HOME"): (10, 70), ("1H", "TT_AWAY"): (10, 70)}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("&", ""))


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, header, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, header, extrasaction="ignore", lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(buf.getvalue(), encoding="utf-8")


# ----------------------------------------------------------------- prices
def american(v):
    s = str(v or "").strip()
    if not re.fullmatch(r"[+-]?\d+", s):
        return None
    x = int(s)
    return x if abs(x) >= 100 else None


def implied(x):
    return 100.0 / (x + 100.0) if x > 0 else -x / (-x + 100.0)


def fnum(v):
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


# ----------------------------------------------------------------- event crosswalk
def build_event_crosswalk(games, page_records, sitemap_ids=frozenset()):
    """games: list of (away, home, tip_utc). Returns one crosswalk row per game.

    An ID is VERIFIED only if a public DK event page (HTTP 200) for it shows leagueId 92483,
    Away participant == board away and Home participant == board home (exact DK spelling),
    startEventDate within 15 min of board tip, and the binding is one-to-one.
    """
    latest = {}
    for r in page_records:
        if r.get("page"):
            prev = latest.get(r["event_id"])
            if prev is None or r["retrieved_utc"] > prev["retrieved_utc"]:
                latest[r["event_id"]] = r
    probed = sorted({int(r["event_id"]) for r in page_records})
    by_pair = defaultdict(list)
    for r in latest.values():
        roles = EV.participants_by_role(r["page"])
        if "Away" in roles and "Home" in roles:
            by_pair[(roles["Away"]["name"], roles["Home"]["name"])].append(r)
    out, used = [], Counter()
    for away, home, tip in games:
        row = {"board_away": away, "board_home": home, "board_tip_utc": tip, "dk_event_id": "",
               "dk_event_name": "", "dk_away_participant_id": "", "dk_home_participant_id": "",
               "dk_league_id": "", "dk_start_utc": "", "dk_event_status_at_retrieval": "",
               "request_url": "", "final_url": "", "retrieved_utc": "", "html_sha256": "",
               "discovery": "", "state": S.EID_MISSING, "reason": ""}
        cands = by_pair.get((away, home), [])
        reasons, good = [], []
        for r in cands:
            p = r["page"]
            if p.get("leagueId") != EV.NCAAB_MEN_LEAGUE_ID:
                reasons.append(f"{r['event_id']}:DK_EVENT_NOT_NCAAB_MEN"); continue
            try:
                dt = abs(EV.parse_utc(p["startEventDate"]) - EV.parse_utc(tip))
            except (ValueError, TypeError, KeyError):
                reasons.append(f"{r['event_id']}:DK_EVENT_TIP_MISMATCH"); continue
            if dt > TIP_TOLERANCE:
                reasons.append(f"{r['event_id']}:DK_EVENT_TIP_MISMATCH({int(dt.total_seconds()//60)}min)"); continue
            good.append(r)
        if len(good) == 1:
            r = good[0]; p = r["page"]; roles = EV.participants_by_role(p)
            row.update({"dk_event_id": r["event_id"], "dk_event_name": p.get("eventName") or "",
                        "dk_away_participant_id": roles["Away"].get("id") or "",
                        "dk_home_participant_id": roles["Home"].get("id") or "",
                        "dk_league_id": p.get("leagueId") or "", "dk_start_utc": p.get("startEventDate") or "",
                        "dk_event_status_at_retrieval": p.get("eventStatus") or "",
                        "request_url": r["request_url"], "final_url": r["final_url"],
                        "retrieved_utc": r["retrieved_utc"], "html_sha256": r.get("html_sha256", ""),
                        "discovery": "SITEMAP+EVENT_PAGE" if r["event_id"] in sitemap_ids else "ID_PROBE+EVENT_PAGE",
                        "state": S.EID_VERIFIED})
            used[r["event_id"]] += 1
        else:
            span = (f"{probed[0]}-{probed[-1]}" if probed else "none")
            row["reason"] = ("DK_EVENT_ID_MISSING: no public DK event page with exact away/home names "
                             f"(sitemap snapshot + {len(probed)} IDs probed in {span})"
                             if not good and not reasons else
                             "DK_EVENT_ID_MISSING: " + (";".join(reasons) if not good else "multiple candidate events"))
        out.append(row)
    for row in out:
        if row["dk_event_id"] and used[row["dk_event_id"]] != 1:
            row.update({"state": S.EID_MISSING, "reason": "DK_EVENT_ID_MISSING: event bound to >1 board game",
                        "dk_event_id": ""})
    return out


# ----------------------------------------------------------------- ESPN venue/neutral
def match_espn(games, espn_events, team_aliases):
    """team_aliases: board name -> ESPN location (explicit, from the team crosswalk)."""
    out = {}
    for away, home, tip in games:
        def keys(t):
            return {norm(t.get("location") or ""), norm(t.get("shortDisplayName") or ""), norm(t.get("abbreviation") or "")}
        want_h = {norm(home), norm(team_aliases.get(home, ""))} - {""}
        want_a = {norm(away), norm(team_aliases.get(away, ""))} - {""}
        hits = [e for e in espn_events if e["date"][:16] == tip[:16]
                and keys(e["home"]) & want_h and keys(e["away"]) & want_a]
        out[(away, home, tip)] = hits[0] if len(hits) == 1 else None
    return out


# ----------------------------------------------------------------- core
def _gkey(r):
    return (r["away"], r["home"], r["tip_utc"])


def _family_key(r):
    return (_gkey(r), r["period"], r["market"], r.get("player") or "")


def load_captures(pdf_original, pdf_corrected, transcript):
    """Return (rows, truncated_original_rows). Rows carry capture metadata."""
    orig = read_csv(pdf_original)
    corr = read_csv(pdf_corrected)
    if len(orig) != len(corr):
        raise ValueError("corrected copy row count differs from original")
    rows, truncated = [], []
    for i, (o, c) in enumerate(zip(orig, corr), start=2):
        changed = any(o[k] != c[k] for k in o)
        if changed:
            truncated.append(dict(o, capture_id="pdf_0636CT_original", source_file=Path(pdf_original).name, source_row=i))
        rows.append(dict(c, capture_id="pdf_0636CT", source_file=Path(pdf_corrected).name, source_row=i,
                         provenance=S.PROV_PDF_RETRANSCRIBED if changed else S.PROV_PDF))
    for i, t in enumerate(read_csv(transcript), start=2):
        rows.append(dict(t, capture_id="transcript_0517_0534CT", source_file=Path(transcript).name, source_row=i,
                         provenance=S.PROV_TRANSCRIPT))
    return rows, truncated


def _price_checks(r, reasons):
    m = r["market"]
    pa, pb = american(r.get("price_a")), american(r.get("price_b"))
    one_sided = not str(r.get("price_b") or "").strip()
    if one_sided:
        reasons.append("ONE_SIDED_QUOTE")
        if r.get("player") and "player team not established" in (r.get("note") or ""):
            reasons.append("PLAYER_TEAM_NOT_ESTABLISHED")
        return None
    if pa is None or pb is None:
        reasons.append("PRICE_INVALID_AMERICAN"); return None
    ia, ib = implied(pa), implied(pb)
    if m in SUPPORTED and not 1.0 <= ia + ib <= 1.15:   # unsupported families need not be complementary pairs
        reasons.append("PRICE_PAIR_IMPLAUSIBLE")
    line = fnum(r.get("line"))
    if m == "ML":
        if str(r.get("line") or "").strip():
            reasons.append("LINE_INVALID")
    elif m in ("SPREAD", "ALT_SPREAD"):
        if line is None or abs(line) > 60 or (line * 2) % 1:
            reasons.append("LINE_INVALID")
    elif m in TOTAL_LIKE:
        lo, hi = LINE_RANGES.get((r["period"], m), (0, 999))
        if line is None or not lo <= line <= hi or (line * 2) % 1:
            reasons.append("LINE_INVALID")
    return ia, ib


def _novig_home_or_over(r):
    pa, pb = american(r.get("price_a")), american(r.get("price_b"))
    if pa is None or pb is None:
        return None
    ia, ib = implied(pa), implied(pb)
    return ia / (ia + ib)


def market_identity_checks(rows):
    """In-board consistency checks per (capture, game, period). Returns dict row_index -> [reasons], info."""
    flags = defaultdict(list)
    info = {"orientation": {}, "totals_order": {}, "tt": {}, "alt_spread": {}}
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["capture_id"], _gkey(r), r["period"])].append(i)
    for key, idx in groups.items():
        by = defaultdict(list)
        for i in idx:
            by[rows[i]["market"]].append(i)
        sp = by.get("SPREAD", []); ml = by.get("ML", []); tot = by.get("TOTAL", [])
        # 1. spread favourite vs moneyline favourite (price_a = home)
        if len(sp) == 1 and len(ml) == 1:
            L = fnum(rows[sp[0]]["line"]); q = _novig_home_or_over(rows[ml[0]])
            if L is not None and q is not None and L != 0:
                ok = (L < 0) == (q > 0.5)
                info["orientation"][key] = "AGREE" if ok else "CONFLICT"
                if not ok:
                    for i in sp + ml:
                        flags[i].append("ORIENTATION_SPREAD_VS_ML_CONFLICT")
        # 2. team totals vs main
        th, ta = by.get("TT_HOME", []), by.get("TT_AWAY", [])
        if len(th) == 1 and len(ta) == 1 and len(tot) == 1 and len(sp) == 1:
            H, A = fnum(rows[th[0]]["line"]), fnum(rows[ta[0]]["line"])
            T, L = fnum(rows[tot[0]]["line"]), fnum(rows[sp[0]]["line"])
            if None not in (H, A, T, L):
                dsum, dmar = abs(H + A - T), abs((H - A) - (-L))
                ok = dsum <= TT_TOLERANCE and dmar <= TT_TOLERANCE
                info["tt"][key] = {"sum_diff": round(dsum, 2), "margin_diff": round(dmar, 2), "ok": ok}
                if not ok:
                    for i in th + ta:
                        flags[i].append("TT_INCONSISTENT_WITH_MAIN")
        # 3. totals order via alternate total vs main total
        if len(tot) == 1 and by.get("ALT_TOTAL"):
            T = fnum(rows[tot[0]]["line"]); qm = _novig_home_or_over(rows[tot[0]])
            verdicts = []
            for i in by["ALT_TOTAL"]:
                A = fnum(rows[i]["line"]); qa = _novig_home_or_over(rows[i])
                if None in (T, A, qm, qa) or A == T or abs(qa - qm) < 1e-9:
                    continue   # equal no-vig probabilities carry no order information
                verdicts.append((A < T) == (qa > qm))
            if verdicts:
                v = "SUPPORTED" if all(verdicts) else "CONFLICT"
                info["totals_order"][key] = v
                if v == "CONFLICT":
                    for i in tot + by["ALT_TOTAL"]:
                        flags[i].append("TOTALS_ORDER_CONFLICT")
        # 4. alternate spread vs main spread (price_a = home)
        if len(sp) == 1 and by.get("ALT_SPREAD"):
            L = fnum(rows[sp[0]]["line"]); qm = _novig_home_or_over(rows[sp[0]])
            verdicts = []
            for i in by["ALT_SPREAD"]:
                A = fnum(rows[i]["line"]); qa = _novig_home_or_over(rows[i])
                if None in (L, A, qm, qa) or A == L or abs(qa - qm) < 1e-9:
                    continue
                verdicts.append((A > L) == (qa > qm))   # more points for home -> higher home cover prob
            if verdicts:
                v = "AGREE" if all(verdicts) else "CONFLICT"
                info["alt_spread"][key] = v
                if v == "CONFLICT":
                    for i in sp + by["ALT_SPREAD"]:
                        flags[i].append("ALT_SPREAD_ORIENTATION_CONFLICT")
    return flags, info


def transcript_explicit_totals_order(markdown_text, transcript_rows):
    """The operator markdown states 'Total O<line>, <price>' and 'Total U<line>, <price>' explicitly.
    Returns True when the transcript CSV main TOTAL row puts the stated Over price in price_a."""
    m_o = re.search(r"Total O(\d+(?:\.\d)?), ([+-]\d+)", markdown_text)
    m_u = re.search(r"Total U(\d+(?:\.\d)?), ([+-]\d+)", markdown_text)
    if not (m_o and m_u):
        return False
    for r in transcript_rows:
        if r["market"] == "TOTAL" and r["period"] == "FG":
            return (fnum(r["line"]) == float(m_o.group(1)) and american(r["price_a"]) == int(m_o.group(2))
                    and american(r["price_b"]) == int(m_u.group(2)))
    return False


def reconcile(rows, truncated, event_xw, espn_by_game, team_xw, *, as_of_utc=None,
              transcript_totals_verified=False, require_authenticated=False,
              issue57_hold_games=frozenset()):
    xw = {(r["board_away"], r["board_home"], r["board_tip_utc"]): r for r in event_xw}
    canon = {r["board_name"]: r for r in team_xw}
    flags, info = market_identity_checks(rows)
    # supersession: a later capture of the same (game, period, market family, player) wins
    latest_cap = {}
    for r in rows:
        k = _family_key(r)
        if k not in latest_cap or r["captured_utc"] > latest_cap[k][0]:
            latest_cap[k] = (r["captured_utc"], r["capture_id"])
    derived, ledger = [], []
    for i, r in enumerate(rows):
        reasons, notes = [], []
        g = _gkey(r); x = xw.get(g) or {}
        board_id = (r.get("dk_event_id") or "").strip()
        eid, state = "", S.EID_MISSING
        if x.get("state") == S.EID_VERIFIED:
            if board_id and board_id != x["dk_event_id"]:
                reasons.append("DK_EVENT_TEAM_MISMATCH"); notes.append(f"board id {board_id} != verified {x['dk_event_id']}")
            else:
                eid = x["dk_event_id"]; state = S.EID_BOARD_VERIFIED if board_id else S.EID_VERIFIED
        else:
            reasons.append("DK_EVENT_ID_MISSING")
            if board_id:
                notes.append(f"board carried {board_id} but no public page confirmed it")
        try:
            tip = EV.parse_utc(r["tip_utc"]); cap = EV.parse_utc(r["captured_utc"])
            if cap >= tip:
                reasons.append("LIVE_AT_CAPTURE")
            if as_of_utc is not None and as_of_utc >= tip:
                reasons.append("STARTED_BEFORE_AS_OF")
            tip_ct = tip.astimezone(CT).strftime("%Y-%m-%d %H:%M CT")
        except (ValueError, KeyError):
            reasons.append("LINE_INVALID"); notes.append("tip/capture clock unparsable"); tip_ct = ""
        imp = _price_checks(r, reasons)
        m = r["market"]
        if m not in SUPPORTED and "ONE_SIDED_QUOTE" not in reasons:
            reasons.append("UNSUPPORTED_MARKET")
        if "selected rung only" in (r.get("note") or ""):
            notes.append("SELECTED_RUNG_ONLY")
        reasons += flags.get(i, [])
        key = (r["capture_id"], g, r["period"])
        totals_order = ""
        if m in TOTAL_LIKE and imp is not None:
            if r["provenance"] == S.PROV_PDF_RETRANSCRIBED and m == "TOTAL":
                totals_order = "over_under"; notes.append("over/under order stated in PR #530 re-transcription")
            elif r["capture_id"].startswith("transcript") and m in ("TOTAL", "ALT_TOTAL") and transcript_totals_verified:
                totals_order = "over_under"; notes.append("over/under order matches explicit O/U text in operator markdown")
            elif m in ("TOTAL", "ALT_TOTAL") and info["totals_order"].get(key) == "SUPPORTED":
                totals_order = "over_under"; notes.append("alt-vs-main total prices support price_a=over")
            elif "TOTALS_ORDER_CONFLICT" not in reasons:
                reasons.append("TOTALS_ORDER_UNVERIFIED")
        if latest_cap[_family_key(r)][1] != r["capture_id"]:
            reasons.append("SUPERSEDED_BY_LATER_CAPTURE")
        if g in issue57_hold_games:
            reasons.append("ISSUE57_ORIENTATION_HOLD")
        if require_authenticated and r["provenance"] != S.PROV_AUTHENTICATED:
            reasons.append("UNAUTHENTICATED_SOURCE")
        soft = {"TOTALS_ORDER_UNVERIFIED", "ISSUE57_ORIENTATION_HOLD"}
        if "SUPERSEDED_BY_LATER_CAPTURE" in reasons and not (set(reasons) - soft - {"SUPERSEDED_BY_LATER_CAPTURE", "DK_EVENT_ID_MISSING"}):
            disp = S.SUPERSEDED
        elif set(reasons) - soft:
            disp = S.REJECTED
        elif reasons:
            disp = S.HELD
        else:
            disp = S.ACCEPTED
        e = espn_by_game.get(g)
        d = S.DerivedRow(
            sport=r.get("sport", "CBB"), away=r["away"], home=r["home"], market=m, line=r.get("line", ""),
            price_a=r.get("price_a", ""), price_b=r.get("price_b", ""), period=r["period"], player=r.get("player", ""),
            tip_utc=r["tip_utc"], captured_utc=r["captured_utc"], dk_event_id=eid,
            row_key=f"{r['capture_id']}:{r['source_row']}", capture_id=r["capture_id"], source_file=r["source_file"],
            source_row=r["source_row"], provenance=r["provenance"], authenticated=int(r["provenance"] == S.PROV_AUTHENTICATED),
            dk_event_id_state=state, dk_event_url=x.get("final_url", "") if eid else "",
            dk_event_retrieved_utc=x.get("retrieved_utc", "") if eid else "", dk_start_utc=x.get("dk_start_utc", "") if eid else "",
            away_canonical=(canon.get(r["away"]) or {}).get("cbbd_norm_key", ""),
            home_canonical=(canon.get(r["home"]) or {}).get("cbbd_norm_key", ""),
            espn_event_id=e["espn_event_id"] if e else "", neutral_site=("1" if e["neutral_site"] else "0") if e else "",
            venue=e["venue"] if e else "", tip_ct=tip_ct,
            implied_a=f"{imp[0]:.6f}" if imp else "", implied_b=f"{imp[1]:.6f}" if imp else "",
            novig_a=f"{imp[0]/(imp[0]+imp[1]):.6f}" if imp else "", novig_b=f"{imp[1]/(imp[0]+imp[1]):.6f}" if imp else "",
            totals_order=totals_order, disposition=disp, reason_codes=";".join(dict.fromkeys(reasons)),
            notes="; ".join(notes))
        if not e:
            d.notes = "; ".join(filter(None, [d.notes, "ESPN_EVENT_UNMATCHED"]))
        derived.append(d)
    for t in truncated:
        ledger.append({"row_key": f"{t['capture_id']}:{t['source_row']}", "capture_id": t["capture_id"],
                       "source_file": t["source_file"], "source_row": t["source_row"], "away": t["away"], "home": t["home"],
                       "period": t["period"], "market": t["market"], "line": t["line"], "player": t.get("player", ""),
                       "price_a": t["price_a"], "price_b": t["price_b"], "disposition": S.REJECTED,
                       "reason_codes": "LINE_TRUNCATED_SUPERSEDED_PR530",
                       "reason_text": S.REASONS["LINE_TRUNCATED_SUPERSEDED_PR530"], "notes": "original row kept unchanged on main"})
    for d in derived:
        if d.disposition != S.ACCEPTED:
            ledger.append({"row_key": d.row_key, "capture_id": d.capture_id, "source_file": d.source_file,
                           "source_row": d.source_row, "away": d.away, "home": d.home, "period": d.period,
                           "market": d.market, "line": d.line, "player": d.player, "price_a": d.price_a,
                           "price_b": d.price_b, "disposition": d.disposition, "reason_codes": d.reason_codes,
                           "reason_text": " | ".join(S.REASONS[c] for c in d.reason_codes.split(";") if c),
                           "notes": d.notes})
    return derived, ledger, info


# Dated games that must never enter a pregame runner board, even if a later
# research ruling accepts their orientation. Owner, Nov 25: St Bonaventure -4.5 /
# Belmont +4.5 is accepted for retrospective research only; ISSUE57 hold is kept
# and this matchup is excluded from any pregame card.
PREGAME_EXCLUSIONS = frozenset({
    ("Saint Bonaventure", "Belmont", "2026-11-25T15:00:00Z"),
})


def runner_board(derived):
    """Rows the runner may ingest: ACCEPTED or HELD-only-for-totals-order (runner keeps its own totals gate).
    Same leading columns as the original boards plus totals_order and provenance."""
    keep = []
    for d in derived:
        if (d.away, d.home, d.tip_utc) in PREGAME_EXCLUSIONS:
            continue
        codes = set(filter(None, d.reason_codes.split(";")))
        if d.disposition == S.ACCEPTED or (d.disposition == S.HELD and codes == {"TOTALS_ORDER_UNVERIFIED"}):
            keep.append(d.as_dict())
    return keep


RUNNER_COLUMNS = ["sport", "away", "home", "market", "line", "price_a", "price_b", "period", "player", "tip_utc",
                  "captured_utc", "dk_event_id", "totals_order", "provenance", "authenticated", "row_key", "notes"]


def espn_orientation_check(derived, espn_by_game):
    """Soft cross-check: board FG spread favourite (price_a=home) vs ESPN's CURRENT DraftKings-labelled
    feed at retrieval. Lines move between capture and retrieval, so disagreement is reported, not rejected."""
    out = []
    for d in derived:
        if d.capture_id != "pdf_0636CT" or d.period != "FG" or d.market != "SPREAD":
            continue
        e = espn_by_game.get((d.away, d.home, d.tip_utc))
        o = (e or {}).get("odds") or {}
        L = fnum(d.line)
        if L is None or L == 0 or o.get("home_favorite") is None:
            out.append({"game": f"{d.away} @ {d.home}", "board_home_line": d.line, "espn": o.get("details"), "verdict": "NO_FEED"})
            continue
        agree = (L < 0) == bool(o["home_favorite"])
        out.append({"game": f"{d.away} @ {d.home}", "board_home_line": d.line, "espn": o.get("details"),
                    "espn_home_spread": o.get("spread"), "verdict": "AGREE" if agree else "DIFFERS"})
    return out


def cross_capture_diff(rows, game):
    """Same game captured twice: compare matching (period, market[, line for ladders/players]) rows."""
    caps = defaultdict(dict)
    for r in rows:
        if _gkey(r)[:2] != game:
            continue
        k = (r["period"], r["market"], r.get("player") or "",
             r["line"] if r["market"] in ("ALT_SPREAD", "ALT_TOTAL") or r.get("player") else "")
        caps[r["capture_id"]][k] = r
    ids = sorted(caps)
    out = []
    if len(ids) < 2:
        return out
    a, b = caps[ids[0]], caps[ids[1]]
    for k in sorted(set(a) & set(b)):
        ra, rb = a[k], b[k]
        out.append({"period": k[0], "market": k[1], "player": k[2],
                    ids[0]: {"captured_utc": ra["captured_utc"], "line": ra["line"], "price_a": ra["price_a"], "price_b": ra.get("price_b", "")},
                    ids[1]: {"captured_utc": rb["captured_utc"], "line": rb["line"], "price_a": rb["price_a"], "price_b": rb.get("price_b", "")},
                    "same_line": fnum(ra["line"]) == fnum(rb["line"]),
                    "same_prices": (ra["price_a"].lstrip("+"), (ra.get("price_b") or "").lstrip("+")) == (rb["price_a"].lstrip("+"), (rb.get("price_b") or "").lstrip("+"))})
    return out
