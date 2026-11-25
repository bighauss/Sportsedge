"""Pluggable rating models for the CBB rolling-origin backtest (research, PAPER/0u).

Every model receives the SAME inputs at an origin:
  prior      -- current-season admitted finals with possessions, strictly before the origin
  carry      -- previous-season end ratings (dict team -> {"off","def"}) or {} (built
                only from previous-season finals, never from the target season)
and must return a projector `project(home, away, neutral) -> dict(home_points,
away_points, margin, total)` or raise ``native.Pass`` / ValueError to abstain.

Built-in models all reuse the FROZEN native projection formula
(``cbbd_native_score_model.project``, imported read-only) and differ only in how
team ratings are estimated, so differences isolate the rating method:

  native_frozen  repo reconstruction (research.cbb_hca.public_factorial_backtest.context,
                 8-game shrink toward league mean) + native.project. This is the
                 frozen native FORMULA on reconstructed raw ratings; it is NOT a replay
                 of CBBD /ratings/adjusted (no point-in-time CBBD archive exists).
  raw            unshrunk per-100 offensive/defensive ratings + native.project
  regularized    8-game shrink toward a preseason prior = previous-season rating
                 regressed 50% to league mean (weight 5 games) + native.project
  sched_adj      iterative opponent/venue-adjusted ratings (ridge toward the same
                 preseason prior) + native.project

A challenger (e.g. models/cbb/fullgame on grok-cbb/fullgame-ev-20261125) plugs in
via ``register(name, builder)`` or ``--model name=module:callable`` where
``builder(prior, carry) -> project``.

All hyperparameters are fixed constants chosen before any evaluation run; none
were tuned on the evaluated seasons.
"""
from collections import defaultdict
from statistics import mean
import importlib

SHRINK_GAMES = 8          # same as the repo reconstruction default
CARRY_REGRESS = 0.5       # previous-season rating regressed halfway to league mean
CARRY_WEIGHT_GAMES = 5    # pseudo-games of preseason prior
ADJ_ITERS = 30
MIN_QUALIFIED_GAMES = 4   # same as the min pace-games gate


def _native():
    import cbbd_native_score_model as native  # frozen file, read-only import
    return native


def _residual_hca(prior, ratings, qualified):
    hist = defaultdict(int)
    for g in prior:
        hist[g["home"]] += 1
        hist[g["away"]] += 1
    residual = []
    for g in prior:
        if g["neutral"] or g["home"] not in ratings or g["away"] not in ratings:
            continue
        if qualified and min(hist[g["home"]], hist[g["away"]]) < MIN_QUALIFIED_GAMES:
            continue
        h, a = ratings[g["home"]], ratings[g["away"]]
        expected = (h["off"] + a["def"] - a["off"] - h["def"]) * g["possessions"] / 100
        residual.append(g["margin"] - expected)
    return {"value": mean(residual) if len(residual) >= 50 else None, "n": len(residual)}


def repaired_hca(prior):
    """HCA repair selected on VALIDATION seasons 2022-2024 only (see RESULTS.md):
    mean non-neutral residual on UNSHRUNK per-100 ratings, games where both teams
    have >= MIN_QUALIFIED_GAMES prior games. The native rule (residual on SHRUNK
    ratings, all games) is confounded by home buy-games against rarely-seen
    (mostly non-Division-I) visitors whose shrunk ratings are far too high.
    """
    league, pace = _league(prior)
    out = _residual_hca(prior, _shrunk(prior, 0, {}, league, pace), True)
    out["basis"] = "repaired_raw_qualified_residual_mean"
    return out


def _base_ctx(prior, ratings, league, pace, repaired=True):
    """Native-shaped context. repaired=True uses repaired_hca(); False = native rule."""
    hist = defaultdict(list)
    for g in prior:
        hist[g["home"]].append(g["possessions"])
        hist[g["away"]].append(g["possessions"])
    if repaired:
        hca = repaired_hca(prior)
    else:
        hca = _residual_hca(prior, ratings, False)
        hca["basis"] = "native_residual_mean"
    return {"ratings": ratings, "league_mean_ortg": league, "league_pace": pace,
            "team_pace": {t: (mean(v), len(v)) for t, v in hist.items()},
            "settings": {"min_pace_games": 4},  # same as repo reconstruction
            "hca": hca}


def _league(prior):
    pace = mean(g["possessions"] for g in prior)
    league = 100 * sum(g["total"] for g in prior) / (2 * sum(g["possessions"] for g in prior))
    return league, pace


def _projector(ctx):
    native = _native()

    def project(home, away, neutral):
        p = native.project(ctx, home, away, neutral=neutral, _need_sd=False)
        return {k: p[k] for k in ("home_points", "away_points", "margin", "total", "possessions", "hca_applied")}
    project.ctx = ctx
    return project


def _shrunk(prior, k, carry, league, pace):
    hist = defaultdict(list)
    for g in prior:
        p = g["possessions"]
        hist[g["home"]].append((g["home_points"], g["away_points"], p))
        hist[g["away"]].append((g["away_points"], g["home_points"], p))
    out = {}
    for t, rows in hist.items():
        po = sum(r[2] for r in rows)
        c = carry.get(t) if "_league" in carry else None
        pri_o = league + CARRY_REGRESS * (c["off"] - carry["_league"]) if c else league
        pri_d = league + CARRY_REGRESS * (c["def"] - carry["_league"]) if c else league
        wk = k * pace
        out[t] = {"off": (100 * sum(r[0] for r in rows) + wk * pri_o) / (po + wk),
                  "def": (100 * sum(r[1] for r in rows) + wk * pri_d) / (po + wk)}
    return out


def build_native_frozen(prior, carry):
    from research.cbb_hca.public_factorial_backtest import context
    return _projector(context(prior, SHRINK_GAMES))


def build_raw(prior, carry):
    league, pace = _league(prior)
    return _projector(_base_ctx(prior, _shrunk(prior, 0, {}, league, pace), league, pace))


def build_regularized(prior, carry):
    league, pace = _league(prior)
    k = SHRINK_GAMES if "_league" not in carry else CARRY_WEIGHT_GAMES + SHRINK_GAMES
    return _projector(_base_ctx(prior, _shrunk(prior, k, carry, league, pace), league, pace))


def schedule_adjusted(prior, carry, league, pace, k=SHRINK_GAMES):
    """Possession-weighted ridge: pts/100 = lg + (O_t - lg) + (D_u - lg) +/- h/2.

    Solved by Gauss-Seidel style alternation; ridge pulls toward the preseason prior
    with weight k games of league-average possessions.
    """
    import numpy as np
    teams = sorted({g["home"] for g in prior} | {g["away"] for g in prior})
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    off_t, def_t, y, w, loc = [], [], [], [], []
    for g in prior:
        p = g["possessions"]
        for o, d, pts, l in ((g["home"], g["away"], g["home_points"], 0 if g["neutral"] else 1),
                             (g["away"], g["home"], g["away_points"], 0 if g["neutral"] else -1)):
            off_t.append(ix[o]); def_t.append(ix[d]); y.append(100 * pts / p); w.append(p); loc.append(l)
    off_t, def_t, y, w, loc = map(np.asarray, (off_t, def_t, y, w, loc))
    w = w.astype(float)
    pri_o = np.full(n, league); pri_d = np.full(n, league)
    if carry and "_league" in carry:
        for t, i in ix.items():
            c = carry.get(t)
            if c:
                pri_o[i] = league + CARRY_REGRESS * (c["off"] - carry["_league"])
                pri_d[i] = league + CARRY_REGRESS * (c["def"] - carry["_league"])
    wk = k * pace
    O, D, h = pri_o.copy(), pri_d.copy(), 0.0
    for _ in range(ADJ_ITERS):
        r = y - (D[def_t] - league) - loc * h / 2
        O = (np.bincount(off_t, w * r, n) + wk * pri_o) / (np.bincount(off_t, w, n) + wk)
        r = y - (O[off_t] - league) - loc * h / 2
        D = (np.bincount(def_t, w * r, n) + wk * pri_d) / (np.bincount(def_t, w, n) + wk)
        m = loc != 0
        if m.any():
            res = y[m] - O[off_t[m]] - D[def_t[m]] + league
            h = 2 * float(np.sum(w[m] * res * loc[m]) / np.sum(w[m]))
    return {t: {"off": float(O[i]), "def": float(D[i])} for t, i in ix.items()}, h


def build_sched_adj(prior, carry):
    league, pace = _league(prior)
    ratings, _h = schedule_adjusted(prior, carry, league, pace)
    return _projector(_base_ctx(prior, ratings, league, pace))


def build_native_hca_repaired(prior, carry):
    """CANDIDATE REPAIR (not frozen): repo reconstruction ratings (8-game shrink) and
    native.project; only the HCA estimator is replaced by repaired_hca()."""
    from research.cbb_hca.public_factorial_backtest import context
    ctx = context(prior, SHRINK_GAMES)
    ctx["hca"] = repaired_hca(prior)
    return _projector(ctx)


BUILTIN = ("native_frozen", "raw", "regularized", "sched_adj", "native_hca_repaired")
MODELS = {"native_frozen": build_native_frozen, "raw": build_raw,
          "regularized": build_regularized, "sched_adj": build_sched_adj,
          "native_hca_repaired": build_native_hca_repaired}


def register(name, builder):
    if name in MODELS:
        raise ValueError("MODEL_NAME_TAKEN")
    MODELS[name] = builder


def load_spec(spec):
    """'name=package.module:callable' -> register a challenger builder."""
    name, target = spec.split("=", 1)
    mod, fn = target.split(":")
    register(name, getattr(importlib.import_module(mod), fn))
    return name


def season_end_carry(games):
    """Previous-season end-of-season schedule-adjusted ratings used as next preseason prior."""
    prior = [g for g in games if g["possessions"] is not None]
    if len(prior) < 150:
        return {}
    league, pace = _league(prior)
    ratings, _ = schedule_adjusted(prior, {}, league, pace)
    ratings["_league"] = league
    return ratings


D1_MIN_GAMES = 15  # same proxy as models/cbb/fullgame/sdv_loader.D1_MIN_GAMES


def d1_set(season_games):
    """Teams with >= D1_MIN_GAMES admitted finals in a COMPLETED season (used for the next season)."""
    c = defaultdict(int)
    for g in season_games:
        c[g["home"]] += 1
        c[g["away"]] += 1
    return {t for t, n in c.items() if n >= D1_MIN_GAMES}
