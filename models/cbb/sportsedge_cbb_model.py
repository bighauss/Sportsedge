"""SportsEdge CBB "run it" model (stdlib only). All weights are UNTESTED starting values.

Data: barttorvik.com (free). KenPom is NOT used.

TEAM CSV columns (barttorvik team_results.csv style; aliases accepted, case-insensitive):
  team, games (G), adjoe, adjde, adj_t (adjt/tempo), efg_o, efg_d, tov_o, tov_d (TO%),
  orb_o, orb_d (OR%/DR-allowed), ftr_o, ftr_d, three_pa_rate (3PR), three_p_o, three_p_d,
  pre_adjoe, pre_adjde, pre_adj_t (optional preseason priors), venue_hca (optional), altitude (0/1 optional)
PLAYER CSV (barttorvik getadvstats csv style): player, team, mpg (min_per), usg, pts40, reb40, ast40, tpm40, rank_in_usage (optional)
GAMES CSV: game_id, home, away, neutral(0/1), away_tz_diff, away_b2b(0/1), home_b2b(0/1)
INJURIES CSV: team, player, status (out/doubtful/questionable), role (top2/rotation)
ODDS CSV: game_id, market, side, line, price_american, opp_price_american
  market in: ml, spread, total, team_total_home, team_total_away, h1_total, h1_spread
  side in: home/away/over/under.  For spread line is from `side` perspective (home -5.5).
PROP ODDS CSV: game_id, player, stat (pts/reb/ast/tpm), line, over_price, under_price

2026-11-21 fixes:
  * LEAGUE oe/tempo now match the current Torvik D-I scale (107.0 / 69.0). The old 105.0 / 67.5
    made every projected total ~8 points too high on the 11/21 slate. Both can be overridden per
    run with set_league(oe=..., tempo=...) or league_from_teams(teams) (D-I mean of the team file).
  * When a team row has no four-factor stats, the matchup leg used to collapse to the league
    average and silently drag that team halfway to average. It now falls back to the ratings leg
    alone (weight 1.0) and says so in the projection notes.
"""
import csv, math, os, sys

LEAGUE = dict(oe=107.0, tempo=69.0, three_p=0.34, efg=0.50, tov=0.18, orb=0.29, ftr=0.32)
K_REG = 12.0           # regression to league mean, games
K_3P = 30.0            # 3P% regressed harder
PRESEASON_FADE = 12.0  # games until preseason prior fully faded
HCA_DEFAULT = 3.0
ALT_TEAMS = {"BYU": 1.0, "Utah": 1.0, "Colorado": 1.0, "Air Force": 1.5, "Wyoming": 1.5,
             "New Mexico": 1.0, "Utah St.": 1.25, "Utah St": 1.25, "Colorado St.": 1.0, "Denver": 0.75, "Nevada": 0.5, "Weber St.": 0.75}
SD_MARGIN, SD_TOTAL, SD_TT, SD_H1, H1_FRAC = 11.0, 11.0, 8.0, 8.0, 0.47
W_MODEL_MKT = 0.30
PROP_ELAST = dict(pts=0.6, reb=0.6, ast=0.6, tpm=0.5)
PROP_SD_FRAC = dict(pts=0.33, reb=0.40, ast=0.45, tpm=0.65)
FOUR_FACTOR_KEYS = ("efg_o", "efg_d", "tov_o", "tov_d", "orb_o", "orb_d", "ftr_o", "ftr_d")

ALIASES = {"team": ["team"], "games": ["games", "g"], "adjoe": ["adjoe", "adj_o", "adjo"],
           "adjde": ["adjde", "adj_d", "adjd"], "adj_t": ["adj_t", "adjt", "tempo", "adj t."],
           "efg_o": ["efg_o", "efg%", "efg"], "efg_d": ["efg_d", "efgd%", "efgd"],
           "tov_o": ["tov_o", "tor", "to%"], "tov_d": ["tov_d", "tord"],
           "orb_o": ["orb_o", "orb", "or%"], "orb_d": ["orb_d", "drb", "ord"],
           "ftr_o": ["ftr_o", "ftr"], "ftr_d": ["ftr_d", "ftrd"],
           "three_pa_rate": ["three_pa_rate", "3pr", "3par"], "three_p_o": ["three_p_o", "3p_o", "3p%"],
           "three_p_d": ["three_p_d", "3p_d", "3pd%"], "pre_adjoe": ["pre_adjoe"], "pre_adjde": ["pre_adjde"],
           "pre_adj_t": ["pre_adj_t"], "venue_hca": ["venue_hca"], "altitude": ["altitude"],
           "player": ["player", "player_name"], "mpg": ["mpg", "min_per", "min"], "usg": ["usg", "usg%"],
           "pts40": ["pts40"], "reb40": ["reb40"], "ast40": ["ast40"], "tpm40": ["tpm40", "3pm40"]}

def set_league(oe=None, tempo=None):
    if oe is not None: LEAGUE["oe"] = float(oe)
    if tempo is not None: LEAGUE["tempo"] = float(tempo)
    return dict(LEAGUE)

def league_from_teams(teams):
    """D-I scale from a FULL team file: mean of (adjoe + adjde) / 2 and mean tempo.
    Only meaningful when the file covers all of D-I, not just one slate."""
    rows = [t for t in teams.values() if t.get("adjoe") and t.get("adjde") and t.get("adj_t")]
    if len(rows) < 300:
        raise ValueError(f"need the full D-I team file (>=300 teams), got {len(rows)}")
    oe = sum((t["adjoe"] + t["adjde"]) / 2 for t in rows) / len(rows)
    tempo = sum(t["adj_t"] for t in rows) / len(rows)
    return set_league(oe, tempo)

def _f(x, d=None):
    try: return float(x)
    except (TypeError, ValueError): return d

def _norm(row):
    low = {k.strip().lower(): v for k, v in row.items() if k}
    out = dict(low)
    for canon, al in ALIASES.items():
        for a in al:
            if a in low and low[a] not in (None, ""):
                out[canon] = low[a]; break
    return out

def read_csv(path):
    if not path or not os.path.exists(path): return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [_norm(r) for r in csv.DictReader(fh)]

def load_teams(path):
    t = {}
    for r in read_csv(path):
        t[r["team"]] = {k: (_f(v) if k != "team" else v) for k, v in r.items()}
    return t

def load_players(path):
    p = {}
    for r in read_csv(path):
        for k in ("mpg", "usg", "pts40", "reb40", "ast40", "tpm40"): r[k] = _f(r.get(k), 0.0)
        p.setdefault(r["team"], []).append(r)
    for team, lst in p.items():
        lst.sort(key=lambda x: -x["usg"] * x["mpg"])
        for i, x in enumerate(lst): x["usage_rank"] = i + 1
    return p

# ---------- math ----------
def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def am_to_dec(a): a = float(a); return 1 + (a / 100 if a > 0 else 100 / -a)
def am_to_imp(a): return 1 / am_to_dec(a)
def novig(a, b):
    pa, pb = am_to_imp(a), am_to_imp(b); return pa / (pa + pb)
def p_over(mean, line, sd): return 1 - ncdf((line - mean) / sd)

def regress(val, lg, games, k):
    if val is None: return lg
    w = games / (games + k); return w * val + (1 - w) * lg

def blend_prior(cur, pre, games):
    if pre is None or cur is None: return cur
    w = min(1.0, games / PRESEASON_FADE); return w * cur + (1 - w) * pre

# ---------- projection ----------
def team_eff(t):
    g = t.get("games") or 0
    o = blend_prior(t.get("adjoe"), t.get("pre_adjoe"), g)
    d = blend_prior(t.get("adjde"), t.get("pre_adjde"), g)
    tp = blend_prior(t.get("adj_t"), t.get("pre_adj_t"), g)
    return o or LEAGUE["oe"], d or LEAGUE["oe"], tp or LEAGUE["tempo"], g

def ratings_ppp(off, de):
    o, _, _, _ = team_eff(off); _, d, _, _ = team_eff(de)
    return o * d / LEAGUE["oe"] / 100.0

def has_four_factors(t):
    return all(t.get(k) is not None for k in FOUR_FACTOR_KEYS)

def matchup_ppp(off, de):
    """Advanced-stats leg: four factors + 3P matchup, regressed (k=12, 3P k=30)."""
    g = min(off.get("games") or 0, de.get("games") or 0)
    R = lambda key, t, lg: regress(t.get(key), lg * (100 if key not in ("adjoe",) else 1), t.get("games") or 0, K_REG)
    efg = (R("efg_o", off, LEAGUE["efg"]) + R("efg_d", de, LEAGUE["efg"])) / 2 - 100 * LEAGUE["efg"]
    tov = (R("tov_o", off, LEAGUE["tov"]) + R("tov_d", de, LEAGUE["tov"])) / 2 - 100 * LEAGUE["tov"]
    orb = (R("orb_o", off, LEAGUE["orb"]) + R("orb_d", de, LEAGUE["orb"])) / 2 - 100 * LEAGUE["orb"]
    ftr = (R("ftr_o", off, LEAGUE["ftr"]) + R("ftr_d", de, LEAGUE["ftr"])) / 2 - 100 * LEAGUE["ftr"]
    # 3P: heavy regression, opp 3P defense, scaled by 3PA rate
    p3o = regress(off.get("three_p_o"), 100 * LEAGUE["three_p"], off.get("games") or 0, K_3P)
    p3d = regress(de.get("three_p_d"), 100 * LEAGUE["three_p"], de.get("games") or 0, K_3P)
    par = (off.get("three_pa_rate") or 38.0) / 100
    three_adj = par * ((p3o + p3d) / 2 - 100 * LEAGUE["three_p"]) * 3 * 0.01 * 0.6  # pts/poss beyond eFG overlap
    ppp = LEAGUE["oe"] / 100 + 0.018 * efg - 0.012 * tov + 0.005 * orb + 0.002 * ftr + three_adj * 0.25
    return ppp

def possessions(h, a):
    _, _, th, _ = team_eff(h); _, _, ta, _ = team_eff(a)
    return th * ta / LEAGUE["tempo"]

def adjustments(game, home, away, inj, players):
    notes, adj = [], {"home": 0.0, "away": 0.0}
    neutral = int(_f(game.get("neutral"), 0) or 0)
    if not neutral:
        hca = home.get("venue_hca") or HCA_DEFAULT
        hca = max(2.0, min(4.5, hca))
        adj["home"] += hca / 2; adj["away"] -= hca / 2; notes.append(f"HCA {hca:+.1f}")
        alt = ALT_TEAMS.get(home["team"], 0.0) or (home.get("altitude") or 0)
        if alt: adj["home"] += alt / 2; adj["away"] -= alt / 2; notes.append(f"altitude {alt:+.2f}")
    if (_f(game.get("away_tz_diff"), 0) or 0) >= 2 or int(_f(game.get("away_b2b"), 0) or 0):
        adj["away"] -= 0.75; notes.append("away travel/b2b -0.75")
    if int(_f(game.get("home_b2b"), 0) or 0): adj["home"] -= 0.75; notes.append("home b2b -0.75")
    for side, t in (("home", home), ("away", away)):
        for i in inj.get(t["team"], []):
            st = i.get("status", "").lower()
            mult = 1.0 if st == "out" else 0.6 if st == "doubtful" else 0.25 if st == "questionable" else 0
            role = i.get("role") or ""
            if not role:
                pr = next((p for p in players.get(t["team"], []) if p["player"] == i["player"]), None)
                role = "top2" if pr and pr["usage_rank"] <= 2 else "rotation"
            pen = (3.0 if role == "top2" else 0.75) * mult  # midpoints of -2..-4 / -0.5..-1
            adj[side] -= pen; notes.append(f"{t['team']} {i['player']} {st} -{pen:.2f}")
    return adj, notes

def project_game(game, teams, inj, players):
    h, a = teams[game["home"]], teams[game["away"]]
    poss = possessions(h, a)
    ff = has_four_factors(h) and has_four_factors(a)
    w_stats = 0.5 if ff else 0.0
    ph = (1 - w_stats) * ratings_ppp(h, a) + w_stats * matchup_ppp(h, a)
    pa = (1 - w_stats) * ratings_ppp(a, h) + w_stats * matchup_ppp(a, h)
    adj, notes = adjustments(game, h, a, inj, players)
    if not ff:
        notes.append("ratings-only (no four factors)")
    hp, ap = ph * poss + adj["home"], pa * poss + adj["away"]
    return dict(home_pts=hp, away_pts=ap, margin=hp - ap, total=hp + ap, poss=poss, notes=notes)

# ---------- pricing ----------
def model_prob(proj, market, side, line):
    tempo_scale = math.sqrt(proj["poss"] / LEAGUE["tempo"])
    m, t = proj["margin"], proj["total"]
    if market == "ml":
        p = 1 - ncdf(-m / SD_MARGIN); return p if side == "home" else 1 - p
    if market == "spread":   # line from side perspective
        mm = m if side == "home" else -m
        return 1 - ncdf((-line - mm) / SD_MARGIN)
    if market == "total":
        p = p_over(t, line, SD_TOTAL * tempo_scale); return p if side == "over" else 1 - p
    if market.startswith("team_total"):
        mean = proj["home_pts"] if market.endswith("home") else proj["away_pts"]
        p = p_over(mean, line, SD_TT); return p if side == "over" else 1 - p
    if market == "h1_total":
        p = p_over(H1_FRAC * t, line, SD_H1); return p if side == "over" else 1 - p
    if market == "h1_spread":
        mm = H1_FRAC * (m if side == "home" else -m)
        return 1 - ncdf((-line - mm) / (SD_H1 * 0.85))
    raise ValueError(market)

def projection_for(proj, market):
    return {"total": proj["total"], "team_total_home": proj["home_pts"],
            "team_total_away": proj["away_pts"], "h1_total": H1_FRAC * proj["total"]}.get(market)

def stars(ev):
    return 5 if ev >= 0.08 else 4 if ev >= 0.05 else 3 if ev >= 0.03 else 2 if ev >= 0.015 else 1

def price_row(p_model, price, opp_price):
    # Both *observed* sides are required: a single implied probability contains vig.
    if opp_price in (None, "") or price in (None, ""):
        raise ValueError("NO_VIG_REQUIRES_TWO_CAPTURED_PRICES")
    for item in (price, opp_price):
        v = float(item)
        if not math.isfinite(v) or v != int(v) or abs(v) < 100:
            raise ValueError("INVALID_AMERICAN_PRICE")
    dec = am_to_dec(price)
    pm = novig(price, opp_price)
    pb = W_MODEL_MKT * p_model + (1 - W_MODEL_MKT) * pm
    return dict(model_p=p_model, market_p=pm, blend_p=pb, raw_ev=p_model * dec - 1, blend_ev=pb * dec - 1)


def captured_opposite(o, odds):
    """Validate actual reciprocal two-sided prices for the same captured market."""
    gid, mk, side = o["game_id"], o["market"], o["side"].lower()
    sides = {"home": "away", "away": "home"} if mk in ("ml", "spread") else {"over": "under", "under": "over"}
    if side not in sides:
        raise ValueError("UNKNOWN_MARKET_SIDE")
    raw_line = o.get("line")
    l1 = float(raw_line) if raw_line not in ("", None) else 0.0
    candidate = []
    for r in odds:
        if r is o or r["game_id"] != gid or r["market"] != mk or r["side"].lower() != sides[side]:
            continue
        rl = r.get("line")
        l2 = float(rl) if rl not in ("", None) else 0.0
        if (mk == "spread" and abs(l1 + l2) < 1e-9) or (mk != "spread" and abs(l1 - l2) < 1e-9):
            candidate.append(r)
    if len(candidate) != 1:
        raise ValueError("MISSING_OR_AMBIGUOUS_OPPOSITE_QUOTE")
    cp = candidate[0]["price_american"]
    declared = o.get("opp_price_american")
    if declared not in ("", None) and float(declared) != float(cp):
        raise ValueError("DECLARED_OPPOSING_PRICE_MISMATCH")
    return cp

def contradicts(side, line, proj_val):
    if proj_val is None: return False
    return (side == "under" and line < proj_val) or (side == "over" and line > proj_val)

# ---------- props ----------
def project_prop(pl, stat, team_proj_pts, team_base_pts, opp, players_team):
    base = pl[stat + "40"] * pl["mpg"] / 40.0
    ratio = team_proj_pts / team_base_pts if team_base_pts else 1.0
    mean = base * (1 + PROP_ELAST[stat] * (ratio - 1))
    if stat == "tpm" and opp:
        p3d = regress(opp.get("three_p_d"), 34.0, opp.get("games") or 0, K_3P)
        mean *= p3d / 34.0
    return mean

def resolve_prop_player(game, prop, players):
    """Fail-closed name/optional-ID lookup restricted to the exact event teams.

    The standalone CSV model does not authenticate roster observations.
    Never resolve a same-name player from a different game by first match.
    """
    teams = (game["home"], game["away"])
    team_hint = (prop.get("team") or "").strip()
    player_hint = (prop.get("player") or "").strip()
    id_hint = (prop.get("player_id") or "").strip()
    if team_hint and team_hint not in teams:
        return None, "PROP_TEAM_NOT_IN_EVENT"
    if not player_hint and not id_hint:
        return None, "PROP_SUBJECT_MISSING"
    matches = [
        p for team in teams if not team_hint or team == team_hint
        for p in players.get(team, [])
        if (not player_hint or p.get("player") == player_hint)
        and (not id_hint or str(p.get("player_id") or "").strip() == id_hint)
    ]
    if len(matches) != 1:
        return None, "AMBIGUOUS_PROP_PLAYER" if matches else "PROP_PLAYER_NOT_ON_EVENT_ROSTER"
    return matches[0], None


def run_card(inputs, out_dir="."):
    teams = load_teams(inputs["teams"]); players = load_players(inputs.get("players"))
    games = read_csv(inputs["games"]); inj = {}
    for r in read_csv(inputs.get("injuries")): inj.setdefault(r["team"], []).append(r)
    odds = read_csv(inputs.get("odds")); props = read_csv(inputs.get("props"))
    rows, dropped, projs = [], [], {}
    for g in games:
        pj = project_game(g, teams, inj, players); projs[g["game_id"]] = (g, pj)
    for o in odds:
        g, pj = projs[o["game_id"]]; line = _f(o.get("line"), 0.0)
        mk, sd = o["market"], o["side"]
        pv = projection_for(pj, mk)
        label = f"{g['away']}@{g['home']} {mk} {sd} {line:g}" if mk != "ml" else f"{g['away']}@{g['home']} ML {g[sd]}"
        if contradicts(sd, line, pv): dropped.append(label); continue
        try:
            opposite_price = captured_opposite(o, odds)
            pr = price_row(model_prob(pj, mk, sd, line), o["price_american"], opposite_price)
        except (ValueError, TypeError, OverflowError) as exc:
            dropped.append(f"{label} NO_PRICE_PAIR:{exc}")
            continue
        rows.append(dict(type="game", game_id=o["game_id"], bet=label, side=sd, line=line, price=o["price_american"], proj=pv, **pr))
    for p in props:
        if p.get("game_id") not in projs:
            dropped.append(f"PROP_EVENT_NOT_FOUND:{p.get('game_id')}:{p.get('player')}")
            continue
        g, pj = projs[p["game_id"]]
        pl, reason = resolve_prop_player(g, p, players)
        if reason:
            dropped.append(f"{reason}:{p.get('game_id')}:{p.get('player')}")
            continue
        out_names = {i["player"] for i in inj.get(pl["team"], []) if i.get("status", "").lower() == "out"}
        if pl["player"] in out_names: continue
        home_side = pl["team"] == g["home"]
        tp = pj["home_pts"] if home_side else pj["away_pts"]
        opp = teams[g["away"] if home_side else g["home"]]
        own = teams[pl["team"]]; o_, _, _, _ = team_eff(own)
        base_pts = o_ / 100 * pj["poss"]
        mean_model = project_prop(pl, p["stat"], tp, base_pts, opp, players.get(pl["team"]))
        line = _f(p["line"]); po_mkt = novig(p["over_price"], p["under_price"])
        sdv = max(0.8, PROP_SD_FRAC[p["stat"]] * max(mean_model, line))
        # market-implied mean: solve p_over(mu,line,sd)=po_mkt
        mu_mkt = line + sdv * _inv_ncdf(po_mkt)
        mean = 0.7 * mean_model + 0.3 * mu_mkt
        po = p_over(mean, line, sdv)
        for sd, price, opp_price, pm in (("over", p["over_price"], p["under_price"], po), ("under", p["under_price"], p["over_price"], 1 - po)):
            lab = f"{p['player']} {sd} {line:g} {p['stat']}"
            if contradicts(sd, line, mean): dropped.append(lab); continue
            pr = price_row(pm, price, opp_price)
            rows.append(dict(type="prop", game_id=p["game_id"], bet=lab, side=sd, line=line, price=price, proj=mean, team=pl["team"], **pr))
    rows = [r for r in rows if r["blend_ev"] > 0]
    rows.sort(key=lambda r: -r["blend_ev"])
    for r in rows: r["stars"] = stars(r["blend_ev"])
    stacks = _stacks(rows, projs)
    _write(rows, dropped, projs, stacks, out_dir)
    return dict(rows=rows, dropped=dropped, projections=projs, stacks=stacks)

def _inv_ncdf(p):
    p = min(max(p, 1e-6), 1 - 1e-6); lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if ncdf(mid) < p: lo = mid
        else: hi = mid
    return (lo + hi) / 2

def _stacks(rows, projs):
    """Same-signal stacks: >=2 plays in one game pointing the same direction (e.g. over + team total over + overs on props)."""
    out = {}
    for r in rows:
        b = r["bet"]
        sig = "over" if " over " in b else "under" if " under " in b else None
        if sig: out.setdefault((r["game_id"], sig), []).append(b)
    return {f"{k[0]}:{k[1]}": v for k, v in out.items() if len(v) >= 2}

def _write(rows, dropped, projs, stacks, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cols = ["rank", "stars", "type", "bet", "price", "proj", "model_p", "market_p", "blend_p", "raw_ev", "blend_ev"]
    with open(os.path.join(out_dir, "cbb_card.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["stars"], r["type"], r["bet"], r["price"], "" if r["proj"] is None else f"{r['proj']:.1f}"] +
                       [f"{r[c]:.4f}" for c in cols[6:]])
    L = ["# SportsEdge CBB Run It Card", "", "## Projections", "| Game | Home | Away | Total | Poss | Notes |", "|---|---|---|---|---|---|"]
    for gid, (g, p) in projs.items():
        L.append(f"| {g['away']}@{g['home']} | {p['home_pts']:.1f} | {p['away_pts']:.1f} | {p['total']:.1f} | {p['poss']:.1f} | {'; '.join(p['notes'])} |")
    L += ["", "## Plays (ranked by blended EV)", "| # | Stars | Bet | Price | Win% | Raw EV | Blend EV |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        fl = " 🔥" if r["stars"] >= 4 else ""
        L.append(f"| {i} | {'★'*r['stars']}{fl} | {r['bet']} | {r['price']} | {100*r['blend_p']:.1f}% | {100*r['raw_ev']:+.1f}% | {100*r['blend_ev']:+.1f}% |")
    L += ["", "## Same-signal stacks (correlated, size down)"] + [f"- {k}: {', '.join(v)}" for k, v in stacks.items()]
    L += ["", f"## Dropped (contradict projection): {len(dropped)}"] + [f"- {d}" for d in dropped]
    with open(os.path.join(out_dir, "cbb_card.md"), "w") as fh: fh.write("\n".join(L) + "\n")

if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "samples"
    res = run_card({k: os.path.join(d, f"{k}.csv") for k in ("teams", "players", "games", "injuries", "odds", "props")}, out_dir=sys.argv[2] if len(sys.argv) > 2 else "out")
    print(f"{len(res['rows'])} plays, {len(res['dropped'])} dropped")
