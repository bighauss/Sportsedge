#!/usr/bin/env python3
"""CFB RUN IT: capture -> SportsEdge CFB model -> ranked card.

Runs the existing, unmodified model in models/cfb/sportsedge_cfb_model.py on
live CFBD season data plus a user-supplied DraftKings line intake JSON.

Fail-closed rules (a game or market is WITHHELD with a reason, never estimated):
  * CFBD_API_KEY missing                  -> whole run exits 2 before any request
  * team not in CFBD advanced stats       -> game withheld
  * game already kicked off at run time   -> game withheld (stale line)
  * no live forecast for an outdoor venue -> game withheld
  * injury intake missing                 -> run exits 2 unless --allow-no-injury-feed,
                                             and then every game says "injuries: none supplied"
  * prop player not uniquely matched to CFBD season stats for that game -> prop withheld
DraftKings milestone props are one-sided (over only). Their market probability is the
raw implied probability INCLUDING vig (no fair under price exists), so blended EV is
conservative. Under bets are never generated for one-sided props.
Keys are never printed; raw captures are written only to --private-dir.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, sys, unicodedata, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sportsedge_cfb_model as M  # production model, imported unchanged

CT = ZoneInfo("America/Chicago")
CFBD = "https://api.collegefootballdata.com"
ALIASES = {"miamifl": ["miami"], "ulm": ["ulmonroe", "louisianamonroe"],
           "fiu": ["floridainternational"], "uconn": ["connecticut"]}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())

class Fail(Exception):
    pass

# ---------------------------------------------------------------- fetch
def http_bytes(url, key=None, timeout=60):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               **({"Authorization": f"Bearer {key}"} if key else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise Fail(f"HTTP_{r.status}")
        body = r.read()
    if key and key.encode() in body:
        raise Fail("SECRET_ECHO")
    return body

def http_json(url, key=None, timeout=60):
    return json.loads(http_bytes(url, key, timeout))

def sha256(b):
    return hashlib.sha256(b).hexdigest()

def capture_cfbd(season, key, fetch=http_bytes):
    """Returns (parsed capture, raw bytes by source, receipts). Raw bytes are kept for the
    private archive; receipts (sha256, bytes, observed time) are public."""
    q = lambda p, **kw: f"{CFBD}{p}?" + urllib.parse.urlencode(kw)
    eps = {
        "games": q("/games", year=season, seasonType="regular", classification="fbs"),
        "advanced": q("/stats/season/advanced", year=season, excludeGarbageTime="true"),
        "team_stats": q("/stats/season", year=season),
        "talent": q("/talent", year=season),
        "returning": q("/player/returning", year=season),
        "ratings": q("/ratings/sp", year=season),
        "teams": q("/teams/fbs", year=season),
        "venues": q("/venues"),
        "player_rushing": q("/stats/player/season", year=season, category="rushing"),
        "player_passing": q("/stats/player/season", year=season, category="passing"),
        "player_receiving": q("/stats/player/season", year=season, category="receiving"),
    }
    out, raw, receipts = {}, {}, []
    for name, url in eps.items():
        try:
            b = fetch(url, key)
            out[name] = json.loads(b)
        except Exception as e:  # never echo the key; url has no key
            raise Fail(f"CFBD_{name}_BLOCKED:{type(e).__name__}")
        raw[name] = b
        receipts.append({"source": name, "provider": "collegefootballdata.com", "bytes": len(b),
                         "sha256": sha256(b), "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    return out, raw, receipts

def fetch_weather(lat, lon, kickoff_utc, fetch=http_json):
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,precipitation,snowfall",
        "wind_speed_unit": "mph", "timezone": "UTC", "forecast_days": 3})
    d = fetch(url)
    hrs = d["hourly"]["time"]; tgt = kickoff_utc.strftime("%Y-%m-%dT%H:00")
    if tgt not in hrs:
        raise Fail("FORECAST_HOUR_MISSING")
    i = hrs.index(tgt)
    rows = [min(i + k, len(hrs) - 1) for k in range(4)]  # ~game window
    wind = max(d["hourly"]["wind_speed_10m"][j] for j in rows)
    rain = sum(d["hourly"]["precipitation"][j] for j in rows)
    snow = sum(d["hourly"]["snowfall"][j] for j in rows)
    ptype = "snow" if snow >= 0.5 else "heavy_rain" if rain >= 6 else "light" if rain >= 0.5 else "none"
    return {"windSpeed": round(wind, 1), "precipitation_type": ptype, "isForecast": True}

# ---------------------------------------------------------------- model input shaping (no estimates)
REQUIRED_ADV = ["offense.plays", "offense.drives", "offense.ppa", "offense.successRate",
                "offense.explosiveness", "offense.pointsPerOpportunity", "offense.fieldPosition.averageStart",
                "offense.rushingPlays.ppa", "offense.passingPlays.ppa", "offense.passingPlays.rate",
                "defense.ppa", "defense.successRate", "defense.explosiveness",
                "defense.pointsPerOpportunity", "defense.havoc.total",
                "defense.rushingPlays.ppa", "defense.passingPlays.ppa"]

def missing_adv(row):
    return [k for k in REQUIRED_ADV if M.g(row, k) is None]

def games_played(games, now_utc):
    """Completed FBS-listed games per team that started before the run (point-in-time count).
    Replaces the model's offense.drives/12 fallback, which is used only when `games` is absent."""
    n = {}
    for g in games:
        ko = dt.datetime.fromisoformat(g["startDate"].replace("Z", "+00:00"))
        if g.get("completed") and ko < now_utc:
            for t in (g["homeTeam"], g["awayTeam"]):
                n[t] = n.get(t, 0) + 1
    return n

def with_games(adv, gp):
    """Copies of advanced rows with an explicit `games` count; rows lacking a count are left
    without one and flagged by the caller (no estimate is inserted)."""
    out = []
    for r in adv:
        r2 = dict(r)
        if gp.get(r["team"]):
            r2["games"] = gp[r["team"]]
        out.append(r2)
    return out

def sp_relative(ratings):
    """CFBD SP+ offense/defense are absolute; the model expects points vs average team."""
    ro = [g for g in ratings if g.get("team") and g.get("team") != "nationalAverages"
          and M.g(g, "offense.rating") is not None and M.g(g, "defense.rating") is not None]
    if not ro:
        return {}
    mo = sum(M.g(r, "offense.rating") for r in ro) / len(ro)
    md = sum(M.g(r, "defense.rating") for r in ro) / len(ro)
    return {r["team"]: {"team": r["team"], "rating": r.get("rating"),
                        "offense": {"rating": M.g(r, "offense.rating") - mo},
                        "defense": {"rating": M.g(r, "defense.rating") - md}} for r in ro}

def team_volume(team_stats):
    v = {}
    for r in team_stats:
        v.setdefault(r["team"], {})[r.get("statName")] = float(r.get("statValue") or 0)
    return v

def player_table(cap):
    """Keyed by (team, CFBD playerId). Rows without a provider ID are dropped (never name-keyed).
    A playerId seen on two teams or under two names is quarantined."""
    p, names, teams = {}, {}, {}
    for cat in ("rushing", "passing", "receiving"):
        for r in cap["player_" + cat]:
            pid = r.get("playerId")
            if pid in (None, "", 0):
                continue
            pid = str(pid)
            names.setdefault(pid, set()).add(r["player"]); teams.setdefault(pid, set()).add(r["team"])
            p.setdefault((r["team"], pid), {"name": r["player"]})[f"{cat}.{r['statType']}"] = float(r["stat"] or 0)
    bad = {pid for pid in names if len(names[pid]) > 1 or len(teams[pid]) > 1}
    return {k: v for k, v in p.items() if k[1] not in bad}

def usage_row(player, team, market, stats, vol):
    tv = vol.get(team, {})
    ra, pa = tv.get("rushingAttempts"), tv.get("passAttempts")
    s = stats
    if market == "rush_yds":
        car = s.get("rushing.CAR")
        if not car or not ra: return None
        return {"share": car / ra, "eff": s.get("rushing.YDS", 0) / car}
    if market == "pass_yds":
        att = s.get("passing.ATT")
        if not att or not pa: return None
        return {"share": att / pa, "eff": s.get("passing.YDS", 0) / att}
    if market in ("rec_yds", "receptions"):
        rec = s.get("receiving.REC")
        if not rec or not pa: return None
        return {"share": rec / pa, "eff": (s.get("receiving.YDS", 0) / rec) if market == "rec_yds" else 1.0}
    return None

def match_player(name, teams, ptable, truncated=False):
    """Exact normalized name within the game's two teams -> exactly one provider ID.
    Prefix match only for names DraftKings truncated with an ellipsis. Otherwise None."""
    n = norm(name)
    hits = [k for k, v in ptable.items() if k[0] in teams and
            (norm(v["name"]) == n or (truncated and norm(v["name"]).startswith(n)))]
    return hits[0] if len(hits) == 1 else None

# ---------------------------------------------------------------- run
def run(intake, cap, now_utc, weather_fetch=fetch_weather, allow_no_injury_feed=False, legacy_inputs=False):
    if "injuries" not in intake and not allow_no_injury_feed:
        raise Fail("INJURY_INTAKE_MISSING")
    inj = intake.get("injuries", [])
    adv = cap["advanced"] if legacy_inputs else with_games(cap["advanced"], games_played(cap["games"], now_utc))
    teamkey = {norm(r["team"]): r["team"] for r in adv}
    def resolve(name):
        n = norm(name.replace("…", ""))
        for c in [n] + ALIASES.get(n, []):
            if c in teamkey: return teamkey[c]
        c = [v for k, v in teamkey.items() if k.startswith(n)] if name.endswith("…") else []
        return c[0] if len(c) == 1 else None
    venues = {v.get("id"): v for v in cap["venues"]}
    ctx = {"adv": M.by(adv, "team"), "lm": M.league_means(adv),
           "talent": M.by(cap["talent"], "team"), "ret": M.by(cap["returning"], "team"),
           "ratings": sp_relative(cap["ratings"]), "teams": M.by(cap["teams"], "school"),
           "venues": {}, "injuries": inj, "weather": {}, "rest": {}, "cross": {}, "usage": []}
    games_by_pair = {}
    for g in cap["games"]:
        if g.get("completed"): continue
        k = (g["awayTeam"], g["homeTeam"])
        games_by_pair[k] = None if k in games_by_pair else g     # duplicate pair -> unusable
    games_by_pair = {k: v for k, v in games_by_pair.items() if v is not None}
    ptable, vol = player_table(cap), team_volume(cap["team_stats"])
    rows, projs, withheld, meta = [], [], [], {}
    for L in intake["lines"]:
        label = f"{L['awayTeam']} @ {L['homeTeam']}"
        A, H = resolve(L["awayTeam"]), resolve(L["homeTeam"])
        if not A or not H:
            withheld.append((label, "team not in CFBD FBS advanced stats (FCS or unmatched name)")); continue
        if not legacy_inputs:
            bad = [f"{t}: {', '.join(missing_adv(ctx['adv'][t]))}" for t in (A, H) if missing_adv(ctx["adv"][t])]
            bad += [f"{t}: games played unknown" for t in (A, H) if not ctx["adv"][t].get("games")]
            if bad:
                withheld.append((label, "required input missing -> " + "; ".join(bad))); continue
        g = games_by_pair.get((A, H))
        if not g:
            why = "home/away orientation mismatch with CFBD" if games_by_pair.get((H, A)) else "no CFBD game record"
            withheld.append((label, why)); continue
        if L.get("cfbd_game_id") is not None and str(L["cfbd_game_id"]) != str(g["id"]):
            withheld.append((label, f"intake game id {L['cfbd_game_id']} != CFBD {g['id']}")); continue
        ko = dt.datetime.fromisoformat(g["startDate"].replace("Z", "+00:00"))
        if L.get("kickoff_ct"):
            want = dt.datetime.combine(now_utc.astimezone(CT).date(),
                                       dt.datetime.strptime(L["kickoff_ct"], "%I:%M %p").time(), CT)
            if abs((ko - want).total_seconds()) > 20 * 60:
                withheld.append((label, f"kickoff mismatch: DK {L['kickoff_ct']} CT vs CFBD {ko.astimezone(CT):%-I:%M %p} CT")); continue
        if g.get("completed") or ko <= now_utc:
            withheld.append((label, f"kicked off {ko.astimezone(CT):%-I:%M %p} CT before run")); continue
        ven = venues.get(g.get("venueId"), {})
        dome = bool(ven.get("dome"))
        if not dome:
            lat = next((v for v in (ven.get("latitude"), M.g(ven, "location.x"), M.g(ven, "location.latitude")) if v is not None), None)
            lon = next((v for v in (ven.get("longitude"), M.g(ven, "location.y"), M.g(ven, "location.longitude")) if v is not None), None)
            if lat is None:
                withheld.append((label, "venue coordinates missing -> no forecast")); continue
            try:
                w = weather_fetch(lat, lon, ko.astimezone(dt.timezone.utc))
            except Exception as e:
                withheld.append((label, f"weather forecast unavailable ({e})")); continue
            ctx["weather"][g["id"]] = {**w, "gameId": g["id"], "roof": "open"}
        line = dict(L, homeTeam=H, awayTeam=A)
        try:
            pj = M.run_game(g, ctx)
        except Exception as e:
            withheld.append((label, f"model error: {e}")); continue
        if "injuries" not in intake:
            pj["notes"].append("injuries: none supplied")
        pj["kickoff_ct"] = f"{ko.astimezone(CT):%-I:%M %p} CT"; pj["kickoff_utc"] = ko.isoformat()
        projs.append(pj)
        rows += M.price_game(pj, line)
        for mk, need in (("homeTT", f"{H} team total"), ("awayTT", f"{A} team total")):
            if line.get(mk) is None: withheld.append((label, f"{need}: no line in intake"))
        # one-sided milestone props
        for p in intake.get("props", []):
            if resolve(p["away"]) != A or resolve(p["home"]) != H: continue
            hit = match_player(p["player"], (A, H), ptable, p.get("truncated", False))
            if not hit:
                withheld.append((label, f"prop {p['player']} {p['market']}: player identity not unique in CFBD")); continue
            team, pid = hit; player = ptable[hit]["name"]
            u = usage_row(player, team, p["market"], ptable[hit], vol)
            if not u:
                withheld.append((label, f"prop {player} {p['market']}: no season usage")); continue
            mm, why = M.project_prop({"team": team, "market": p["market"], **u}, pj, ctx)
            sd_f = M.PROP_SD_FRAC.get(p["market"], 0.45)
            p_imp = M.imp(p["overOdds"])
            sd_line = max(1.0, sd_f * float(p["line"]))
            mkt_mean = float(p["line"]) + sd_line * M.N.inv_cdf(min(max(p_imp, 1e-4), 1 - 1e-4))
            mean = M.PROP_MODEL_W * mm + (1 - M.PROP_MODEL_W) * mkt_mean
            po = M.pgt(mean, float(p["line"]), max(1.0, sd_f * mean))
            M.bet(rows, pj, f"Prop {p['market']}", f"{player} Over {p['line']}", p["line"], p["overOdds"],
                  po, p_imp, "over", f"{g['id']}|PTS|UP|{player}", mean)
            rows[-1]["player_id"] = pid
            rows[-1]["why"] = f"{team}: {why}; model {mm:.1f} / mkt {mkt_mean:.1f} (one-sided, vig in mkt p)"
    card = M.finalize(rows)
    return card, projs, withheld, ctx

INJURY_MAX_AGE_H = 6

def eligibility(intake, now_utc):
    """Card-level eligibility. This runner never emits official wagers: the model is unvalidated.
    Reasons are listed so a missing input is never mistaken for a model finding."""
    reasons = ["MODEL_UNVALIDATED_PAPER_0U"]
    if "injuries" not in intake:
        reasons.append("INJURY_INTAKE_MISSING")
    else:
        rv = intake.get("injuries_reviewed_utc")
        if not rv:
            reasons.append("INJURY_REVIEW_TIME_MISSING")
        elif (now_utc - dt.datetime.fromisoformat(rv.replace("Z", "+00:00"))).total_seconds() > INJURY_MAX_AGE_H * 3600:
            reasons.append("INJURY_REVIEW_STALE")
    return {"state": "RESEARCH_ONLY", "official_counted": 0, "approved_stake_u": 0, "reasons": reasons}

def to_doc(card, projs, withheld, intake, now_utc, receipts):
    """Two separate records: raw model projections and the market-adjusted card."""
    raw = [{"game": f"{p['away']} @ {p['home']}", "cfbd_game_id": p["game"]["id"], "kickoff_utc": p["kickoff_utc"],
            "kickoff_ct": p["kickoff_ct"], "pts_home": p["pts_home"], "pts_away": p["pts_away"],
            "margin": p["margin"], "total": p["total"], "plays": p["plays"], "ratings_pts": p["ratings_pts"],
            "matchup_pts": p["matchup_pts"], "hfa": p["hfa"], "weather": p["weather"], "notes": p["notes"]}
           for p in projs]
    ko = {r["game"]: r["kickoff_utc"] for r in raw}
    rows = []
    for r in card:
        r = {k: v for k, v in r.items() if k not in ("p_blend", "ev_blend")} | {
            "p_blend": r["p_blend"], "ev_blend": r["ev_blend"], "kickoff_utc": ko.get(r["game"])}
        rows.append(r)
    return {"model_projections": {"schema": "sportsedge-cfb-run-it-raw-v1",
                                  "model_file_sha256": sha256(open(M.__file__, "rb").read()),
                                  "run_utc": now_utc.isoformat(), "games": raw},
            "card": {"schema": "sportsedge-cfb-run-it-card-v1", "run_utc": now_utc.isoformat(),
                     "lines_captured": intake.get("captured"), "eligibility": eligibility(intake, now_utc),
                     "receipts": receipts, "rows": rows, "withheld": [list(w) for w in withheld]}}

def recheck(doc, now_utc):
    """Immediately before publication: anything that has kicked off moves to withheld."""
    c = doc["card"]; keep = []
    started = {g["game"] for g in doc["model_projections"]["games"]
               if dt.datetime.fromisoformat(g["kickoff_utc"]) <= now_utc}
    for r in c["rows"]:
        if r["game"] in started:
            c["withheld"].append([r["game"], f"{r['market']} {r['pick']}: kicked off before publication"])
        else:
            keep.append(r)
    for i, r in enumerate(keep, 1):
        r["rank"] = i
    c["rows"] = keep; c["rechecked_utc"] = now_utc.isoformat()
    doc["model_projections"]["games"] = [g for g in doc["model_projections"]["games"] if g["game"] not in started]
    return doc

def render(doc):
    c, raw = doc["card"], doc["model_projections"]
    run = dt.datetime.fromisoformat(c["run_utc"]).astimezone(CT)
    o = ["# SportsEdge CFB RUN IT card", "",
         f"**{c['eligibility']['state']}** — 0u · reasons: {', '.join(c['eligibility']['reasons'])}", "",
         f"Run {run:%Y-%m-%d %-I:%M %p} CT" + (f" · rechecked {dt.datetime.fromisoformat(c['rechecked_utc']).astimezone(CT):%-I:%M %p} CT" if c.get("rechecked_utc") else "")
         + f" · lines: {c.get('lines_captured')} · model sha256 {raw['model_file_sha256'][:12]}", "",
         "_All weights untested starting values. p model = raw model; p blend = 30% model / 70% market._", "",
         "## Raw model projections", "", "| Game | Kickoff | Home | Away | Margin (H) | Total | Plays/team | Weather | Inputs |",
         "|---|---|---|---|---|---|---|---|---|"]
    for g in raw["games"]:
        o.append(f"| {g['game']} | {g['kickoff_ct']} | {g['pts_home']:.1f} | {g['pts_away']:.1f} | {g['margin']:+.1f} | "
                 f"{g['total']:.1f} | {g['plays']:.1f} | {g['weather']} | {'; '.join(g['notes']) or 'none'} |")
    o += ["", "## Ranked by blended EV", "",
          "| # | Stars | Game | Market | Pick | Odds | Proj | p model | p mkt | p blend | EV raw | EV blend |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in c["rows"]:
        mk = r["market"].startswith("Prop")
        proj = "-" if r["proj"] is None else f"{r['proj']:.1f}"
        o.append(f"| {r['rank']} | {'*' * r['stars']}{' FIRE' if r['flames'] else ''} | {r['game']} | {r['market']} | {r['pick']} | "
                 f"{r['odds']:+d} | {proj} | {r['p_model']:.3f} | "
                 f"{r['p_market']:.3f}{'*' if mk else ''} | {r['p_blend']:.3f} | {r['ev_raw']*100:+.1f}% | {r['ev_blend']*100:+.1f}% |")
    o += ["", "\\* one-sided milestone price: market probability includes vig.", "", "## Withheld", ""]
    o += [f"- {g}: {w}" for g, w in c["withheld"]] or ["- none"]
    o += ["", "## Source receipts", ""] + [f"- {r['source']}: {r['bytes']} bytes, sha256 {r['sha256'][:16]}…" for r in c["receipts"]]
    return "\n".join(o) + "\n"

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("intake", nargs="?"); a.add_argument("--season", type=int)
    a.add_argument("--out", default="cfb_run_it_out"); a.add_argument("--private-dir", default=None)
    a.add_argument("--allow-no-injury-feed", action="store_true")
    a.add_argument("--recheck", action="store_true", help="re-gate an existing --out card against the clock and re-render")
    a.add_argument("--fixture", help="offline CFBD capture JSON (tests only)")
    a.add_argument("--now", help="ISO UTC override (tests only)")
    x = a.parse_args(argv)
    now = dt.datetime.fromisoformat(x.now) if x.now else dt.datetime.now(dt.timezone.utc)
    if x.recheck:
        f = os.path.join(x.out, "cfb_run_it.json")
        doc = recheck(json.load(open(f)), now)
        json.dump(doc, open(f, "w"), indent=1, default=str)
        open(os.path.join(x.out, "cfb_card.md"), "w").write(render(doc))
        print(f"rechecked: {len(doc['card']['rows'])} rows remain"); return 0
    intake = json.load(open(x.intake))
    try:
        if x.fixture:
            cap = json.load(open(x.fixture)); wf = lambda *_: cap["_weather"]
            raw = {"fixture": open(x.fixture, "rb").read()}
            receipts = [{"source": "fixture", "bytes": len(raw["fixture"]), "sha256": sha256(raw["fixture"]),
                         "observed_utc": now.isoformat()}]
        else:
            key = os.environ.get("CFBD_API_KEY")
            if not key: raise Fail("CFBD_API_KEY_ABSENT")
            if x.private_dir is None: raise Fail("PRIVATE_DIR_REQUIRED_FOR_LIVE_CAPTURE")
            cap, raw, receipts = capture_cfbd(x.season, key); wf = fetch_weather
        if x.private_dir:
            os.makedirs(x.private_dir, mode=0o700, exist_ok=True)
            for name, b in raw.items():
                open(os.path.join(x.private_dir, f"{name}.json"), "wb").write(b)
        card, projs, withheld, ctx = run(intake, cap, now, wf, x.allow_no_injury_feed)
    except Fail as e:
        print(f"BLOCKED {e}", file=sys.stderr); return 2
    os.makedirs(x.out, exist_ok=True)
    doc = to_doc(card, projs, withheld, intake, now, receipts)
    json.dump(doc, open(os.path.join(x.out, "cfb_run_it.json"), "w"), indent=1, default=str)
    json.dump(receipts, open(os.path.join(x.out, "receipts.json"), "w"), indent=1)
    open(os.path.join(x.out, "cfb_card.md"), "w").write(render(doc))
    print(f"{len(projs)} games projected, {len(card)} +EV rows, {len(withheld)} withheld")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
