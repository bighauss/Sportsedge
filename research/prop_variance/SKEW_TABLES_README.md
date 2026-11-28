# Sport-specific skew tables: CFB and CBB (opt-in, PAPER)

`fit_skew_tables.py` builds one table per sport from that sport's **own** walk-forward
forecasts (prior games only) on **train seasons only**. No coefficients are shared
across sports. The tables are evaluated on untouched holdout seasons. Bias is reported,
never tuned by hand.

| Sport | Train | Holdout | Source |
|---|---|---|---|
| CFB | 2014–2021 | 2022–2025 | cfbfastR-data player_stats (PBP-derived; see CFB_INPUT_SHA256SUMS) |
| CBB | 2021-22, 2022-23 | 2023-24, 2024-25 | lbenz730/ncaahoopR_data box scores |

Evaluator: `sportsedge/markets/prop_skew.py`. The over, push and under probabilities sum
to 1. Push probability is non-zero only on whole-number lines. P(over) never increases as
the line goes up. A forecast below the table's `min_mean` is refused (`LOW_VOLUME_FORECAST`),
never extrapolated. The top forecast bin is open-ended.

## Holdout: proxy lines at 0.75–1.25× forecast, half-point and whole-number

| Sport | Stat | n | Brier skew | Brier pinned | max abs over-bias, skew | max abs over-bias, pinned |
|---|---|---|---|---|---|---|
| CFB | pass_yds | 4,547 | **0.2149** | 0.2289 | 0.040 | 0.087 |
| CFB | rush_yds | 12,551 | **0.2303** | 0.2432 | 0.024 | 0.106 |
| CFB | rec_yds | 15,615 | **0.2287** | 0.2431 | 0.019 | 0.098 |
| CFB | receptions | 15,616 | **0.2126** | 0.2266 | 0.019 | 0.048 |
| CBB | pts | 139,156 | **0.2317** | 0.2428 | 0.009 | 0.165 |
| CBB | reb | 153,826 | **0.2262** | 0.2351 | 0.007 | 0.139 |
| CBB | ast | 112,282 | **0.2173** | 0.2273 | 0.008 | 0.158 |
| CBB | tpm | 112,612 | **0.2067** | 0.2179 | 0.007 | 0.142 |

Push calibration on whole-number lines at the forecast (actual / skew / pinned): CBB pts
0.065 / 0.066 / 0.130, CBB ast 0.225 / 0.223 / 0.364, CFB rush 0.012 / 0.011 / 0.019.

## Residual problems (not fixed; do not hand-correct)
- **CFB still over-biased**: +1.1 to +4.0 pts on pass/rush/rec lines across offsets.
  This is season drift, so it needs rolling refits. CFB pass_yds at or above the forecast
  is +3.4 to +4.0 pts.
- **CBB top bin is coarse** (all forecasts ≥ 15.7 pts share one bin). For forecasts of
  19–23 pts at a 0.925× line, the skew table predicts 42.9% over vs 39.5% actual. Finer
  top bins are needed.
- Proxy lines, not DraftKings lines: this is calibration, not edge.

Opt-in: `cfb_prop_independent.price_props_independent(..., distribution="cfb-prop-skew-v1")`
and `models/cbb/cbb_prop_skew.price_props_skew(inputs)`. Neither runner calls these yet:
`cfb_run_it` still prices props with the pinned market-anchored path, and the CBB RUN IT
runner does not price props at all.
