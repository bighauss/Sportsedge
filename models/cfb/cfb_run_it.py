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
import cfb_injury_intake as INJ

CT = ZoneInfo("America/Chicago")
# Frozen model file must match the reviewed research engine.
MODEL_SHA256_PIN = "1f24cf1a925147a1601d0ba2f04ada30c4cf25173ab6df73bcb16016cff735be"
CFBD = "https://api.collegefootballdata.com"
ALIASES = {"miamifl": ["miami"], "ulm": ["ulmonroe", "louisianamonroe"],
           "fiu": ["floridainternational"], "uconn": ["connecticut"]}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())

class Fail(Exception):
    pass


def require_cfbd_neutral_flag(game):
    """Fail closed before the unchanged frozen model can coerce unknown -> home.

    This protects the CFB RUN IT entrypoint; it does not rewrite or certify the
    separately SHA-pinned legacy model's direct-call behavior.
    """
    if type(game.get("neutralSite")) is not bool:
        raise Fail("CFBD neutralSite missing or not boolean")
    return game["neutralSite"]

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

def weather_url(lat, lon):
    return "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,precipitation,snowfall",
        "wind_speed_unit": "mph", "timezone": "UTC", "forecast_days": 3})

def weather_values(d, kickoff_utc):
    """Translate only captured forecast fields; original response bytes are archived by main."""
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

def fetch_weather(lat, lon, kickoff_utc, game_id=None, fetch=http_json):
    """Standalone weather helper; live runner wraps this with original-byte receipts."""
    return weather_values(fetch(weather_url(lat, lon)), kickoff_utc)

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
    """Count only unique, previously completed game IDs observed in the live snapshot.

    A missing or duplicate event ID makes every involved team's denominator
    unknown; the caller withholds that team rather than silently undercounting
    or inflating its per-game production.
    """
    seen, ambiguous = {}, set()
    for g in games:
        sides = {g.get("homeTeam"), g.get("awayTeam")}
        game_id = g.get("id")
        if game_id in (None, "", 0):
            ambiguous.update(sides)
            continue
        key = str(game_id)
        if key in seen:
            ambiguous.update(sides)
            ambiguous.update((seen[key].get("homeTeam"), seen[key].get("awayTeam")))
            continue
        seen[key] = g
    n = {}
    for g in seen.values():
        ko = dt.datetime.fromisoformat(g["startDate"].replace("Z", "+00:00"))
        if g.get("completed") and ko < now_utc:
            for t in (g["homeTeam"], g["awayTeam"]):
                n[t] = n.get(t, 0) + 1
    for t in ambiguous:
        n.pop(t, None)
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
def run(intake, cap, now_utc, weather_fetch=fetch_weather, allow_no_injury_feed=False, legacy_inputs=False,
        injury_file=None):
    if sha256(open(M.__file__, "rb").read()) != MODEL_SHA256_PIN:
        raise Fail("FROZEN_MODEL_FILE_SHA_DRIFT")
    adv = cap["advanced"] if legacy_inputs else with_games(cap["advanced"], games_played(cap["games"], now_utc))
    teamkey = {norm(r["team"]): r["team"] for r in adv}
    def resolve(name):
        n = norm(name.replace("…", ""))
        for c in [n] + ALIASES.get(n, []):
            if c in teamkey: return teamkey[c]
        c = [v for k, v in teamkey.items() if k.startswith(n)] if name.endswith("…") else []
        return c[0] if len(c) == 1 else None
    if injury_file is not None:   # (doc, path): manual phone file overrides inline intake rows
        merged = INJ.merge(intake.copy(), injury_file[0], injury_file[1], resolve)
        intake.clear(); intake.update(merged)
    if "injuries" not in intake and not allow_no_injury_feed:
        raise Fail("INJURY_INTAKE_MISSING")
    inj = intake.get("injuries", [])
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
    shadow_means = []
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
            want = dt.datetime.combine(ko.astimezone(CT).date(),
                                       dt.datetime.strptime(L["kickoff_ct"], "%I:%M %p").time(), CT)
            if abs((ko - want).total_seconds()) > 20 * 60:
                withheld.append((label, f"kickoff mismatch: DK {L['kickoff_ct']} CT vs CFBD {ko.astimezone(CT):%-I:%M %p} CT")); continue
        if g.get("completed") or ko <= now_utc:
            withheld.append((label, f"kicked off {ko.astimezone(CT):%-I:%M %p} CT before run")); continue
        # Unknown venue status is not an eligible home game; quarantine before
        # weather/adjustments/projection rather than bool(None) -> False.
        try:
            require_cfbd_neutral_flag(g)
        except Fail as exc:
            withheld.append((label, str(exc))); continue
        ven = venues.get(g.get("venueId"), {})
        dome = bool(ven.get("dome"))
        if not dome:
            lat = next((v for v in (ven.get("latitude"), M.g(ven, "location.x"), M.g(ven, "location.latitude")) if v is not None), None)
            lon = next((v for v in (ven.get("longitude"), M.g(ven, "location.y"), M.g(ven, "location.longitude")) if v is not None), None)
            if lat is None:
                withheld.append((label, "venue coordinates missing -> no forecast")); continue
            try:
                w = weather_fetch(lat, lon, ko.astimezone(dt.timezone.utc), g["id"])
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
        else:
            gap = INJ.missing_coverage(intake, (A, H))
            if gap: pj["notes"].append("injury coverage missing: " + ", ".join(gap))
            for r in intake.get("injuries_listed", []):
                if r["team"] in (A, H):
                    pj["notes"].append(f"injury {r['team']} {r['player']} {r['status']} "
                                       f"{'applied ' + r['role'] if r['applied'] else 'listed only'} [{r['source']}]")
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
                shadow_means.append({"game_id": str(g["id"]), "stat": p["market"],
                                     "status": "BLOCKED", "reason": "PLAYER_IDENTITY_UNMATCHED"})
                withheld.append((label, f"prop {p['player']} {p['market']}: player identity not unique in CFBD")); continue
            team, pid = hit; player = ptable[hit]["name"]
            shadow_means.append(shadow_prop_mean(cap, pj, ctx, team, pid, p["market"],
                                                 player, p.get("truncated", False)))
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
    ctx["shadow_prop_means"] = {"schema": "sportsedge-cfb-shadow-prop-means-v1",
                                 "scope": "OFFER_ATTEMPTS_IN_PROJECTED_GAMES_ONLY",
                                 "attempts": len(shadow_means),
                                 "mean_only": sum(r["status"] == "MEAN_ONLY" for r in shadow_means),
                                 "blocked": sum(r["status"] == "BLOCKED" for r in shadow_means),
                                 "release_ready": False, "rows": shadow_means}
    ctx["quant_arithmetic_audit"] = quant_arithmetic_audit(rows)
    card = M.finalize(rows)
    for row in card:
        row["stars"] = 0
        row["flames"] = ""
        row["stars_label"] = "N/A — uncalibrated"
        row["projection_mode"] = ("MARKET_ANCHORED_RESEARCH" if row["market"].startswith("Prop")
                                  else "LEGACY_GAME_RESEARCH")
        row["settlement_model"] = "LEGACY_ZERO_PUSH_ASSUMPTION"
    return card, projs, withheld, ctx

INJURY_MAX_AGE_H = 6

def shadow_prop_mean(cap, pj, ctx, team, pid, market, player, truncated):
    """Market-blind legacy mean, NOT a calibrated or PIT-certified forecast.

    Scope: matched offered player/stat attempts only; no quote or line argument.
    Reject ambiguous source rows and unknown yardage rather than assume zero.
    """
    import math

    identity = {"game_id": str(pj["game"]["id"]), "team": team,
                "player_id": str(pid), "stat": market, "period": "FG"}
    base = {**identity, "model_sha256": MODEL_SHA256_PIN,
            "mode": "MARKET_BLIND_LEGACY_MEAN_RESEARCH",
            "pit_verified": False, "participation_verified": False,
            "distribution": None, "release_ready": False,
            "approved_stake_u": 0, "official_counted": 0}

    def blocked(reason):
        return {**base, "status": "BLOCKED", "reason": reason}

    if truncated:
        return blocked("TRUNCATED_NAME_NOT_EXACT_IDENTITY")
    spec = {"rush_yds": ("rushing", "CAR", "YDS", "rushingAttempts"),
            "pass_yds": ("passing", "ATT", "YDS", "passAttempts"),
            "rec_yds": ("receiving", "REC", "YDS", "passAttempts"),
            "receptions": ("receiving", "REC", None, "passAttempts")}.get(market)
    if spec is None:
        return blocked("UNSUPPORTED_STAT")
    cat, count_key, yards_key, denominator_key = spec
    try:
        def number(v):
            if isinstance(v, bool) or v is None or v == "":
                raise ValueError("missing or invalid numeric input")
            x = float(v)
            if not math.isfinite(x):
                raise ValueError("nonfinite numeric input")
            return x

        def player_stat(stat):
            found = [r for r in cap["player_" + cat]
                     if r["team"] == team and str(r.get("playerId")) == str(pid)
                     and r["statType"] == stat]
            if len(found) != 1 or norm(found[0]["player"]) != norm(player):
                raise ValueError("missing, duplicate or mismatched player stat")
            return number(found[0]["stat"])

        count = player_stat(count_key)
        den_rows = [r for r in cap["team_stats"]
                    if r["team"] == team and r["statName"] == denominator_key]
        if len(den_rows) != 1:
            raise ValueError("missing or duplicate team denominator")
        den = number(den_rows[0]["statValue"])
        if not (0 < count <= den) or not count.is_integer() or not den.is_integer():
            raise ValueError("invalid usage counts")
        yards = player_stat(yards_key) if yards_key is not None else None
        if yards is not None and not yards.is_integer():
            raise ValueError("nonintegral season yardage")
        u = {"team": team, "market": market, "share": count / den,
             "eff": yards / count if yards is not None else 1.0}
        opp = pj["away"] if team == pj["home"] else pj["home"]
        ppa_key = ("defense.rushingPlays.ppa" if market == "rush_yds"
                   else "defense.passingPlays.ppa")
        info = pj["info"][0 if team == pj["home"] else 1]
        plays = number(pj["plays"])
        pass_rate = number(info["pass_rate"])
        points = number(pj["pts_home"] if team == pj["home"] else pj["pts_away"])
        opp_ppa = number(M.g(ctx["adv"][opp], ppa_key))
        league_ppa = number(ctx["lm"][ppa_key])
        if plays <= 0 or not 0 <= pass_rate <= 1 or points < 0:
            raise ValueError("invalid game features")
        features = {**identity, "opponent": opp, "count": count, "denominator": den,
                    "yards": yards, "plays": plays, "pass_rate": pass_rate,
                    "team_points": points, "opponent_ppa": opp_ppa, "league_ppa": league_ppa}
        mean, _ = M.project_prop(u, pj, ctx)
        if not math.isfinite(mean):
            raise ValueError("nonfinite mean")
        digest = sha256(json.dumps(features, sort_keys=True, separators=(",", ":"),
                                  allow_nan=False).encode("utf-8"))
        return {**base, "status": "MEAN_ONLY", "mean": mean,
                "feature_values_sha256": digest}
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return blocked("SOURCE_INPUT_INVALID: " + str(exc))


def quant_arithmetic_audit(rows):
    """Read-only master-quant cross-check of ALL legacy priced rows, before filtering.

    This verifies the legacy no-push arithmetic only, not settlement or calibration.
    Market-anchored player probabilities are never independent forecasts.
    """
    import math
    _repo_on_path()
    from research.audit.master import odds

    counts = {"priced_rows": len(rows), "arithmetic_checked": 0,
              "market_anchored_prop_rows": 0, "integer_line_push_unmodelled": 0,
              "nonpositive_blended_ev_rows": 0}
    for i, row in enumerate(rows):
        try:
            values = [row[k] for k in ("p_model", "p_market", "p_blend",
                                       "ev_raw", "ev_blend", "odds")]
            if any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not math.isfinite(v) for v in values):
                raise ValueError("nonfinite or nonnumeric")
            p, market, blend, raw_ev, blend_ev, price = values
            if not all(0 <= v <= 1 for v in (p, market, blend)):
                raise ValueError("probability outside [0,1]")
            if abs(price) < 100:
                raise ValueError("invalid American price")
            if not math.isclose(blend, M.P_BLEND_MODEL * p + (1 - M.P_BLEND_MODEL) * market,
                                rel_tol=0, abs_tol=1e-12):
                raise ValueError("blend mismatch")
            for prob, actual in ((p, raw_ev), (blend, blend_ev)):
                if not math.isclose(odds.ev_per_unit(prob, price, p_push=0.0), actual,
                                    rel_tol=0, abs_tol=1e-12):
                    raise ValueError("EV mismatch")
            line = row.get("line")
            if line is not None and (isinstance(line, bool) or
                                     not isinstance(line, (int, float)) or not math.isfinite(line)):
                raise ValueError("invalid line")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise Fail(f"QUANT_ARITHMETIC_MISMATCH row={i + 1}: {exc}") from exc
        counts["arithmetic_checked"] += 1
        counts["market_anchored_prop_rows"] += int(row["market"].startswith("Prop"))
        counts["integer_line_push_unmodelled"] += int(line is not None and float(line).is_integer())
        counts["nonpositive_blended_ev_rows"] += int(blend_ev <= 0)
    with open(odds.__file__, "rb") as module_file:
        master_odds_sha = sha256(module_file.read())
    return {"schema": "sportsedge-cfb-legacy-quant-audit-v1",
            "scope": "ALL_LEGACY_PRICED_ROWS_BEFORE_SELECTION_FILTER",
            "master_odds_sha256": master_odds_sha,
            "arithmetic_convention": "LEGACY_ZERO_PUSH_ASSUMPTION",
            "calibration": "UNVERIFIED", "source_authentication": "UNVERIFIED",
            "release_ready": False, "official_counted": 0, "approved_stake_u": 0,
            **counts}


def eligibility(intake, now_utc, teams=()):
    """Card-level eligibility. This runner never emits official wagers: the model is unvalidated.
    Reasons are listed so a missing input is never mistaken for a model finding."""
    reasons = ["MODEL_UNVALIDATED_PAPER_0U"]
    if "injuries" not in intake:
        reasons.append("INJURY_INTAKE_MISSING")
    else:
        rv = intake.get("injuries_reviewed_utc")
        if not rv:
            reasons.append("INJURY_REVIEW_TIME_MISSING")
        else:
            try:
                reviewed = dt.datetime.fromisoformat(rv.replace("Z", "+00:00"))
                delta = (now_utc - reviewed).total_seconds()
            except (ValueError, TypeError):
                reasons.append("INJURY_REVIEW_TIME_INVALID")
            else:
                if delta < 0:
                    reasons.append("INJURY_REVIEW_FUTURE")
                elif delta > INJURY_MAX_AGE_H * 3600:
                    reasons.append("INJURY_REVIEW_STALE")
        gap = INJ.missing_coverage(intake, teams)
        if gap: reasons.append("INJURY_COVERAGE_PARTIAL: " + ", ".join(gap))
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
                     "lines_captured": intake.get("captured"), "eligibility": eligibility(intake, now_utc, [t for p in projs for t in (p["away"], p["home"])]),
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
         "_Uncalibrated research. Game probabilities use the legacy model; prop probabilities are market-anchored. p blend = 30% legacy probability / 70% market. Pushes are not modelled. No calibrated stars._", "",
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
        o.append(f"| {r['rank']} | N/A | {r['game']} | {r['market']} | {r['pick']} | "
                 f"{r['odds']:+d} | {proj} | {r['p_model']:.3f} | "
                 f"{r['p_market']:.3f}{'*' if mk else ''} | {r['p_blend']:.3f} | {r['ev_raw']*100:+.1f}% | {r['ev_blend']*100:+.1f}% |")
    o += ["", "\\* one-sided milestone price: market probability includes vig.", "", "## Withheld", ""]
    o += [f"- {g}: {w}" for g, w in c["withheld"]] or ["- none"]
    o += ["", "## Source receipts", ""] + [f"- {r['source']}: {r['bytes']} bytes, sha256 {r['sha256'][:16]}…" for r in c["receipts"]]
    return "\n".join(o) + "\n"

def _repo_on_path():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

def freeze_ledger(doc, ledger_path, now_utc=None):
    """Append one PAPER CARD_FROZEN entry (card hash + post-recheck rows) to the CFB hash chain.

    Requires the freeze recheck to have run. Refuses a tampered chain (cfb_ledger.verify) and any
    game ID already frozen in an earlier CARD_FROZEN entry. official_counted / approved_stake_u stay 0.
    """
    _repo_on_path()
    from models.cfb import cfb_ledger as ledger
    from models.cfb import cfb_capture_store as store
    c = doc["card"]
    if not c.get("rechecked_utc"):
        raise ledger.LedgerRefused("CARD_NOT_RECHECKED_BEFORE_FREEZE")
    if c.get("eligibility", {}).get("official_counted", 0) != 0 or c.get("eligibility", {}).get("approved_stake_u", 0) != 0:
        raise ledger.LedgerRefused("CARD_NON_PAPER")
    ids = {g["game"]: str(g["cfbd_game_id"]) for g in doc["model_projections"]["games"]}
    game_ids = sorted({ids[r["game"]] for r in c["rows"] if r["game"] in ids})
    if any(r["game"] not in ids for r in c["rows"]):
        raise ledger.LedgerRefused("CARD_ROW_WITHOUT_GAME_ID")
    prior = ledger.verify(ledger_path)
    seen = {str(g) for e in prior if e.get("type") == "CARD_FROZEN" for g in e.get("game_ids", [])}
    dup = sorted(seen.intersection(game_ids))
    if dup:
        raise ledger.LedgerRefused("GAME_ALREADY_FROZEN:" + ",".join(dup))
    card_sha = sha256(json.dumps(c, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode())
    rows = [r | {"cfbd_game_id": ids[r["game"]]} for r in c["rows"]]
    now = now_utc.astimezone(dt.timezone.utc) if now_utc else store.now_utc()
    return ledger.append(ledger_path, {
        "type": "CARD_FROZEN", "source": "cfb_run_it", "card_schema": c.get("schema"),
        "card_sha256": card_sha, "card_run_utc": c["run_utc"], "card_rechecked_utc": c["rechecked_utc"],
        "model_file_sha256": doc["model_projections"].get("model_file_sha256"),
        "game_ids": game_ids, "rows": json.loads(json.dumps(rows, default=str))}, now=now)

def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("intake", nargs="?"); a.add_argument("--season", type=int)
    a.add_argument("--out", default="cfb_run_it_out"); a.add_argument("--private-dir", default=None)
    a.add_argument("--allow-no-injury-feed", action="store_true")
    a.add_argument("--injuries", help="manual injury file models/cfb/injuries/<date>.json (overrides intake rows)")
    a.add_argument("--recheck", action="store_true", help="re-gate an existing --out card against the clock and re-render")
    a.add_argument("--freeze-ledger", metavar="PATH", help="append the rechecked --out card to the PAPER hash-chained ledger")
    a.add_argument("--ledger", metavar="PATH", help="alias of --freeze-ledger (run after --recheck)")
    a.add_argument("--fixture", help="offline CFBD capture JSON (tests only)")
    a.add_argument("--now", help="ISO UTC override (tests only)")
    x = a.parse_args(argv)
    now = dt.datetime.fromisoformat(x.now) if x.now else dt.datetime.now(dt.timezone.utc)
    lp = x.freeze_ledger or x.ledger
    if lp and not x.recheck:
        _repo_on_path()
        from models.cfb import cfb_ledger as ledger
        from models.cfb import cfb_capture_store as store
        try:
            e = freeze_ledger(json.load(open(os.path.join(x.out, "cfb_run_it.json"))), lp,
                              now if x.now else None)
        except (ledger.LedgerRefused, store.CaptureRefused) as err:
            print(f"LEDGER_BLOCKED {err}", file=sys.stderr); return 2
        print(f"ledger: CARD_FROZEN seq {e['seq']} games {len(e['game_ids'])} rows {len(e['rows'])} PAPER 0u"); return 0
    if x.recheck:
        f = os.path.join(x.out, "cfb_run_it.json")
        doc = recheck(json.load(open(f)), now)
        json.dump(doc, open(f, "w"), indent=1, default=str)
        open(os.path.join(x.out, "cfb_card.md"), "w").write(render(doc))
        print(f"rechecked: {len(doc['card']['rows'])} rows remain"); return 0
    intake_raw = open(x.intake, "rb").read()
    intake = json.loads(intake_raw)
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
            cap, raw, receipts = capture_cfbd(x.season, key)
            # The exact operator intake is part of the evidence, not merely a displayed timestamp.
            raw["operator_lines"] = intake_raw
            receipts.append({"source": "operator_lines", "provider": "operator_supplied",
                             "bytes": len(intake_raw), "sha256": sha256(intake_raw),
                             "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
            def wf(lat, lon, kickoff_utc, game_id):
                source = f"weather_game_{game_id}"
                if source in raw:
                    raise Fail("DUPLICATE_WEATHER_GAME_ID")
                # Store original bytes before parsing; a malformed source still has a receipt.
                body = http_bytes(weather_url(lat, lon))
                raw[source] = body
                receipts.append({"source": source, "provider": "open-meteo.com",
                                 "game_id": game_id, "bytes": len(body), "sha256": sha256(body),
                                 "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
                return weather_values(json.loads(body), kickoff_utc)
        if not x.fixture:
            now = dt.datetime.now(dt.timezone.utc)  # actual provider observation is after the pre-fetch clock
        injf = None
        if x.injuries:
            try:
                doc_i, rec_i = INJ.load_manual(x.injuries)
            except INJ.InjuryFileError as e:
                raise Fail(str(e)) from None
            injf = (doc_i, x.injuries)
            # The original file must be in the same protected source/receipt census.
            original_injuries = open(x.injuries, "rb").read()
            raw["manual_injuries"] = original_injuries
            receipts.append({**rec_i, "bytes": len(original_injuries),
                             "sha256": sha256(original_injuries)})
        card, projs, withheld, ctx = run(intake, cap, now, wf,
                                         x.allow_no_injury_feed, injury_file=injf)
        if x.private_dir:
            os.makedirs(x.private_dir, mode=0o700, exist_ok=True)
            for name, b in raw.items():
                with open(os.path.join(x.private_dir, f"{name}.json"), "wb") as capture:
                    capture.write(b)
    except Fail as e:
        print(f"BLOCKED {e}", file=sys.stderr); return 2
    os.makedirs(x.out, exist_ok=True)
    doc = to_doc(card, projs, withheld, intake, now, receipts)
    doc["original_run_quant_arithmetic_audit"] = ctx["quant_arithmetic_audit"]
    doc["original_run_shadow_prop_means"] = ctx["shadow_prop_means"]
    json.dump(doc, open(os.path.join(x.out, "cfb_run_it.json"), "w"), indent=1, default=str)
    json.dump(receipts, open(os.path.join(x.out, "receipts.json"), "w"), indent=1)
    open(os.path.join(x.out, "cfb_card.md"), "w").write(render(doc))
    print(f"{len(projs)} games projected, {len(card)} +EV rows, {len(withheld)} withheld")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
