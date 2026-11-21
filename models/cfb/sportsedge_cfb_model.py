#!/usr/bin/env python3
"""
SportsEdge CFB "RUN IT" model  (2026-11-15, Claude)
====================================================
Self-contained (Python 3.8+ stdlib only). Mirrors the NFL RUN IT standard:

  team points = 50% ratings model + 50% advanced-stats matchup
                (season stats regressed to league mean, k = 6 games;
                 early-season prior = talent + returning production, fades out by week 6)
              + adjustments (injuries, travel/rest, venue/home field, altitude, weather)
  totals driven by tempo (plays/game of both teams)
  pricing: Normal model -> win prob per market
       margin SD 15.5, total SD 15, team total SD 11, 1H mean = 0.5 x full, SD 11
  raw EV   = p_model * decimal - 1
  blend EV = p_blend * decimal - 1,  p_blend = 0.30*p_model + 0.70*p_novig_market
  ranked by blended EV, stars 1-5, unders below projection / overs above projection dropped,
  same-signal stacks flagged.
  props = usage share x team volume x efficiency x opponent factor, blended
          70% model / 30% market-implied mean.

ALL WEIGHTS ARE UNTESTED STARTING VALUES. Not validated / not backtested.

INPUT FILES (CSV or JSON; JSON may be a list or CFBD-shaped nested objects;
CSV uses dotted column names for nested fields, e.g. "offense.ppa").
Field names match collegefootballdata.com (CFBD) v2 responses:

 games      (/games)                id, season, week, homeTeam, awayTeam, neutralSite, venue, venueId,
                                    startDate   [optional extras: kickoff_local]
 advanced   (/stats/season/advanced) team, conference, offense.{plays, drives, ppa, successRate,
                                    explosiveness, pointsPerOpportunity, fieldPosition.averageStart,
                                    havoc.total, rushingPlays.{ppa,successRate,rate},
                                    passingPlays.{ppa,successRate,rate}}, defense.{same}
                                    [optional: games  (else estimated as offense.drives/12)]
 talent     (/talent)               team, talent
 returning  (/player/returning)     team, percentPPA   (0-1)
 ratings    (existing SportsEdge ratings model; or /ratings/sp as a stand-in)
                                    team, rating, offense.rating, defense.rating
                                    (points vs average team; defense: lower = better, SP+ style)
 lines      (/lines, or a flat odds CSV)  homeTeam, awayTeam, lines[0].{spread, overUnder,
                                    homeMoneyline, awayMoneyline}; plus SportsEdge extras (flat):
                                    spreadHomeOdds, spreadAwayOdds, overOdds, underOdds,
                                    homeTT, homeTTOver, homeTTUnder, awayTT, awayTTOver, awayTTUnder,
                                    h1Spread, h1HomeOdds, h1AwayOdds, h1Total, h1Over, h1Under
 teams      (/teams)                school, location.timezone, location.elevation  [optional]
 venues     (SportsEdge file)       venue, hfa (1.5-4.0), elevation_ft   [optional]
 injuries   (SportsEdge file)       team, player, role in {QB, STAR_SKILL, DB, OL}, status OUT
                                    [optional: impact override in points]
 weather    (/games/weather or forecast) gameId, windSpeed, precipitation_type in
                                    {none, light, heavy_rain, snow}, isForecast (must be true), roof
 schedule_rest (SportsEdge)         team, days_rest
 crosscheck (optional)              gameId, sp_spread, fpi_spread, sasser_spread, corbie_spread (home perspective,
                                    negative = home favored)  -> display only, never used in projection
 usage      (cfbfastR / CFBD /stats/player/season derived)
                                    player, team, pos, market in {rush_yds, rec_yds, pass_yds, receptions},
                                    share (of team carries/targets/attempts), eff (yds per touch or catch rate),
                                    games
 props      (odds)                  gameId, player, market, line, overOdds, underOdds
"""
import csv, json, math, os, sys
from statistics import NormalDist

# ---------------------------------------------------------------- constants (untested starting values)
K_REGRESS = 6.0          # games of league-mean regression
PRIOR_FADE_WEEK = 6      # talent/returning prior fully gone by week 6
W_RATINGS = 0.50
W_MATCHUP = 0.50
LG_PPG = 28.0            # FBS-ish points per team-game
LG_PLAYS = 70.0          # plays per team-game
PTS_PER_PPA_PLAY = 1.0   # 1 point of PPA per play ~ 1 point scored (PPA is in points)
SD_MARGIN, SD_TOTAL, SD_TT, SD_1H = 15.5, 15.0, 11.0, 11.0
H1_SHARE = 0.5
HFA_DEFAULT = 2.5
INJ = {"QB": -5.5, "STAR_SKILL": -1.5, "OL": -0.75}   # QB range -4..-7 (use 'impact' to override)
MULTI_DB_OUT_OPP = 1.5   # 2+ DBs out -> opponent +1.5
TRAVEL_TZ_PEN = -0.5     # 2+ time zones
SHORT_WEEK_PEN = -0.5    # < 6 days rest
WIND_PEN = -2.0          # 15+ mph
PRECIP_PEN = {"heavy_rain": -2.0, "snow": -3.0}
ALTITUDE_FT = 5000; ALTITUDE_HOME = 1.0
P_BLEND_MODEL = 0.30
PROP_MODEL_W = 0.70
PROP_SD_FRAC = {"rush_yds": 0.45, "rec_yds": 0.50, "pass_yds": 0.28, "receptions": 0.40}
N = NormalDist()

# ---------------------------------------------------------------- loaders
def _unflatten(row):
    out = {}
    for k, v in row.items():
        if k is None: continue
        v = _num(v)
        cur = out; parts = k.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return out

def _num(v):
    if isinstance(v, str):
        s = v.strip()
        if s == "": return None
        if s.lower() in ("true", "false"): return s.lower() == "true"
        try: return int(s)
        except ValueError:
            try: return float(s)
            except ValueError: return s
    return v

def load(path):
    """Load CSV (dotted columns -> nested) or JSON list. Missing/None path -> []."""
    if not path or not os.path.exists(path): return []
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            return [_unflatten(r) for r in csv.DictReader(f)]
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, list) else [d]

def g(d, path, default=None):
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict) or cur.get(p) is None: return default
        cur = cur[p]
    return cur

def by(rows, key):
    return {g(r, key): r for r in rows}

def normalize_line(r):
    """Accept CFBD /lines shape (nested lines[]) or flat row."""
    flat = dict(r)
    ls = r.get("lines")
    if isinstance(ls, list) and ls:
        for k, v in ls[0].items(): flat.setdefault(k, v)
    return flat

# ---------------------------------------------------------------- odds math
def dec(am):
    am = float(am); return 1 + (am / 100 if am > 0 else 100 / -am)
def imp(am): return 1 / dec(am)
def novig(a, b):
    pa, pb = imp(a), imp(b); return pa / (pa + pb), pb / (pa + pb)
def pgt(mean, line, sd): return 1 - N.cdf((line - mean) / sd)   # P(X > line)

# ---------------------------------------------------------------- league means & regression
STAT_KEYS = ["ppa", "successRate", "explosiveness", "pointsPerOpportunity",
             "fieldPosition.averageStart", "havoc.total",
             "rushingPlays.ppa", "passingPlays.ppa", "passingPlays.rate"]

def league_means(adv):
    m = {}
    for side in ("offense", "defense"):
        for k in STAT_KEYS:
            vals = [g(r, f"{side}.{k}") for r in adv if g(r, f"{side}.{k}") is not None]
            m[f"{side}.{k}"] = sum(vals) / len(vals) if vals else 0.0
    pl = [team_games_plays(r)[1] for r in adv]
    m["plays_pg"] = sum(pl) / len(pl) if pl else LG_PLAYS
    return m

def team_games_plays(r):
    gp = r.get("games") or (g(r, "offense.drives", 0) / 12.0) or 1
    plays = g(r, "offense.plays", LG_PLAYS * gp)
    return gp, plays / gp

def regressed(r, lm, key, week, prior_shift=0.0):
    """(n*x + k*mean)/(n+k); early-season prior shifts the mean anchor, fading to 0 by week 6."""
    gp = team_games_plays(r)[0]
    x = g(r, key, lm[key])
    fade = max(0.0, (PRIOR_FADE_WEEK - week) / PRIOR_FADE_WEEK)
    anchor = lm[key] + prior_shift * fade
    return (gp * x + K_REGRESS * anchor) / (gp + K_REGRESS)

def prior_shift(team, talent, ret):
    """Prior in PPA units from talent composite z-score and returning production. Offense +, defense -."""
    tv = [t["talent"] for t in talent.values() if t.get("talent") is not None]
    if not tv or team not in talent: tz = 0.0
    else:
        mu = sum(tv) / len(tv); sd = (sum((v - mu) ** 2 for v in tv) / len(tv)) ** 0.5 or 1
        tz = (talent[team]["talent"] - mu) / sd
    rp = g(ret.get(team, {}), "percentPPA", 0.5)
    return 0.04 * tz + 0.08 * (rp - 0.5)

# ---------------------------------------------------------------- matchup model
def matchup_points(off, dfn, lm, week, pri_off, pri_def, plays):
    """Expected points for `off` vs `dfn` from regressed advanced stats."""
    def o(k): return regressed(off, lm, f"offense.{k}", week, pri_off if k.endswith("ppa") else 0)
    def d(k): return regressed(dfn, lm, f"defense.{k}", week, -pri_def if k.endswith("ppa") else 0)
    pass_rate = o("passingPlays.rate") or 0.5
    rush = o("rushingPlays.ppa") + d("rushingPlays.ppa") - lm["defense.rushingPlays.ppa"]
    pas = o("passingPlays.ppa") + d("passingPlays.ppa") - lm["defense.passingPlays.ppa"]
    split_ppa = pass_rate * pas + (1 - pass_rate) * rush
    ovr_ppa = o("ppa") + d("ppa") - lm["defense.ppa"]
    ppa = 0.6 * split_ppa + 0.4 * ovr_ppa
    pts = LG_PPG + plays * (ppa - lm["offense.ppa"]) * PTS_PER_PPA_PLAY
    sr = (o("successRate") - lm["offense.successRate"]) + (d("successRate") - lm["defense.successRate"])
    ex = (o("explosiveness") - lm["offense.explosiveness"]) + (d("explosiveness") - lm["defense.explosiveness"])
    ppo = (o("pointsPerOpportunity") - lm["offense.pointsPerOpportunity"]) + \
          (d("pointsPerOpportunity") - lm["defense.pointsPerOpportunity"])
    fp = (o("fieldPosition.averageStart") - lm["offense.fieldPosition.averageStart"])
    havoc = (d("havoc.total") - lm["defense.havoc.total"])  # defense havoc created
    pts += 20 * sr + 4 * ex + 2.0 * ppo + 0.15 * fp - 15 * havoc
    return pts, {"ppa": round(ppa, 3), "pass_rate": round(pass_rate, 2)}

def ratings_points(rt_off, rt_def):
    """Existing ratings model: points = league + offense rating + opponent defense rating."""
    return LG_PPG / 1.0 + g(rt_off, "offense.rating", 0) + g(rt_def, "defense.rating", 0) - 0.0

# ---------------------------------------------------------------- adjustments
def injury_adj(team, injuries):
    out = [i for i in injuries if i.get("team") == team and str(i.get("status", "OUT")).upper() == "OUT"]
    own, opp, notes = 0.0, 0.0, []
    dbs = 0
    for i in out:
        role = str(i.get("role", "")).upper()
        if role == "DB": dbs += 1; continue
        v = i.get("impact")
        v = float(v) if v not in (None, "") else INJ.get(role, 0.0)
        if role == "QB": v = max(-7.0, min(-4.0, v))
        own += v; notes.append(f"{i.get('player')} {role} OUT {v:+.2f}")
    if dbs >= 2: opp += MULTI_DB_OUT_OPP; notes.append(f"{dbs} DBs OUT -> opp +{MULTI_DB_OUT_OPP}")
    return own, opp, notes

TZ_STD = {"America/New_York": -5, "America/Detroit": -5, "America/Indiana/Indianapolis": -5,
          "America/Kentucky/Louisville": -5, "America/Chicago": -6, "America/Denver": -7,
          "America/Boise": -7, "America/Phoenix": -7, "America/Los_Angeles": -8,
          "Pacific/Honolulu": -10, "America/Anchorage": -9}

def tz_of(team, teams):
    """location.tzOffset (hours) if given, else location.timezone (IANA name, CFBD /teams field)."""
    t = teams.get(team, {})
    off = g(t, "location.tzOffset")
    return off if off is not None else TZ_STD.get(g(t, "location.timezone"))

def checked_neutral_site(game):
    """Reject absent or untyped CFBD venue status before assigning home field."""
    if type(game.get("neutralSite")) is not bool:
        raise ValueError("CFBD neutralSite missing or not boolean")
    return game["neutralSite"]


def run_game(game, ctx):
    H, A = game["homeTeam"], game["awayTeam"]
    week = int(game.get("week", 10))
    adv, lm = ctx["adv"], ctx["lm"]
    if H not in adv or A not in adv: raise KeyError(f"missing advanced stats for {H} or {A}")
    pri = {t: prior_shift(t, ctx["talent"], ctx["ret"]) for t in (H, A)}
    ppg_h, ppg_a = team_games_plays(adv[H])[1], team_games_plays(adv[A])[1]
    plays = (ppg_h + ppg_a) / 2.0            # tempo: both teams' plays/game drive the total
    tempo_scale = plays / lm["plays_pg"]
    notes = []
    mh, ih = matchup_points(adv[H], adv[A], lm, week, pri[H], pri[A], plays)
    ma, ia = matchup_points(adv[A], adv[H], lm, week, pri[A], pri[H], plays)
    rt = ctx["ratings"]
    if H in rt and A in rt:
        rh = ratings_points(rt[H], rt[A]) * tempo_scale
        ra = ratings_points(rt[A], rt[H]) * tempo_scale
        ph, pa = W_RATINGS * rh + W_MATCHUP * mh, W_RATINGS * ra + W_MATCHUP * ma
    else:
        rh = ra = None; ph, pa = mh, ma; notes.append("no ratings row -> matchup only")
    # venue / home field
    neutral = checked_neutral_site(game)
    ven = ctx["venues"].get(game.get("venue"), {})
    hfa = 0.0 if neutral else float(ven.get("hfa") or HFA_DEFAULT)
    hfa = max(0.0, min(4.0, hfa))
    ph += hfa / 2; pa -= hfa / 2
    elev = ven.get("elevation_ft") or g(ctx["teams"].get(H, {}), "location.elevation")
    if elev and float(elev) >= ALTITUDE_FT and not neutral:
        ph += ALTITUDE_HOME / 2; pa -= ALTITUDE_HOME / 2; notes.append(f"altitude {elev}ft home +{ALTITUDE_HOME}")
    # injuries
    for t, side in ((H, "h"), (A, "a")):
        own, opp, n = injury_adj(t, ctx["injuries"])
        if side == "h": ph += own; pa += opp
        else: pa += own; ph += opp
        notes += [f"{t}: {x}" for x in n]
    # travel / rest
    th, ta = tz_of(H, ctx["teams"]), tz_of(A, ctx["teams"])
    if th is not None and ta is not None and abs(th - ta) >= 2 and not neutral:
        pa += TRAVEL_TZ_PEN; notes.append(f"{A} travel {abs(th-ta)} TZ {TRAVEL_TZ_PEN}")
    for t in (H, A):
        rest = ctx["rest"].get(t, {}).get("days_rest")
        if rest is not None and rest < 6:
            if t == H: ph += SHORT_WEEK_PEN
            else: pa += SHORT_WEEK_PEN
            notes.append(f"{t} short week ({rest}d) {SHORT_WEEK_PEN}")
    # weather (live forecast only; domes ignored)
    w = ctx["weather"].get(game["id"], {})
    wx_note = "none"
    if w and w.get("isForecast") is True and str(w.get("roof", "open")).lower() not in ("dome", "closed"):
        tot_adj = 0.0
        if (w.get("windSpeed") or 0) >= 15: tot_adj += WIND_PEN
        tot_adj += PRECIP_PEN.get(str(w.get("precipitation_type", "none")).lower(), 0.0)
        ph += tot_adj / 2; pa += tot_adj / 2
        wx_note = f"wind {w.get('windSpeed')} mph, {w.get('precipitation_type')} -> total {tot_adj:+.1f}"
    elif w:
        wx_note = "ignored (not a live forecast or roof closed)"
    ph, pa = max(ph, 3.0), max(pa, 3.0)
    return {"game": game, "home": H, "away": A, "pts_home": ph, "pts_away": pa,
            "margin": ph - pa, "total": ph + pa, "plays": plays,
            "ratings_pts": (rh, ra), "matchup_pts": (mh, ma), "hfa": hfa,
            "weather": wx_note, "notes": notes, "info": (ih, ia), "prior": pri}

# ---------------------------------------------------------------- pricing / EV
def stars(ev):
    return 5 if ev >= .08 else 4 if ev >= .05 else 3 if ev >= .03 else 2 if ev >= .015 else 1

def bet(rows, proj, market, pick, line, odds, p_model, p_mkt, direction=None, signal=None, mean=None):
    if odds is None or p_model is None: return
    d = dec(odds)
    p_blend = P_BLEND_MODEL * p_model + (1 - P_BLEND_MODEL) * p_mkt
    rows.append({"gameId": proj["game"]["id"] if proj else None,
                 "game": f"{proj['away']} @ {proj['home']}" if proj else "",
                 "market": market, "pick": pick, "line": line, "odds": odds,
                 "p_model": p_model, "p_market": p_mkt, "p_blend": p_blend,
                 "ev_raw": p_model * d - 1, "ev_blend": p_blend * d - 1,
                 "direction": direction, "proj": mean, "signal": signal})

def price_game(proj, L):
    rows = []; H, A = proj["home"], proj["away"]; gid = proj["game"]["id"]
    m, t = proj["margin"], proj["total"]
    if L.get("homeMoneyline") and L.get("awayMoneyline"):
        nh, na = novig(L["homeMoneyline"], L["awayMoneyline"])
        ph = pgt(m, 0, SD_MARGIN)
        bet(rows, proj, "ML", H, None, L["homeMoneyline"], ph, nh, signal=f"{gid}|SIDE|{H}", mean=m)
        bet(rows, proj, "ML", A, None, L["awayMoneyline"], 1 - ph, na, signal=f"{gid}|SIDE|{A}", mean=-m)
    s = L.get("spread")  # home perspective, e.g. -7 = home favored by 7
    # Do not invent -110 when a real capture omitted either side.
    if s is not None and L.get("spreadHomeOdds") is not None and L.get("spreadAwayOdds") is not None:
        ho, ao = L["spreadHomeOdds"], L["spreadAwayOdds"]
        nh, na = novig(ho, ao); pc = pgt(m, -s, SD_MARGIN)
        bet(rows, proj, "Spread", f"{H} {s:+g}", s, ho, pc, nh, signal=f"{gid}|SIDE|{H}", mean=m)
        bet(rows, proj, "Spread", f"{A} {-s:+g}", -s, ao, 1 - pc, na, signal=f"{gid}|SIDE|{A}", mean=-m)
    def ou(market, line, oo, uo, mean, sd, sig):
        if line is None or oo is None or uo is None: return
        no, nu = novig(oo, uo); po = pgt(mean, line, sd)
        bet(rows, proj, market, f"Over {line}", line, oo, po, no, "over", sig + "|UP", mean)
        bet(rows, proj, market, f"Under {line}", line, uo, 1 - po, nu, "under", sig + "|DOWN", mean)
    ou("Total", L.get("overUnder"), L.get("overOdds"), L.get("underOdds"), t, SD_TOTAL, f"{gid}|PTS")
    ou(f"{H} TT", L.get("homeTT"), L.get("homeTTOver"), L.get("homeTTUnder"), proj["pts_home"], SD_TT, f"{gid}|PTS")
    ou(f"{A} TT", L.get("awayTT"), L.get("awayTTOver"), L.get("awayTTUnder"), proj["pts_away"], SD_TT, f"{gid}|PTS")
    ou("1H Total", L.get("h1Total"), L.get("h1Over"), L.get("h1Under"), H1_SHARE * t, SD_1H, f"{gid}|PTS")
    s1 = L.get("h1Spread")
    if s1 is not None and L.get("h1HomeOdds") and L.get("h1AwayOdds"):
        nh, na = novig(L["h1HomeOdds"], L["h1AwayOdds"]); pc = pgt(H1_SHARE * m, -s1, SD_1H)
        bet(rows, proj, "1H Spread", f"{H} {s1:+g}", s1, L["h1HomeOdds"], pc, nh, signal=f"{gid}|SIDE|{H}", mean=H1_SHARE * m)
        bet(rows, proj, "1H Spread", f"{A} {-s1:+g}", -s1, L["h1AwayOdds"], 1 - pc, na, signal=f"{gid}|SIDE|{A}", mean=-H1_SHARE * m)
    return rows

# ---------------------------------------------------------------- props
def project_prop(u, proj, ctx):
    team = u["team"]; opp = proj["away"] if team == proj["home"] else proj["home"]
    plays = proj["plays"]
    info = proj["info"][0] if team == proj["home"] else proj["info"][1]
    pass_rate = info["pass_rate"]
    pts_ratio = (proj["pts_home"] if team == proj["home"] else proj["pts_away"]) / LG_PPG
    lm, oa = ctx["lm"], ctx["adv"][opp]
    mk = u["market"]
    if mk in ("rush_yds",):
        vol = plays * (1 - pass_rate)
        opp_f = 1 + 1.5 * (g(oa, "defense.rushingPlays.ppa", lm["defense.rushingPlays.ppa"]) - lm["defense.rushingPlays.ppa"])
    else:
        vol = plays * pass_rate
        opp_f = 1 + 1.5 * (g(oa, "defense.passingPlays.ppa", lm["defense.passingPlays.ppa"]) - lm["defense.passingPlays.ppa"])
    vol *= 0.85 + 0.15 * pts_ratio   # game-script nudge
    mean = float(u["share"]) * vol * float(u["eff"]) * max(0.6, min(1.4, opp_f))
    return mean, f"vol {vol:.1f} x share {u['share']} x eff {u['eff']} x opp {opp_f:.2f}"

def price_props(proj, ctx, prop_rows):
    rows = []
    usage = {(u["player"], u["market"]): u for u in ctx["usage"]}
    for p in prop_rows:
        if p.get("gameId") != proj["game"]["id"]: continue
        u = usage.get((p["player"], p["market"]))
        if not u: continue
        mm, why = project_prop(u, proj, ctx)
        sd_f = PROP_SD_FRAC.get(p["market"], 0.45)
        no, nu = novig(p["overOdds"], p["underOdds"])
        sd_line = max(1.0, sd_f * float(p["line"]))
        mkt_mean = float(p["line"]) + sd_line * N.inv_cdf(min(max(no, 1e-4), 1 - 1e-4))
        mean = PROP_MODEL_W * mm + (1 - PROP_MODEL_W) * mkt_mean
        sd = max(1.0, sd_f * mean)
        po = pgt(mean, float(p["line"]), sd)
        team = u["team"]
        up = "UP" if p["market"] != "rush_yds" else "RUSH"
        lbl = f"{p['player']} {p['market']}"
        bet(rows, proj, f"Prop {p['market']}", f"{p['player']} Over {p['line']}", p["line"], p["overOdds"],
            po, no, "over", f"{proj['game']['id']}|PTS|UP", mean)
        bet(rows, proj, f"Prop {p['market']}", f"{p['player']} Under {p['line']}", p["line"], p["underOdds"],
            1 - po, nu, "under", f"{proj['game']['id']}|PTS|DOWN", mean)
        rows[-1]["why"] = rows[-2]["why"] = f"{team}: {why}; model {mm:.1f} / mkt {mkt_mean:.1f}"
    return rows

# ---------------------------------------------------------------- filter / rank / stacks
def contradicts(r):
    if r["direction"] == "under" and r["line"] is not None and r["proj"] is not None and r["line"] < r["proj"]: return True
    if r["direction"] == "over" and r["line"] is not None and r["proj"] is not None and r["line"] > r["proj"]: return True
    return False

def finalize(rows):
    keep = [r for r in rows if r["ev_blend"] > 0 and not contradicts(r)]
    keep.sort(key=lambda r: r["ev_blend"], reverse=True)
    cnt = {}
    for r in keep: cnt[r["signal"]] = cnt.get(r["signal"], 0) + 1
    for i, r in enumerate(keep, 1):
        r["rank"] = i; r["stars"] = stars(r["ev_blend"])
        r["flames"] = "FIRE" if r["stars"] >= 4 else ""
        r["stack_flag"] = f"STACK x{cnt[r['signal']]}" if cnt[r["signal"]] > 1 else ""
    return keep

# ---------------------------------------------------------------- run_card
def build_ctx(inp):
    adv_rows = load(inp.get("advanced"))
    ctx = {"adv": by(adv_rows, "team"), "lm": league_means(adv_rows),
           "talent": by(load(inp.get("talent")), "team"), "ret": by(load(inp.get("returning")), "team"),
           "ratings": by(load(inp.get("ratings")), "team"), "teams": by(load(inp.get("teams")), "school"),
           "venues": by(load(inp.get("venues")), "venue"), "injuries": load(inp.get("injuries")),
           "weather": by(load(inp.get("weather")), "gameId"), "rest": by(load(inp.get("schedule_rest")), "team"),
           "cross": by(load(inp.get("crosscheck")), "gameId"), "usage": load(inp.get("usage"))}
    return ctx

CARD_COLS = ["rank", "stars", "flames", "game", "market", "pick", "odds", "proj", "p_model", "p_market",
             "p_blend", "ev_raw", "ev_blend", "stack_flag", "why"]

def run_card(inputs, out_dir="."):
    """inputs: dict of name -> file path (see module doc), or path to such a JSON.
    Writes cfb_card.csv and cfb_card.md into out_dir. Returns (card_rows, projections)."""
    if isinstance(inputs, str):
        base = os.path.dirname(os.path.abspath(inputs))
        with open(inputs) as f: inputs = json.load(f)
        inputs = {k: (os.path.join(base, v) if isinstance(v, str) and not os.path.isabs(v) else v) for k, v in inputs.items()}
    ctx = build_ctx(inputs)
    lines = {}
    for r in load(inputs.get("lines")) + load(inputs.get("lines_extra")):
        L = normalize_line(r); lines[(L["homeTeam"], L["awayTeam"])] = L
    props = load(inputs.get("props"))
    rows, projs = [], []
    for game in load(inputs.get("games")):
        pj = run_game(game, ctx); projs.append(pj)
        L = lines.get((pj["home"], pj["away"]))
        if L: rows += price_game(pj, L)
        rows += price_props(pj, ctx, props)
    card = finalize(rows)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "cfb_card.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CARD_COLS, extrasaction="ignore"); w.writeheader()
        for r in card: w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    with open(os.path.join(out_dir, "cfb_card.md"), "w") as f:
        f.write(render_md(card, projs, ctx))
    return card, projs

def render_md(card, projs, ctx):
    o = ["# SportsEdge CFB RUN IT card", "", "_All weights untested starting values._", ""]
    for p in projs:
        gm = p["game"]; cc = ctx["cross"].get(gm["id"], {})
        o += [f"## {p['away']} @ {p['home']}  (wk {gm.get('week')}, {gm.get('venue','')}"
              f"{', neutral' if gm.get('neutralSite') else ''})",
              f"**Projection:** {p['home']} {p['pts_home']:.1f} - {p['away']} {p['pts_away']:.1f} | "
              f"margin {p['margin']:+.1f} | total {p['total']:.1f} | 1H total {H1_SHARE*p['total']:.1f}",
              f"- Ratings pts (H/A): {_f(p['ratings_pts'][0])}/{_f(p['ratings_pts'][1])}; "
              f"matchup pts: {p['matchup_pts'][0]:.1f}/{p['matchup_pts'][1]:.1f}; plays/team {p['plays']:.1f}; HFA {p['hfa']}",
              f"- Weather: {p['weather']}",
              f"- Key inputs: {'; '.join(p['notes']) or 'none'}"]
        if cc:
            o.append("- Cross-check (home spread): " + ", ".join(f"{k}={v}" for k, v in cc.items() if k != "gameId")
                     + f" | model {-p['margin']:+.1f}")
        o.append("")
    o += ["## Ranked card (by blended EV)", "",
          "| # | Stars | Game | Market | Pick | Odds | Proj | p model | p blend | EV raw | EV blend | Flag |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in card:
        o.append(f"| {r['rank']} | {'*'*r['stars']} {r['flames']} | {r['game']} | {r['market']} | {r['pick']} | "
                 f"{r['odds']:+d} | {_f(r['proj'])} | {r['p_model']:.3f} | {r['p_blend']:.3f} | "
                 f"{r['ev_raw']*100:+.1f}% | {r['ev_blend']*100:+.1f}% | {r['stack_flag']} |")
    return "\n".join(o) + "\n"

def _f(x): return "-" if x is None else f"{x:.1f}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python sportsedge_cfb_model.py inputs.json [out_dir]"); sys.exit(1)
    card, _ = run_card(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ".")
    print(f"{len(card)} plays written to cfb_card.csv / cfb_card.md")
