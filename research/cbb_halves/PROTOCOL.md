# CBB halves model: preregistered evaluation protocol (PAPER/0u, NON_COUNTED)

Written and committed before the single run on the untouched test window.

## Data
- Source: public sportsdataverse ESPN men's college basketball release files
  (`espn_mens_college_basketball_pbp`, `..._schedules`, `..._team_boxscores`), seasons 2019–2026.
  `fetch_sdv.py` downloads them and records the URL, byte count and sha256 of every file.
- `build_halves_dataset.py` derives one row per completed game (H1 score = cumulative score on
  the last period-1 play; regulation and final scores; OT periods; H1 possessions estimate).
  Every admitted game matches the schedule's final score, and from 2023 on also the schedule's
  period-1 linescore. Rejected games are listed with a reason code.
- The 6,297-game H1 dataset reported in issue #57 could not be located (see README). This is a
  rebuild and does not claim to be that dataset.

## Splits (chronological, by season; season N = the season ending in spring N)
1. **Projector tuning:** 2019–2020 only. Three hyper-parameters of the point-in-time full-game
   projector (`pit_fullgame.py`: k0=0.25, k_min=0.045, carry=0.8), chosen by FG MAE on 2020 with
   2019 as burn-in.
2. **Development / validation:** rolling origin. For S in 2021..2025, fit on seasons < S and score on S.
   Every modelling choice is made here: feature sets, the heteroscedastic SD form, and the
   residual shape (normal vs empirical quantile table, chosen per target by mean discrete log score).
3. **Untouched test:** season 2026 (Nov 3, 2025 – Apr 7, 2026). It's scored exactly once, by
   `fit_halves.py --stage test`, using coefficients fitted on 2019–2025 with the dev-chosen shapes.
   Those exact coefficients ship as `models/cbb/halves/coefficients_halves_v1.json`. No change
   made after seeing the test result may be reported as test-validated.
   Season 2027 (in progress) is not used.

## Targets and products
- H1, pregame H2 including OT (`H2`), pregame regulation H2 (`H2REG`), halftime-adjusted H2
  including OT (`HT_H2`) and halftime-adjusted regulation H2 (`HT_H2REG`). Each has margin, total
  and team points (home and away).
- Pregame products never see first-half data. Halftime products add the realized H1 score and
  optionally H1 possessions.

## Metrics (per held-out season and on the test window)
MAE, RMSE and bias. Bias is also split by favorite/underdog perspective for margins, and by
high/low projection for totals, with over/under rates at the model line. Discrete log score.
Brier, log loss and ECE for P(Y > L) at five half-point lines around the mean. Calibration
tables. Push probability vs frequency at integer lines. Three-way and two-way moneyline
Brier/log loss, tie rate vs predicted, and 50/80/95% interval coverage. Baseline: the legacy
constants in `models/cbb/sportsedge_cbb_model.py` (H1 = 0.47 × FG, SD 8 total / 6.8 spread),
and 0.53 × FG for H2.

## Not measurable here
There are no historical H1/H2 sportsbook lines in these sources, so ROI, CLV and
market-relative calibration can't be computed. Every output stays PAPER/0u, NON_COUNTED.

## Addenda (same splits; no change to the untouched 2026 window)

### Joint margin/total and H1–H2 dependence
Copula kind and correlations are chosen on the same 2021–2025 rolling-origin
folds, then frozen on 2019–2025, in `fit_joint.py`. They live in
`coefficients_halves_joint_v1.json` and do not alter v1 means or SDs. Season
2026 is not used for selection or fit. Any 2026 joint metric is a **secondary
re-use** of the already-scored test window.

### Production-compatible means
`fit_halves.py --stage refit --projections <csv> --out-coefficients <path>
--train-until 2025` refits half means and SDs on an external pregame full-game
projector (the FG1/FG1C walk-forward from `models/cbb/fullgame`, PR #534, after
`import_fullgame_forecasts.py`). The refit refuses to overwrite
`coefficients_halves_v1.json` and refuses a training window that includes 2026.
`TOTALS_BIAS.md` forbids using 2026 to correct the known totals intercept drift.
