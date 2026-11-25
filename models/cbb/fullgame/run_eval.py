"""Build the full-game EV/projection evidence report (RESEARCH ONLY, PAPER / 0u, NON_COUNTED).

Splits (fixed before looking at evaluation rows):
  TUNE 2020-2022   FG1 hyper-parameters (grid, margin RMSE + 0.5 * total RMSE)
  residual fits    every season S uses the same engine's walk-forward residuals from seasons < S
  VALIDATION 2024-2025  nine-weight blend selection (log loss); TEST 2026-2027 untouched by selection
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

from . import evaluate as E
from . import espn_odds as O
import cbb_pricing as PR

def logit(p):
    p = min(1 - 1e-9, max(1e-9, p)); return math.log(p / (1 - p))


def blend_pairs(mrows, w):
    out = []
    for m in mrows:
        if not m or m["y"] is None:
            continue
        pm = m["p"][0] / (1 - m["push"])
        z = w * logit(pm) + (1 - w) * logit(m["novig"][0])
        out.append((1 / (1 + math.exp(-z)), m["y"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", required=True); ap.add_argument("--odds", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    seasons = list(range(2020, 2028))
    tags = {e: "base" for e in ("RAW", "REG", "NATIVE_RECON", "SA")}; tags["FG1"] = "fg1t"
    data = E.load(a.wf, tags, seasons)
    recal = E.add_recalibrated(data, "FG1")
    rep = {"status": "RESEARCH_ONLY_PAPER_0U_NON_COUNTED", "splits": {"tune": [2020, 2021, 2022],
           "eval": [2023, 2024, 2025, 2026, 2027], "blend_validation": [2024, 2025], "blend_test": [2026, 2027]},
           "point": {}, "ml_identical": {}, "market": {}, "bias": {}, "point_bias": {}, "blend": {}, "dists": {}, "blend_open": {}}
    rep["recalibration"] = recal
    ENG = E.ENGINES + ("FG1C",)
    quotes_all, census = {}, {}
    for s in range(2023, 2028):
        q, c = O.load_dir(a.odds, [r["game_id"] for r in data[s]])
        quotes_all.update(q); census[s] = c
    rep["odds_census"] = census
    mk_store, mk_open = {}, {}
    for s in range(2023, 2028):
        rows = data[s]
        ident = [r for r in rows if all(e in r["f"] for e in ENG)]
        rep["point"][s] = {e: E.point_metrics(ident, e) for e in ENG}
        rep["point"][s]["FG1_all_rows"] = E.point_metrics([r for r in rows if "FG1" in r["f"]], "FG1")
        rep["point"][s]["FG1C_all_rows"] = E.point_metrics([r for r in rows if "FG1C" in r["f"]], "FG1C")
        dists = {e: E.fit_dists({k: v for k, v in data.items() if k >= (2022 if e == "FG1C" else 0)}, e, s) for e in ENG}
        rep["dists"][s] = {e: {t: {str(k): v.as_dict() for k, v in d[t].items()} for t in d} for e, d in dists.items()}
        # ML on identical rows vs actual outcome (all games, no odds needed)
        rep["ml_identical"][s] = {}
        for e in ENG:
            pairs = []
            for r in ident:
                from .pricing import ml_probs, phase_of
                p, _ = ml_probs(dists[e]["margin"][phase_of(r["n_home"], r["n_away"])], r["f"][e]["margin"])
                pairs.append((p, int(r["home_points"] > r["away_points"])))
            rep["ml_identical"][s][e] = E.prob_metrics(pairs)
        # market: before/after + attribution on identical market rows
        mlr = E.fit_ml_recal(data, "FG1C", s) if s >= 2024 else None
        rep.setdefault("ml_recal", {})[s] = mlr
        both = [r for r in rows if "NATIVE_RECON" in r["f"] and "FG1C" in r["f"] and r["game_id"] in quotes_all]
        combos = {"BEFORE_native_recon_OLD": ("NATIVE_RECON", "OLD"), "native_recon_NEW": ("NATIVE_RECON", "NEW"),
                  "fg1_OLD": ("FG1", "OLD"), "fg1_NEW": ("FG1", "NEW"), "AFTER_fg1c_NEW": ("FG1C", "NEW"), "AFTER_fg1c_NEW_mltail": ("FG1C", "NEWR")}
        rep["market"][s] = {}
        for name, (e, pr) in combos.items():
            mr = [m for m in E.market_rows(both, quotes_all, e, dists[e], "NEW" if pr == "NEWR" else pr,
                                           ml_recal=mlr if pr == "NEWR" else None) if m]
            rep["market"][s][name] = E.summarize_market(mr)
            if name == "AFTER_fg1c_NEW_mltail":
                rep["bias"][s] = E.bias_report(mr)
        allq = [r for r in rows if "FG1C" in r["f"] and r["game_id"] in quotes_all]
        mr_all = [m for m in E.market_rows(allq, quotes_all, "FG1C", dists["FG1C"], "NEW", ml_recal=mlr) if m]
        rep["market"][s]["FG1C_NEW_all_quote_rows"] = E.summarize_market(mr_all)
        rep["bias"][f"{s}_all_quote_rows"] = E.bias_report(mr_all)
        rep["point_bias"][s] = {"FG1": E.point_bias(allq, "FG1", quotes_all), "FG1C": E.point_bias(allq, "FG1C", quotes_all)}
        mk_store[s] = mr_all
        qo, _ = O.load_dir(a.odds, [r["game_id"] for r in allq], which="open")
        mk_open[s] = [m for m in E.market_rows(allq, qo, "FG1C", dists["FG1C"], "NEW", ml_recal=mlr) if m]
        rep["market"][s]["FG1C_NEW_vs_OPEN"] = E.summarize_market(mk_open[s])
    # nine-weight blend: select on validation seasons, report once on test seasons
    for mk in ("spread", "total", "moneyline"):
        val = [m for s in (2024, 2025) for m in mk_store[s] if m["market"] == mk]
        tst = [m for s in (2026, 2027) for m in mk_store[s] if m["market"] == mk]
        vres = {str(w): E.prob_metrics(blend_pairs(val, w))["log_loss"] for w in PR.OWNER_BLEND_WEIGHTS}
        best = min(PR.OWNER_BLEND_WEIGHTS, key=lambda w: vres[str(w)])
        tres = E.prob_metrics(blend_pairs(tst, best))
        rep["blend"][mk] = {"validation_log_loss": vres, "selected_model_weight": best,
                            "test": {k: tres[k] for k in ("n", "brier", "log_loss", "ece")},
                            "test_market_only": {k: E.prob_metrics(blend_pairs(tst, 0.0))[k] for k in ("n", "brier", "log_loss", "ece")},
                            "test_model_only": {k: E.prob_metrics(blend_pairs(tst, 1.0))[k] for k in ("n", "brier", "log_loss", "ece")}}
    for mk in ("spread", "total", "moneyline"):
        val = [m for s in (2024, 2025) for m in mk_open[s] if m["market"] == mk]
        tst = [m for s in (2026, 2027) for m in mk_open[s] if m["market"] == mk]
        vres = {str(w): E.prob_metrics(blend_pairs(val, w))["log_loss"] for w in PR.OWNER_BLEND_WEIGHTS}
        best = min(PR.OWNER_BLEND_WEIGHTS, key=lambda w: vres[str(w)])
        rep["blend_open"][mk] = {"validation_log_loss": vres, "selected_model_weight": best,
                                 "test": {k: E.prob_metrics(blend_pairs(tst, best))[k] for k in ("n", "brier", "log_loss", "ece")},
                                 "test_market_only": {k: E.prob_metrics(blend_pairs(tst, 0.0))[k] for k in ("n", "brier", "log_loss", "ece")},
                                 "test_model_only": {k: E.prob_metrics(blend_pairs(tst, 1.0))[k] for k in ("n", "brier", "log_loss", "ece")}}
    rep["ml_dog_bands_close_2024_2027"] = E.ml_dog_bands([m for s in (2024, 2025, 2026, 2027) for m in mk_store[s]])
    rep["blend_test_ev_counts_open"] = {mk: {"selected_w": rep["blend_open"][mk]["selected_model_weight"],
        "independent": E.blended_ev_counts([m for s in (2026, 2027) for m in mk_open[s] if m["market"] == mk], 1.0),
        "selected": E.blended_ev_counts([m for s in (2026, 2027) for m in mk_open[s] if m["market"] == mk],
                                        rep["blend_open"][mk]["selected_model_weight"])} for mk in ("spread", "total", "moneyline")}
    Path(a.out).write_text(json.dumps(rep, indent=1, default=str))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
