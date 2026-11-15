"""
SportsEdge MLB "RUN IT" model  (2026-11-15, Claude)
=====================================================
Self-contained, standard library only (Python 3.8+). No network.

Pipeline (mirrors the NFL RUN IT standard):
  team runs = 50% existing ratings model + 50% advanced-stats matchup
            (Statcast/FanGraphs stats regressed to league mean, k = 60 games)
  -> adjustments (lineups by PA/slot, bullpen fatigue, rest/travel, park by hand,
     temperature, wind, roof, altitude, umpire, OAA, catcher framing)
  -> negative binomial runs per team (var = 1.6 x mean)
  -> win prob for ML, run line, total, team totals, F5 (ML/total), NRFI/YRFI
  -> props: pitcher Ks, pitcher outs, batter hits / total bases / HR
     (usage x efficiency x opponent; mean blended 70/30 with market-implied mean)
  -> raw EV = p*dec-1 ; blended EV with p_blend = 0.30*model_p + 0.70*no-vig p
  -> filter contradicting overs/unders, flag same-signal stacks
  -> ranked card (blended EV desc, 1-5 stars) as CSV + markdown.

!!! EVERY WEIGHT / CONSTANT BELOW IS AN UNTESTED STARTING VALUE. !!!
They have NOT been backtested or calibrated. Treat output as research only.

Input CSVs (column names; extra columns ignored). See README for sources.
  games.csv     game_id,date,away,home,park,start_time,roof(open|closed|dome),
                temp_f,wind_mph,wind_dir(out|in|cross|none),altitude_ft,
                umpire,ump_runs_per_game,away_sp_id,home_sp_id,
                away_rating_runs,home_rating_runs   (existing ratings model),
                away_rest_days,home_rest_days,away_travel_tz,home_travel_tz
  pitchers.csv  (Savant custom leaderboard + FanGraphs) player_id,name,team,
                p_throws,g,gs,ip,xera,xwoba,k_percent,bb_percent,csw_percent,
                velo_season,velo_last3,bf_per_start,tto3_xwoba,
                usage_FF,usage_SI,usage_FC,usage_SL,usage_CU,usage_CH,usage_FS,
                whiff_FF,whiff_SI,whiff_FC,whiff_SL,whiff_CU,whiff_CH,whiff_FS
                (percents as 0-100 numbers, like Savant exports)
  batters.csv   player_id,name,team,stand(L|R|S),pa,xwoba,xslg,barrel_batted_rate,
                hard_hit_percent,bat_speed,k_percent,ba,iso,hr_per_pa,
                xwoba_vs_L,xwoba_vs_R,pa_vs_L,pa_vs_R,
                xwoba_FF,xwoba_SI,xwoba_FC,xwoba_SL,xwoba_CU,xwoba_CH,xwoba_FS
  lineups.csv   game_id,team,slot(1-9),player_id     (MLB StatsAPI confirmed)
  bullpen.csv   team,ip,xfip,k_bb_percent,pitches_last3
  parks.csv     park,pf_runs_lhb,pf_runs_rhb,pf_hr   (100 = neutral)
  defense.csv   team,oaa,framing_runs,games           (season totals)
  odds.csv      game_id,market,selection,line,price
                market in ML,RL,TOTAL,TT_AWAY,TT_HOME,F5_ML,F5_TOTAL,NRFI
                selection: away|home (ML/RL/F5_ML), over|under (totals),
                nrfi|yrfi (NRFI). price = American odds. line = side's line
                (RL: -1.5/+1.5 from the selected team's view).
  prop_odds.csv game_id,player_id,market(K|OUTS|HITS|TB|HR),line,over_price,under_price
"""

import csv
import math
import os
import sys

# ---------------------------------------------------------------------------
# CONSTANTS  (ALL UNTESTED STARTING VALUES)
# ---------------------------------------------------------------------------
W = {
    "ratings_weight": 0.50,          # existing ratings model share
    "matchup_weight": 0.50,          # advanced-stats matchup share
    "regress_k_games": 60,           # regression constant (games)
    "pa_per_game": 4.1,              # to convert batter PA -> games
    "bf_per_game_pitcher": 22.0,     # to convert pitcher BF -> "games"
    "lg_runs_per_team": 4.45,
    "lg_xwoba": 0.315,
    "lg_xera": 4.15,
    "lg_k_pct": 22.5,
    "lg_bb_pct": 8.3,
    "lg_csw": 28.5,
    "lg_whiff": 25.0,
    "lg_hr_per_pa": 0.031,
    "lg_ba": 0.245,
    "lg_iso": 0.160,
    "lg_barrel": 7.5,
    "lg_hardhit": 39.0,
    "lg_bat_speed": 71.5,
    "lg_bullpen_xfip": 4.10,
    "xwoba_run_exp": 2.0,            # runs ~ (xwoba/lg)^exp
    "pitcher_blend_xera": 0.6,       # pitcher quality: xERA vs (K-BB/CSW) composite
    "pitch_mix_weight": 0.5,         # batter: pitch-type matchup vs overall
    "platoon_regress_pa": 400,       # platoon split regression (PA)
    "slot_pa": [4.6, 4.5, 4.4, 4.3, 4.2, 4.1, 4.0, 3.9, 3.8],
    "tto_penalty_per_bf_over_18": 0.004,
    "velo_drop_per_mph": 0.025,      # +2.5% runs allowed per mph velo loss
    "bullpen_fatigue_threshold": 120, # pitches in last 3 days
    "bullpen_fatigue_per_10": 0.01,  # +1% bullpen runs per 10 pitches over
    "temp_per_10f": 0.01,            # +1% runs per 10F above 70
    "wind_per_mph": 0.007,           # out +0.7%/mph, in -0.7%/mph
    "altitude_per_1000ft": 0.012,
    "rest0_penalty": -0.005, "tz_penalty_per_hr": -0.006,
    "oaa_runs_per_out": 0.8,
    "nb_var_ratio": 1.6,
    "home_extra_inn_win": 0.52,
    "f5_share": 0.54,               # share of runs scored by end of 5
    "first_inn_share": 0.115,       # share in 1st (top of order)
    "first_inn_var_ratio": 2.2,     # 1st-inning runs are very overdispersed
    "f5_sp_weight": 0.85,
    "model_weight_blend": 0.30,     # p_blend = 0.3 model + 0.7 market
    "prop_model_weight": 0.70,      # prop mean blend 70 model / 30 market
    "max_runs": 30,
    "stars": [(0.08, 5), (0.05, 4), (0.03, 3), (0.015, 2), (0.0, 1)],
}
PITCHES = ["FF", "SI", "FC", "SL", "CU", "CH", "FS"]


# ---------------------------------------------------------------------------
# DATA LOADERS
# ---------------------------------------------------------------------------
def _num(v, default=None):
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).replace("%", "").strip())
    except ValueError:
        return default


def load_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
                for r in csv.DictReader(f)]


def load_keyed(path, key):
    return {r[key]: r for r in load_csv(path)}


def load_inputs(folder):
    p = lambda n: os.path.join(folder, n)
    return {
        "games": load_csv(p("games.csv")),
        "pitchers": load_keyed(p("pitchers.csv"), "player_id"),
        "batters": load_keyed(p("batters.csv"), "player_id"),
        "lineups": load_csv(p("lineups.csv")),
        "bullpen": load_keyed(p("bullpen.csv"), "team"),
        "parks": load_keyed(p("parks.csv"), "park"),
        "defense": load_keyed(p("defense.csv"), "team"),
        "odds": load_csv(p("odds.csv")),
        "prop_odds": load_csv(p("prop_odds.csv")),
    }


# ---------------------------------------------------------------------------
# HELPERS: regression, odds
# ---------------------------------------------------------------------------
def regress(x, n_games, lg, k=None):
    k = W["regress_k_games"] if k is None else k
    if x is None:
        return lg
    n = max(n_games or 0, 0)
    return (n * x + k * lg) / (n + k)


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)


def implied(a):
    return 1 / american_to_decimal(a)


def no_vig(p_a, p_b):
    s = p_a + p_b
    return p_a / s, p_b / s


# ---------------------------------------------------------------------------
# PROJECTION: pitchers, batters, lineup vs starter
# ---------------------------------------------------------------------------
def pitcher_profile(p):
    """Regressed starter profile. Returns run multiplier (1 = league avg) etc."""
    bf = (_num(p.get("bf_per_start"), 22) or 22) * max(_num(p.get("gs"), 0), 0)
    g_eq = bf / W["bf_per_game_pitcher"] if bf else _num(p.get("g"), 0)
    xera = regress(_num(p.get("xera")), g_eq, W["lg_xera"])
    k = regress(_num(p.get("k_percent")), g_eq, W["lg_k_pct"])
    bb = regress(_num(p.get("bb_percent")), g_eq, W["lg_bb_pct"])
    csw = regress(_num(p.get("csw_percent")), g_eq, W["lg_csw"])
    xw = regress(_num(p.get("xwoba")), g_eq, W["lg_xwoba"])
    # composite skill: K-BB and CSW vs league (each pt of K-BB ~ -1.5% runs)
    kbb_mult = 1 - 0.015 * ((k - bb) - (W["lg_k_pct"] - W["lg_bb_pct"]))
    csw_mult = 1 - 0.01 * (csw - W["lg_csw"])
    xera_mult = xera / W["lg_xera"]
    mult = W["pitcher_blend_xera"] * xera_mult + (1 - W["pitcher_blend_xera"]) * kbb_mult * csw_mult
    vs, v3 = _num(p.get("velo_season")), _num(p.get("velo_last3"))
    if vs and v3:
        mult *= 1 + W["velo_drop_per_mph"] * max(vs - v3, -1.0)
    bfs = regress(_num(p.get("bf_per_start")), g_eq, 22.0)
    # times-through-order penalty for long leashes
    mult *= 1 + W["tto_penalty_per_bf_over_18"] * max(bfs - 18, 0)
    usage = {t: (_num(p.get("usage_" + t), 0) or 0) / 100 for t in PITCHES}
    tot = sum(usage.values()) or 1
    usage = {t: u / tot for t, u in usage.items()}
    whiff = sum(usage[t] * (_num(p.get("whiff_" + t), W["lg_whiff"]) or W["lg_whiff"]) for t in PITCHES)
    return {"name": p.get("name", ""), "throws": p.get("p_throws", "R"), "mult": mult,
            "k_pct": k, "bb_pct": bb, "xwoba": xw, "bf_per_start": bfs,
            "ip_per_start": bfs / 4.25, "usage": usage, "whiff": whiff, "xera": xera}


def batter_vs_pitcher(b, pp):
    """Batter xwOBA vs this starter: pitch-mix weighted + regressed platoon."""
    lg = W["lg_xwoba"]
    games = (_num(b.get("pa"), 0) or 0) / W["pa_per_game"]
    base = regress(_num(b.get("xwoba")), games, lg)
    mix_num, mix_w = 0.0, 0.0
    for t, u in pp["usage"].items():
        v = _num(b.get("xwoba_" + t))
        if v is not None and u > 0:
            mix_num += u * v
            mix_w += u
    mix = mix_num / mix_w if mix_w else base
    mix = regress(mix, games * 0.5, base)  # pitch-type samples are smaller
    xw = W["pitch_mix_weight"] * mix + (1 - W["pitch_mix_weight"]) * base
    # platoon
    stand = b.get("stand", "R")
    if stand == "S":
        stand = "L" if pp["throws"] == "R" else "R"
    side = pp["throws"]
    split = _num(b.get("xwoba_vs_" + side))
    pa_s = _num(b.get("pa_vs_" + side), 0) or 0
    if split is not None:
        lg_platoon = 0.012 if stand != side else -0.012  # generic platoon edge
        prior = base + lg_platoon
        k = W["platoon_regress_pa"]
        adj = (pa_s * split + k * prior) / (pa_s + k)
        xw += adj - base
    elif stand != side:
        xw += 0.012
    else:
        xw -= 0.012
    # contact quality nudges (barrel, hard-hit, bat speed)
    br = regress(_num(b.get("barrel_batted_rate")), games, W["lg_barrel"])
    hh = regress(_num(b.get("hard_hit_percent")), games, W["lg_hardhit"])
    bs = regress(_num(b.get("bat_speed")), games, W["lg_bat_speed"])
    xw += 0.0015 * (br - W["lg_barrel"]) + 0.0004 * (hh - W["lg_hardhit"]) + 0.001 * (bs - W["lg_bat_speed"])
    # pitcher quality vs this batter (xwOBA allowed relative to league)
    xw *= (pp["xwoba"] / lg) ** 0.5
    return {"xwoba": xw, "stand": stand, "games": games}


def lineup_for(inp, gid, team):
    rows = sorted([r for r in inp["lineups"] if r["game_id"] == gid and r["team"] == team],
                  key=lambda r: int(r["slot"]))
    return [(int(r["slot"]), inp["batters"].get(r["player_id"]), r["player_id"]) for r in rows]


def lineup_matchup(inp, gid, team, pp):
    """PA-weighted lineup xwOBA vs starter; returns details per batter."""
    lu = lineup_for(inp, gid, team)
    num = den = 0.0
    hands = {"L": 0.0, "R": 0.0}
    rows = []
    k_num = 0.0
    for slot, b, pid in lu:
        if b is None:
            continue
        pa = W["slot_pa"][slot - 1]
        m = batter_vs_pitcher(b, pp)
        num += pa * m["xwoba"]
        den += pa
        hands[m["stand"]] += pa
        kp = regress(_num(b.get("k_percent")), m["games"], W["lg_k_pct"])
        k_num += pa * kp
        rows.append({"slot": slot, "pid": pid, "b": b, "pa": pa, "m": m, "k_pct": kp})
    if den == 0:
        return {"xwoba": W["lg_xwoba"], "hands": {"L": .4, "R": .6}, "rows": [], "k_pct": W["lg_k_pct"], "confirmed": False}
    return {"xwoba": num / den, "hands": {h: v / den for h, v in hands.items()}, "rows": rows,
            "k_pct": k_num / den, "confirmed": len(rows) >= 9}


def bullpen_mult(bp):
    if not bp:
        return 1.0, 0
    ip = _num(bp.get("ip"), 0) or 0
    xfip = regress(_num(bp.get("xfip")), ip / 3.0, W["lg_bullpen_xfip"])
    mult = xfip / W["lg_bullpen_xfip"]
    p3 = _num(bp.get("pitches_last3"), 0) or 0
    over = max(p3 - W["bullpen_fatigue_threshold"], 0)
    mult *= 1 + W["bullpen_fatigue_per_10"] * over / 10
    return mult, p3


def matchup_runs(inp, g, side):
    """Advanced-stats team run projection for `side` batting ('away'|'home')."""
    opp = "home" if side == "away" else "away"
    team, opp_team = g[side], g[opp]
    sp = inp["pitchers"].get(g[opp + "_sp_id"], {})
    pp = pitcher_profile(sp)
    lu = lineup_matchup(inp, g["game_id"], team, pp)
    off_mult = (lu["xwoba"] / W["lg_xwoba"]) ** W["xwoba_run_exp"]
    sp_share = min(pp["ip_per_start"] / 9.0, 0.85)
    bp_m, bp_p3 = bullpen_mult(inp["bullpen"].get(opp_team))
    pit_mult = sp_share * pp["mult"] + (1 - sp_share) * bp_m
    runs = W["lg_runs_per_team"] * off_mult * pit_mult
    return {"runs": runs, "pp": pp, "lu": lu, "sp_share": sp_share, "bp_mult": bp_m,
            "bp_p3": bp_p3, "pit_mult": pit_mult, "off_mult": off_mult}


# ---------------------------------------------------------------------------
# ADJUSTMENTS
# ---------------------------------------------------------------------------
def environment_mult(inp, g, hands):
    notes = []
    park = inp["parks"].get(g.get("park", ""), {})
    pf = (hands.get("L", .4) * (_num(park.get("pf_runs_lhb"), 100) or 100)
          + hands.get("R", .6) * (_num(park.get("pf_runs_rhb"), 100) or 100)) / 100
    m = pf
    roof = (g.get("roof") or "open").lower()
    if roof == "open":
        t = _num(g.get("temp_f"), 70)
        m *= 1 + W["temp_per_10f"] * (t - 70) / 10
        wd = (g.get("wind_dir") or "none").lower()
        ws = _num(g.get("wind_mph"), 0) or 0
        sign = 1 if wd == "out" else -1 if wd == "in" else 0
        m *= 1 + sign * W["wind_per_mph"] * ws
        notes.append(f"{t:.0f}F wind {ws:.0f} {wd}")
    else:
        notes.append(f"roof {roof}")
    # park factor already embeds normal altitude; apply only the excess above 1000 ft
    alt = _num(g.get("altitude_ft"), 0) or 0
    m *= 1 + W["altitude_per_1000ft"] * max(alt - 1000, 0) / 1000 * 0.25
    notes.append(f"PF {pf:.3f}")
    return m, notes


def team_adjust(inp, g, side):
    """Rest/travel, defense (OAA, framing of the *fielding* team)."""
    opp = "home" if side == "away" else "away"
    m = 1.0
    if (_num(g.get(side + "_rest_days"), 1) or 0) == 0:
        m *= 1 + W["rest0_penalty"]
    m *= 1 + W["tz_penalty_per_hr"] * abs(_num(g.get(side + "_travel_tz"), 0) or 0)
    d = inp["defense"].get(g[opp], {})
    games = _num(d.get("games"), 162) or 162
    oaa = regress((_num(d.get("oaa"), 0) or 0) / games, games, 0.0)
    fr = regress((_num(d.get("framing_runs"), 0) or 0) / games, games, 0.0)
    def_runs_saved = oaa * W["oaa_runs_per_out"] + fr
    m *= 1 - def_runs_saved / W["lg_runs_per_team"]
    return m


def project_game(inp, g):
    out = {}
    ump_total = _num(g.get("ump_runs_per_game"), 0) or 0
    for side in ("away", "home"):
        mu = matchup_runs(inp, g, side)
        env, notes = environment_mult(inp, g, mu["lu"]["hands"])
        adj = team_adjust(inp, g, side)
        matchup = mu["runs"] * env * adj + ump_total / 2
        rating = _num(g.get(side + "_rating_runs"), matchup)
        final = W["ratings_weight"] * rating + W["matchup_weight"] * matchup
        out[side] = dict(mu, matchup_runs=matchup, rating_runs=rating, runs=max(final, 0.5),
                         env=env, env_notes=notes, adj=adj)
    return out


# ---------------------------------------------------------------------------
# PRICING: negative binomial runs
# ---------------------------------------------------------------------------
def nb_pmf(mean, ratio=None, n=None):
    ratio = W["nb_var_ratio"] if ratio is None else ratio
    n = W["max_runs"] if n is None else n
    mean = max(mean, 1e-6)
    if ratio <= 1.0001:
        pm = [math.exp(-mean + k * math.log(mean) - math.lgamma(k + 1)) for k in range(n + 1)]
    else:
        r = mean / (ratio - 1)
        p = r / (r + mean)
        pm = [math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                       + r * math.log(p) + k * math.log(1 - p)) for k in range(n + 1)]
    s = sum(pm)
    return [x / s for x in pm]


def joint(ma, mh):
    a, h = nb_pmf(ma), nb_pmf(mh)
    return a, h


def p_side_margin(a, h, side, line):
    """P(side wins after applying `line` to side's score). Returns (win, push)."""
    win = push = 0.0
    for i, pa in enumerate(a):
        for j, ph in enumerate(h):
            diff = (i - j) if side == "away" else (j - i)
            d = diff + line
            pr = pa * ph
            if abs(d) < 1e-9:
                push += pr
            elif d > 0:
                win += pr
    return win, push


def p_ml(a, h, side, tie_home=None):
    tie_home = W["home_extra_inn_win"] if tie_home is None else tie_home
    w, tie = p_side_margin(a, h, side, 0)
    return w + tie * (tie_home if side == "home" else 1 - tie_home)


def p_over_dist(pm, line):
    over = sum(p for k, p in enumerate(pm) if k > line + 1e-9)
    push = sum(p for k, p in enumerate(pm) if abs(k - line) < 1e-9)
    return over, push


def total_dist(a, h):
    t = [0.0] * (len(a) + len(h))
    for i, pa in enumerate(a):
        for j, ph in enumerate(h):
            t[i + j] += pa * ph
    return t


def win_prob_ex_push(win, push):
    return win / (1 - push) if push < 1 else 0.0


def price_game(proj, g):
    """Returns dict market -> function(selection, line) -> (p_win_ex_push, model_line)."""
    ma, mh = proj["away"]["runs"], proj["home"]["runs"]
    a, h = joint(ma, mh)
    tot = total_dist(a, h)
    # F5: starters weigh more
    f5 = {}
    for s in ("away", "home"):
        r = proj[s]
        sp_like = r["runs"] * (r["pp"]["mult"] / r["pit_mult"]) if r["pit_mult"] else r["runs"]
        f5[s] = W["f5_share"] * (W["f5_sp_weight"] * sp_like + (1 - W["f5_sp_weight"]) * r["runs"])
    fa, fh = joint(f5["away"], f5["home"])
    f5tot = total_dist(fa, fh)
    # first inning: top of order (slots 1-3 bat) -> use NB with tighter variance
    p0 = {s: nb_pmf(W["first_inn_share"] * proj[s]["runs"], W["first_inn_var_ratio"], 12)[0] for s in ("away", "home")}
    nrfi = p0["away"] * p0["home"]

    def f(market, sel, line):
        line = _num(line, 0) or 0
        if market == "ML":
            return p_ml(a, h, sel), None
        if market == "RL":
            w, pu = p_side_margin(a, h, sel, line)
            return win_prob_ex_push(w, pu), None
        if market == "F5_ML":   # F5 ML 2-way: tie = push (most US books for 2-way F5 ML)
            w, pu = p_side_margin(fa, fh, sel, 0)
            return win_prob_ex_push(w, pu), None
        if market in ("TOTAL", "TT_AWAY", "TT_HOME", "F5_TOTAL"):
            dist = {"TOTAL": tot, "TT_AWAY": a, "TT_HOME": h, "F5_TOTAL": f5tot}[market]
            ov, pu = p_over_dist(dist, line)
            p = ov if sel == "over" else 1 - ov - pu
            return win_prob_ex_push(p, pu), None
        if market == "NRFI":
            return (nrfi if sel == "nrfi" else 1 - nrfi), None
        return None, None

    proj_vals = {"TOTAL": ma + mh, "TT_AWAY": ma, "TT_HOME": mh,
                 "F5_TOTAL": f5["away"] + f5["home"]}
    return f, proj_vals, {"f5": f5, "nrfi": nrfi}


# ---------------------------------------------------------------------------
# PROPS
# ---------------------------------------------------------------------------
def binom_over(n, p, line):
    """P(X > line) for Binomial(n,p) with non-integer n handled by interpolation."""
    def over_int(nn):
        tot = 0.0
        for k in range(nn + 1):
            if k > line + 1e-9:
                tot += math.comb(nn, k) * p ** k * (1 - p) ** (nn - k)
        return tot
    lo = int(math.floor(n))
    fr = n - lo
    return (1 - fr) * over_int(lo) + fr * over_int(lo + 1)


def poisson_over(mean, line):
    return 1 - sum(math.exp(-mean) * mean ** k / math.factorial(k) for k in range(int(math.floor(line)) + 1))


def solve_mean(over_fn, p_target, lo=0.01, hi=40.0):
    """Market-implied mean: find m with over_fn(m) = p_target (over_fn increasing)."""
    for _ in range(60):
        mid = (lo + hi) / 2
        if over_fn(mid) < p_target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def tb_over(pa, single, double, triple, hr, line):
    """Total bases distribution over n PA (n fractional -> interpolated)."""
    out = 1 - single - double - triple - hr
    step = [out, single, double, triple, hr]
    def dist(n):
        d = [1.0]
        for _ in range(n):
            nd = [0.0] * (len(d) + 4)
            for i, v in enumerate(d):
                for b, q in enumerate(step):
                    nd[i + b] += v * q
            d = nd
        return sum(v for k, v in enumerate(d) if k > line + 1e-9)
    lo = int(math.floor(pa))
    fr = pa - lo
    return (1 - fr) * dist(lo) + fr * dist(lo + 1)


def prop_models(inp, g, proj):
    """Return {(player_id, market): (over_fn(mean)->p, model_mean, label, team, signal_side)}."""
    models = {}
    for side in ("away", "home"):
        opp = "home" if side == "away" else "away"
        # Pitcher props: opposing lineup is proj[opp]['lu'] vs this side's SP?
        # proj[x]['pp'] is the SP x's lineup faces, i.e. the opponent's SP.
        pp = proj[opp]["pp"]               # SP pitching for `side`
        lu = proj[opp]["lu"]               # lineup facing him
        sp_id = g[side + "_sp_id"]
        # log5 K% (usage x efficiency x opponent)
        pk, bk, lk = pp["k_pct"] / 100, lu["k_pct"] / 100, W["lg_k_pct"] / 100
        k_rate = (pk * bk / lk) / ((pk * bk / lk) + (1 - pk) * (1 - bk) / (1 - lk))
        k_rate *= 1 + 0.01 * (pp["whiff"] - W["lg_whiff"])
        bf = pp["bf_per_start"]
        models[(sp_id, "K")] = (lambda m, bf=bf: binom_over(bf, min(m / bf, 0.95), _LINE[0]),
                                bf * k_rate, pp["name"], g[side], "pitcher_" + side)
        outs = pp["ip_per_start"] * 3 * (1 / max(proj[opp]["off_mult"], 0.5)) ** 0.3
        models[(sp_id, "OUTS")] = (lambda m: poisson_over_normal(m, _LINE[0], 0.17),
                                   outs, pp["name"], g[side], "pitcher_" + side)
        # Batter props for `side` batting vs opponent SP (proj[side])
        bat = proj[side]
        env = bat["env"]
        for r in bat["lu"]["rows"]:
            b, pa = r["b"], r["pa"]
            games = r["m"]["games"]
            q = (r["m"]["xwoba"] / W["lg_xwoba"])
            ba = regress(_num(b.get("ba")), games, W["lg_ba"]) * q ** 0.8 * env ** 0.5
            iso = regress(_num(b.get("iso")), games, W["lg_iso"]) * q * env ** 0.7
            hrr = regress(_num(b.get("hr_per_pa")), games, W["lg_hr_per_pa"]) * q ** 1.2 * env
            bb = 0.085
            hit_pa = ba * (1 - bb)
            hr = min(hrr, hit_pa * 0.6)
            xbh_bases = max(iso * (1 - bb) - 3 * hr, 0)  # ISO = 2B + 2*3B + 3*HR per AB
            triple = xbh_bases * 0.05
            double = max(xbh_bases - 2 * triple, 0)
            single = max(hit_pa - hr - double - triple, 0.0)
            name, team, pid = b.get("name", r["pid"]), g[side], r["pid"]
            models[(pid, "HITS")] = (lambda m, pa=pa: binom_over(pa, min(m / pa, .95), _LINE[0]),
                                     pa * hit_pa, name, team, "offense_" + side)
            tb_mean = pa * (single + 2 * double + 3 * triple + 4 * hr)
            def tb_fn(m, pa=pa, s=single, d=double, t=triple, h=hr, base=tb_mean):
                sc = m / base if base else 1
                return tb_over(pa, s * sc, d * sc, t * sc, h * sc, _LINE[0])
            models[(pid, "TB")] = (tb_fn, tb_mean, name, team, "offense_" + side)
            models[(pid, "HR")] = (lambda m: 1 - math.exp(-m) if _LINE[0] < 1 else poisson_over(m, _LINE[0]),
                                   pa * hr, name, team, "offense_" + side)
    return models


_LINE = [0.5]  # current line, set by caller (keeps lambdas simple)


def poisson_over_normal(mean, line, cv):
    sd = max(mean * cv, 0.5)
    z = (line + 0.5 - mean) / sd if abs(line - round(line)) < 1e-9 else (line - mean) / sd
    return 0.5 * math.erfc(z / math.sqrt(2))


# ---------------------------------------------------------------------------
# EV / BLEND / STARS
# ---------------------------------------------------------------------------
def ev_row(model_p, price, nv_p, push=0.0):
    """Price a no-vig conditional win probability on the same no-push basis.

    Distinguish W/P/L: p(win)=(1-push)*p(win|no push), losses refunded
    only for pushes. Applying p_cond*decimal-1 to integer totals or F5 ML
    would incorrectly treat refunded pushes as wins/losses.
    """
    if not (0 <= push < 1 and 0 <= model_p <= 1 and 0 <= nv_p <= 1):
        raise ValueError("INVALID_PUSH_AWARE_PROBABILITY")
    dec = american_to_decimal(price)
    p_blend = W["model_weight_blend"] * model_p + (1 - W["model_weight_blend"]) * nv_p
    model_win, blend_win = model_p * (1 - push), p_blend * (1 - push)
    model_loss, blend_loss = (1 - model_p) * (1 - push), (1 - p_blend) * (1 - push)
    return {"dec": dec, "model_p": model_win, "nv_p": nv_p, "p_blend": blend_win,
            "p_push": push, "ev_raw": model_win * (dec - 1) - model_loss,
            "ev_blend": blend_win * (dec - 1) - blend_loss}


def stars(ev):
    for th, s in W["stars"]:
        if ev >= th:
            return s
    return 0


# ---------------------------------------------------------------------------
# FILTER + STACK FLAGS
# ---------------------------------------------------------------------------
def contradicts(sel, line, projection):
    """Drop unders whose line is below projection, overs whose line is above."""
    if projection is None or line is None:
        return False
    if sel == "under" and line < projection:
        return True
    if sel == "over" and line > projection:
        return True
    return False


def signal_of(row):
    """Direction tag for same-signal stack detection."""
    m, s, gid = row["market"], row["selection"], row["game_id"]
    if m in ("TOTAL", "F5_TOTAL"):
        return f"{gid}:runs_{'up' if s == 'over' else 'down'}"
    if m == "NRFI":
        return f"{gid}:runs_{'down' if s == 'nrfi' else 'up'}"
    if m in ("TT_AWAY", "TT_HOME"):
        return f"{gid}:runs_{'up' if s == 'over' else 'down'}"
    if m in ("ML", "RL", "F5_ML"):
        return f"{gid}:side_{s}"
    if m in ("HITS", "TB", "HR"):
        return f"{gid}:runs_{'up' if s == 'over' else 'down'}"
    if m in ("K", "OUTS"):
        return f"{gid}:{row['signal_side']}_{'good' if s == 'over' else 'bad'}"
    return f"{gid}:{m}"


def flag_stacks(rows):
    from collections import Counter
    c = Counter(r["signal"] for r in rows)
    for r in rows:
        r["stack_flag"] = f"STACK x{c[r['signal']]}" if c[r["signal"]] > 1 else ""
    return rows


# ---------------------------------------------------------------------------
# RUN CARD
# ---------------------------------------------------------------------------
MARKET_NAMES = {"ML": "Moneyline", "RL": "Run line", "TOTAL": "Total", "TT_AWAY": "Away team total",
                "TT_HOME": "Home team total", "F5_ML": "F5 ML", "F5_TOTAL": "F5 total", "NRFI": "NRFI/YRFI",
                "K": "Pitcher Ks", "OUTS": "Pitcher outs", "HITS": "Hits", "TB": "Total bases", "HR": "Home run"}


def _pair_game_odds(odds_rows, gid):
    rows = [r for r in odds_rows if r["game_id"] == gid]
    pairs = {}
    for r in rows:
        key = (r["market"], abs(_num(r.get("line"), 0) or 0))
        pairs.setdefault(key, []).append(r)
    # A pair must be complementary and have one captured price per selection.
    # Equal prices or equal row counts do not establish a valid two-sided book.
    valid = {}
    for key, pair in pairs.items():
        if len(pair) != 2:
            continue
        a, b = pair
        market = key[0]
        sa, sb = a["selection"].lower(), b["selection"].lower()
        if market in ("ML", "RL", "F5_ML"):
            if {sa, sb} != {"home", "away"}:
                continue
            if market == "RL" and abs(_num(a.get("line"),0) + _num(b.get("line"),0)) > 1e-9:
                continue
        elif market in ("TOTAL", "TT_AWAY", "TT_HOME", "F5_TOTAL"):
            if {sa, sb} != {"over", "under"} or abs(_num(a.get("line"),0) - _num(b.get("line"),0)) > 1e-9:
                continue
        elif market == "NRFI":
            if {sa, sb} != {"nrfi", "yrfi"}:
                continue
        else:
            continue
        try:
            odds = [float(a["price"]), float(b["price"])]
            if any(not math.isfinite(x) or int(x) != x or abs(x) < 100 for x in odds):
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        valid[key] = pair
    return valid


def run_card(inputs, out_dir=None, min_ev=0.0):
    """inputs: dict from load_inputs() or a folder path. Writes card CSV + MD.
    Returns (rows, markdown)."""
    inp = load_inputs(inputs) if isinstance(inputs, str) else inputs
    out_dir = out_dir or (inputs if isinstance(inputs, str) else ".")
    card, context = [], []
    for g in inp["games"]:
        gid = g["game_id"]
        proj = project_game(inp, g)
        f, proj_vals, extra = price_game(proj, g)
        context.append(_context_line(g, proj, extra))
        # --- game markets
        for (mkt, _), sides in _pair_game_odds(inp["odds"], gid).items():
            if len(sides) != 2:
                continue
            imp = [implied(s["price"]) for s in sides]
            nv = no_vig(*imp)
            for s, nvp in zip(sides, nv):
                line = _num(s.get("line"))
                p, push = f(mkt, s["selection"], line)
                if p is None:
                    continue
                row = {"game_id": gid, "game": f"{g['away']}@{g['home']}", "type": "game", "market": mkt,
                       "selection": s["selection"], "line": line, "price": int(float(s["price"])),
                       "projection": proj_vals.get(mkt), "signal_side": ""}
                # Models report P(win | no push); carry push mass separately.
                if mkt in ("RL", "F5_ML"):
                    d_a, d_h = (joint(proj["away"]["runs"], proj["home"]["runs"])
                                if mkt == "RL" else
                                joint(extra["f5"]["away"], extra["f5"]["home"]))
                    _, push = p_side_margin(d_a, d_h, s["selection"], line if mkt == "RL" else 0)
                elif mkt in ("TOTAL", "TT_AWAY", "TT_HOME", "F5_TOTAL"):
                    dist = {"TOTAL": total_dist(*joint(proj["away"]["runs"], proj["home"]["runs"])),
                            "TT_AWAY": joint(proj["away"]["runs"], proj["home"]["runs"])[0],
                            "TT_HOME": joint(proj["away"]["runs"], proj["home"]["runs"])[1],
                            "F5_TOTAL": total_dist(*joint(extra["f5"]["away"], extra["f5"]["home"]))}[mkt]
                    _, push = p_over_dist(dist, line)
                else:
                    push = 0.0
                row.update(ev_row(p, s["price"], nvp, push=push))
                card.append(row)
        # --- props
        models = prop_models(inp, g, proj)
        for po in [r for r in inp["prop_odds"] if r["game_id"] == gid]:
            key = (po["player_id"], po["market"])
            if key not in models:
                continue
            fn, mmean, label, team, sigside = models[key]
            line = _num(po["line"])
            _LINE[0] = line
            nv_over, nv_under = no_vig(implied(po["over_price"]), implied(po["under_price"]))
            mkt_mean = solve_mean(fn, nv_over, 0.001, max(mmean * 6, 3))
            blend_mean = W["prop_model_weight"] * mmean + (1 - W["prop_model_weight"]) * mkt_mean
            p_over = fn(blend_mean)
            for sel, p, nvp, price in (("over", p_over, nv_over, po["over_price"]),
                                       ("under", 1 - p_over, nv_under, po["under_price"])):
                row = {"game_id": gid, "game": f"{g['away']}@{g['home']}", "type": "prop", "market": po["market"],
                       "selection": sel, "line": line, "price": int(float(price)), "player": label,
                       "projection": round(blend_mean, 2), "model_mean": round(mmean, 2),
                       "market_mean": round(mkt_mean, 2), "signal_side": sigside}
                row.update(ev_row(p, price, nvp))
                card.append(row)
    # filter + rank
    kept = [r for r in card if not (r["market"] in ("TOTAL", "TT_AWAY", "TT_HOME", "F5_TOTAL") or r["type"] == "prop")
            or not contradicts(r["selection"], r["line"], r["projection"])]
    kept = [r for r in kept if r["ev_blend"] > min_ev]
    for r in kept:
        r["stars"] = stars(r["ev_blend"])
        r["signal"] = signal_of(r)
    flag_stacks(kept)
    kept.sort(key=lambda r: r["ev_blend"], reverse=True)
    md = render_markdown(kept, context)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        write_csv(kept, os.path.join(out_dir, "mlb_card.csv"))
        with open(os.path.join(out_dir, "mlb_card.md"), "w") as fh:
            fh.write(md)
    return kept, md


def _context_line(g, proj, extra):
    a, h = proj["away"], proj["home"]
    return (f"**{g['away']} @ {g['home']}** ({g.get('park','')}, {g.get('start_time','')}) | "
            f"SP {g['away']}: {h['pp']['name']} / {g['home']}: {a['pp']['name']} | "
            f"Proj {g['away']} {a['runs']:.2f} - {g['home']} {h['runs']:.2f}, total {a['runs']+h['runs']:.2f} | "
            f"NRFI {extra['nrfi']:.1%} | Ump {g.get('umpire','?')} | {'; '.join(a['env_notes'])} | "
            f"Lineups {'confirmed' if a['lu']['confirmed'] and h['lu']['confirmed'] else 'PARTIAL'} | "
            f"Pen pitches L3: {g['away']} {h['bp_p3']:.0f}, {g['home']} {a['bp_p3']:.0f}")


CSV_COLS = ["rank", "stars", "game", "type", "market", "player", "selection", "line", "price", "projection",
            "model_p", "nv_p", "p_blend", "ev_raw", "ev_blend", "stack_flag"]


def write_csv(rows, path):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["stars"], r["game"], r["type"], MARKET_NAMES.get(r["market"], r["market"]),
                        r.get("player", ""), r["selection"], r["line"], r["price"],
                        "" if r["projection"] is None else round(r["projection"], 2),
                        round(r["model_p"], 4), round(r["nv_p"], 4), round(r["p_blend"], 4),
                        round(r["ev_raw"], 4), round(r["ev_blend"], 4), r["stack_flag"]])


def render_markdown(rows, context):
    out = ["# SportsEdge MLB RUN IT card", "",
           "_All weights are untested starting values. Ranked by blended EV._", "", "## Game context"]
    out += ["- " + c for c in context]
    for title, typ in (("Game Card", "game"), ("Prop Card", "prop")):
        out += ["", f"## {title}", "", "| # | Play | Price | Win % (model/blend) | EV raw | EV blend | Stars | Stack |",
                "|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate([x for x in rows if x["type"] == typ], 1):
            fire = " 🔥" if r["stars"] >= 4 else ""
            who = r.get("player") or r["game"]
            ln = "" if r["line"] is None or r["market"] in ("ML", "F5_ML", "NRFI") else f" {r['line']:+g}" if r["market"] == "RL" else f" {r['line']:g}"
            play = f"{who} {MARKET_NAMES.get(r['market'])} {r['selection']}{ln}{fire}"
            out.append(f"| {i} | {play} | {r['price']:+d} | {r['model_p']:.1%} / {r['p_blend']:.1%} | "
                       f"{r['ev_raw']:+.1%} | {r['ev_blend']:+.1%} | {'★'*r['stars']} | {r['stack_flag']} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "sample_inputs")
    rows, md = run_card(folder)
    print(md)
