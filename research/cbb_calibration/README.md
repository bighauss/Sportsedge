# CBB calibration research: props, margins, totals, team totals (Nov 28 2026)

PAPER research only. **Proxy lines, not sportsbook lines**, so this measures the shape and
width of outcome distributions around a no-leakage baseline. It does not measure edge vs
DraftKings. CBB-specific; no NFL or CFB coefficients are reused.

## Data (free, no API key)
`lbenz730/ncaahoopR_data` (public GitHub, CSV), commit `ee3615621d426fa72f252dae0fb3e243bf2d28ff`,
folders `{2021-22,2022-23,2023-24,2024-25}/{box_scores,schedules}`. Not committed. Rerun:
`python research/cbb_calibration/fit_cbb_calibration.py <path-to-ncaahoopR_data>`.
The `sportsdataverse/hoopR-mbb-data` repo is parquet-only, and no parquet reader is
installed in this sandbox.

## Method
- Train 2021-22 and 2022-23. **Untouched holdout 2023-24 and 2024-25.**
- Props: EWMA (α 0.35) of the player's prior games only (≥3); prop-eligible means
  pts≥5, reb≥2, ast≥1, 3pm≥0.5. The pinned pricing is reproduced exactly:
  normal, sd = max(0.8, PROP_SD_FRAC × max(mean, line)). It is compared with an empirical
  distribution of Y/f in forecast bins taken from train. Rows with no activity are
  dropped as DNP (MIN is 0 throughout this source). 4,142 duplicate player rows were
  dropped (the same game appears in both teams' folders).
- Games: baseline = ½(team prior scored EWMA + opponent prior allowed EWMA), plus a
  home shift fitted on train (2.18 pts/team). **This is a simple baseline, not the pinned
  CBB model**, which needs as-of Torvik ratings and can't run point-in-time here, so the
  game-width numbers are an upper bound on model error.
- First halves: **NOT_COVERED**; the box scores have no half scores. pbp_logs could
  supply them later.

## Props, holdout
| Stat | n | Mean f | Pinned frac | Implied frac | Median Y/f | ECE pinned | ECE empirical | Log loss pinned → empirical |
|---|---|---|---|---|---|---|---|---|
| pts | 139,156 | 10.6 | 0.33 | 0.58 | 0.91 | 0.071 | **0.007** | 0.684 → 0.658 |
| reb | 153,826 | 4.3 | 0.40 | 0.61 | 0.89 | 0.075 | **0.005** | 0.678 → 0.656 |
| ast | 112,282 | 2.3 | 0.45 | 0.77 | 0.80 | 0.100 | **0.009** | 0.680 → 0.650 |
| 3pm | 112,612 | 1.4 | 0.65 | 0.96 | 0.74 | 0.117 | **0.013** | 0.686 → 0.652 |

**Pinned P(over) minus actual over rate, by proxy line:**
| Line | pts | reb | ast | 3pm |
|---|---|---|---|---|
| 0.75f | +16.5 | +13.9 | +15.8 | +14.2 |
| 0.90f | +11.1 | +10.3 | +12.3 | +12.8 |
| 1.00f | +5.7 | +6.7 | +9.4 | +11.7 |
| 1.10f | +1.5 | +4.3 | +7.5 | +10.7 |
| 1.25f | −2.2 | +2.0 | +5.1 | +9.2 |

All figures are percentage points. The pinned prop normal is far too narrow and
symmetric, and it **systematically favours overs**. For 3pm and assists the over is
overstated at every offset tested.

## Games, holdout (n = 11,392; 87% true home)
- **Residual SD vs pinned SD:** margin 12.9 vs 11.0, total 17.4 vs 11.0, team total 10.8 vs 8.0.
  Skew is mildly positive (margin 0.18, total 0.28) and excess kurtosis is about 0.5.
- **Totals, pinned SD 11:** P(over) is +7.2 pts too high for lines 6 below forecast and
  −5.9 pts too low for lines 6 above. ECE is 0.041 pinned vs 0.009 with the train-fitted SD.
- **Team totals, pinned SD 8:** ECE 0.037 pinned vs 0.003 fitted. The gap is +6.0 pts
  6 below the forecast and −5.5 pts 6 above.
- **Margin, pinned SD 11:** ECE 0.016 pinned vs 0.008 fitted, a smaller effect.
- **Bias:** holdout home margin bias is +0.5 pts after the train home shift. The forecast
  favourite beats its forecast margin 51.2% of the time (n = 10,177), so there is no
  meaningful favourite or dog bias at this level.
- **Key numbers:** the most common final |margin| values are 3 (6.2%), 4, 5 and 2. That
  is a flat profile, not NFL-style key numbers.

## Caveats
- The total and team-total width partly reflects the weakness of this baseline (no tempo
  or efficiency adjustment). The pinned SD_TOTAL = 11 should be re-fitted on residuals
  of the actual CBB model, using as-of ratings, before it is changed.
- The prop findings are robust to the baseline: the skew (median Y/f 0.74–0.91) is a
  property of the outcomes.
