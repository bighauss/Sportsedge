"""Inflated-EV and directional-bias diagnostics for CBB full-game (PAPER / 0u).

Emits counts of EV>30% / EV>10%, favourite bias, and over/under bias from the
existing evaluate.summarize_market and bias_report helpers. No model changes,
no promotion, no fabricated rows.
"""
from __future__ import annotations
from . import evaluate as E


def emit(mrows, threshold=0.30):
    """Return a research-only diagnostic dict."""
    summary = E.summarize_market(mrows, threshold=threshold)
    bias = E.bias_report(mrows)
    return {
        "label": "PAPER_0U_RESEARCH_ONLY",
        "ev_flags": {k: {"ev_gt_30": v.get("ev_gt_30"), "ev_gt_10": v.get("ev_gt_10"),
                         "mean_best_ev": v.get("mean_best_ev")} for k, v in summary.items()},
        "directional_bias": bias,
        "note": "Flags only; positive paper EV is not verified +EV. No counted bets.",
    }


if __name__ == "__main__":
    print("diagnostic module ready (no live data)")
