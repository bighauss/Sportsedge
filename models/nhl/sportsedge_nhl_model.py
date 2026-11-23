#!/usr/bin/env python3
"""
SportsEdge NHL "RUN IT" model  (stdlib only, Python 3.8+)
==========================================================

Implements the SportsEdge RUN IT STANDARD for the NHL:

  team goals = 50% existing ratings model + 50% advanced-stats matchup
               (season stats regressed to league mean, k = 30 games)
             + adjustments (confirmed goalie GSAx, backup, back-to-back,
               travel / time zones, home ice, manual lineup adj)
  pricing    = Poisson per team (+ late empty-net adjustment, OT/SO)
  EV         = raw EV  = p_model * decimal - 1
               blend EV with p_blend = 0.30*p_model + 0.70*p_market_novig
  card       = ranked by blended EV, 1-5 stars, flames on 4-5 stars
  props      = usage x efficiency x opponent, blended 70/30 with
               market-implied mean
  filter     = drop unders whose line < projection, overs whose line > projection
  stacks     = flag picks in one game sharing the same signal

ALL WEIGHTS ARE UNTESTED STARTING VALUES. Nothing here has been backtested.

---------------------------------------------------------------------------
INPUT FILES (all CSV; header names are case-sensitive)
---------------------------------------------------------------------------
teams_csv  - MoneyPuck "teams.csv" (one row per team per situation). Used:
    team, situation ('5on5','5on4','4on5','all'), games_played,
    iceTime (seconds), scoreVenueAdjustedxGoalsFor,
    scoreVenueAdjustedxGoalsAgainst (falls back to xGoalsFor/xGoalsAgainst),
    shotsOnGoalFor, shotsOnGoalAgainst, shotAttemptsFor, shotAttemptsAgainst,
    penaltiesFor, penaltiesAgainst
    NOTE: this file treats penaltiesFor = penalties TAKEN by the team and
    penaltiesAgainst = penalties DRAWN (taken by opponents). Verify against
    the MoneyPuck data dictionary; swap with PENALTY_COLS_SWAPPED = True.

goalies_csv - MoneyPuck "goalies.csv". Used (situation == 'all'):
    name, team, situation, games_played, xGoals, goals, ongoal (shots faced)

skaters_csv - MoneyPuck "skaters.csv". Used (situation == 'all'):
    name, team, position, situation, games_played, icetime (seconds),
    I_F_shotAttempts, I_F_shotsOnGoal, I_F_points, OnIce_F_xGoals, OnIce_F_goals

ratings_csv - existing SportsEdge ratings model output:
    team, off_gpg, def_gpg     (projected goals for / against per game
                                vs an average opponent)

games_csv - today's slate (you fill from NHL API + DailyFaceoff):
    game_id, date, start_time, venue, home, away,
    home_goalie, away_goalie            (MUST be confirmed names)
    home_goalie_confirmed, away_goalie_confirmed   (1/0)
    home_goalie_is_backup, away_goalie_is_backup   (1/0)
    home_b2b, away_b2b                  (1/0)
    home_tz_shift, away_tz_shift        (time zones crossed in last 48h, int)
    home_lineup_adj, away_lineup_adj    (manual goals/game adj, e.g. -0.10
                                         for a top-line forward out)

odds_csv - market prices (American odds):
    game_id, market, selection, line, price, book
    market in: ML (2-way incl OT/SO), ML3 (regulation 3-way), PL (puck line),
               TOTAL, TT_HOME, TT_AWAY, P1_ML3, P1_TOTAL, P1_ML2 (1P no draw)
    selection in: home, away, draw, over, under
    line: PL line from the SELECTION's side (e.g. home -1.5 / away +1.5);
          total line for totals; blank for ML.
    Give BOTH sides of each market so the no-vig price can be computed.

props_csv - player prop prices:
    game_id, player, team, opp, market (SOG | POINTS | SAVES), line,
    over_price, under_price, proj_toi (optional, minutes; skaters only)

Usage:
    python3 sportsedge_nhl_model.py inputs.json        # keys = names above + out_dir
"""
import csv
import json
import math
import os
import sys

# --------------------------------------------------------------------------
# WEIGHTS (untested starting values)
# --------------------------------------------------------------------------
W = {
    "ratings_weight": 0.50,          # vs 0.50 advanced matchup
    "k_games": 30.0,                 # team stat regression
    "k_goalie_shots": 1500.0,        # GSAx / save% regression
    "home_ice_goals": 0.15,          # total goal-differential swing to home
    "b2b_goals": 0.20,               # goal-diff penalty (spec range 0.15-0.25)
    "tz_goals_per_zone": 0.05,       # per time zone crossed beyond 1
    "tz_cap": 0.15,
    "backup_goals_against": 0.10,    # extra GA when confirmed starter is the backup
    "avg_pp_minutes": 1.85,          # minutes per power play opportunity
    "other_strength_goals": 0.12,    # 4v4/3v3/SH/penalty shots per team per game
    # Empty-net rates refit 2026-11-22 on 285 2026-27 NHL finals (|final margin| shape;
    # was 0.13 / 0.07, which put 25% on 2-goal games vs 18% observed and 17% on
    # 3-goal games vs 22%). Walk-forward (fit first 142, test next 143): log-loss
    # 1.4416 -> 1.4208. See PR for evidence; PAPER / 0u.
    "en_p_lead1": 0.11,              # P(empty-net goal | regulation lead by 1)
    "en_p_lead2": 0.32,              # P(empty-net goal | lead by 2)
    "ot_shrink": 0.5,                # OT win prob shrink toward 50%
    "period_share": (0.305, 0.335, 0.36),
    "market_blend_model": 0.30,      # p_blend = 0.30 model + 0.70 market
    "prop_model_weight": 0.70,       # prop mean = 0.70 model + 0.30 market-implied
    "max_goals": 14,
}
PENALTY_COLS_SWAPPED = False
LEAGUE_SV_DEFAULT = 0.903

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def fnum(x, d=0.0):
    try:
        if x is None or str(x).strip() == "":
            return d
        return float(x)
    except ValueError:
        return d


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def regress(value, n, mean, k):
    return (value * n + mean * k) / (n + k) if (n + k) > 0 else mean


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100.0 if a > 0 else 100.0 / -a)


def implied(a):
    return 1.0 / american_to_decimal(a)


def poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def poisson_sf(line, lam):
    """P(X > line) for half lines; for integer lines P(X > line) (push separate)."""
    n = int(math.floor(line))
    return 1.0 - sum(poisson_pmf(i, lam) for i in range(n + 1))


def poisson_mean_for_over(line, p_over):
    lo, hi = 0.01, 200.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if poisson_sf(line, mid) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def stars_for(ev):
    if ev >= 0.08: return 5
    if ev >= 0.05: return 4
    if ev >= 0.03: return 3
    if ev >= 0.015: return 2
    return 1

# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------
def load_teams(path):
    """-> {team: {sit: dict}}, league means per 60 / per game."""
    rows = read_csv(path)
    T = {}
    for r in rows:
        T.setdefault(r["team"], {})[r["situation"]] = r

    def per60(r, col, fb=None):
        v = r.get(col)
        if (v is None or v == "") and fb:
            v = r.get(fb)
        ice = fnum(r.get("iceTime"))
        return fnum(v) / ice * 3600.0 if ice > 0 else 0.0

    out = {}
    for t, s in T.items():
        r5, rpp, rpk, ra = s.get("5on5"), s.get("5on4"), s.get("4on5"), s.get("all")
        if not (r5 and ra):
            continue
        gp = fnum(ra["games_played"], 1)
        taken = fnum(ra.get("penaltiesFor"))
        drawn = fnum(ra.get("penaltiesAgainst"))
        if PENALTY_COLS_SWAPPED:
            taken, drawn = drawn, taken
        out[t] = {
            "gp": gp,
            "xgf60_5": per60(r5, "scoreVenueAdjustedxGoalsFor", "xGoalsFor"),
            "xga60_5": per60(r5, "scoreVenueAdjustedxGoalsAgainst", "xGoalsAgainst"),
            "min5_pg": fnum(r5["iceTime"]) / 60.0 / gp,
            "ppxgf60": per60(rpp, "xGoalsFor") if rpp else 0.0,
            "pkxga60": per60(rpk, "xGoalsAgainst") if rpk else 0.0,
            "taken_pg": taken / gp,
            "drawn_pg": drawn / gp,
            "sogf60": per60(ra, "shotsOnGoalFor"),
            "soga60": per60(ra, "shotsOnGoalAgainst"),
            "cf60": per60(ra, "shotAttemptsFor"),
            "ca60": per60(ra, "shotAttemptsAgainst"),
            "xgf_pg": fnum(ra.get("xGoalsFor")) / gp,
        }
    keys = ["xgf60_5", "xga60_5", "min5_pg", "ppxgf60", "pkxga60", "taken_pg",
            "drawn_pg", "sogf60", "soga60", "cf60", "ca60", "xgf_pg"]
    lg = {k: sum(v[k] for v in out.values()) / len(out) for k in keys}
    # league 5v5 rate symmetric: use mean of for/against
    lg["xg60_5"] = (lg["xgf60_5"] + lg["xga60_5"]) / 2
    lg["pp_pk60"] = (lg["ppxgf60"] + lg["pkxga60"]) / 2
    lg["pen_pg"] = (lg["taken_pg"] + lg["drawn_pg"]) / 2
    lg["sog60"] = (lg["sogf60"] + lg["soga60"]) / 2
    lg["c60"] = (lg["cf60"] + lg["ca60"]) / 2
    k = W["k_games"]
    for t, v in out.items():
        g = v["gp"]
        v["r_xgf60_5"] = regress(v["xgf60_5"], g, lg["xg60_5"], k)
        v["r_xga60_5"] = regress(v["xga60_5"], g, lg["xg60_5"], k)
        v["r_ppxgf60"] = regress(v["ppxgf60"], g, lg["pp_pk60"], k)
        v["r_pkxga60"] = regress(v["pkxga60"], g, lg["pp_pk60"], k)
        v["r_taken_pg"] = regress(v["taken_pg"], g, lg["pen_pg"], k)
        v["r_drawn_pg"] = regress(v["drawn_pg"], g, lg["pen_pg"], k)
        v["r_sogf60"] = regress(v["sogf60"], g, lg["sog60"], k)
        v["r_soga60"] = regress(v["soga60"], g, lg["sog60"], k)
        v["r_ca60"] = regress(v["ca60"], g, lg["c60"], k)
    return out, lg


def load_goalies(path):
    G, shots_tot, saves_tot = {}, 0.0, 0.0
    for r in read_csv(path):
        if r.get("situation", "all") != "all":
            continue
        shots, goals, xg = fnum(r.get("ongoal")), fnum(r.get("goals")), fnum(r.get("xGoals"))
        G[r["name"]] = {"team": r["team"], "shots": shots, "goals": goals,
                        "gsax": xg - goals, "gp": fnum(r.get("games_played"))}
        shots_tot += shots
        saves_tot += shots - goals
    lg_sv = saves_tot / shots_tot if shots_tot > 0 else LEAGUE_SV_DEFAULT
    k = W["k_goalie_shots"]
    for g in G.values():
        g["gsax_per_shot"] = g["gsax"] / (g["shots"] + k)          # regressed to 0
        g["r_sv"] = regress((g["shots"] - g["goals"]) / g["shots"] if g["shots"] else lg_sv,
                            g["shots"], lg_sv, k)
    return G, lg_sv


def load_skaters(path):
    S = {}
    for r in read_csv(path):
        if r.get("situation", "all") != "all":
            continue
        gp = max(fnum(r.get("games_played")), 1)
        ice_min = fnum(r.get("icetime")) / 60.0
        if ice_min <= 0:
            continue
        cf = fnum(r.get("I_F_shotAttempts"))
        sog = fnum(r.get("I_F_shotsOnGoal"))
        oig = fnum(r.get("OnIce_F_goals"))
        S[r["name"]] = {
            "team": r["team"], "gp": gp, "toi_pg": ice_min / gp,
            "icf60": cf / ice_min * 60, "sog_per_cf": sog / cf if cf else 0.5,
            "oixgf60": fnum(r.get("OnIce_F_xGoals")) / ice_min * 60,
            "ipp": fnum(r.get("I_F_points")) / oig if oig else 0.0,
        }
    if S:
        m_ipp = sum(s["ipp"] for s in S.values()) / len(S)
        for s in S.values():  # light regression of IPP (k = 20 games, untested)
            s["ipp"] = min(regress(s["ipp"], s["gp"], m_ipp, 20.0), 1.0)
    return S


def load_ratings(path):
    return {r["team"]: {"off": fnum(r["off_gpg"]), "def": fnum(r["def_gpg"])}
            for r in read_csv(path)}

# --------------------------------------------------------------------------
# projection
# --------------------------------------------------------------------------
def matchup_goals(team, opp, T, lg):
    """Advanced-stats expected goals for `team` vs `opp` (neutral site)."""
    a, b = T[team], T[opp]
    m5 = lg["xg60_5"]
    rate5 = a["r_xgf60_5"] * b["r_xga60_5"] / m5
    mins5 = (a["min5_pg"] + b["min5_pg"]) / 2
    ev = rate5 * mins5 / 60.0
    pp_opps = (b["r_taken_pg"] + a["r_drawn_pg"]) / 2
    pp_rate = a["r_ppxgf60"] * b["r_pkxga60"] / lg["pp_pk60"]
    pp = pp_opps * W["avg_pp_minutes"] * pp_rate / 60.0
    return ev + pp + W["other_strength_goals"], {"ev": ev, "pp": pp, "pp_opps": pp_opps}


def ratings_goals(team, opp, R, lg_gpg):
    return R[team]["off"] * R[opp]["def"] / lg_gpg


def project_game(g, T, lg, G, R):
    h, a = g["home"], g["away"]
    notes = []
    for side in ("home", "away"):
        if str(g.get(side + "_goalie_confirmed", "0")).strip() not in ("1", "true", "True"):
            return None, ["SKIP: %s goalie not confirmed" % side]
    lg_gpg = sum(v["off"] for v in R.values()) / len(R)
    mh, dh = matchup_goals(h, a, T, lg)
    ma, da = matchup_goals(a, h, T, lg)
    rh, ra = ratings_goals(h, a, R, lg_gpg), ratings_goals(a, h, R, lg_gpg)
    w = W["ratings_weight"]
    lam_h = w * rh + (1 - w) * mh
    lam_a = w * ra + (1 - w) * ma
    base_h, base_a = lam_h, lam_a

    # goalies: opponent goalie GSAx/shot * expected shots faced
    exp_shots_h = T[h]["r_sogf60"] * T[a]["r_soga60"] / lg["sog60"]   # shots by home
    exp_shots_a = T[a]["r_sogf60"] * T[h]["r_soga60"] / lg["sog60"]
    gadj = {}
    for side, opp_side, shots in (("home", "away", exp_shots_h), ("away", "home", exp_shots_a)):
        gname = g[opp_side + "_goalie"]
        gl = G.get(gname)
        adj = 0.0
        if gl is None:
            notes.append("goalie %s not in file: league-average used" % gname)
        else:
            adj = -gl["gsax_per_shot"] * shots
        if str(g.get(opp_side + "_goalie_is_backup", "0")) == "1":
            adj += W["backup_goals_against"]
        gadj[side] = adj
    lam_h += gadj["home"]
    lam_a += gadj["away"]

    # home ice
    lam_h += W["home_ice_goals"] / 2
    lam_a -= W["home_ice_goals"] / 2
    # b2b and travel: penalty split as -half own goals, +half opp goals
    adj_log = {"home_ice": W["home_ice_goals"]}
    for side, other in (("home", "away"), ("away", "home")):
        pen = 0.0
        if str(g.get(side + "_b2b", "0")) == "1":
            pen += W["b2b_goals"]
        tz = abs(int(fnum(g.get(side + "_tz_shift"))))
        pen += min(max(tz - 1, 0) * W["tz_goals_per_zone"], W["tz_cap"])
        lineup = fnum(g.get(side + "_lineup_adj"))
        adj_log[side + "_b2b_travel_pen"] = pen
        adj_log[side + "_lineup"] = lineup
        if side == "home":
            lam_h += -pen / 2 + lineup
            lam_a += pen / 2
        else:
            lam_a += -pen / 2 + lineup
            lam_h += pen / 2
    lam_h, lam_a = max(lam_h, 0.5), max(lam_a, 0.5)
    proj = {
        "lam_h": lam_h, "lam_a": lam_a, "ratings_h": rh, "ratings_a": ra,
        "matchup_h": mh, "matchup_a": ma, "base_h": base_h, "base_a": base_a,
        "goalie_adj_h": gadj["home"], "goalie_adj_a": gadj["away"],
        "pp_opps_h": dh["pp_opps"], "pp_opps_a": da["pp_opps"],
        "shots_h": exp_shots_h, "shots_a": exp_shots_a, **adj_log,
    }
    return proj, notes

# --------------------------------------------------------------------------
# pricing
# --------------------------------------------------------------------------
def score_matrix(lh, la, empty_net=True):
    n = W["max_goals"]
    M = [[poisson_pmf(i, lh) * poisson_pmf(j, la) for j in range(n + 1)] for i in range(n + 1)]
    tot = sum(map(sum, M))
    M = [[p / tot for p in row] for row in M]     # renormalise truncated tail
    if not empty_net:
        return M
    E = [[0.0] * (n + 2) for _ in range(n + 2)]
    for i in range(n + 1):
        for j in range(n + 1):
            p = M[i][j]
            d = i - j
            pe = W["en_p_lead1"] if abs(d) == 1 else W["en_p_lead2"] if abs(d) == 2 else 0.0
            E[i][j] += p * (1 - pe)
            if pe:
                if d > 0:
                    E[i + 1][j] += p * pe
                else:
                    E[i][j + 1] += p * pe
    return E


class GamePricer:
    def __init__(self, lh, la):
        self.lh, self.la = lh, la
        self.M = score_matrix(lh, la, True)
        share_ot = lh / (lh + la)
        self.p_ot_home = 0.5 + (share_ot - 0.5) * W["ot_shrink"]
        s1 = W["period_share"][0]
        self.P1 = score_matrix(lh * s1, la * s1, False)
        self._dist()

    def _dist(self):
        """final-score outcome distributions incl OT/SO (OT/SO winner +1 goal)."""
        self.reg = {"home": 0.0, "draw": 0.0, "away": 0.0}
        self.diff = {}       # regulation diff
        self.total = {}      # final total incl OT goal
        self.tt_h, self.tt_a = {}, {}
        po = self.p_ot_home
        for i, row in enumerate(self.M):
            for j, p in enumerate(row):
                if p == 0:
                    continue
                d = i - j
                self.diff[d] = self.diff.get(d, 0) + p
                if d > 0: self.reg["home"] += p
                elif d < 0: self.reg["away"] += p
                else: self.reg["draw"] += p
                if d == 0:
                    for (hi, aj, q) in ((i + 1, j, po), (i, j + 1, 1 - po)):
                        self.total[hi + aj] = self.total.get(hi + aj, 0) + p * q
                        self.tt_h[hi] = self.tt_h.get(hi, 0) + p * q
                        self.tt_a[aj] = self.tt_a.get(aj, 0) + p * q
                else:
                    self.total[i + j] = self.total.get(i + j, 0) + p
                    self.tt_h[i] = self.tt_h.get(i, 0) + p
                    self.tt_a[j] = self.tt_a.get(j, 0) + p
        self.ml_home = self.reg["home"] + self.reg["draw"] * po
        self.p1 = {"home": 0.0, "draw": 0.0, "away": 0.0}
        self.p1_total = {}
        for i, row in enumerate(self.P1):
            for j, p in enumerate(row):
                k = "home" if i > j else "away" if j > i else "draw"
                self.p1[k] += p
                self.p1_total[i + j] = self.p1_total.get(i + j, 0) + p

    @staticmethod
    def _ou(dist, sel, line):
        """-> (p_win, p_push)"""
        over = sum(p for t, p in dist.items() if t > line)
        push = sum(p for t, p in dist.items() if t == line)
        under = 1 - over - push
        return (over, push) if sel == "over" else (under, push)

    def mean(self, dist):
        return sum(t * p for t, p in dist.items())

    def price(self, market, sel, line):
        """-> (p_win, p_push, projection_value_for_filter or None)"""
        if market == "ML":
            p = self.ml_home if sel == "home" else 1 - self.ml_home
            return p, 0.0, None
        if market == "ML3":
            return self.reg[sel], 0.0, None
        if market == "PL":
            # line from selection's side; final margin: reg diff, ties become +/-1
            sgn = 1 if sel == "home" else -1
            win = push = 0.0
            for d, p in self.diff.items():
                outs = [(d, 1.0)] if d != 0 else [(1, self.p_ot_home), (-1, 1 - self.p_ot_home)]
                for dd, q in outs:
                    m = sgn * dd + line
                    if m > 0: win += p * q
                    elif m == 0: push += p * q
            return win, push, None
        if market == "TOTAL":
            w, pu = self._ou(self.total, sel, line); return w, pu, self.mean(self.total)
        if market == "TT_HOME":
            w, pu = self._ou(self.tt_h, sel, line); return w, pu, self.mean(self.tt_h)
        if market == "TT_AWAY":
            w, pu = self._ou(self.tt_a, sel, line); return w, pu, self.mean(self.tt_a)
        if market == "P1_ML3":
            return self.p1[sel], 0.0, None
        if market == "P1_ML2":   # draw = push (refund)
            return self.p1[sel], self.p1["draw"], None
        if market == "P1_TOTAL":
            w, pu = self._ou(self.p1_total, sel, line); return w, pu, self.mean(self.p1_total)
        raise ValueError("unknown market " + market)

# --------------------------------------------------------------------------
# EV
# --------------------------------------------------------------------------
def ev_from(p_win, p_push, dec):
    return p_win * (dec - 1) - (1 - p_win - p_push)


def novig(prices):
    imp = [implied(x) for x in prices]
    s = sum(imp)
    return [x / s for x in imp]


def blended_ev(p_win, p_push, p_mkt_cond, dec):
    """p_mkt_cond = no-vig market prob of winning given no push."""
    p_model_cond = p_win / (1 - p_push) if p_push < 1 else 0.0
    pb = W["market_blend_model"] * p_model_cond + (1 - W["market_blend_model"]) * p_mkt_cond
    pw = pb * (1 - p_push)
    return ev_from(pw, p_push, dec), pb


SIGNAL = {  # (market, selection) -> signal tag
    ("ML", "home"): "home_side", ("ML3", "home"): "home_side", ("PL", "home"): "home_side",
    ("TT_HOME", "over"): "home_side", ("TT_AWAY", "under"): "home_side",
    ("P1_ML3", "home"): "home_side", ("P1_ML2", "home"): "home_side",
    ("ML", "away"): "away_side", ("ML3", "away"): "away_side", ("PL", "away"): "away_side",
    ("TT_AWAY", "over"): "away_side", ("TT_HOME", "under"): "away_side",
    ("P1_ML3", "away"): "away_side", ("P1_ML2", "away"): "away_side",
    ("TOTAL", "over"): "high_scoring", ("P1_TOTAL", "over"): "high_scoring",
    ("TOTAL", "under"): "low_scoring", ("P1_TOTAL", "under"): "low_scoring",
}


def contradicts(sel, line, projection):
    if projection is None:
        return False
    if sel == "under" and line < projection:
        return True
    if sel == "over" and line > projection:
        return True
    return False

# --------------------------------------------------------------------------
# props
# --------------------------------------------------------------------------
def project_prop(pr, S, G, T, lg, projs):
    m = pr["market"].upper()
    gp = projs.get(pr["game_id"])
    if m == "SAVES":
        gl = G.get(pr["player"])
        if not gl or not gp:
            return None, "no goalie/game data"
        proj, _g = gp
        shots = proj["shots_a"] if pr["team"] == _g["home"] else proj["shots_h"]
        return shots * gl["r_sv"], "opp shots %.1f x sv %.3f" % (shots, gl["r_sv"])
    s = S.get(pr["player"])
    if not s:
        return None, "no skater data"
    toi = fnum(pr.get("proj_toi"), s["toi_pg"]) or s["toi_pg"]
    o = T.get(pr["opp"])
    if m == "SOG":
        supp = o["r_ca60"] / lg["c60"] if o else 1.0
        rate = s["icf60"] * s["sog_per_cf"]
        return toi * rate / 60 * supp, "TOI %.1f x SOG/60 %.2f x opp %.2f" % (toi, rate, supp)
    if m == "POINTS":
        supp = o["r_xga60_5"] / lg["xg60_5"] if o else 1.0
        val = toi * s["oixgf60"] / 60 * s["ipp"] * supp
        return val, "TOI %.1f x oiXGF/60 %.2f x IPP %.2f x opp %.2f" % (toi, s["oixgf60"], s["ipp"], supp)
    return None, "unknown prop market"

# --------------------------------------------------------------------------
# card
# --------------------------------------------------------------------------
def run_card(inputs):
    T, lg = load_teams(inputs["teams_csv"])
    G, lg_sv = load_goalies(inputs["goalies_csv"])
    S = load_skaters(inputs["skaters_csv"]) if inputs.get("skaters_csv") else {}
    R = load_ratings(inputs["ratings_csv"])
    games = read_csv(inputs["games_csv"])
    odds = read_csv(inputs["odds_csv"])
    props = read_csv(inputs["props_csv"]) if inputs.get("props_csv") else []
    out_dir = inputs.get("out_dir", ".")
    os.makedirs(out_dir, exist_ok=True)

    projs, pricers, notes, gmeta = {}, {}, [], {}
    for g in games:
        proj, n = project_game(g, T, lg, G, R)
        notes += ["%s: %s" % (g["game_id"], x) for x in n]
        gmeta[g["game_id"]] = g
        if proj:
            projs[g["game_id"]] = (proj, g)
            pricers[g["game_id"]] = GamePricer(proj["lam_h"], proj["lam_a"])

    picks, dropped = [], []
    # group odds rows into markets for no-vig
    groups = {}
    for o in odds:
        if o["game_id"] not in pricers:
            continue
        mkt = o["market"].upper()
        line = fnum(o.get("line"))
        key_line = abs(line) if mkt == "PL" else line
        groups.setdefault((o["game_id"], mkt, key_line, o.get("book", "")), []).append(o)
    for (gid, mkt, _kl, book), rows in groups.items():
        if len(rows) < 2:
            notes.append("%s %s: one-sided market skipped (need both sides for no-vig)" % (gid, mkt))
            continue
        nv = novig([r["price"] for r in rows])
        gpz = pricers[gid]
        g = gmeta[gid]
        for r, pm in zip(rows, nv):
            sel = r["selection"].lower()
            line = fnum(r.get("line"))
            pw, pp, projv = gpz.price(mkt, sel, line)
            dec = american_to_decimal(r["price"])
            raw = ev_from(pw, pp, dec)
            bev, pb = blended_ev(pw, pp, pm, dec)
            team = g["home"] if sel == "home" else g["away"] if sel == "away" else ""
            rec = {"game_id": gid, "matchup": "%s@%s" % (g["away"], g["home"]), "type": "game",
                   "market": mkt, "pick": (team or sel) + ("" if mkt in ("ML", "ML3", "P1_ML3", "P1_ML2") and sel != "draw" else " %s" % (r.get("line") or "")).rstrip(),
                   "selection": sel, "line": r.get("line", ""), "price": r["price"], "book": book,
                   "model_p": round(pw, 4), "push_p": round(pp, 4), "market_p": round(pm, 4),
                   "blend_p": round(pb, 4), "raw_ev": round(raw, 4), "blend_ev": round(bev, 4),
                   "projection": round(projv, 2) if projv is not None else "",
                   "why": "", "signal": SIGNAL.get((mkt, sel), "")}
            if contradicts(sel, line, projv):
                dropped.append(rec); continue
            picks.append(rec)

    for pr in props:
        val, why = project_prop(pr, S, G, T, lg, projs)
        if val is None:
            notes.append("prop %s %s skipped: %s" % (pr["player"], pr["market"], why)); continue
        line = fnum(pr["line"])
        nv_over, nv_under = novig([pr["over_price"], pr["under_price"]])
        mkt_mean = poisson_mean_for_over(line, nv_over)
        mean = W["prop_model_weight"] * val + (1 - W["prop_model_weight"]) * mkt_mean
        p_over = poisson_sf(line, mean)
        p_push = poisson_pmf(int(line), mean) if line == int(line) else 0.0
        for sel, price, pm in (("over", pr["over_price"], nv_over), ("under", pr["under_price"], nv_under)):
            pw = p_over if sel == "over" else 1 - p_over - p_push
            dec = american_to_decimal(price)
            bev, pb = blended_ev(pw, p_push, pm, dec)
            g = gmeta.get(pr["game_id"], {})
            rec = {"game_id": pr["game_id"], "matchup": "%s@%s" % (g.get("away", "?"), g.get("home", "?")),
                   "type": "prop", "market": pr["market"].upper(),
                   "pick": "%s %s %s" % (pr["player"], sel, pr["line"]), "selection": sel,
                   "line": pr["line"], "price": price, "book": pr.get("book", ""),
                   "model_p": round(pw, 4), "push_p": round(p_push, 4), "market_p": round(pm, 4),
                   "blend_p": round(pb, 4), "raw_ev": round(ev_from(pw, p_push, dec), 4),
                   "blend_ev": round(bev, 4), "projection": round(mean, 2),
                   "why": "%s; model %.2f, mkt-implied %.2f" % (why, val, mkt_mean),
                   "signal": ("%s_side" % ("home" if pr["team"] == g.get("home") else "away"))
                             if sel == "over" else ""}
            if contradicts(sel, line, mean):
                dropped.append(rec); continue
            picks.append(rec)

    picks = [p for p in picks if p["blend_ev"] > 0]
    picks.sort(key=lambda p: p["blend_ev"], reverse=True)
    stack_count = {}
    for p in picks:
        if p["signal"]:
            stack_count[(p["game_id"], p["signal"])] = stack_count.get((p["game_id"], p["signal"]), 0) + 1
    for i, p in enumerate(picks, 1):
        p["rank"] = i
        p["stars"] = stars_for(p["blend_ev"])
        p["flame"] = "FIRE" if p["stars"] >= 4 else ""
        n = stack_count.get((p["game_id"], p["signal"]), 0)
        p["stack_flag"] = "STACK:%s x%d" % (p["signal"], n) if n > 1 else ""

    cols = ["rank", "stars", "flame", "type", "matchup", "market", "pick", "price", "book",
            "model_p", "market_p", "blend_p", "push_p", "raw_ev", "blend_ev", "projection",
            "stack_flag", "why", "game_id", "selection", "line", "signal"]
    csv_path = os.path.join(out_dir, "nhl_card.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(picks)

    md = ["# SportsEdge NHL RUN IT card", "", "All weights untested starting values.", ""]
    for gid, (proj, g) in projs.items():
        gpz = pricers[gid]
        md += ["## %s @ %s  (%s %s, %s)" % (g["away"], g["home"], g.get("date", ""), g.get("start_time", ""), g.get("venue", "")),
               "", "**Projection:** %s %.2f | %s %.2f | Total %.2f | %s ML %.1f%% | Reg draw %.1f%%" % (
                   g["home"], proj["lam_h"], g["away"], proj["lam_a"], gpz.mean(gpz.total),
                   g["home"], 100 * gpz.ml_home, 100 * gpz.reg["draw"]),
               "", "**Key inputs:** goalies %s (H) / %s (A); ratings %.2f-%.2f, matchup %.2f-%.2f; "
               "goalie adj %+.2f/%+.2f; PP opps %.2f/%.2f; exp SOG %.1f/%.1f; home ice +%.2f; "
               "B2B/travel pen H %.2f A %.2f; lineup H %+.2f A %+.2f" % (
                   g["home_goalie"], g["away_goalie"], proj["ratings_h"], proj["ratings_a"],
                   proj["matchup_h"], proj["matchup_a"], proj["goalie_adj_h"], proj["goalie_adj_a"],
                   proj["pp_opps_h"], proj["pp_opps_a"], proj["shots_h"], proj["shots_a"],
                   proj["home_ice"], proj["home_b2b_travel_pen"], proj["away_b2b_travel_pen"],
                   proj["home_lineup"], proj["away_lineup"]), ""]
        for typ, title in (("game", "Game Card"), ("prop", "Prop Card")):
            rows = [p for p in picks if p["game_id"] == gid and p["type"] == typ]
            md += ["### " + title, ""]
            if not rows:
                md += ["_no +EV plays_", ""]; continue
            md += ["| # | Play | Price | Win % | Raw EV | Blend EV | Stars | Flag |",
                   "|---|---|---|---|---|---|---|---|"]
            for p in rows:
                md.append("| %d | %s%s | %s | %.1f%% | %+.1f%% | %+.1f%% | %s | %s |" % (
                    p["rank"], "[FIRE] " if p["flame"] else "", p["market"] + " " + p["pick"], p["price"],
                    100 * p["model_p"], 100 * p["raw_ev"], 100 * p["blend_ev"],
                    "*" * p["stars"], p["stack_flag"]))
            md.append("")
    if notes:
        md += ["## Notes", ""] + ["- " + n for n in notes] + [""]
    md += ["Dropped (contradict projection): %d" % len(dropped)]
    md_path = os.path.join(out_dir, "nhl_card.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md) + "\n")
    return {"picks": picks, "dropped": dropped, "projections": projs, "pricers": pricers,
            "notes": notes, "csv": csv_path, "md": md_path}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(1)
    with open(sys.argv[1]) as f:
        res = run_card(json.load(f))
    print("picks: %d  dropped: %d  -> %s, %s" % (len(res["picks"]), len(res["dropped"]), res["csv"], res["md"]))
