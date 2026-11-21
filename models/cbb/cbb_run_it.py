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
import argparse, csv, hashlib, io, json, os, re, sys, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import cbbd_paper_card as PC                       # noqa: E402
import cbbd_paper_ledger as LG                     # noqa: E402
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
        gid, p = b.get("gameId"), (b.get("teamStats") or {}).get("possessions")
        if gid is not None and isinstance(p, (int, float)):
            poss.setdefault(str(gid), []).append(float(p))
    out, census = [], {"finals": 0, "no_possessions": 0}
    obs = parse_z(observed_utc)
    for g in games:
        if g.get("status") != "final" or g.get("startTimeTbd") is not False:
            continue
        if parse_z(g["startDate"]) >= obs:
            continue
        ps = poss.get(str(g["id"]), [])
        if len(ps) != 2:
            census["no_possessions"] += 1; continue
        census["finals"] += 1
        out.append({"game_id": str(g["id"]), "season": season, "tipoff_utc": utcz(parse_z(g["startDate"])),
                    "final_captured_utc": observed_utc, "home_team_id": str(g["homeTeamId"]),
                    "away_team_id": str(g["awayTeamId"]), "neutral": bool(g.get("neutralSite")),
                    "home_points": g.get("homePoints"), "away_points": g.get("awayPoints"),
                    "possessions": sum(ps) / 2})
    return out, census

def slate(games, day_ct, now_utc, season):
    rows = []
    for g in games:
        tip = parse_z(g["startDate"])
        if tip.astimezone(CT).date() != day_ct or tip <= now_utc or g.get("startTimeTbd") is not False:
            continue
        rows.append({"game_id": str(g["id"]), "season": str(season), "tipoff_utc": utcz(tip),
                     "home_team_id": str(g["homeTeamId"]), "away_team_id": str(g["awayTeamId"]),
                     "neutral": "1" if g.get("neutralSite") else "0",
                     "_home": g.get("homeTeam"), "_away": g.get("awayTeam")})
    return rows

def _match(slate_rows, home, away):
    hs, as_ = set(cands(home)), set(cands(away))
    hits = [r for r in slate_rows if norm(r["_home"]) in hs and norm(r["_away"]) in as_]
    if len(hits) == 1: return hits[0], None
    rev = [r for r in slate_rows if norm(r["_home"]) in as_ and norm(r["_away"]) in hs]
    return None, ("home/away orientation mismatch" if rev else "no unique CBBD game for names" if not hits
                  else "ambiguous CBBD game")

def registry(slate_rows, espn, espn_sha, captured_utc):
    """ESPN neutral-site flags for exactly matched games (orientation and tip within 15 min)."""
    rows, miss = [], []
    evs = []
    for e in espn.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        teams = {x.get("homeAway"): x.get("team", {}) for x in c.get("competitors", [])}
        if "home" in teams and "away" in teams and c.get("date"):
            evs.append((teams, c))
    for r in slate_rows:
        tip = parse_z(r["tipoff_utc"])
        hit = []
        for teams, c in evs:
            hn = {norm(teams["home"].get(k, "")) for k in ("location", "shortDisplayName", "displayName")}
            an = {norm(teams["away"].get(k, "")) for k in ("location", "shortDisplayName", "displayName")}
            if norm(r["_home"]) in hn and norm(r["_away"]) in an and \
                    abs((parse_z(c["date"]) - tip).total_seconds()) <= 900:
                hit.append(c)
        if len(hit) != 1:
            miss.append((r["game_id"], "ESPN event not uniquely matched")); continue
        rows.append({"game_id": r["game_id"], "neutral": "1" if hit[0].get("neutralSite") else "0",
                     "source": "ESPN", "source_sha256": espn_sha, "published_utc": captured_utc,
                     "captured_utc": captured_utc, "tipoff_utc": r["tipoff_utc"]})
    return rows, miss

MK = {"SPREAD": "spread", "TOTAL": "total", "ML": "moneyline"}

def board_quotes(board_rows, slate_rows, captured_utc, book="DraftKings"):
    out, unmatched = [], []
    for b in board_rows:
        if b.get("sport") != "CBB" or b.get("market") not in MK: continue
        g, why = _match(slate_rows, b["home"], b["away"])
        if not g:
            unmatched.append((f"{b['away']} @ {b['home']}", b["market"], why)); continue
        out.append({"game_id": g["game_id"], "market": MK[b["market"]], "book": book,
                    "line": b["line"] or None, "price_a": b["price_a"], "price_b": b["price_b"],
                    "captured_utc": captured_utc})
    return out, unmatched

def write_csv(path, header, rows):
    buf = io.StringIO(); w = csv.DictWriter(buf, header, extrasaction="ignore", lineterminator="\n")
    w.writeheader(); w.writerows(rows); Path(path).write_text(buf.getvalue(), encoding="utf-8")

# ---------------------------------------------------------------- orchestration
def build(*, work, season, now_utc, games, boxes, observed_utc, ratings_body, ratings_receipt,
          espn, espn_sha, espn_captured, board_rows, board_captured_utc, ledger_path=None):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    day = now_utc.astimezone(CT).date()
    s = slate(games, day, now_utc, season)
    pg, pcensus = prior_games(games, boxes, observed_utc, season)
    reg, reg_miss = registry(s, espn, espn_sha, espn_captured)
    quotes, unmatched = board_quotes(board_rows, s, board_captured_utc)
    write_csv(work / "slate.csv", list(PC.SLATE_COLUMNS), s)
    write_csv(work / "registry.csv", ["game_id", "neutral", "source", "source_sha256", "published_utc",
                                      "captured_utc", "tipoff_utc"], reg)
    freeze = stamp(now_utc)
    card = PC.build_card(freeze_utc=freeze, built_utc=freeze, season=season,
                         slate_path=work / "slate.csv", registry_path=work / "registry.csv",
                         ratings_body=ratings_body, ratings_receipt=ratings_receipt,
                         prior_games=pg, quotes=[(q, "OPERATOR") for q in quotes],
                         input_sha256={"espn_scoreboard": espn_sha})
    ledger = None
    if ledger_path:
        ledger = LG.append(ledger_path, LG.card_entries(card), clock=lambda: now_utc)
    names = {r["game_id"]: (r["_away"], r["_home"], r["tipoff_utc"]) for r in s}
    extra = {"prior_census": pcensus, "registry_unmatched": reg_miss, "quotes_unmatched": unmatched,
             "slate_games": len(s), "ledger": ledger}
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
    if card.get("context_error"):
        o += [f"**Context error (all games PASS):** {card['context_error']}", ""]
    priced = []
    for r in card["rows"]:
        for m in r["markets"]:
            if m["status"] == "PRICED_PAPER":
                side, ev = _best(m); priced.append((ev, r, m, side))
    priced.sort(key=lambda x: -x[0])
    o += ["## Priced markets (best side by paper EV)", "",
          "| # | Game | Tip (CT) | Market | Side | Line | Price | p model | p no-vig | Paper EV |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, (ev, r, m, side) in enumerate(priced, 1):
        a, h, tip = names.get(r["game_id"], ("?", "?", r["tipoff_utc"]))
        q = m["quote"]; price = q["price_a"] if side == m["sides"][0] else q["price_b"]
        line = "" if q["line"] is None else (f"{q['line']:g}" if m["market"] == "total"
                                             else f"{(q['line'] if side == 'home' else -q['line']):+g}")
        o.append(f"| {i} | {a} @ {h} | {parse_z(tip).astimezone(CT):%-I:%M %p} | {m['market']} | {side} | {line} | "
                 f"{price:+d} | {m['model_prob'][side]:.3f} | {m['market_novig_prob'][side]:.3f} | {ev*100:+.1f}% |")
    o += ["", "## Withheld", ""]
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

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--board", required=True); a.add_argument("--board-captured-utc", required=True)
    a.add_argument("--season", type=int, required=True)
    a.add_argument("--private-dir", required=True); a.add_argument("--out", required=True)
    a.add_argument("--ledger"); a.add_argument("--season-start-utc", default="2026-11-01T00:00:00Z")
    x = a.parse_args(argv)
    key = os.environ.get("CBBD_API_KEY")
    try:
        if not key: raise Hold("CBBD_API_KEY_ABSENT")
        priv = Path(x.private_dir); priv.mkdir(mode=0o700, parents=True, exist_ok=False)
        from sportsedge.validation import daily_ratings_capture as DR
        rc = DR.capture(priv / "ratings", [DR.cbbd_source(x.season)])
        rec = [r for r in rc["receipts"] if r["source"] == "cbbd_ratings_adjusted"]
        if len(rec) != 1 or rec[0]["state"] != "CAPTURED": raise Hold(f"RATINGS_{rec and rec[0]['state']}")
        ratings = (priv / "ratings" / rec[0]["file"]).read_bytes()
        now = datetime.now(timezone.utc)
        import cbbd_prospective_capture as CAP
        gcap = CAP.capture_games(season=x.season, start_utc=x.season_start_utc,
                                 end_utc=utcz(now + timedelta(hours=30)), private_dir=priv / "games", key=key)
        games = json.loads(Path(gcap["raw_path"]).read_bytes())
        q = urllib.parse.urlencode({"season": x.season, "startDateRange": x.season_start_utc, "endDateRange": utcz(now)})
        boxes, brec = capture_raw("cbbd_games_teams", f"{BOX_URL}?{q}", priv / "games", key)
        espn_url = f"{ESPN_URL}?" + urllib.parse.urlencode({"dates": now.astimezone(CT).strftime("%Y%m%d"),
                                                             "groups": 50, "limit": 500})
        espn, erec = capture_raw("espn_scoreboard", espn_url, priv / "games")
        board_raw = Path(x.board).read_bytes()
        board = list(csv.DictReader(io.StringIO(board_raw.decode("utf-8-sig"))))
        now = datetime.now(timezone.utc)
        card, names, extra = build(work=Path(x.out) / "work", season=x.season, now_utc=now, games=games,
                                   boxes=boxes, observed_utc=gcap["observed_utc"], ratings_body=ratings,
                                   ratings_receipt=rec[0], espn=espn, espn_sha=erec["sha256"],
                                   espn_captured=erec["observed_utc"], board_rows=board,
                                   board_captured_utc=x.board_captured_utc, ledger_path=x.ledger)
    except (Hold, PC.Pass, ValueError, OSError) as e:
        print(f"BLOCKED {type(e).__name__}: {e}", file=sys.stderr); return 2
    receipts = [{"source": "cbbd_ratings_adjusted", **{k: rec[0].get(k) for k in ("bytes", "sha256", "observed_utc")}},
                {"source": "cbbd_games", "bytes": None, "sha256": gcap["sha256"], "observed_utc": gcap["observed_utc"]},
                brec, erec, {"source": "dk_board", "bytes": len(board_raw), "sha256": sha(board_raw),
                             "observed_utc": x.board_captured_utc}]
    out = Path(x.out); out.mkdir(parents=True, exist_ok=True)
    (out / "cbb_card.json").write_text(json.dumps(card, indent=1, sort_keys=True))
    (out / "receipts.json").write_text(json.dumps(receipts, indent=1))
    md = render(card, names, extra) + "\n## Source receipts\n\n" + "\n".join(
        f"- {r['source']}: sha256 {str(r['sha256']).replace('sha256:', '')[:16]}…" for r in receipts) + "\n"
    (out / "cbb_card.md").write_text(md)
    print(f"slate {extra['slate_games']}, projected {card['projected_rows']}, priced {card['priced_market_rows']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
