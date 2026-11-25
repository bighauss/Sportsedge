"""Fit the halves copulas on chronological residuals (PAPER/0u, NON_COUNTED).

Protocol (same splits as PROTOCOL.md):
  * Rolling-origin folds S in 2021..2025: mean and SD from seasons < S, then the copula
    (Gaussian rho / empirical grid, and the 4x4 H1–H2 correlation) is estimated on those
    training residuals and scored on S. The copula kind is chosen here.
  * Final coefficients are estimated on 2019–2025 only. Season 2026 is not used for
    selection or fit. If this script prints 2026 numbers they are a SECONDARY RE-USE
    of the already-scored test window and must be labelled as such.

Usage:
  python research/cbb_halves/fit_joint.py --cache <fetch cache> --stage dev
  python research/cbb_halves/fit_joint.py --cache <fetch cache> --stage final
  python research/cbb_halves/fit_joint.py --cache <fetch cache> --stage secondary-2026
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "models" / "cbb"))
import fit_halves as FH  # noqa: E402
from halves import halves_model as HM  # noqa: E402
from halves import halves_joint as HJ  # noqa: E402

PERIODS = ["H1", "H2", "H2REG", "HT_H2", "HT_H2REG"]
GRID_N = 16  # unit-square resolution excluding the forced 0/1 border -> 17x17 CDF


def residual_frame(df, fit, period):
    mu_m, _ = FH.predict_mean(df, fit[f"{period}_MARGIN"])
    mu_t, _ = FH.predict_mean(df, fit[f"{period}_TOTAL"])
    sd_m = FH.predict_sd(df, fit[f"{period}_MARGIN"])
    sd_t = FH.predict_sd(df, fit[f"{period}_TOTAL"])
    ok = np.isfinite(mu_m) & np.isfinite(mu_t) & np.isfinite(sd_m) & np.isfinite(sd_t) & (sd_m > 0) & (sd_t > 0)
    ym = df[f"y_{period}_MARGIN"].values[ok].astype(float)
    yt = df[f"y_{period}_TOTAL"].values[ok].astype(float)
    zm = (ym - mu_m[ok]) / sd_m[ok]
    zt = (yt - mu_t[ok]) / sd_t[ok]
    return {"ok": ok, "mu_m": mu_m[ok], "mu_t": mu_t[ok], "sd_m": sd_m[ok], "sd_t": sd_t[ok],
            "ym": ym, "yt": yt, "zm": zm, "zt": zt}


def gaussian_rho(zm, zt):
    if len(zm) < 20:
        return 0.0
    c = np.corrcoef(zm, zt)[0, 1]
    return float(0.0 if not np.isfinite(c) else min(max(c, -0.95), 0.95))


def empirical_grid(zm, zt, n=GRID_N):
    """Copula CDF on a (n+1)x(n+1) grid including the 0 and 1 borders."""
    u = np.clip(0.5 * (1 + np.vectorize(lambda z: math.erf(z / math.sqrt(2)))(zm)), 1e-6, 1 - 1e-6)
    v = np.clip(0.5 * (1 + np.vectorize(lambda z: math.erf(z / math.sqrt(2)))(zt)), 1e-6, 1 - 1e-6)
    # density histogram on n x n interior cells, Laplace smooth, prefix-sum to CDF
    H, _, _ = np.histogram2d(u, v, bins=n, range=[[0, 1], [0, 1]])
    H = H + 0.5
    H = H / H.sum()
    cdf = np.zeros((n + 1, n + 1))
    cdf[1:, 1:] = np.cumsum(np.cumsum(H, 0), 1)
    cdf[-1, :] = np.linspace(0, 1, n + 1) * 0 + cdf[-1, :]
    cdf[:, -1] = 1.0
    cdf[-1, :] = 1.0
    cdf[0, :] = 0.0
    cdf[:, 0] = 0.0
    # enforce margins roughly by not touching the forced borders further
    return [[float(x) for x in row] for row in cdf]


def _copula_cdf_vec(kind, u, v, spec):
    u = np.clip(np.asarray(u, float), 1e-12, 1 - 1e-12)
    v = np.clip(np.asarray(v, float), 1e-12, 1 - 1e-12)
    if kind == "independent":
        return u * v
    if kind == "empirical":
        return np.array([HJ.empirical_copula_cdf(a, b, spec["cdf_grid"]) for a, b in zip(u, v)])
    if kind != "gaussian":
        raise ValueError(kind)
    # vectorised 16-point integral of the bivariate-normal formula
    rho = min(max(float(spec["rho"]), -0.999), 0.999)
    h = np.array([HJ._norm_ppf(x) for x in u])
    k = np.array([HJ._norm_ppf(x) for x in v])
    ph, pk = FH._ncdf(h), FH._ncdf(k)
    if abs(rho) < 1e-12:
        return ph * pk
    a, b = 0.0, rho
    acc = np.zeros(len(u))
    for x, w in zip(HJ._GL16_X, HJ._GL16_W):
        t = 0.5 * (b - a) * x + 0.5 * (b + a)
        one = 1.0 - t * t
        expo = -((h * h + k * k - 2.0 * h * k * t) / (2.0 * one))
        acc += w * np.exp(np.clip(expo, -700, 700)) / math.sqrt(one)
    return np.clip(ph * pk + 0.5 * (b - a) * acc / (2.0 * math.pi), 0.0, 1.0)


def joint_log_score(res, kind, spec):
    """Continuity-corrected copula probability of the realised integers (matches runtime joint_cell)."""
    shape = {"kind": "normal"}
    def F(mu, sd, k):
        return FH.shape_cdf_vec(shape, (np.asarray(k, float) + 0.5 - mu) / sd)
    um, um1 = F(res["mu_m"], res["sd_m"], res["ym"]), F(res["mu_m"], res["sd_m"], res["ym"] - 1)
    ut, ut1 = F(res["mu_t"], res["sd_t"], res["yt"]), F(res["mu_t"], res["sd_t"], res["yt"] - 1)
    p = (_copula_cdf_vec(kind, um, ut, spec) - _copula_cdf_vec(kind, um1, ut, spec)
         - _copula_cdf_vec(kind, um, ut1, spec) + _copula_cdf_vec(kind, um1, ut1, spec))
    return float(-np.log(np.clip(p, 1e-12, 1.0)).mean())


def corr4(z):
    c = np.corrcoef(z, rowvar=False)
    c = np.clip(np.nan_to_num(c, nan=0.0), -0.95, 0.95)
    np.fill_diagonal(c, 1.0)
    # symmetrize
    c = 0.5 * (c + c.T)
    return [[float(x) for x in row] for row in c]


def fit_all(train, fit):
    periods = {}
    for p in PERIODS:
        res = residual_frame(train, fit, p)
        periods[p] = {
            "gaussian": {"kind": "gaussian", "rho": gaussian_rho(res["zm"], res["zt"]),
                         "n_train": int(len(res["zm"]))},
            "empirical": {"kind": "empirical", "cdf_grid": empirical_grid(res["zm"], res["zt"]),
                          "n_train": int(len(res["zm"]))},
            "independent": {"kind": "independent", "n_train": int(len(res["zm"]))},
        }
        periods[p]["rho_home_away"] = float(np.corrcoef(
            (res["yt"] + res["ym"]) / 2 - (res["mu_t"] + res["mu_m"]) / 2,
            (res["yt"] - res["ym"]) / 2 - (res["mu_t"] - res["mu_m"]) / 2)[0, 1])
    # H1–H2 pregame only (HT already conditions on H1 in the mean)
    z1 = residual_z(train, fit, "H1")
    z2 = residual_z(train, fit, "H2")
    m = z1["ok"] & z2["ok"]
    mat = corr4(np.column_stack([z1["zm"][m], z1["zt"][m], z2["zm"][m], z2["zt"][m]]))
    h1h2 = {"kind": "gaussian", "corr": mat, "order": ["H1_MARGIN", "H1_TOTAL", "H2_MARGIN", "H2_TOTAL"],
            "n_train": int(m.sum()),
            "corr_names": {"H1_MARGIN:H2_MARGIN": mat[0][2], "H1_TOTAL:H2_TOTAL": mat[1][3],
                           "H1_MARGIN:H2_TOTAL": mat[0][3], "H1_TOTAL:H2_MARGIN": mat[1][2]}}
    return periods, h1h2


def residual_z(df, fit, period):
    mu_m, _ = FH.predict_mean(df, fit[f"{period}_MARGIN"])
    mu_t, _ = FH.predict_mean(df, fit[f"{period}_TOTAL"])
    sd_m = FH.predict_sd(df, fit[f"{period}_MARGIN"])
    sd_t = FH.predict_sd(df, fit[f"{period}_TOTAL"])
    ok = np.isfinite(mu_m) & np.isfinite(mu_t) & (sd_m > 0) & (sd_t > 0)
    zm = np.full(len(df), np.nan); zt = np.full(len(df), np.nan)
    zm[ok] = (df[f"y_{period}_MARGIN"].values[ok] - mu_m[ok]) / sd_m[ok]
    zt[ok] = (df[f"y_{period}_TOTAL"].values[ok] - mu_t[ok]) / sd_t[ok]
    return {"ok": ok, "zm": zm, "zt": zt, "mu_m": mu_m, "mu_t": mu_t, "sd_m": sd_m, "sd_t": sd_t}


def score_period(test, fit, period, kind, spec):
    res = residual_frame(test, fit, period)
    return {
        "n": int(len(res["ym"])),
        "rho_train_applied": spec.get("rho"),
        "realized_rho": gaussian_rho(res["zm"], res["zt"]),
        "joint_log_score": joint_log_score(res, kind, spec),
        "indep_log_score": joint_log_score(res, "independent", {}),
    }


def run(cache, stage):
    g = FH.load_frame(Path(cache))
    (HERE / "results").mkdir(exist_ok=True)
    if stage == "dev":
        folds = {}
        for S in FH.DEV_SEASONS:
            tr, te = g[g.season < S], g[g.season == S]
            fit = {}
            for p in PERIODS:
                fit.update(FH.fit_period(tr, p))
            periods, h1h2 = fit_all(tr, fit)
            scored = {}
            for p in PERIODS:
                scored[p] = {k: score_period(te, fit, p, k, periods[p][k])
                             for k in ("gaussian", "empirical", "independent")}
            folds[S] = {"scored": scored, "h1h2_corr": h1h2["corr_names"]}
            print("fold", S, {p: {k: round(scored[p][k]["joint_log_score"], 4) for k in scored[p]} for p in ("H1", "H2")},
                  flush=True)
        choice = {}
        for p in PERIODS:
            mean_ls = {k: float(np.mean([folds[S]["scored"][p][k]["joint_log_score"] for S in FH.DEV_SEASONS]))
                       for k in ("gaussian", "empirical", "independent")}
            choice[p] = {"choice": min(mean_ls, key=mean_ls.get), "mean_joint_log_score": mean_ls}
        report = {"label": "PAPER_0U", "counting": "NON_COUNTED", "stage": "dev",
                  "dataset_sha256": FH.dataset_sha256(), "folds": folds, "kind_choice": choice,
                  "note": "Copula kind chosen on rolling-origin folds 2021-2025 only."}
        (HERE / "results" / "joint_dev_report.json").write_text(
            json.dumps(FH.rnd(report), indent=1, sort_keys=True) + "\n")
        return report
    # final (or secondary) uses kind choices from dev
    dev = json.loads((HERE / "results" / "joint_dev_report.json").read_text())
    kinds = {p: v["choice"] for p, v in dev["kind_choice"].items()}
    tr = g[g.season < FH.TEST_SEASON]
    fit = {}
    for p in PERIODS:
        fit.update(FH.fit_period(tr, p))
    periods, h1h2 = fit_all(tr, fit)
    packed = {}
    for p in PERIODS:
        kind = kinds[p]
        packed[p] = {k: periods[p][kind][k] for k in periods[p][kind]}
        packed[p]["kind"] = kind
        packed[p]["rho_home_away_train"] = periods[p]["rho_home_away"]
        if kind == "gaussian":
            packed[p]["rho"] = periods[p]["gaussian"]["rho"]
        if kind == "independent":
            packed[p]["rho"] = 0.0
    coef = {"model_version": "cbb-halves-joint-v1-research", "label": "PAPER_0U", "counting": "NON_COUNTED",
            "approved_stake_u": 0, "trained_seasons": sorted(int(x) for x in tr.season.unique()),
            "untouched_test_season": FH.TEST_SEASON,
            "dataset_sha256": FH.dataset_sha256(),
            "kind_choice": kinds,
            "fit_note": ("Copula kind chosen on rolling-origin folds 2021-2025; correlations and "
                         "grids estimated on 2019-2025 only. Season 2026 was not used for selection or fit."),
            "secondary_reuse_note": ("Any metric on season 2026 is a SECONDARY RE-USE of the already-scored "
                                     "halves test window, not a first untouched evaluation."),
            "periods": packed, "h1_h2": h1h2}
    raw = (json.dumps(coef, indent=1, sort_keys=True) + "\n").encode()
    outp = ROOT / "models" / "cbb" / "halves" / "coefficients_halves_joint_v1.json"
    if stage == "final":
        outp.write_bytes(raw)
        report = {"label": "PAPER_0U", "counting": "NON_COUNTED", "stage": "final",
                  "coefficients_sha256": hashlib.sha256(raw).hexdigest(),
                  "kind_choice": kinds, "h1_h2": h1h2["corr_names"],
                  "period_rho": {p: packed[p].get("rho") for p in PERIODS}}
        (HERE / "results" / "joint_final_report.json").write_text(
            json.dumps(FH.rnd(report), indent=1, sort_keys=True) + "\n")
        return report
    # secondary reuse of 2026
    te = g[g.season == FH.TEST_SEASON]
    scored = {}
    for p in PERIODS:
        kind = packed[p]["kind"]
        scored[p] = score_period(te, fit, p, kind, packed[p])
        scored[p]["kind"] = kind
    # H1-H2 realized correlations
    z1, z2 = residual_z(te, fit, "H1"), residual_z(te, fit, "H2")
    m = z1["ok"] & z2["ok"]
    realized = {}
    if m.sum() > 20:
        mat = corr4(np.column_stack([z1["zm"][m], z1["zt"][m], z2["zm"][m], z2["zt"][m]]))
        realized = {"H1_MARGIN:H2_MARGIN": mat[0][2], "H1_TOTAL:H2_TOTAL": mat[1][3],
                    "H1_MARGIN:H2_TOTAL": mat[0][3], "H1_TOTAL:H2_MARGIN": mat[1][2]}
    report = {"label": "PAPER_0U", "counting": "NON_COUNTED", "stage": "secondary-2026",
              "warning": "SECONDARY RE-USE of season 2026; not a first untouched test.",
              "coefficients_sha256": hashlib.sha256(raw).hexdigest() if outp.exists() else hashlib.sha256(raw).hexdigest(),
              "periods": scored, "h1_h2_realized": realized, "h1_h2_fitted": h1h2["corr_names"]}
    (HERE / "results" / "joint_secondary_2026.json").write_text(
        json.dumps(FH.rnd(report), indent=1, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--stage", choices=("dev", "final", "secondary-2026"), required=True)
    a = ap.parse_args()
    run(a.cache, a.stage)
