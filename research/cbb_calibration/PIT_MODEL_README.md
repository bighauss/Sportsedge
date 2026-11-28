# CBB: point-in-time backtest of the pinned model + dedicated first halves (Nov 28 2026)

PAPER research only. These are proxy lines, not DraftKings lines. No coefficients are changed.

## Data
`lbenz730/ncaahoopR_data` @ `ee3615621d426fa72f252dae0fb3e243bf2d28ff`:
- box_scores, 2021-22 through 2024-25
- pbp_logs, used only to derive halftime and final scores; the raw files were deleted after
  parsing, and the derived `halves.csv` digest is in `HALVES_SHA256SUMS`

Nothing raw is committed. The data is free and public, from GitHub; no API key is needed.

## 1. Pinned model, point-in-time (`cbb_pit_model_backtest.py`)
`models/cbb/sportsedge_cbb_model.project_game` is called **unchanged** (blob 8bbe83b7,
pinned by test). Only its rating inputs are rebuilt, each from the team's **prior** games
that season:
- one-pass opponent-adjusted adjoe/adjde
- possessions per 40 minutes
- four factors, 3P% and 3PA rate
- the previous season's final ratings as `pre_*`

Where this differs from live use:
- Live inputs are Torvik ratings, which use an iterative full-season opponent adjustment;
  this backtest uses a one-pass adjustment.
- There is no venue HCA (default 3.0), travel, back-to-back or injury data.
- Altitude names only partly match.
- Teams need at least 3 prior games, and both teams' box scores must exist, so non-D-I
  games are excluded.
- 100 implausible boxes were rejected and counted.

**Leakage audit:**
- Train runs to 2023-04-03; the holdout starts 2023-11-06.
- Game-id overlap is 0.
- Each forecast is computed before that game's update (tested).

| Holdout 2023-25 (10,125 games) | Mean resid (actual − model) | Residual SD | Pinned SD | MAE | Skew |
|---|---|---|---|---|---|
| Margin | +0.65 | 11.77 | 11.0 | 9.29 | 0.09 |
| Total | **−2.30** | **17.00** | 11.0 × tempo | 13.50 | 0.27 |
| Team total | −1.15 | 10.34 | 8.0 | 8.25 | 0.13 |

- **Totals are over-projected** in every season: −6.2, −3.9, −3.1 and −1.5 pts by season,
  and worst in Nov–Dec. With the pinned SD, P(over) is overstated by +6.8 pts at the
  projection and +12.6 pts at projection − 6 (ECE 0.067).
- Refitting the SD on train removes the offset slope but leaves +6.8 pts at every offset.
  **The mean bias is the problem, not only the width.**
- The model **under-separates teams**. Favourites beat the model margin by +1.6 pts and
  cover the model number 55.9% of the time (train: +1.1 pts, 54.6%). So model margins are
  too small, which biases toward underdogs.
- Home: +0.75 pts beyond the default 3.0 HCA (non-neutral games).
- Margin SD 11.8 vs pinned 11.0 is roughly right.

Part of the total bias may come from the reconstruction (one-pass adjustment, fixed
`LEAGUE` constants oe=105 / tempo=67.5) rather than the live Torvik inputs. This must be
re-checked with archived point-in-time Torvik ratings before `SD_TOTAL`, `LEAGUE` or any
coefficient is changed.

## 2. First halves (`fit_cbb_first_half.py`, data from `extract_cbb_halves.py`)
- Validation: the pbp final must equal the box final, in either orientation.
- Holdout: 9,561 games. Dropped: 529 with no pbp, 472 with mismatched finals (counted).
- Observed 1H share of the total is 0.468 every season; the pinned `H1_FRAC` of 0.47 is right.

| Holdout 1H total | Mean resid | MAE | Assumed SD (real ~10.0) | ECE | Brier | P(over) bias at projection |
|---|---|---|---|---|---|---|
| Pinned (0.47 × full total, SD_H1 8) | −1.30 | 8.03 | 8.0 | 0.055 | 0.2383 | **+5.7 pts** |
| Pinned + train bias/SD refit | +1.27 | 8.00 | 9.99 | 0.045 | **0.2375** | **−4.5 pts** (overcorrects) |
| Dedicated (prior 1H scored/allowed EWMA) | −0.12 | 8.15 | 10.21 | **0.010** | 0.2380 | +1.3 pts |

- 1H margin: the pinned SD is 6.8 vs a real ~9.4. Spreads are too confident.
- No method dominates.
  - The dedicated 1H model is the best calibrated and closest to unbiased.
  - The pinned scaled mean is slightly more accurate (lower MAE and Brier once refit).
  - A static bias refit fails because the full-game total bias drifts by season.
- The fix order is: (1) fix the full-game total over-projection; (2) set the 1H SDs to
  ~10 for totals and ~9.4 for margins; (3) consider blending the dedicated 1H forecast.

Reproduce:
```
python research/cbb_calibration/cbb_pit_model_backtest.py NCAAHOOPR_DATA
python research/cbb_calibration/extract_cbb_halves.py halves.csv NCAAHOOPR_DATA   # partial clone
python research/cbb_calibration/fit_cbb_first_half.py NCAAHOOPR_DATA halves.csv
```
