"""Render RESULTS_TABLES.md from a harness output directory (no hand-typed numbers)."""
import argparse
import csv
import json
from pathlib import Path


def rd(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def fmt(v, nd=3):
    if v in (None, ""):
        return "-"
    try:
        x = float(v)
    except ValueError:
        return v
    return f"{x:.{nd}f}" if not x.is_integer() or nd == 0 else (f"{int(x)}" if abs(x) >= 100 else f"{x:.{nd}f}")


def table(rows, cols, nd=3, heads=None):
    out = ["| " + " | ".join(heads or cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(fmt(r.get(c), nd) if c not in ("model", "group", "family", "target", "status", "dimension", "cell", "season", "basis") else str(r.get(c)) for c in cols) + " |")
    return "\n".join(out)


def main(d, out):
    d = Path(d)
    meta = json.loads((d / "meta.json").read_text())
    pm, pr, bs, sel = rd(d / "point_metrics.csv"), rd(d / "probability_metrics.csv"), rd(d / "bootstrap_ci.csv"), rd(d / "blend_selection.csv")
    bl, sp, bet, cov, hca, cal = (rd(d / f) for f in ("blend_weights_all.csv", "bias_splits.csv", "betting_splits.csv", "coverage.csv", "hca_by_season.csv", "calibration_bins.csv"))
    L = [f"# CBB rolling-origin backtest: tables (generated from `{d.name}`)", "",
         f"Status: {meta['status']}, label {meta['label']}, official_counted={meta['official_counted']}, approved_stake_u={meta['approved_stake_u']}.",
         f"Generated {meta['generated_utc']} UTC. Identical rows: {meta['identical_rows']} of {meta['total_rows']} games. Models: {', '.join(meta['models'])}.",
         f"Splits: {meta['splits']}. Blend weights (independent share): {meta['blend_weights']} - source: {meta['blend_weights_source']}.",
         f"Leakage: {meta['leakage']['origins_checked']} origins checked, {meta['leakage']['violation_count']} violations; blend selection seasons {meta['leakage']['selection_seasons']}, test seasons {meta['leakage']['test_seasons']}.",
         f"Market quarantine: {meta['market_quarantine']}. CLV: {meta['clv_status']}. Bootstrap: {meta['bootstrap']}.", "",
         "## 1. Coverage by season", table(cov, [c for c in cov[0] if c != "providers"], 0), "",
         "Providers per season (selected sportsbook row per game):", ""]
    for c in cov:
        L.append(f"- {c['season']}: {c['providers']}")
    L += ["", "## 2. Point accuracy on identical rows (pred - actual)"]
    for g in ("TRAIN", "VALIDATION", "TEST", "ALL"):
        L += [f"### {g}", table([r for r in pm if r["group"] == g and r["target"] in ("margin", "total")], ["model", "target", "n", "mae", "rmse", "bias", "residual_sd"]), ""]
    L += ["## 3. Clustered (by date) bootstrap 95% CIs, ALL identical rows", table(bs, ["model", "metric", "n", "estimate", "ci95_lo", "ci95_hi", "delta_vs_native", "delta_ci95_lo", "delta_ci95_hi"]), ""]
    L += ["## 4. Probability metrics (Brier, log loss, ECE)"]
    for g in ("VALIDATION", "TEST"):
        L += [f"### {g}", table([r for r in pr if r["group"] == g and not r["model"].endswith("_ON_MARKET_ROWS")], ["family", "model", "basis", "n", "brier", "log_loss", "ece", "mean_p", "freq"], 4), ""]
    L += ["## 5. Bias splits (ALL identical rows)", table(sp, ["model", "dimension", "cell", "target", "n", "bias_pred_minus_actual", "mae", "rmse", "residual_sd"]), ""]
    L += ["## 6. HCA diagnostics (home-court identical rows)", table(hca, ["model", "season", "n_home_court_rows", "mean_hca_applied", "mean_pred_margin", "mean_actual_margin"], 2), ""]
    L += ["## 7. Nine blend weights - every weight evaluated independently (VALIDATION and TEST)",
          "p = w * p_independent + (1 - w) * p_market_novig_close. ROI = flat 1u on the positive-EV side at the close price; max drawdown in units, chronological.", ""]
    for g in ("VALIDATION", "TEST"):
        L += [f"### {g}", table([r for r in bl if r["group"] == g], ["model", "family", "w_independent", "n", "log_loss", "brier", "close_n_bets", "close_roi", "close_units", "close_max_dd_u"], 4), ""]
    L += ["## 8. Blend selection (validation log loss only) -> one-shot TEST report", table(sel, [c for c in sel[0]], 4), ""]
    L += ["## 9. Betting splits, pure independent model (w=1) at the close, ALL seasons (diagnostic; includes train/validation/test)",
          table(bet, ["model", "family", "dimension", "cell", "n_bets", "roi", "units", "max_drawdown_u", "mean_claimed_ev"]), ""]
    L += ["## 10. Calibration bins (ALL)", table(cal, ["family", "model", "bin", "n", "mean_p", "freq"], 3), ""]
    Path(out).write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("dir"); a.add_argument("out")
    x = a.parse_args(); main(x.dir, x.out)
