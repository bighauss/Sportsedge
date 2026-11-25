"""Point-in-time CBB full-game rating engines (CHALLENGER research; PAPER / 0u, NON_COUNTED).

Pure python (stdlib only). Never imports or edits the frozen production models. Every engine
forecasts a game using ONLY games played on earlier dates (strictly prior) plus, where the engine
uses one, a preseason prior built from the PREVIOUS season's final state.

Engines
  RAW         native additive formula on raw season-to-date ORtg/DRtg; HCA = mean in-sample residual
              of prior non-neutral games (the frozen native model's HCA rule).
  REG         RAW with ratings and pace shrunk toward the league mean by ``k`` pseudo-games.
  NATIVE_RECON native formula fed by current-season schedule-adjusted ratings (no preseason prior);
              mean-residual HCA at every non-neutral game. Closest public reconstruction of the frozen
              CBBD-native model (which consumes CBBD adjusted ratings that cannot be replayed).
  SA          schedule-adjusted ridge: eff = mu + off_i + def_j + h*s (s = +-1/2 only at HOME_VERIFIED),
              pace = pi + q_i + q_j; current season only.
  FG1         SA + preseason prior (previous-season final ratings regressed by ``carry``), recency
              weighting (form), jointly fitted HCA with a prior from earlier seasons.
Home-court is applied in projections ONLY when site == HOME_VERIFIED; NEUTRAL and UNVERIFIED get 0.
"""
from __future__ import annotations
import math
from collections import defaultdict
from datetime import date

HOME = "HOME_VERIFIED"


def _d(s):
    return date.fromisoformat(s[:10])


def usable(g):
    """Fit/forecast rows: two-team box possessions and both teams Division I (non-D1 games carry
    near-unrated opponents whose blowout margins otherwise leak into the home-court estimate)."""
    return (g.get("possessions") is not None and g["home"] != g["away"]
            and g.get("home_d1", True) and g.get("away_d1", True))


# ---------------------------------------------------------------- raw / regularized (native formula)
class RawState:
    def __init__(self):
        self.pf = defaultdict(float); self.pa = defaultdict(float)
        self.poss = defaultdict(float); self.n = defaultdict(int)
        self.games = []

    def add(self, g):
        p = g["possessions"]
        for t, f, a in ((g["home"], g["home_points"], g["away_points"]),
                        (g["away"], g["away_points"], g["home_points"])):
            self.pf[t] += f; self.pa[t] += a; self.poss[t] += p; self.n[t] += 1
        self.games.append(g)


def raw_ratings(st, k=0.0):
    tot_p = sum(st.poss.values())
    if not tot_p:
        return None
    lg = 100 * sum(st.pf.values()) / tot_p
    lp = tot_p / max(1, sum(st.n.values()))
    r = {}
    for t in st.n:
        n = st.n[t]
        o = 100 * st.pf[t] / st.poss[t]; d = 100 * st.pa[t] / st.poss[t]; pace = st.poss[t] / n
        if k:
            o = (n * o + k * lg) / (n + k); d = (n * d + k * lg) / (n + k); pace = (n * pace + k * lp) / (n + k)
        r[t] = (o, d, pace, n)
    return {"teams": r, "lg": lg, "lp": lp}


def native_project(rt, home, away, hca):
    oh, dh, ph, _ = rt["teams"][home]; oa, da, pa, _ = rt["teams"][away]
    lg, lp = rt["lg"], rt["lp"]
    poss = ph * pa / lp
    eh, ea = oh + da - lg, oa + dh - lg
    hp = eh * poss / 100 + hca / 2; ap = ea * poss / 100 - hca / 2
    return hp, ap, poss


def native_hca(rt, games):
    """Frozen-native rule: mean residual of prior NON-NEUTRAL games, in-sample, actual possessions."""
    res = []
    for g in games:
        if g["neutral"] is not False or g["home"] not in rt["teams"] or g["away"] not in rt["teams"]:
            continue
        oh, dh, _, _ = rt["teams"][g["home"]]; oa, da, _, _ = rt["teams"][g["away"]]
        eh, ea = oh + da - rt["lg"], oa + dh - rt["lg"]
        res.append((g["home_points"] - g["away_points"]) - (eh - ea) * g["possessions"] / 100)
    return (sum(res) / len(res), len(res)) if len(res) >= 50 else (None, len(res))


# ---------------------------------------------------------------- schedule-adjusted ridge
class AdjustedFit:
    """Weighted ridge solved by Gauss-Seidel, warm-started across dates."""

    def __init__(self, *, lam=2.0, lam_pace=2.0, half_life=None, prior=None, hca_prior=0.0,
                 hca_lam=0.0, unverified_term=True, iters=12, mu0=103.0, pi0=68.0):
        self.lam, self.lam_pace, self.half_life = lam, lam_pace, half_life
        self.prior = prior or {}
        self.hca_prior, self.hca_lam, self.iters = hca_prior, hca_lam, iters
        self.unverified_term = unverified_term
        self.o = defaultdict(float); self.d = defaultdict(float); self.q = defaultdict(float)
        self.mu, self.pi, self.h, self.hu = mu0, pi0, hca_prior, 0.0
        self.n = defaultdict(int)
        self.default_prior = (0.0, 0.0, 0.0)

    def prior_of(self, t):
        return self.prior.get(t, self.default_prior)

    def fit(self, games, today):
        obs = []   # (off, def, eff, w, s_verified, s_unverified)
        pace_obs = []
        n = defaultdict(int)
        for g in games:
            age = (today - _d(g["date"])).days
            w = 0.5 ** (age / self.half_life) if self.half_life else 1.0
            sv = 0.5 if g["site"] == HOME else 0.0
            su = 0.5 if (g["site"] == "UNVERIFIED" and self.unverified_term) else 0.0
            p = g["possessions"]
            obs.append((g["home"], g["away"], 100 * g["home_points"] / p, w, sv, su))
            obs.append((g["away"], g["home"], 100 * g["away_points"] / p, w, -sv, -su))
            pace_obs.append((g["home"], g["away"], p, w))
            n[g["home"]] += 1; n[g["away"]] += 1
        self.n = n
        if not obs:
            return self
        o, d, q = self.o, self.d, self.q
        by_off, by_def, by_team_pace = defaultdict(list), defaultdict(list), defaultdict(list)
        for i, ob in enumerate(obs):
            by_off[ob[0]].append(i); by_def[ob[1]].append(i)
        for j, (a, b, p, w) in enumerate(pace_obs):
            by_team_pace[a].append(j); by_team_pace[b].append(j)
        for _ in range(self.iters):
            sw = sum(ob[3] for ob in obs)
            self.mu = sum(ob[3] * (ob[2] - o[ob[0]] - d[ob[1]] - self.h * ob[4] - self.hu * ob[5]) for ob in obs) / sw
            num = sum(ob[3] * ob[4] * (ob[2] - self.mu - o[ob[0]] - d[ob[1]] - self.hu * ob[5]) for ob in obs)
            den = sum(ob[3] * ob[4] ** 2 for ob in obs)
            self.h = (num + self.hca_lam * self.hca_prior) / (den + self.hca_lam) if den + self.hca_lam else self.hca_prior
            if self.unverified_term:
                num = sum(ob[3] * ob[5] * (ob[2] - self.mu - o[ob[0]] - d[ob[1]] - self.h * ob[4]) for ob in obs)
                den = sum(ob[3] * ob[5] ** 2 for ob in obs)
                self.hu = num / (den + 1.0) if den else 0.0
            for t, idx in by_off.items():
                po = self.prior_of(t)[0]
                s = sum(obs[i][3] * (obs[i][2] - self.mu - d[obs[i][1]] - self.h * obs[i][4] - self.hu * obs[i][5]) for i in idx)
                ws = sum(obs[i][3] for i in idx)
                o[t] = (s + self.lam * po) / (ws + self.lam)
            for t, idx in by_def.items():
                pd_ = self.prior_of(t)[1]
                s = sum(obs[i][3] * (obs[i][2] - self.mu - o[obs[i][0]] - self.h * obs[i][4] - self.hu * obs[i][5]) for i in idx)
                ws = sum(obs[i][3] for i in idx)
                d[t] = (s + self.lam * pd_) / (ws + self.lam)
            # centre offence/defence (identifiability) into mu
            if o:
                mo = sum(o.values()) / len(o); md = sum(d.values()) / len(d)
                for t in o: o[t] -= mo
                for t in d: d[t] -= md
                self.mu += mo + md
            swp = sum(x[3] for x in pace_obs)
            self.pi = sum(x[3] * (x[2] - q[x[0]] - q[x[1]]) for x in pace_obs) / swp
            for t, idx in by_team_pace.items():
                pq = self.prior_of(t)[2]
                s = ws = 0.0
                for j in idx:
                    a, b, p, w = pace_obs[j]
                    other = b if a == t else a
                    s += w * (p - self.pi - q[other]); ws += w
                q[t] = (s + self.lam_pace * pq) / (ws + self.lam_pace)
        return self

    def has(self, t):
        return t in self.o or t in self.prior

    def team(self, t):
        if t in self.o:
            return self.o[t], self.d[t], self.q[t]
        return self.prior_of(t)

    def project(self, home, away, site):
        oh, dh, qh = self.team(home); oa, da, qa = self.team(away)
        poss = self.pi + qh + qa
        s = 0.5 if site == HOME else 0.0
        eh = self.mu + oh + da + self.h * s
        ea = self.mu + oa + dh - self.h * s
        return eh * poss / 100, ea * poss / 100, poss

    def final_state(self):
        return {t: (self.o[t], self.d[t], self.q[t]) for t in self.o}, self.mu, self.pi, self.h


def make_prior(final, carry, carry_pace=None, new_team=None):
    """Previous-season final ratings regressed toward 0 by ``carry``; unseen teams get ``new_team``."""
    teams, _, _, _ = final
    cp = carry if carry_pace is None else carry_pace
    pri = {t: (carry * o, carry * d, cp * q) for t, (o, d, q) in teams.items()}
    if new_team is None:
        os_ = sorted(v[0] for v in teams.values()); ds = sorted(v[1] for v in teams.values())
        k = max(0, int(0.1 * len(os_)) - 1)
        new_team = (carry * os_[k], carry * ds[-1 - k], 0.0) if os_ else (0.0, 0.0, 0.0)
    return pri, new_team


# ---------------------------------------------------------------- walk forward
def walk_forward(games, engines, *, min_games=3, priors=None):
    """Forecast each game from strictly-earlier dates. ``engines`` = names to run.

    Returns (forecasts, final_states). A forecast carries n_home/n_away (current-season games) so
    callers can restrict comparisons to identical rows.
    """
    priors = priors or {}
    games = sorted((g for g in games if usable(g)), key=lambda g: (g["date"], g["game_id"]))
    by_date = defaultdict(list)
    for g in games:
        by_date[g["date"]].append(g)
    raw = RawState()
    adj = {}
    for name in engines:
        if name in ("SA", "NATIVE_RECON"):
            adj[name] = AdjustedFit(lam=2.0, lam_pace=2.0)
        elif name.startswith("FG1"):
            cfg = priors[name]
            f = AdjustedFit(lam=cfg["lam"], lam_pace=cfg["lam_pace"], half_life=cfg.get("half_life"),
                            prior=cfg["prior"], hca_prior=cfg["hca_prior"], hca_lam=cfg["hca_lam"],
                            mu0=cfg.get("mu0", 103.0), pi0=cfg.get("pi0", 68.0))
            f.default_prior = cfg["new_team"]
            adj[name] = f
    out = []
    seen = []
    for day in sorted(by_date):
        today = _d(day)
        if seen:
            rt = raw_ratings(raw); rtk = raw_ratings(raw, k=12.0)
            hca_raw = native_hca(rt, raw.games)[0] if rt else None
            hca_reg = native_hca(rtk, raw.games)[0] if rtk else None
            for f in adj.values():
                f.fit(seen, today)
            nat = adj.get("NATIVE_RECON")
            nat_rt = None
            if nat is not None and nat.o:
                nat_rt = {"teams": {t: (nat.mu + nat.o[t], nat.mu + nat.d[t], nat.pi + nat.q[t], nat.n[t])
                                    for t in nat.o}, "lg": nat.mu, "lp": nat.pi}
                hca_nat = native_hca(nat_rt, seen)[0]
        for g in by_date[day]:
            h, a = g["home"], g["away"]
            nh, na = raw.n.get(h, 0), raw.n.get(a, 0)
            rec = {"game_id": g["game_id"], "date": day, "season": g["season"], "site": g["site"],
                   "neutral": g["neutral"], "home": h, "away": a, "n_home": nh, "n_away": na,
                   "home_points": g["home_points"], "away_points": g["away_points"],
                   "possessions": g["possessions"], "f": {}}
            if seen:
                for name in engines:
                    try:
                        if name == "RAW" and min(nh, na) >= min_games and hca_raw is not None:
                            p = native_project(rt, h, a, 0.0 if g["neutral"] is not False else hca_raw)
                        elif name == "REG" and min(nh, na) >= min_games and hca_reg is not None:
                            p = native_project(rtk, h, a, 0.0 if g["neutral"] is not False else hca_reg)
                        elif name == "NATIVE_RECON" and nat_rt and min(nh, na) >= min_games and hca_nat is not None \
                                and h in nat_rt["teams"] and a in nat_rt["teams"]:
                            p = native_project(nat_rt, h, a, 0.0 if g["neutral"] is not False else hca_nat)
                        elif name == "SA" and min(nh, na) >= min_games:
                            p = adj[name].project(h, a, g["site"])
                        elif name.startswith("FG1"):
                            p = adj[name].project(h, a, g["site"])
                        else:
                            continue
                    except KeyError:
                        continue
                    rec["f"][name] = {"home_points": p[0], "away_points": p[1], "margin": p[0] - p[1],
                                      "total": p[0] + p[1], "possessions": p[2]}
            out.append(rec)
        for g in by_date[day]:
            raw.add(g)
            seen.append(g)
    if seen:
        from datetime import timedelta
        end = _d(max(g["date"] for g in seen)) + timedelta(days=1)
        for f in adj.values():
            f.fit(seen, end)
    finals = {name: f.final_state() for name, f in adj.items()}
    return out, finals
