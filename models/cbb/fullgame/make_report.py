"""Render evidence tables (markdown) + a compact summary JSON from run_eval / nov24_diagnosis outputs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def tables(r, nov):
    L = []
    L.append("### A. Projection accuracy on identical rows (games where all six engines forecast; strictly-prior data)\n")
    L.append("| Season | Engine | n | Margin MAE | Margin RMSE | Margin bias | Total MAE | Total RMSE | Total bias | Team-pts MAE | ML Brier | ML log loss | ML ECE |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("2023", "2024", "2025", "2026", "2027"):
        for e in ("RAW", "REG", "NATIVE_RECON", "SA", "FG1", "FG1C"):
            m = r["point"][s][e]; ml = r["ml_identical"][s][e]
            L.append(f"| {s} | {e} | {m['n']} | {m['margin']['mae']:.2f} | {m['margin']['rmse']:.2f} | {m['margin']['bias']:+.2f} | "
                     f"{m['total']['mae']:.2f} | {m['total']['rmse']:.2f} | {m['total']['bias']:+.2f} | {m['team_points']['mae']:.2f} | "
                     f"{ml['brier']:.4f} | {ml['log_loss']:.4f} | {ml['ece']:.3f} |")
    L.append("\nBias = mean(actual - forecast); margin is home minus away. 2027 = season to date (Nov 1-25, 2026).\n")
    L.append("### B. Market rows at the CLOSE (identical rows; DK 2026-27, ESPN BET 2024-25): before vs after\n")
    L.append("| Season | Config | Market | Rows | EV>30% | EV>10% | Model Brier | Mkt Brier | Model LL | Mkt LL | Model ECE | Flat ROI (best side, EV>0) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("2024", "2025", "2026", "2027"):
        for c in ("BEFORE_native_recon_OLD", "native_recon_NEW", "fg1_OLD", "AFTER_fg1c_NEW"):
            for mk in ("spread", "total", "moneyline"):
                d = r["market"][s][c][mk]
                L.append(f"| {s} | {c} | {mk} | {d['rows']} | {d['ev_gt_30']} | {d['ev_gt_10']} | {d['model']['brier']:.4f} | "
                         f"{d['market']['brier']:.4f} | {d['model']['log_loss']:.4f} | {d['market']['log_loss']:.4f} | "
                         f"{d['model']['ece']:.3f} | {d['flat_roi']:+.3f} |")
    L.append("\nOLD = RUN IT constants (normal, SD 12.5 / 17); NEW = chronologically fitted phase Student-t with location, push-aware.\n")
    L.append("### C. Favourite / underdog / over / under bias of the AFTER model probability (vs outcomes, at market lines)\n")
    L.append("| Season | Spread: fav p - rate (SE) | ML: fav p - rate (SE) | Total: over p - rate (SE) |")
    L.append("|---|---|---|---|")
    for s in ("2024", "2025", "2026", "2027"):
        b = r["bias"][s]
        f = lambda k, key: f"{b[k][key]:+.4f} ({b[k]['se']:.4f})"
        L.append(f"| {s} | {f('spread', 'fav_bias_p_minus_rate')} | {f('moneyline', 'fav_bias_p_minus_rate')} | {f('total', 'over_bias_p_minus_rate')} |")
    L.append("\n| Season | FG1 fav-oriented margin residual (SE) | FG1C | FG1 total residual (SE) | FG1C |")
    L.append("|---|---|---|---|---|")
    for s in ("2024", "2025", "2026", "2027"):
        pb = r["point_bias"][s]
        g = lambda e, k: f"{pb[e][k]['mean']:+.2f} ({pb[e][k]['se']:.2f})"
        L.append(f"| {s} | {g('FG1', 'favourite_margin_residual')} | {g('FG1C', 'favourite_margin_residual')} | {g('FG1', 'total_residual')} | {g('FG1C', 'total_residual')} |")
    L.append("\n### D. Moneyline underdog price bands (AFTER, close, 2024-2027 pooled)\n")
    L.append("| Dog price band | n | mean p model | mean p no-vig | win rate (SE) | EV>30% rows |")
    L.append("|---|---|---|---|---|---|")
    for b in r["ml_dog_bands_close_2024_2027"]:
        L.append(f"| {b['band']} | {b['n']} | {b['mean_p_model']:.4f} | {b['mean_p_novig']:.4f} | {b['win_rate']:.4f} ({b['se']:.4f}) | {b['ev_gt_30']} |")
    L.append("\n### E. Nine owner weights (logit blend) - selected on VALIDATION 2024-25, scored once on TEST 2026-27\n")
    L.append("| Lines | Market | Validation log loss by model weight (1.0 ... 0.0) | Selected w | Test LL selected | Test LL market-only | Test LL model-only | Test n |")
    L.append("|---|---|---|---|---|---|---|---|")
    for key, lab in (("blend", "close"), ("blend_open", "open")):
        for mk, v in r[key].items():
            vals = " / ".join(f"{v['validation_log_loss'][w]:.4f}" for w in v["validation_log_loss"])
            L.append(f"| {lab} | {mk} | {vals} | {v['selected_model_weight']} | {v['test']['log_loss']:.4f} | "
                     f"{v['test_market_only']['log_loss']:.4f} | {v['test_model_only']['log_loss']:.4f} | {v['test']['n']} |")
    L.append("\nTest-window (2026-27, open lines) EV>30% counts: " + "; ".join(
        f"{mk}: independent {v['independent']['ev_gt_30']}/{v['independent']['rows']}, selected-w {v['selected']['ev_gt_30']}/{v['selected']['rows']}"
        for mk, v in r["blend_test_ev_counts_open"].items()))
    s = nov["summary"]
    L.append("\n### F. Nov 24, 2026 card (run 45452279760), identical 167 rows / 62 games, re-priced at the card's own prices\n")
    L.append("| Quantity | Card (frozen native + RUN IT pricing) | FG1C challenger | Market |")
    L.append("|---|---|---|---|")
    L.append(f"| Margin MAE vs actual (n={s['card_margin_error_vs_actual']['n']}) | {s['card_margin_error_vs_actual']['mean_abs']:.2f} | {s['fg1c_margin_error_vs_actual']['mean_abs']:.2f} | {s['market_margin_error_vs_actual']['mean_abs']:.2f} |")
    L.append(f"| Total MAE vs actual (n={s['card_total_error_vs_actual']['n']}) | {s['card_total_error_vs_actual']['mean_abs']:.2f} | {s['fg1c_total_error_vs_actual']['mean_abs']:.2f} | {s['market_total_error_vs_actual']['mean_abs']:.2f} |")
    L.append(f"| Mean abs gap to market margin | {s['card_minus_market_margin']['mean_abs']:.2f} | {s['fg1c_minus_market_margin']['mean_abs']:.2f} | - |")
    o = s["card_margin_on_market_margin_ols"]
    L.append(f"| OLS card margin on market margin | slope {o['slope']:.3f}, intercept {o['intercept']:+.2f} | - | - |")
    b = s["big_favourites_abs_market_ge_15"]
    L.append(f"| Favourites with market >= 15 (n={b['n']}): mean margin | {b['card_margin_mean']:.2f} | {b['fg1c_margin_mean']:.2f} | {b['market_margin_mean']:.2f} (actual {b['actual_margin_mean_fav_oriented']:.2f}) |")
    L.append(f"| Rows with paper EV > 30% | {s['ev_gt_30_card']} | {s['ev_gt_30_fg1c_independent']} independent; {s['ev_gt_30_blend_selected']} at validation-selected weights | - |")
    L.append(f"| Rows with paper EV > 10% | {s['ev_gt_10_card']} | {s['ev_gt_10_fg1c_independent']} independent; {s['ev_gt_10_blend_selected']} at selected weights | - |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True); ap.add_argument("--nov24", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = json.loads(Path(a.eval).read_text()); nov = json.loads(Path(a.nov24).read_text())
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "tables.md").write_text(tables(r, nov))
    summary = {k: r[k] for k in ("status", "splits", "odds_census", "recalibration", "ml_recal", "bias", "point_bias",
                                 "blend", "blend_open", "ml_dog_bands_close_2024_2027", "blend_test_ev_counts_open")}
    summary["point"] = r["point"]; summary["ml_identical"] = {s: {e: {k: v[k] for k in ("n", "brier", "log_loss", "ece")} for e, v in x.items()} for s, x in r["ml_identical"].items()}
    summary["market"] = {s: {c: {mk: {k: d[k] for k in ("rows", "ev_gt_30", "ev_gt_10", "mean_best_ev", "flat_bets", "flat_roi")} |
                                 {"model": {k: d["model"][k] for k in ("n", "brier", "log_loss", "ece", "mean_p", "rate")},
                                  "market": {k: d["market"][k] for k in ("n", "brier", "log_loss", "ece")}}
                                 for mk, d in x.items() if d.get("model")} for c, x in v.items()} for s, v in r["market"].items()}
    summary["dists_2027"] = r["dists"]["2027"]
    summary["nov24"] = nov["summary"]
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    (out / "nov24_rows.json").write_text(json.dumps({"games": nov["games"], "rows": nov["rows"], "unmatched": nov["unmatched"]}, indent=1))


if __name__ == "__main__":
    main()
