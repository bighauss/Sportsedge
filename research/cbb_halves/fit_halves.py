"""Fit and evaluate the CBB halves models chronologically (PAPER/0u, NON_COUNTED).

Protocol (preregistered in research/cbb_halves/PROTOCOL.md, fixed before the test run):
  * Tuning of the point-in-time full-game projector: seasons 2019-2020 only.
  * Development / validation: rolling-origin folds, test season S in 2021..2025, each fitted only
    on seasons < S. Every modelling choice (residual shape, feature variants) is made here.
  * Untouched test window: season 2026 (Nov 2025 - Apr 2026). Evaluated exactly once with the
    coefficients fitted on 2019-2025; those same coefficients ship as coefficients_halves_v1.json.

Usage:
  python research/cbb_halves/fit_halves.py --cache <fetch cache> --stage dev
  python research/cbb_halves/fit_halves.py --cache <fetch cache> --stage test   # once
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import erf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "models" / "cbb"))
import pit_fullgame as F  # noqa: E402

PIT_PARAMS = dict(k0=0.25, k_min=0.045, carry=0.8)  # tuned on 2019-2020 only
DEV_SEASONS = (2021, 2022, 2023, 2024, 2025)
TEST_SEASON = 2026
P_GRID = [0.001, 0.0025, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075] + \
         [round(float(x), 3) for x in np.arange(0.1, 0.9001, 0.025)] + \
         [0.925, 0.95, 0.97, 0.98, 0.99, 0.995, 0.9975, 0.999]

SD_BASE = ["1", "abs_M10", "T140_20", "early"]
SD_HT = SD_BASE + ["abs_m1_10"]
PREGAME_SPEC = {
    "MARGIN": [("base", ["1", "M"], SD_BASE, [])],
    "TOTAL": [("pace", ["1", "T", "poss_dev"], SD_BASE, ["poss"]), ("base", ["1", "T"], SD_BASE, [])],
    "TEAM": [("base", None, ["1", "mu_team_dev10", "early"], [])],
}
HALFTIME_SPEC = {
    "MARGIN": [("base", ["1", "M", "m1"], SD_HT, [])],
    "TOTAL": [("pace", ["1", "T", "t1", "abs_m1_10", "poss_dev", "poss1_dev"], SD_HT, ["poss", "poss1"]),
              ("score", ["1", "T", "t1", "abs_m1_10", "poss_dev"], SD_HT, ["poss"]),
              ("base", ["1", "T", "t1", "abs_m1_10"], SD_HT, [])],
    "TEAM": [("base", None, ["1", "mu_team_dev10", "early", "abs_m1_10"], [])],
}
SPEC = {"H1": PREGAME_SPEC, "H2": PREGAME_SPEC, "H2REG": PREGAME_SPEC,
        "HT_H2": HALFTIME_SPEC, "HT_H2REG": HALFTIME_SPEC}
PERIODS = ["H1", "H2", "H2REG", "HT_H2", "HT_H2REG"]


# --------------------------------------------------------------------------- data
def apply_external_projections(g: pd.DataFrame, path) -> pd.DataFrame:
    """Replace the point-in-time projector with pregame forecasts from a CSV.

    Required columns: game_id, proj_home, proj_away. Optional: proj_poss, n_home, n_away,
    min_games. Games with no matching row are dropped (they are not silently filled).
    """
    ext = pd.read_csv(path)
    need = {"game_id", "proj_home", "proj_away"}
    if not need <= set(ext.columns):
        raise SystemExit(f"projections CSV missing columns {need - set(ext.columns)}")
    ext["game_id"] = ext.game_id.astype(int)
    keep = ["game_id", "proj_home", "proj_away"]
    for c in ("proj_poss", "n_home", "n_away", "min_games"):
        if c in ext.columns:
            keep.append(c)
    ext = ext[keep].drop_duplicates("game_id")
    g = g.drop(columns=[c for c in ("proj_home", "proj_away", "proj_poss", "proj_margin",
                                    "proj_total", "min_games", "n_home", "n_away") if c in g.columns],
               errors="ignore")
    g = g.merge(ext, on="game_id", how="inner")
    if "min_games" not in g.columns:
        if "n_home" in g.columns and "n_away" in g.columns:
            g["min_games"] = np.minimum(g.n_home.fillna(0), g.n_away.fillna(0))
        else:
            g["min_games"] = 8.0  # unknown: treat as mid-season, documented
    if "proj_poss" in g.columns:
        g["proj_poss"] = pd.to_numeric(g["proj_poss"], errors="coerce")
    else:
        g["proj_poss"] = np.nan
    g["proj_margin"] = g.proj_home - g.proj_away
    g["proj_total"] = g.proj_home + g.proj_away
    return g


def load_frame(cache: Path, projections=None) -> pd.DataFrame:
    g = pd.concat([pd.read_csv(f) for f in sorted((HERE / "data").glob("halves_games_*.csv"))],
                  ignore_index=True)
    pos = F.team_possessions(cache, sorted(g.season.unique()))
    g = g.merge(pos, on="game_id", how="left")
    if projections:
        g = apply_external_projections(g, projections)
    else:
        g = F.project(g, PIT_PARAMS)
    g["early"] = 1.0 / (1.0 + g.min_games)
    g["M"], g["T"], g["poss"] = g.proj_margin, g.proj_total, g.proj_poss
    g["m1"] = g.h1_home - g.h1_away
    g["t1"] = g.h1_home + g.h1_away
    g["poss1"] = g.h1_poss_est
    g["fg_m"] = g.final_home - g.final_away
    g["fg_t"] = g.final_home + g.final_away
    tgt = {
        "H1": (g.h1_home, g.h1_away),
        "H2": (g.final_home - g.h1_home, g.final_away - g.h1_away),
        "H2REG": (g.reg_home - g.h1_home, g.reg_away - g.h1_away),
    }
    tgt["HT_H2"], tgt["HT_H2REG"] = tgt["H2"], tgt["H2REG"]
    for k, (h, a) in tgt.items():
        g[f"y_{k}_home"], g[f"y_{k}_away"] = h, a
        g[f"y_{k}_MARGIN"], g[f"y_{k}_TOTAL"] = h - a, h + a
    return g


def dataset_sha256():
    """sha256 over the per-season dataset files' sha256 values, in file-name order."""
    h = hashlib.sha256()
    for f in sorted((HERE / "data").glob("halves_games_*.csv")):
        h.update(f.name.encode() + b":" + hashlib.sha256(f.read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def design(df, feats):
    cols = []
    for f in feats:
        if f == "1":
            cols.append(np.ones(len(df)))
        elif f == "abs_M10":
            cols.append(df.M.abs().values / 10)
        elif f == "T140_20":
            cols.append((df["T"].values - 140) / 20)
        elif f == "poss_dev":
            cols.append(df.poss.values - 68)
        elif f == "abs_m1_10":
            cols.append(df.m1.abs().values / 10)
        elif f == "poss1_dev":
            cols.append(df.poss1.values - 34)
        elif f == "mu_team_dev10":
            cols.append((df.mu_team.values - 35) / 10)
        else:
            cols.append(df[f].values.astype(float))
    return np.column_stack(cols)


def fit_sd(X, r):
    """Gaussian MLE of log sigma = X c (heteroscedastic residual scale)."""
    c0 = np.zeros(X.shape[1]); c0[0] = math.log(np.std(r))
    nll = lambda c: np.sum(X @ c) + 0.5 * np.sum(r ** 2 * np.exp(-2 * (X @ c)))
    grad = lambda c: X.sum(0) - X.T @ (r ** 2 * np.exp(-2 * (X @ c)))
    return minimize(nll, c0, jac=grad, method="BFGS").x


def empirical_shape(z):
    q = np.quantile(z, P_GRID)
    q = np.maximum.accumulate(q + np.arange(len(q)) * 1e-9)
    return {"kind": "empirical", "z_knots": [float(x) for x in q], "p_knots": list(P_GRID)}


# --------------------------------------------------------------------------- vectorised mirror of runtime
def _ncdf(z):
    return 0.5 * (1 + erf(z / math.sqrt(2)))


def shape_cdf_vec(shape, z):
    z = np.asarray(z, float)
    if shape["kind"] == "normal":
        return _ncdf(z)
    zs, ps = np.array(shape["z_knots"]), np.array(shape["p_knots"])
    out = np.interp(z, zs, ps)
    lo, hi = z <= zs[0], z >= zs[-1]
    out[lo] = ps[0] * _ncdf(z[lo]) / max(_ncdf(zs[0]), 1e-300)
    out[hi] = 1 - (1 - ps[-1]) * (1 - _ncdf(z[hi])) / max(1 - _ncdf(zs[-1]), 1e-300)
    return out


class PMFBatch:
    """Same discretisation as halves_model.IntegerPMF, vectorised over rows on a common grid."""

    def __init__(self, mu, sd, shape, span=9.0):
        mu, sd = np.asarray(mu, float), np.asarray(sd, float)
        self.lo = int(np.floor((mu - span * sd).min())) - 1
        self.hi = int(np.ceil((mu + span * sd).max())) + 1
        self.k = np.arange(self.lo, self.hi + 1)
        edges = np.concatenate([self.k - 0.5, [self.hi + 0.5]])
        lo_i = np.floor(mu - span * sd)[:, None]; hi_i = np.ceil(mu + span * sd)[:, None]
        cdf = shape_cdf_vec(shape, (edges[None, :] - mu[:, None]) / sd[:, None])
        p = np.clip(np.diff(cdf, axis=1), 0, None)
        p[(self.k[None, :] < lo_i) | (self.k[None, :] > hi_i)] = 0.0
        self.p = p / p.sum(1, keepdims=True)

    def gt(self, x):
        return (self.p * (self.k[None, :] > (np.asarray(x, float)[:, None] + 1e-9))).sum(1)

    def eq_int(self, x):
        idx = np.clip(np.round(x).astype(int) - self.lo, 0, len(self.k) - 1)
        return self.p[np.arange(len(x)), idx]

    def logpmf(self, y):
        idx = np.clip(np.asarray(y).astype(int) - self.lo, 0, len(self.k) - 1)
        return np.log(np.maximum(self.p[np.arange(len(y)), idx], 1e-12))

    def central(self, y, level):
        c = np.cumsum(self.p, 1)
        a = (1 - level) / 2
        lo = self.k[np.argmax(c >= a, axis=1)]
        hi = self.k[np.argmax(c >= 1 - a, axis=1)]
        return float(((y >= lo) & (y <= hi)).mean())


# --------------------------------------------------------------------------- fitting
def ctx_ok(df, req):
    m = np.ones(len(df), bool)
    for r in req:
        m &= df[r].notna().values
    return m


def predict_mean(df, tspec):
    """Mean from the first variant whose inputs are present (runtime rule), vectorised."""
    mu = np.full(len(df), np.nan); used = np.array([None] * len(df), dtype=object)
    for v in tspec["variants"]:
        ok = ctx_ok(df, v["requires"]) & np.isnan(mu)
        if ok.any():
            mu[ok] = design(df[ok], v["mean"]["features"]) @ np.array(v["mean"]["coef"])
            used[ok] = v["name"]
    return mu, used


def predict_sd(df, tspec):
    sd = np.full(len(df), np.nan)
    for v in tspec["variants"]:
        ok = ctx_ok(df, v["requires"]) & np.isnan(sd)
        if ok.any():
            sd[ok] = np.exp(design(df[ok], v["sd"]["features"]) @ np.array(v["sd"]["coef"]))
    return sd


def fit_period(train, period, shapes=None):
    spec = SPEC[period]
    out = {}
    halftime = period.startswith("HT")
    for kind in ("MARGIN", "TOTAL"):
        y = train[f"y_{period}_{kind}"].values.astype(float)
        fg_res = (train.fg_m - train.M).values if kind == "MARGIN" else (train.fg_t - train["T"]).values
        variants = []
        for name, mf, sf, req in spec[kind]:
            ok = ctx_ok(train, req)
            d = train[ok]; yy = y[ok]
            X = design(d, mf); beta = np.linalg.lstsq(X, yy, rcond=None)[0]
            r = yy - X @ beta
            S = design(d, sf); c = fit_sd(S, r)
            z = r / np.exp(S @ c)
            v = {"name": name, "requires": req, "n_train": int(ok.sum()),
                 "mean": {"features": mf, "coef": [float(x) for x in beta]},
                 "sd": {"features": sf, "coef": [float(x) for x in c]},
                 "shape_candidates": {"normal": {"kind": "normal"}, "empirical": empirical_shape(z)}}
            if not halftime:
                fr = fg_res[ok]
                b = float(np.dot(fr, r) / np.dot(fr, fr))
                v.update(beta_fg=b, fg_resid_sd_fit=float(np.std(fr)),
                         cond_resid_sd=float(np.std(r - b * fr)))
            else:
                v["beta_fg"] = None
            variants.append(v)
        out[f"{period}_{kind}"] = {"variants": variants}
    mu_m, _ = predict_mean(train, out[f"{period}_MARGIN"])
    mu_t, _ = predict_mean(train, out[f"{period}_TOTAL"])
    tt = team_rows(train, period, mu_m, mu_t)
    name, _, sf, req = spec["TEAM"][0]
    S = design(tt, sf); r = (tt.y_team - tt.mu_team).values
    c = fit_sd(S, r); z = r / np.exp(S @ c)
    out[f"{period}_TEAM"] = {"variants": [{"name": name, "requires": req, "n_train": int(len(tt)),
                                           "sd": {"features": sf, "coef": [float(x) for x in c]},
                                           "shape_candidates": {"normal": {"kind": "normal"},
                                                                "empirical": empirical_shape(z)}}]}
    for t, s in (shapes or {}).items():
        for v in out[t]["variants"]:
            v["shape"] = v["shape_candidates"][s]
    return out


def team_rows(df, period, mu_m, mu_t):
    rows = []
    for side, sgn in (("home", 1), ("away", -1)):
        d = df.copy(); d["mu_team"] = (mu_t + sgn * mu_m) / 2
        d["y_team"] = df[f"y_{period}_{side}"].values
        rows.append(d)
    tt = pd.concat(rows)
    return tt[tt.mu_team.notna()]


# --------------------------------------------------------------------------- evaluation
def _brier_ll(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(np.mean((p - y) ** 2)), float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(p, y, bins=10):
    b = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum((b == i).mean() * abs(p[b == i].mean() - y[b == i].mean())
                     for i in range(bins) if (b == i).any()))


def calib_table(p, y, bins=10):
    b = np.minimum((p * bins).astype(int), bins - 1)
    return [{"bin": f"{i/bins:.1f}-{(i+1)/bins:.1f}", "n": int((b == i).sum()),
             "pred": round(float(p[b == i].mean()), 4), "obs": round(float(y[b == i].mean()), 4)}
            for i in range(bins) if (b == i).any()]


def evaluate(y, mu, sd, shape, kind):
    y = np.asarray(y, float)
    r = y - mu
    res = {"n": int(len(y)), "mae": float(np.abs(r).mean()), "rmse": float(np.sqrt((r ** 2).mean())),
           "bias": float(r.mean())}
    P = PMFBatch(mu, sd, shape)
    res["log_score"] = float(-P.logpmf(y).mean())
    res["coverage"] = {str(l): P.central(y, l) for l in (0.5, 0.8, 0.95)}
    base = np.floor(mu) + 0.5           # half-point line nearest below the mean
    ps, ys = [], []
    for off in (-6, -3, 0, 3, 6):
        L = base + off
        ps.append(P.gt(L)); ys.append((y > L).astype(float))
    ps, ys = np.concatenate(ps), np.concatenate(ys)
    res["brier_lines"], res["logloss_lines"] = _brier_ll(ps, ys)
    res["ece_lines"] = ece(ps, ys)
    res["calibration_lines"] = calib_table(ps, ys)
    Li = np.round(mu)
    res["push_at_integer_line"] = {"pred": float(P.eq_int(Li).mean()), "obs": float((y == Li).mean())}
    if kind == "MARGIN":
        s = np.sign(mu); m = s != 0
        res["bias_favorite_perspective"] = float((s[m] * r[m]).mean())
        res["bias_underdog_perspective"] = -res["bias_favorite_perspective"]
        pg = P.gt(base)
        fav_p = np.where(mu > 0, pg, 1 - pg)   # half-point line: no push
        fav_y = np.where(mu > 0, y > base, y < base).astype(float)
        res["fav_cover_at_model_line"] = {"pred": float(fav_p.mean()), "obs": float(fav_y.mean())}
        z0 = np.zeros(len(y))
        ph, pt = P.gt(z0), P.eq_int(z0); pa = np.clip(1 - ph - pt, 0, 1)
        Y = np.stack([y > 0, y == 0, y < 0], 1).astype(float)
        Q = np.clip(np.stack([ph, pt, pa], 1), 1e-12, 1)
        res["ml3_brier"] = float(((Q - Y) ** 2).sum(1).mean())
        res["ml3_logloss"] = float(-(Y * np.log(Q)).sum(1).mean())
        res["tie"] = {"pred": float(pt.mean()), "obs": float((y == 0).mean())}
        nz = y != 0
        res["ml_twoway_brier"], res["ml_twoway_logloss"] = _brier_ll(ph[nz] / (ph[nz] + pa[nz]), (y[nz] > 0).astype(float))
        res["ml_twoway_ece"] = ece(ph[nz] / (ph[nz] + pa[nz]), (y[nz] > 0).astype(float))
        fv = mu != 0
        res["ml_fav_win"] = {"pred": float(np.where(mu > 0, ph, pa)[fv].mean()),
                             "obs": float(np.where(mu > 0, y > 0, y < 0)[fv].mean())}
    else:
        med = float(np.median(mu))
        hi = mu >= med
        res["bias_high_proj"], res["bias_low_proj"] = float(r[hi].mean()), float(r[~hi].mean())
        po = P.gt(base); yo = (y > base).astype(float)
        res["over_at_model_line"] = {"pred": float(po.mean()), "obs": float(yo.mean())}
        res["under_at_model_line"] = {"pred": float(1 - po.mean()), "obs": float(1 - yo.mean())}
        res["over_at_model_line_high_proj"] = {"pred": float(po[hi].mean()), "obs": float(yo[hi].mean())}
        res["over_at_model_line_low_proj"] = {"pred": float(po[~hi].mean()), "obs": float(yo[~hi].mean())}
    return res


def eval_period(test, fit, period):
    out = {}
    mu_m, used_m = predict_mean(test, fit[f"{period}_MARGIN"])
    mu_t, used_t = predict_mean(test, fit[f"{period}_TOTAL"])
    for kind, mu, used in (("MARGIN", mu_m, used_m), ("TOTAL", mu_t, used_t)):
        tspec = fit[f"{period}_{kind}"]
        sd = predict_sd(test, tspec)
        ok = np.isfinite(mu) & np.isfinite(sd)
        y = test[f"y_{period}_{kind}"].values[ok]
        cands = tspec["variants"][0]["shape_candidates"] if "shape_candidates" in tspec["variants"][0] else None
        if cands:
            out[kind] = {s: evaluate(y, mu[ok], sd[ok], cands[s], kind) for s in ("normal", "empirical")}
        else:
            out[kind] = {"chosen": evaluate(y, mu[ok], sd[ok], tspec["variants"][0]["shape"], kind)}
        out[kind]["variant_usage"] = {str(k): int(v) for k, v in pd.Series(used[ok]).value_counts().items()}
    tt = team_rows(test, period, mu_m, mu_t)
    v = fit[f"{period}_TEAM"]["variants"][0]
    sd = np.exp(design(tt, v["sd"]["features"]) @ np.array(v["sd"]["coef"]))
    if "shape_candidates" in v:
        out["TEAM"] = {s: evaluate(tt.y_team.values, tt.mu_team.values, sd, v["shape_candidates"][s], "TEAM")
                       for s in ("normal", "empirical")}
    else:
        out["TEAM"] = {"chosen": evaluate(tt.y_team.values, tt.mu_team.values, sd, v["shape"], "TEAM")}
    return out


def legacy_baseline(test, period):
    """sportsedge_cbb_model.py legacy constants: H1 = 0.47 * FG, SD_H1 8 (spread SD 8*0.85).
    Pregame H2 uses the complementary 0.53 share with the same SDs."""
    share = 0.47 if period == "H1" else 0.53
    out = {}
    for kind, mu, sd in (("MARGIN", share * test.M.values, 8 * 0.85), ("TOTAL", share * test["T"].values, 8.0)):
        y = test[f"y_{period}_{kind}"].values
        out[kind] = evaluate(y, mu, np.full(len(y), sd), {"kind": "normal"}, kind)
    return out


def strip(fit, shapes):
    coef_t = {}
    for t, spec in fit.items():
        vs = []
        for var in spec["variants"]:
            v = {k: val for k, val in var.items() if k != "shape_candidates"}
            v["shape"] = var["shape_candidates"][shapes[t]]
            vs.append(v)
        coef_t[t] = {"variants": vs}
    return coef_t


def rnd(o, nd=5):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {str(k): rnd(v, nd) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [rnd(v, nd) for v in o]
    return o


def run(cache, stage, *, projections=None, out_coefficients=None, train_until=None, source_label=None):
    g = load_frame(Path(cache), projections=projections)
    targets = [f"{p}_{k}" for p in PERIODS for k in ("MARGIN", "TOTAL", "TEAM")]
    report = {"label": "PAPER_0U", "counting": "NON_COUNTED", "stage": stage, "pit_params": PIT_PARAMS,
              "dataset_sha256": dataset_sha256()}
    pit = {}
    for s, x in g.groupby("season"):
        e, et = x.fg_m - x.M, x.fg_t - x["T"]
        pit[int(s)] = {"n": int(len(x)), "fg_margin_mae": float(e.abs().mean()),
                       "fg_margin_rmse": float(np.sqrt((e ** 2).mean())), "fg_margin_bias": float(e.mean()),
                       "fg_total_mae": float(et.abs().mean()), "fg_total_rmse": float(np.sqrt((et ** 2).mean())),
                       "fg_total_bias": float(et.mean())}
    report["pit_fullgame_by_season"] = pit
    (HERE / "results").mkdir(exist_ok=True)
    if stage == "dev":
        if TEST_SEASON in DEV_SEASONS:
            raise SystemExit("test season leaked into dev folds")
        folds = {}
        for S in DEV_SEASONS:
            tr, te = g[g.season < S], g[g.season == S]
            fit = {}
            for p in PERIODS:
                fit.update(fit_period(tr, p))
            folds[S] = {p: eval_period(te, fit, p) for p in PERIODS}
            folds[S]["LEGACY_H1"] = legacy_baseline(te, "H1")
            folds[S]["LEGACY_H2"] = legacy_baseline(te, "H2")
            print("fold", S, "done", flush=True)
        report["folds"] = folds
        choice = {}
        for p in PERIODS:
            for k in ("MARGIN", "TOTAL", "TEAM"):
                ls = {s: float(np.mean([folds[S][p][k][s]["log_score"] for S in DEV_SEASONS]))
                      for s in ("normal", "empirical")}
                choice[f"{p}_{k}"] = {"choice": min(ls, key=ls.get), "mean_log_score": ls}
        report["shape_choice"] = choice
        (HERE / "results" / "dev_report.json").write_text(json.dumps(rnd(report), indent=1, sort_keys=True) + "\n")
        return report
    dev = json.loads((HERE / "results" / "dev_report.json").read_text())
    shapes = {t: v["choice"] for t, v in dev["shape_choice"].items()}
    cutoff = TEST_SEASON if train_until is None else (train_until + 1)
    tr, te = g[g.season < cutoff], g[g.season >= cutoff]
    if stage == "refit":
        if out_coefficients is None:
            raise SystemExit("refit requires --out-coefficients (will not overwrite coefficients_halves_v1.json)")
        dest = Path(out_coefficients)
        if dest.resolve() == (ROOT / "models" / "cbb" / "halves" / "coefficients_halves_v1.json").resolve():
            raise SystemExit("refit refuses to overwrite coefficients_halves_v1.json")
        if cutoff > TEST_SEASON:
            raise SystemExit("refit must not include the 2026 test season in training")
    fit = {}
    for p in PERIODS:
        fit.update(fit_period(tr, p))
    version = "cbb-halves-v1-research" if stage != "refit" else "cbb-halves-refit-research"
    coef = {"model_version": version, "label": "PAPER_0U", "counting": "NON_COUNTED",
            "approved_stake_u": 0, "trained_seasons": sorted(int(x) for x in tr.season.unique()),
            "trained_games": int(len(tr)), "untouched_test_season": TEST_SEASON,
            "dataset_sha256": report["dataset_sha256"], "pit_params": None if projections else PIT_PARAMS,
            "projections_source": source_label or (str(projections) if projections else "pit_fullgame"),
            "default_early": float(tr.early.mean()),
            "fit_note": ("Mean and SD models fitted on chronological pregame projections; shapes chosen on "
                         "rolling-origin dev folds 2021-2025; season 2026 untouched until the single test run.")
                         if stage != "refit" else
                         ("Refit of half means/SDs on an external full-game projector. Training seasons are "
                          "strictly before the cutoff; season 2026 is never in the training window. "
                          "coefficients_halves_v1.json is not overwritten."),
            "targets": strip(fit, shapes)}
    raw = (json.dumps(coef, indent=1, sort_keys=True) + "\n").encode()
    dest = Path(out_coefficients) if out_coefficients else (ROOT / "models" / "cbb" / "halves" / "coefficients_halves_v1.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    report["coefficients_sha256"] = hashlib.sha256(raw).hexdigest()
    report["shapes"] = shapes
    report["projections_source"] = coef["projections_source"]
    final = {t: {"variants": v} for t, v in ((t, s["variants"]) for t, s in coef["targets"].items())}
    if stage == "refit":
        # Dev-fold style scores on training-window holdouts only. 2026 is omitted here on purpose.
        folds = {}
        for S in [s for s in DEV_SEASONS if s <= (train_until or 2025)]:
            trs, tes = g[g.season < S], g[g.season == S]
            if tes.empty or trs.empty:
                continue
            f = {}
            for p in PERIODS:
                f.update(fit_period(trs, p))
            packed = strip(f, shapes)
            folds[S] = {p: eval_period(tes, packed, p) for p in PERIODS}
        report["stage"] = "refit"
        report["refit_dev_folds"] = folds
        report["trained_games"] = int(len(tr))
        (HERE / "results" / "refit_report.json").write_text(json.dumps(rnd(report), indent=1, sort_keys=True) + "\n")
        return report
    report["test"] = {p: eval_period(te, final, p) for p in PERIODS}
    report["test"]["LEGACY_H1"] = legacy_baseline(te, "H1")
    report["test"]["LEGACY_H2"] = legacy_baseline(te, "H2")
    (HERE / "results" / "test_report.json").write_text(json.dumps(rnd(report), indent=1, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--stage", choices=("dev", "test", "refit"), required=True)
    ap.add_argument("--projections", help="optional CSV of external pregame full-game projections")
    ap.add_argument("--out-coefficients", help="write coefficients here (refit required; must not be v1)")
    ap.add_argument("--train-until", type=int, default=None,
                    help="last season included in training (refit default 2025)")
    ap.add_argument("--source-label", default=None)
    a = ap.parse_args()
    train_until = a.train_until if a.train_until is not None else (2025 if a.stage == "refit" else None)
    run(a.cache, a.stage, projections=a.projections, out_coefficients=a.out_coefficients,
        train_until=train_until, source_label=a.source_label)
