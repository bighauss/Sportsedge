#!/usr/bin/env python3
"""CBB RUN IT: live capture -> frozen CBBD-native model (via the existing paper-card builder)
-> paper ledger -> sanitized card. PAPER / 0u.

Reuses, unchanged: daily_ratings_capture (CBBD adjusted ratings + receipt),
cbbd_prospective_capture.capture_games (original /games bytes + manifest),
cbbd_paper_card.build_card (frozen model, venue gate, quote gate, no-vig pricing),
cbbd_paper_ledger.card_entries/append (hash-chained ledger).

New here (adapters only, no model code):
  * /games/teams capture -> prior finals with possessions (rows without both teams'
    possessions are dropped; never estimated)
  * slate from CBBD /games for the Central-time date
  * ESPN scoreboard -> venue registry rows (neutral flag must AGREE with CBBD in build_card)
  * DraftKings board CSV -> quotes keyed by exact CBBD game_id (exact normalized names +
    explicit aliases; unmatched rows are listed, never guessed). price_a = home / over.
"""
from __future__ import annotations
from collections import Counter
import argparse, csv, hashlib, io, json, os, re, sys, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import cbbd_paper_card as PC                       # noqa: E402
import cbbd_paper_ledger as LG                     # noqa: E402
import cbb_pricing as PR                           # noqa: E402
from cbbd_native_score_model import stamp          # noqa: E402

CT = ZoneInfo("America/Chicago")
BOX_URL = "https://api.collegebasketballdata.com/games/teams"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
ALIASES = {"saintpeters": ["saintpeters", "stpeters"], "albanyny": ["ualbany", "albany"],
           "queensnc": ["queens", "queensuniversity"], "amcorpuschristi": ["texasamcorpuschristi"],
           "saintthomasmn": ["stthomasminnesota", "stthomas"], "pennsylvania": ["penn", "pennsylvania"],
           "utriograndevalley": ["utriograndevalley", "utrgv"], "etsu": ["easttennesseestate", "etsu"],
           "uncgreensboro": ["uncgreensboro", "ncgreensboro"], "uncwilmington": ["uncwilmington"],
           "uscupstate": ["southcarolinaupstate", "uscupstate"], "umass": ["massachusetts", "umass"],
           "littlerock": ["littlerock", "arkansaslittlerock"], "detroitmercy": ["detroitmercy"],
           "californiabaptist": ["californiabaptist", "calbaptist"], "nichollsstate": ["nicholls", "nichollsstate"]}

class Hold(Exception):
    pass

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("&", ""))

def cands(name):
    n = norm(name)
    return [n] + [a for a in ALIASES.get(n, []) if a != n]

def sha(b):
    return hashlib.sha256(b).hexdigest()

def utcz(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_z(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

# ---------------------------------------------------------------- captures (live only)
def _get(url, key=None):
    h = {"Accept": "application/json", "User-Agent": "SportsEdgeResearchCapture/1.0"}
    if key: h["Authorization"] = "Bearer " + key
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        if r.status != 200: raise Hold(f"HTTP_{r.status}")
        b = r.read()
    if key and key.encode() in b: raise Hold("SECRET_ECHO")
    return b

def capture_raw(name, url, private_dir, key=None, get=_get):
    """One GET; original bytes create-only in private_dir; public receipt returned."""
    b = get(url, key)
    obs = datetime.now(timezone.utc)
    p = Path(private_dir) / f"{name}.raw.json"
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f: f.write(b)
    return json.loads(b), {"source": name, "bytes": len(b), "sha256": sha(b), "observed_utc": utcz(obs),
                           "url_without_credentials": url}

# ---------------------------------------------------------------- adapters (pure)
def prior_games(games, boxes, observed_utc, season):
    """Finals before observation with possessions = mean of both teams' teamStats.possessions."""
    poss = {}
    for b in boxes:
        gid, tid, p = b.get("gameId"), b.get("teamId"), (b.get("teamStats") or {}).get("possessions")
        if gid is not None and tid is not None and type(p) in (int, float):
            poss.setdefault(str(gid), []).append((str(tid), float(p)))
    ids = {}
    for g in games:
        ids[str(g.get("id"))] = ids.get(str(g.get("id")), 0) + 1
    out, census = [], {"finals": 0, "no_possessions": 0, "duplicate_game_id": 0, "team_mismatch": 0}
    obs = parse_z(observed_utc)
    for g in games:
        if g.get("status") != "final" or g.get("startTimeTbd") is not False:
            continue
        if parse_z(g["startDate"]) >= obs:
            continue
        if ids[str(g["id"])] > 1:
            census["duplicate_game_id"] += 1; continue
        # An unknown neutral flag cannot be treated as a true home game:
        # HCA is fitted from non-neutral prior finals.
        if type(g.get("neutralSite")) is not bool:
            census["neutral_unknown"] = census.get("neutral_unknown", 0) + 1; continue
        rows = poss.get(str(g["id"]), [])
        if len(rows) != 2:
            census["no_possessions"] += 1; continue
        if {t for t, _ in rows} != {str(g["homeTeamId"]), str(g["awayTeamId"])}:
            census["team_mismatch"] += 1; continue
        ps = [p for _, p in rows]
        census["finals"] += 1
        out.append({"game_id": str(g["id"]), "season": season, "tipoff_utc": utcz(parse_z(g["startDate"])),
                    "final_captured_utc": observed_utc, "home_team_id": str(g["homeTeamId"]),
                    "away_team_id": str(g["awayTeamId"]), "neutral": g["neutralSite"],
                    "home_points": g.get("homePoints"), "away_points": g.get("awayPoints"),
                    "possessions": sum(ps) / 2})
    return out, census

def slate(games, day_ct, now_utc, season, misses=None):
    rows = []
    for g in games:
        tip = parse_z(g["startDate"])
        if tip.astimezone(CT).date() != day_ct or tip <= now_utc or g.get("startTimeTbd") is not False:
            continue
        if type(g.get("neutralSite")) is not bool:
            if misses is not None:
                misses.append((str(g["id"]), "CBBD neutral-site flag unknown"))
            continue
        rows.append({"game_id": str(g["id"]), "season": str(season), "tipoff_utc": utcz(tip),
                     "home_team_id": str(g["homeTeamId"]), "away_team_id": str(g["awayTeamId"]),
                     "neutral": "1" if g.get("neutralSite") else "0",
                     "_home": g.get("homeTeam"), "_away": g.get("awayTeam")})
    return rows

TIP_WINDOW_S = 900

def board_tip(row):
    """Board tip time (UTC) from optional columns, None if absent; ValueError if present but bad."""
    raw = next((str(row[k]).strip() for k in ("tip_utc", "start_utc") if row and str(row.get(k) or "").strip()), "")
    if not raw: return None
    d = parse_z(raw)
    if d.tzinfo is None: raise ValueError("TIP_NOT_UTC")
    return d

def board_event_id(row):
    return next((str(row[k]).strip() for k in ("dk_event_id", "event_id") if row and str(row.get(k) or "").strip()), None)

def _match(slate_rows, home, away, row=None):
    """Names must match exactly; when the board carries a tip time it must be within 15 min of the
    CBBD tip (this also separates same-name doubleheaders). DK event IDs are bound in board_quotes."""
    hs, as_ = set(cands(home)), set(cands(away))
    hits = [r for r in slate_rows if norm(r["_home"]) in hs and norm(r["_away"]) in as_]
    try:
        tip = board_tip(row)
    except ValueError:
        return None, "board tip time unparsable"
    if tip is not None:
        hits = [r for r in hits if abs((parse_z(r["tipoff_utc"]) - tip).total_seconds()) <= TIP_WINDOW_S]
        if not hits: return None, "no CBBD game within 15 min of board tip time"
    if len(hits) == 1: return hits[0], None
    rev = [r for r in slate_rows if norm(r["_home"]) in as_ and norm(r["_away"]) in hs]
    return None, ("home/away orientation mismatch" if rev else "no unique CBBD game for names" if not hits
                  else "ambiguous CBBD game")

def registry(slate_rows, espn, espn_sha, captured_utc):
    """Venue-only reconciliation. Reverse team designation is admissible ONLY when
    both providers explicitly say neutral; no odds orientation or quote is changed.
    All candidate games still require exact normalized teams, a unique ESPN
    competition and the existing 15-minute window. Ambiguous reuse fails closed.
    """
    rows, miss, evs, proposed = [], [], [], []
    for e in espn.get("events", []):
        competitions = e.get("competitions") or []
        if len(competitions) != 1:
            continue
        c = competitions[0]
        competitors = c.get("competitors") or []
        if len(competitors) != 2 or {x.get("homeAway") for x in competitors} != {"home", "away"}:
            continue
        teams = {x["homeAway"]: x.get("team") or {} for x in competitors}
        try:
            tip = parse_z(c["date"])
            if tip.utcoffset() is None:
                continue
        except (ValueError, TypeError, AttributeError, KeyError):
            continue
        names = {side: {norm(t.get(k, "")) for k in ("location", "shortDisplayName", "displayName")
                        if isinstance(t.get(k), str) and norm(t[k])} for side, t in teams.items()}
        evs.append((names, tip, c))
    for r in slate_rows:
        tip = parse_z(r["tipoff_utc"])
        h, a = norm(r["_home"]), norm(r["_away"])
        hit = []
        if h and a and h != a:
            for i, (names, etip, c) in enumerate(evs):
                if abs((etip - tip).total_seconds()) > TIP_WINDOW_S:
                    continue
                direct = h in names["home"] and a in names["away"]
                reverse = h in names["away"] and a in names["home"]
                if direct or reverse:
                    hit.append((i, c, direct, reverse))
        if len(hit) != 1:
            miss.append((r["game_id"], "ESPN event not uniquely matched"))
            continue
        i, c, direct, reverse = hit[0]
        if direct and reverse:
            miss.append((r["game_id"], "ESPN team orientation ambiguous"))
            continue
        if type(c.get("neutralSite")) is not bool:
            miss.append((r["game_id"], "ESPN neutral-site flag missing or not boolean"))
            continue
        if reverse and not (r.get("neutral") == "1" and c["neutralSite"] is True):
            miss.append((r["game_id"], "ESPN reversed designation requires both providers neutral"))
            continue
        proposed.append((i, r, c))
    used = Counter(i for i, _, _ in proposed)
    for i, r, c in proposed:
        if used[i] != 1:
            miss.append((r["game_id"], "ESPN event reused across CBBD games"))
            continue
        rows.append({"game_id": r["game_id"], "neutral": "1" if c["neutralSite"] else "0",
                     "source": "ESPN", "source_sha256": espn_sha, "published_utc": captured_utc,
                     "captured_utc": captured_utc, "tipoff_utc": r["tipoff_utc"]})
    return rows, miss


MK = {"SPREAD": "spread", "TOTAL": "total", "ML": "moneyline"}

# Spread/ML price_a = home was verified 43/43 (spread sign vs moneyline favourite) on the
# 11/21 Drive board. Total order was checked against same-morning screenshots: 30 agree,
# 4 reversed -> unverified, so totals are withheld until a board format proves it.
TOTALS_ORDER_VERIFIED = False

def _totals_order(row, verified):
    """Totals price order is bound to the BOARD FORMAT, never a global flip: a run-level
    verified flag or a per-row totals_order column ('over_under' = verified, 'under_over' = swap)."""
    t = str(row.get("totals_order") or "").strip().lower()
    if t == "under_over": return "swap"
    if t == "over_under" or (not t and verified): return "ok"
    return None

def board_quotes(board_rows, slate_rows, captured_utc, book="DraftKings",
                 totals_order_verified=TOTALS_ORDER_VERIFIED):
    matched, unmatched = [], []
    for b in board_rows:
        if b.get("sport") != "CBB" or b.get("market") not in MK: continue
        if not PR.full_game_period(b):
            unmatched.append((f"{b['away']} @ {b['home']}", b["market"],
                              "UNSUPPORTED_PERIOD: full-game model cannot price period quote"))
            continue
        order = _totals_order(b, totals_order_verified) if b["market"] == "TOTAL" else "ok"
        if order is None:
            unmatched.append((f"{b['away']} @ {b['home']}", "TOTAL",
                              "over/under price order not verified for this board format")); continue
        g, why = _match(slate_rows, b["home"], b["away"], b)
        if not g:
            unmatched.append((f"{b['away']} @ {b['home']}", b["market"], why)); continue
        matched.append((b, g, order))
    # DK event ID <-> CBBD game must be one-to-one; any conflict quarantines every copy.
    ev_games, game_evs = {}, {}
    for b, g, _ in matched:
        e = board_event_id(b)
        if e: ev_games.setdefault(e, set()).add(g["game_id"]); game_evs.setdefault(g["game_id"], set()).add(e)
    out = []
    for b, g, order in matched:
        e = board_event_id(b)
        if e and (len(ev_games[e]) > 1 or len(game_evs[g["game_id"]]) > 1):
            unmatched.append((f"{b['away']} @ {b['home']}", b["market"], "DK event id conflict")); continue
        pa, pb = (b["price_b"], b["price_a"]) if order == "swap" else (b["price_a"], b["price_b"])
        out.append({"game_id": g["game_id"], "market": MK[b["market"]], "book": book,
                    "line": b["line"] or None, "price_a": pa, "price_b": pb,
                    "captured_utc": str(b.get("captured_utc") or captured_utc)})
    return out, unmatched

def write_csv(path, header, rows):
    buf = io.StringIO(); w = csv.DictWriter(buf, header, extrasaction="ignore", lineterminator="\n")
    w.writeheader(); w.writerows(rows); Path(path).write_text(buf.getvalue(), encoding="utf-8")

# ---------------------------------------------------------------- orchestration
def diagnostic_ledger_entries(card):
    """Under the existing ledger lock: preserve first freezes; append only unseen games.

    The full current diagnostic card remains unchanged and is NOT a second freeze.
    The frozen subset carries its parent digest and its own exact row census.
    """
    def build(entries, now):
        if card.get("schema") != PC.CARD_SCHEMA or card.get("status") != PC.CARD_STATUS or \
                card.get("card_sha256") != PC.card_digest(card) or \
                card.get("official_counted") != 0 or card.get("approved_stake_u") != 0:
            raise LG.LedgerError("DIAGNOSTIC_CARD_INVALID")
        previous = {}
        for entry in entries:
            if entry["kind"] != "CARD_FROZEN":
                continue
            for row in entry["payload"]["rows"]:
                gid = row["game_id"]
                if gid in previous:
                    raise LG.LedgerError("DIAGNOSTIC_LEDGER_DUPLICATE_GAME")
                previous[gid] = row
        current_ids = [r["game_id"] for r in card["rows"]]
        if len(current_ids) != len(set(current_ids)):
            raise LG.LedgerError("DIAGNOSTIC_CARD_DUPLICATE_GAME")
        unseen, overlap = [], []
        for row in card["rows"]:
            old = previous.get(row["game_id"])
            if old is None:
                unseen.append(row)
                continue
            if any(str(old.get(k)) != str(row.get(k)) for k in
                   ("season", "home_team_id", "away_team_id")):
                raise LG.LedgerError("DIAGNOSTIC_GAME_IDENTITY_CONFLICT")
            overlap.append(row["game_id"])
        report = {"state": "DIAGNOSTIC_ONLY_EXISTING_GAMES" if not unseen else "CARD_FROZEN",
                  "rows": len(unseen), "already_frozen": len(overlap),
                  "newly_frozen": len(unseen), "source_card_sha256": card["card_sha256"]}
        if not unseen:
            return [], report
        if not overlap:
            payloads, _ = LG.card_entries(card)(entries, now)
            report["ledger_card_sha256"] = card["card_sha256"]
            return payloads, report
        subset = dict(card)
        subset["rows"] = [dict(row, input_index=i) for i, row in enumerate(unseen)]
        subset["row_count"] = len(unseen)
        subset["projected_rows"] = sum(r["status"] == "PROJECTED" for r in unseen)
        subset["priced_market_rows"] = sum(m["status"] == "PRICED_PAPER"
                                            for r in unseen for m in r["markets"])
        subset["pass_reason_counts"] = dict(sorted(Counter(r["pass_reason"] for r in unseen
                                                           if r["status"] == "PASS").items()))
        subset["ledger_subset"] = {"parent_card_sha256": card["card_sha256"],
                                   "parent_row_count": len(card["rows"]),
                                   "excluded_already_frozen": len(overlap),
                                   "parent_input_indices": [r["input_index"] for r in unseen],
                                   "quote_census_scope": "FULL_PARENT_INPUT"}
        subset["card_sha256"] = PC.card_digest(subset)
        payloads, _ = LG.card_entries(subset)(entries, now)
        report["ledger_card_sha256"] = subset["card_sha256"]
        return payloads, report
    return build


def build(*, work, season, now_utc, games, boxes, observed_utc, ratings_body, ratings_receipt,
          espn, espn_sha, espn_captured, board_rows, board_captured_utc, ledger_path=None,
          totals_order_verified=False, config=None, diagnostic_repeat=False):
    cfg = PR.make_config(**(config or {}))
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    day = now_utc.astimezone(CT).date()
    slate_miss = []
    s = slate(games, day, now_utc, season, slate_miss)
    pg, pcensus = prior_games(games, boxes, observed_utc, season)
    reg, reg_miss = registry(s, espn, espn_sha, espn_captured)
    reg_miss = slate_miss + reg_miss
    quotes, unmatched = board_quotes(board_rows, s, board_captured_utc,
                                     totals_order_verified=totals_order_verified)
    write_csv(work / "slate.csv", list(PC.SLATE_COLUMNS), s)
    write_csv(work / "registry.csv", ["game_id", "neutral", "source", "source_sha256", "published_utc",
                                      "captured_utc", "tipoff_utc"], reg)
    freeze = stamp(now_utc)
    with PR.patched_card(cfg):
        card = PC.build_card(freeze_utc=freeze, built_utc=freeze, season=season,
                             slate_path=work / "slate.csv", registry_path=work / "registry.csv",
                             ratings_body=ratings_body, ratings_receipt=ratings_receipt,
                             prior_games=pg, quotes=[(q, "OPERATOR") for q in quotes],
                             input_sha256={"espn_scoreboard": espn_sha})
    ladders, ladders_skipped = PR.price_ladders(
        board_rows, _match, s, card, cfg, board_captured_utc, event_id=board_event_id,
        totals_order=lambda b: _totals_order(b, totals_order_verified))
    ledger = None
    if ledger_path:
        entry_builder = diagnostic_ledger_entries(card) if diagnostic_repeat else LG.card_entries(card)
        ledger = LG.append(ledger_path, entry_builder, clock=lambda: now_utc)
    names = {r["game_id"]: (r["_away"], r["_home"], r["tipoff_utc"]) for r in s}
    extra = {"prior_census": pcensus, "registry_unmatched": reg_miss, "quotes_unmatched": unmatched,
             "slate_games": len(s), "ledger": ledger, "config": cfg, "ladders": ladders,
             "ladders_skipped": ladders_skipped, "board_rows": len(board_rows)}
    return card, names, extra

def _best(m):
    ev = m["paper_ev_per_1u_at_price"]; side = max(ev, key=ev.get)
    return side, ev[side]

def render(card, names, extra):
    o = ["# SportsEdge CBB RUN IT card", "",
         f"**PAPER / 0u — research only.** status {card['status']} · model {card['model_version']} "
         f"(sha {card['model_code_sha256'][:12]}) · card sha {card['card_sha256'][:12]}", "",
         f"Freeze {parse_z(card['freeze_utc']).astimezone(CT):%Y-%m-%d %-I:%M %p} CT · slate {extra['slate_games']} games · "
         f"projected {card['projected_rows']} · priced markets {card['priced_market_rows']} · "
         f"prior finals used {(card.get('context') or {}).get('prior_games_used')}", ""]
    if (extra.get("ledger") or {}).get("already_frozen", 0):
        report = extra["ledger"]
        o += [f"**Repeat diagnostic:** {report['already_frozen']} games retain their original ledger freeze; "
              f"{report['newly_frozen']} newly frozen. Current projections are not replacement records.", ""]
    cx = card.get("context") or {}
    if cx:
        h, sd = cx.get("hca") or {}, cx.get("sd") or {}
        o += [f"Model context: HCA {h.get('value')} (n {h.get('n')}, sd {h.get('sd')}) · predictive SD margin "
              f"{sd.get('margin')} / total {sd.get('total')} (basis {sd.get('basis')}, n {sd.get('n')}) · "
              f"league pace {cx.get('league_pace')} · league ORtg {cx.get('league_mean_ortg')}", ""]
    cfg = extra.get("config") or PR.DEFAULT_CONFIG
    o += [f"Config: SD margin {cfg['sd_margin']} / total {cfg['sd_total']} (constants, not fitted) · model-vs-market blend "
          f"weight on model {cfg['blend_weight_model']} (EXPERIMENTAL, chronological test pending; candidates "
          f"{[int(w*100) for w in PR.CANDIDATE_BLEND_WEIGHTS]}%) · spreads with |line| > {cfg['blowout_spread_abs']:g} excluded from best plays", ""]
    sides = [(_best(m)[0]) for r in card["rows"] for m in r["markets"] if m["status"] == "PRICED_PAPER"]
    if sides:
        from collections import Counter as _C
        o += [f"Side balance of best-EV picks: {dict(_C(sides))}", ""]
    if card.get("context_error"):
        o += [f"**Context error (all games PASS):** {card['context_error']}", ""]
    o += ["## Independent full-game score projections (before sportsbook prices)", "",
          "Home margin = projected home minus away score; team totals are expected team scores. "
          "No sportsbook line is needed for this section. No first-half or player-prop forecast is implied.", "",
          "| Game | Tip (CT) | Away points | Home points | Home margin | Total | Possessions | Status |",
          "|---|---|---:|---:|---:|---:|---:|---|"]
    for r in card["rows"]:
        a, h, tip = names.get(r["game_id"], ("?", "?", r["tipoff_utc"]))
        when = parse_z(tip).astimezone(CT).strftime("%-I:%M %p")
        if r["status"] != "PROJECTED":
            o.append(f"| {a} @ {h} | {when} | — | — | — | — | — | PASS: {r['pass_reason']} |")
            continue
        p = r["projection"]
        o.append(f"| {a} @ {h} | {when} | {p['away_points']:.2f} | {p['home_points']:.2f} | "
                 f"{p['margin']:+.2f} | {p['total']:.2f} | {p['possessions']:.2f} | PROJECTED |")
    o += ["", "**Pricing diagnostics below are not recommendations or validated positive EV.** "
          "The same-book blend is experimental, not independent market consensus. "
          "Large model-market disagreement, particularly longshots, requires calibration and event review.", ""]
    priced, blowouts = [], []
    for r in card["rows"]:
        for m in r["markets"]:
            if m["status"] == "PRICED_PAPER":
                side, ev = _best(m)
                (blowouts if m.get("blowout_excluded") else priced).append((ev, r, m, side))
    priced.sort(key=lambda x: -x[0])
    o += ["## Priced markets (diagnostic side by paper EV)", "",
          "| # | Game | Tip (CT) | Market | Side | Line | Price | p model | p no-vig | Paper EV | Blend EV (exp.) |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, (ev, r, m, side) in enumerate(priced, 1):
        a, h, tip = names.get(r["game_id"], ("?", "?", r["tipoff_utc"]))
        q = m["quote"]; price = q["price_a"] if side == m["sides"][0] else q["price_b"]
        line = "" if q["line"] is None else (f"{q['line']:g}" if m["market"] == "total"
                                             else f"{(q['line'] if side == 'home' else -q['line']):+g}")
        o.append(f"| {i} | {a} @ {h} | {parse_z(tip).astimezone(CT):%-I:%M %p} | {m['market']} | {side} | {line} | "
                 f"{price:+d} | {m['model_prob'][side]:.3f} | {m['market_novig_prob'][side]:.3f} | {ev*100:+.1f}% | "
                 f"{m['blend']['paper_ev_per_1u_at_price'][side]*100:+.1f}% |")
    if blowouts:
        o += ["", f"## Spreads excluded from best plays (|line| > {cfg['blowout_spread_abs']:g}: blowout-margin compression)", ""]
        for ev, r, m, side in blowouts:
            a, h, _ = names.get(r["game_id"], ("?", "?", ""))
            o.append(f"- {a} @ {h} spread {m['quote']['line']:+g}: model-best {side}, paper EV {ev*100:+.1f}% (not a best play)")
    if extra.get("ladders"):
        o += ["", "## Alt ladders and team totals (same projected mean/SD, normal; PAPER)", "",
              "| Game | Market | Line | Side | Price | p model | Paper EV | Blend EV (exp.) |", "|---|---|---|---|---|---|---|---|"]
        for L in sorted(extra["ladders"], key=lambda x: -max(x["paper_ev"])):
            a, h, _ = names.get(L["game_id"], ("?", "?", ""))
            i = 0 if L["paper_ev"][0] >= L["paper_ev"][1] else 1
            flag = " (blowout-excluded)" if L["blowout_excluded"] else ""
            o.append(f"| {a} @ {h} | {L['kind']}{flag} | {L['line']:g} | {L['sides'][i]} | {L['price'][i]:+d} | "
                     f"{L['model_prob'][i]:.3f} | {L['paper_ev'][i]*100:+.1f}% | {L['blend_ev'][i]*100:+.1f}% |")
    o += ["", "## Withheld", ""]
    o += [f"- {g} {mk}: ladder row skipped ({why})" for g, mk, why in extra.get("ladders_skipped", [])]
    for r in card["rows"]:
        a, h, _ = names.get(r["game_id"], ("?", "?", ""))
        if r["status"] == "PASS":
            o.append(f"- {a} @ {h}: {r['pass_reason']}")
        else:
            o += [f"- {a} @ {h} {m['market']}: {m['pass_reason']}" for m in r["markets"] if m["status"] == "PASS"]
    o += [f"- {g} {mk}: board row unmatched ({why})" for g, mk, why in extra["quotes_unmatched"]]
    o += [f"- game {g}: venue registry: {why}" for g, why in extra["registry_unmatched"]]
    o += ["", f"Prior-game census: {extra['prior_census']} · quote census: {card['quote_census']}",
          f"Ledger: {extra['ledger']}" if extra.get("ledger") else "Ledger: not written (no --ledger)", ""]
    return "\n".join(o)

def _archive(priv, name, b):
    p = Path(priv) / f"{name}.raw.json"
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f: f.write(b)

def replay(evidence_dir, season, out_dir):
    """SHADOW REPLAY: rebuild a card from a stored, decrypted evidence bundle.
    Read-only: never opens a ledger, never makes provider requests, reuses the original freeze
    time, and reports whether the replayed card matches the frozen original."""
    ev = Path(evidence_dir); cap = ev / "capture"
    def one(pattern):
        hits = sorted(cap.rglob(pattern))
        if len(hits) != 1: raise Hold(f"REPLAY_SOURCE_{pattern}_COUNT_{len(hits)}")
        return hits[0]
    original = json.loads((ev / "card" / "cbb_card.json").read_text())
    receipts = {r["source"]: r for r in json.loads((ev / "card" / "receipts.json").read_text())}
    rrec = json.loads(one("receipt.json").read_text())
    rec = [r for r in rrec["receipts"] if r.get("source") == "cbbd_ratings_adjusted"]
    ratings = one("cbbd_ratings_adjusted.json").read_bytes()
    today_raw = [p for p in cap.rglob("cbbd_games_*.raw.json") if not p.name.startswith(("cbbd_games_season", "cbbd_games_teams"))]
    if len(today_raw) != 1: raise Hold("REPLAY_SOURCE_TODAY_GAMES")
    man = json.loads(today_raw[0].with_name(today_raw[0].name.replace(".raw.json", ".manifest.json")).read_text())
    raws = {"today": today_raw[0].read_bytes(), "season": one("cbbd_games_season.raw.json").read_bytes(),
            "boxes": one("cbbd_games_teams.raw.json").read_bytes(), "espn": one("espn_scoreboard.raw.json").read_bytes(),
            "board": (ev / "board.csv").read_bytes()}
    checks = {"today": man.get("source_sha256"), "season": receipts.get("cbbd_games_season", {}).get("sha256"),
              "boxes": receipts.get("cbbd_games_teams", {}).get("sha256"), "espn": receipts.get("espn_scoreboard", {}).get("sha256"),
              "board": receipts.get("dk_board", {}).get("sha256")}
    for k, want in checks.items():
        if sha(raws[k]) != str(want).replace("sha256:", ""): raise Hold(f"REPLAY_SOURCE_HASH_MISMATCH_{k.upper()}")
    by_id = {str(g.get("id")): g for g in json.loads(raws["season"])}
    by_id.update({str(g.get("id")): g for g in json.loads(raws["today"])})
    freeze = parse_z(original["freeze_utc"])
    card, names, extra = build(work=Path(out_dir) / "work", season=season, now_utc=freeze, games=list(by_id.values()),
                               boxes=json.loads(raws["boxes"]), observed_utc=man["local_observed_utc"],
                               ratings_body=ratings, ratings_receipt=rec[0] if len(rec) == 1 else None,
                               espn=json.loads(raws["espn"]), espn_sha=receipts["espn_scoreboard"]["sha256"],
                               espn_captured=receipts["espn_scoreboard"]["observed_utc"],
                               board_rows=list(csv.DictReader(io.StringIO(raws["board"].decode("utf-8-sig")))),
                               board_captured_utc=receipts["dk_board"]["observed_utc"], ledger_path=None)
    strip = lambda c: [{k: v for k, v in r.items()} for r in c["rows"]]
    same = strip(card) == strip(original)
    md = ("# SHADOW REPLAY / 0u — not a pick, not frozen, no ledger write\n\n"
          f"Replay of card {original['card_sha256'][:12]} at its original freeze · rows identical to frozen card: **{same}**\n\n"
          + render(card, names, extra).replace("# SportsEdge CBB RUN IT card", "## Replayed card"))
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "cbb_replay.md").write_text(md)
    (out / "cbb_replay.json").write_text(json.dumps({"label": "SHADOW_REPLAY_0U", "matches_frozen": same, "card": card}, indent=1, sort_keys=True))
    return same

def _err_code(e):
    """Receipt-safe error: exception type plus the reason only when it is a plain upper-case code."""
    m = re.fullmatch(r"[A-Z][A-Z0-9_:]{2,80}", str(e))
    return f"{type(e).__name__}: {e}" if m else type(e).__name__

def _write_receipt(out_dir, run_id, now, card, extra, errors, ledger_path):
    """run_receipt.json: what ran and what came out, including failures. Counts only; no provider bodies."""
    try:
        n_ledger = len(LG.read(ledger_path)) if ledger_path and Path(ledger_path).exists() else 0
    except Exception:  # a broken ledger is reported by the run itself
        n_ledger = None
    rec = {"label": "PAPER_0U", "run_id": str(run_id), "date_ct": now.astimezone(CT).date().isoformat(),
           "generated_utc": utcz(now), "ok": not errors and card is not None,
           "rows_pulled": None if extra is None else {"board_rows": extra["board_rows"], "slate_games": extra["slate_games"],
                                                     "prior_finals_used": extra["prior_census"].get("finals")},
           "games_projected": None if card is None else card["projected_rows"],
           "priced_markets": None if card is None else card["priced_market_rows"],
           "ladder_rows_priced": None if extra is None else len(extra["ladders"]),
           "ledger_rows": n_ledger, "errors": errors,
           "ledger_reconciliation": None if extra is None else extra.get("ledger"),
           "ladders_rejected_by_code": None if extra is None else dict(sorted(
               Counter(w.split(":")[0] for _, _, w in extra["ladders_skipped"]).items())),
           "unmatched": None if extra is None else {"quotes": len(extra["quotes_unmatched"]),
                                                    "registry": len(extra["registry_unmatched"]),
                                                    "ladders": len(extra["ladders_skipped"])}}
    try:
        out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
        (out / "run_receipt.json").write_text(json.dumps(rec, indent=1, sort_keys=True))
    except OSError:
        pass

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--replay-evidence", help="decrypted evidence dir: SHADOW REPLAY, read-only, no ledger")
    a.add_argument("--board"); a.add_argument("--board-captured-utc")
    a.add_argument("--season", type=int, required=True)
    a.add_argument("--private-dir"); a.add_argument("--out", required=True)
    a.add_argument("--ledger")
    a.add_argument("--diagnostic-repeat", action="store_true",
                   help="retain previous game freezes; append unseen games only; report full current diagnostic")
    a.add_argument("--season-start-utc", help="UTC Z start of the prior-finals window; default Nov 1 of the season's start year (2026-11-01 for season 2027)")
    a.add_argument("--fixture-dir", help="offline captures (tests only): ratings.json receipt.json games.json boxes.json espn.json")
    a.add_argument("--now", help="ISO UTC override (tests only)")
    a.add_argument("--totals-order-verified", action="store_true",
                   help="this BOARD FORMAT is verified price_a=over; otherwise totals are withheld "
                        "unless rows carry totals_order=over_under/under_over")
    a.add_argument("--sd-margin", type=float); a.add_argument("--sd-total", type=float)
    a.add_argument("--blend-weight-model", type=float,
                   help="EXPERIMENTAL model weight in [0,1] (default 0.25; chronological test pending)")
    a.add_argument("--blowout-spread-abs", type=float)
    a.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    x = a.parse_args(argv)
    if x.replay_evidence:
        if x.ledger: print("BLOCKED Hold: REPLAY_NEVER_WRITES_LEDGER", file=sys.stderr); return 2
        try:
            same = replay(x.replay_evidence, x.season, x.out)
        except (Hold, PC.Pass, ValueError, OSError, KeyError) as e:
            print(f"BLOCKED {type(e).__name__}: {e}", file=sys.stderr); return 2
        print(f"SHADOW REPLAY done; matches frozen card: {same}"); return 0
    def blocked(code):
        print(f"BLOCKED Hold: {code}", file=sys.stderr)
        _write_receipt(x.out, x.run_id, datetime.now(timezone.utc), None, None, [f"Hold: {code}"], x.ledger)
        return 2
    if not x.board or not x.board_captured_utc:
        return blocked("BOARD_REQUIRED")
    if not Path(x.board).is_file():
        return blocked("BOARD_FILE_MISSING")
    season_start = x.season_start_utc or f"{x.season - 1}-11-01T00:00:00Z"
    try:
        if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", season_start): raise ValueError
        parse_z(season_start)
    except ValueError:
        return blocked("SEASON_START_UTC_INVALID")
    key = os.environ.get("CBBD_API_KEY")
    clock = (lambda: datetime.fromisoformat(x.now)) if x.now else (lambda: datetime.now(timezone.utc))
    try:
        if not key and not x.fixture_dir: raise Hold("CBBD_API_KEY_ABSENT")
        if not x.private_dir: raise Hold("PRIVATE_DIR_REQUIRED")
        priv = Path(x.private_dir); priv.mkdir(mode=0o700, parents=True, exist_ok=False)
        if x.fixture_dir:
            fx = Path(x.fixture_dir); now = clock()
            ratings = (fx / "ratings.json").read_bytes(); rec = [json.loads((fx / "receipt.json").read_text())]
            graw, braw, eraw = (fx / "games.json").read_bytes(), (fx / "boxes.json").read_bytes(), (fx / "espn.json").read_bytes()
            for n, b in (("cbbd_ratings_adjusted", ratings), ("cbbd_games", graw), ("cbbd_games_teams", braw), ("espn_scoreboard", eraw)):
                _archive(priv, n, b)
            games, boxes, espn = json.loads(graw), json.loads(braw), json.loads(eraw)
            obs = utcz(now - timedelta(minutes=30))
            gcap = {"sha256": sha(graw), "observed_utc": obs}
            brec = {"source": "cbbd_games_teams", "bytes": len(braw), "sha256": sha(braw), "observed_utc": obs}
            erec = {"source": "espn_scoreboard", "bytes": len(eraw), "sha256": sha(eraw), "observed_utc": obs}
        else:
            from sportsedge.validation import daily_ratings_capture as DR
            rc = DR.capture(priv / "ratings", [DR.cbbd_source(x.season)])
            rec = [r for r in rc["receipts"] if r["source"] == "cbbd_ratings_adjusted"]
            if len(rec) != 1 or rec[0]["state"] != "CAPTURED": raise Hold(f"RATINGS_{rec and rec[0]['state']}")
            ratings = (priv / "ratings" / rec[0]["file"]).read_bytes()
            now = clock()
            import cbbd_prospective_capture as CAP
            # capture_games allows at most one UTC day: use it for today's Central-time slate,
            # and a separate archived GET for season-to-date finals. Today's rows win on id overlap.
            day0 = datetime.combine(now.astimezone(CT).date(), datetime.min.time(), CT).astimezone(timezone.utc)
            gcap = CAP.capture_games(season=x.season, start_utc=utcz(day0),
                                     end_utc=utcz(day0 + timedelta(hours=24)), private_dir=priv / "games", key=key)
            today = json.loads(Path(gcap["raw_path"]).read_bytes())
            qs = urllib.parse.urlencode({"season": x.season, "startDateRange": season_start, "endDateRange": utcz(day0)})
            season_rows, srec = capture_raw("cbbd_games_season", f"{CAP.BASE}?{qs}", priv / "games", key)
            by_id = {str(g.get("id")): g for g in season_rows}
            by_id.update({str(g.get("id")): g for g in today})
            games = list(by_id.values())
            q = urllib.parse.urlencode({"season": x.season, "startDateRange": season_start, "endDateRange": utcz(now)})
            boxes, brec = capture_raw("cbbd_games_teams", f"{BOX_URL}?{q}", priv / "games", key)
            espn_url = f"{ESPN_URL}?" + urllib.parse.urlencode({"dates": now.astimezone(CT).strftime("%Y%m%d"),
                                                                 "groups": 50, "limit": 500})
            espn, erec = capture_raw("espn_scoreboard", espn_url, priv / "games")
            now = clock()
        board_raw = Path(x.board).read_bytes()
        board = list(csv.DictReader(io.StringIO(board_raw.decode("utf-8-sig"))))
        card, names, extra = build(work=Path(x.out) / "work", season=x.season, now_utc=now, games=games,
                                   boxes=boxes, observed_utc=gcap["observed_utc"], ratings_body=ratings,
                                   ratings_receipt=rec[0], espn=espn, espn_sha=erec["sha256"],
                                   espn_captured=erec["observed_utc"], board_rows=board,
                                   board_captured_utc=x.board_captured_utc, ledger_path=x.ledger,
                                   totals_order_verified=x.totals_order_verified,
                                   diagnostic_repeat=x.diagnostic_repeat,
                                   config={"sd_margin": x.sd_margin, "sd_total": x.sd_total,
                                           "blend_weight_model": x.blend_weight_model,
                                           "blowout_spread_abs": x.blowout_spread_abs})
    except (Hold, PC.Pass, ValueError, OSError, LG.LedgerError) as e:
        print(f"BLOCKED {type(e).__name__}: {e}", file=sys.stderr)
        _write_receipt(x.out, x.run_id, clock(), None, None, [_err_code(e)], x.ledger)
        return 2
    receipts = [{"source": "cbbd_ratings_adjusted", **{k: rec[0].get(k) for k in ("bytes", "sha256", "observed_utc")}},
                {"source": "cbbd_games", "sha256": gcap["sha256"], "observed_utc": gcap["observed_utc"]},
                brec, erec, *([srec] if not x.fixture_dir else []), {"source": "dk_board", "bytes": len(board_raw), "sha256": sha(board_raw),
                             "observed_utc": x.board_captured_utc}]
    out = Path(x.out); out.mkdir(parents=True, exist_ok=True)
    (out / "cbb_card.json").write_text(json.dumps(card, indent=1, sort_keys=True))
    (out / "receipts.json").write_text(json.dumps(receipts, indent=1))
    md = render(card, names, extra) + "\n## Source receipts\n\n" + "\n".join(
        f"- {r['source']}: sha256 {str(r['sha256']).replace('sha256:', '')[:16]}…" for r in receipts) + "\n"
    (out / "cbb_card.md").write_text(md)
    _write_receipt(x.out, x.run_id, now, card, extra, [], x.ledger)
    print(f"slate {extra['slate_games']}, projected {card['projected_rows']}, priced {card['priced_market_rows']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
