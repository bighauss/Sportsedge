# CBB multi-season rolling-origin backtest (WS4) - results

Status: **RESEARCH, PAPER / 0u, NON_COUNTED.** Nothing here promotes a model, changes a frozen
file, or authorizes a stake. Every number below is copied from the committed CSVs in
`results/run3_final/` (rendered in full, without hand-typing, in `results/run3_final/TABLES.md`).

Branch `grok-cbb/backtest-harness-20261125`, based on main `7fc5aaa9`. Run 3 generated
2026-11-25 17:29 UTC (11:29 AM CT).

## What was run

* **Rolling origin.** Every Monday of every season 2019-2026 (2026 = the 2025-26 season) is an
  origin. Each model is fit only on admitted finals with game day < origin (plus the previous
  season's end ratings as a preseason prior where the model uses one) and forecasts every game in
  [origin, origin + 7 days). 175 origins, 47,124 games.
* **Identical rows.** All metrics compare models on the same 35,791 games on which every model
  produced a forecast.
* **Predictive SDs.** Each model's spread, total and moneyline probabilities use the RMSE of that
  model's own earlier residuals (current and previous season, game day < origin, at least 300).
* **Splits, fixed in code before any run.** Train 2019-2021 is used only to warm up the SD history.
  Validation 2022-2024 is the only data the blend weight is selected on, by mean log loss and never
  by profit. Test 2025-2026 reports the selected weight once.
* **Nine blend weights.** The owner's Nov 25 spec (t26u item 6): 100/0, 87.5/12.5, 75/25,
  62.5/37.5, 50/50, 37.5/62.5, 25/75, 12.5/87.5, 0/100, as independent/market. The blend is
  p = w * p_independent + (1 - w) * p_market_no-vig_close. The independent forecast never sees
  market data. Every weight is evaluated on its own for each model, family, season and split.
* **Leakage checks.** These are both run-time assertions and unit tests:
  * No prior game falls on or after its origin.
  * The SD history is strictly before the origin.
  * Previous-season carry doesn't overlap the target season.
  * Validation and test seasons are disjoint.
  * A perturbation test changes later outcomes and shows that earlier forecasts don't move.
  * Result: 175 origins checked, 0 violations.
* **Bootstrap.** 1,000 resamples of whole game dates (clustered by date).

### Models (pluggable: `--model name=module:callable`)

| Name | What it is |
|---|---|
| `native_frozen` | The repo's own public reconstruction: `research.cbb_hca.public_factorial_backtest.context` (8-game shrink), fed to the frozen `cbbd_native_score_model.project`, which is imported read-only. This is the frozen native **formula** on reconstructed ratings, **not** a replay of CBBD `/ratings/adjusted`, because no point-in-time CBBD archive exists. |
| `raw` | Unshrunk per-100 ratings plus the native projection. |
| `regularized` | 8-game shrink toward a preseason prior (previous-season rating regressed 50%) plus the native projection. |
| `sched_adj` | Opponent and venue-adjusted ridge ratings (same prior) plus the native projection. |
| `native_hca_repaired` | `native_frozen` with only the HCA estimator replaced. See finding 1. **A candidate repair, not frozen.** |
| `FG1` | The full-game stream's engine (`models/cbb/fullgame/ratings.py` on `grok-cbb/fullgame-ev-20261125` @ `3003e772`), imported read-only through `fg1_adapter.py` and run under this harness's weekly-origin protocol. |

`raw`, `regularized` and `sched_adj` also use the repaired HCA estimator in run 3. Run 1 (the
"before" numbers, in `results/run1_as_specified/`) used the native mean-residual HCA rule for every
model.

## Data and coverage

* **Finals.** Sportsdataverse ESPN `mbb_schedule_{season}` and `team_box_{season}` parquet, the same
  release CI's factorial workflow downloads. Games are admitted with the repo's own
  `schedule_games`. Possessions are a box-score estimate.
* **Historical odds.** These exist and are real. They come from ESPN's public core API,
  `sports.core.api.espn.com/.../events/{id}/competitions/{id}/odds`, collected by
  `espn_odds_collect.py`. All 47,140 completed games were requested, with 0 failed fetches; 43,047
  games have a usable sportsbook row.
  * Each game gets one row under a fixed provider preference: DraftKings first (provider 40 through
    2024-25, 100 in 2025-26), then ESPN BET and the other US books.
  * The following are never used: numberfire, teamrankings, accuscore (these are models), and the
    live-odds feeds 59 and 200.
  * Providers by season are listed in TABLES.md section 1. 2019 is mostly Unibet, 2020-2024 mostly
    DraftKings, 2025 ESPN BET, and 2026 DraftKings (4,805) plus ESPN BET (944).
* **Pre-2024 closes.** These come from ESPN's `current` field because there is no explicit `close`
  node. They are flagged per row (`close_from_current_fallback`).
* **2023 spread and total are quarantined.** Their closes are inconsistent with the finals: the
  spread residual mean is -5.63 with MAE 14.3, against MAE 8.6-9.1 in every other season, and 6.8%
  of totals fall outside [110, 190]. 2023 moneylines pass and are kept. This independently matches
  the full-game stream's "2023 ML only".
* **CLV is BLOCKED (`BLOCKED_OPEN_LINES_FAIL_VALIDATION`).** ESPN's `open` nodes fail sanity checks.
  37% of open totals differ from the close by more than 15 points, and there are decimal prices in
  total fields and spread sign flips. A first pass that used them produced impossible CLV (about
  100 points) and open-price ROI of +26% to +66%. Those numbers were discarded, not reported. ROI
  is computed only at the close.
* **Close timing** is ESPN's label and isn't authenticated against tip time.

| Season | Admitted finals | Identical rows | Spread lines | Total lines | ML lines |
|---|---|---|---|---|---|
| 2019 | 6,049 | 4,339 | 5,375 | 5,363 | 5,133 |
| 2020 | 5,767 | 4,509 | 5,313 | 5,312 | 5,114 |
| 2021 | 4,285 | 3,050 | 3,839 | 3,706 | 3,736 |
| 2022 | 5,966 | 4,286 | 5,419 | 5,419 | 5,385 |
| 2023 | 6,222 | 4,769 | 0 (quarantined) | 0 (quarantined) | 5,670 |
| 2024 | 6,243 | 4,895 | 5,754 | 5,752 | 5,496 |
| 2025 | 6,292 | 4,954 | 5,763 | 5,762 | 5,647 |
| 2026 | 6,300 | 4,989 | 5,706 | 5,734 | 5,507 |

Line counts are for all admitted games, not just identical rows.

## Findings

### 1. Defect: the native HCA rule over-predicts home teams by about 4.7 points

* **Size.** `native_frozen` margin bias (pred - actual) is +4.70 overall, with 95% CI +4.47 to
  +4.91. In the test window it's +5.22.
* **Applied HCA.** The model applies 6.5-10.5 points of HCA by season (8.6+ in every season except
  2021), while home-court games actually average a 3.1-4.7 point margin (TABLES.md section 6).
* **Mechanism.** HCA is the mean residual of all prior non-neutral games computed on **shrunk**
  ratings. Home "buy games" against rarely-seen visitors, mostly non-Division I, leave those
  visitors shrunk far toward the league mean. Their blowout losses become huge positive home
  residuals.
* **Repair selection.** Six candidate estimators were scored on **validation seasons only**
  (`results/hca_repair_selection_validation.txt`). Bias and MAE are on 12,947-12,948 validation
  home-court games:

  | Candidate | Bias | MAE |
  |---|---|---|
  | Native rule | +5.568 | 10.561 |
  | Shrunk, qualified | +2.297 | 9.658 |
  | Raw, all | -0.812 | 9.630 |
  | **Raw, both teams ≥ 4 prior games** | **+0.467** | **9.562** |
  | No HCA | -4.009 | 9.998 |

  The selected estimator is the raw, qualified one in bold. A raw variant needing ≥ 8 prior games
  had a lower MAE of 9.425, but it covers only 11,680 games, so it was not comparable.
* **Before and after, all identical rows:**
  * Margin MAE goes from 10.465 to 9.611. The delta is -0.854, with CI -0.928 to -0.773.
  * Margin bias goes from +4.696 to +0.194, with CI -0.013 to +0.397.
  * ML ECE in the test window goes from 0.109 to 0.013.
* **Caveat.** This repair was designed after I had seen run 1's tables, which included the test
  seasons. Its test numbers are therefore **not** untouched-test evidence.
* **Not established.** This doesn't show that the production native model, which runs on CBBD
  adjusted ratings, has the same defect. That needs checking on production inputs, by the full-game
  stream or the owner.

### 2. Model ranking on identical rows: FG1 is best, but no model beats the close

| Window | Metric | native_frozen | raw | regularized | sched_adj | native_hca_repaired | FG1 |
|---|---|---|---|---|---|---|---|
| Test 2025-26 (n=9,943) | Margin MAE | 10.876 | 10.241 | 9.658 | 9.730 | 9.799 | **9.113** |
| Test 2025-26 | Margin bias | +5.222 | +0.628 | +0.162 | +0.249 | +0.100 | +0.347 |
| Test 2025-26 | Total MAE | 13.691 | 14.076 | 13.620 | 13.613 | 13.691 | **13.346** |
| Test 2025-26 | Total bias | +0.947 | +1.205 | +0.903 | +0.815 | +0.947 | +0.895 |
| Validation 2022-24 (n=13,950) | Margin MAE | 10.448 | 10.018 | 9.386 | 9.422 | 9.542 | **8.936** |
| All (n=35,791) | Margin MAE, delta vs native (CI) | 0 | -0.374 (-0.455, -0.275) | -1.016 (-1.095, -0.936) | -0.990 (-1.070, -0.908) | -0.854 (-0.928, -0.773) | **-1.479 (-1.559, -1.402)** |

**Log loss against the no-vig close, on the same test-window market rows:**

| Family | Market | FG1 | native_frozen |
|---|---|---|---|
| ML (9,698 rows) | **0.5419** | 0.5592 | 0.6372 |
| Spread (9,897 rows) | **0.6929** | 0.7141 | 0.7947 |
| Total (9,920 rows) | **0.6930** | 0.7110 | 0.7256 |

Across all seasons, FG1 minus market log loss is:
* ML: +0.013 (CI +0.012 to +0.015)
* Spread: +0.017 (CI +0.015 to +0.020)
* Total: +0.014 (CI +0.012 to +0.016)

Every model is worse than the closing market in every family, and every CI excludes zero.

### 3. Nine-weight blend: validation picks 0/100 (market only) everywhere

* **Selection.** For all 6 models and all 3 families, the weight with the lowest validation log loss
  is w_independent = 0. Reported once on the test window, the selected blend is identical to the
  market (ML 0.5419, spread 0.6929, total 0.6930), with no bets.
* **Profitability.** Every nonzero weight loses at the close in both validation and test.
  * The one exception is FG1 total at 12.5/87.5 in validation: +8.3% ROI on 141 bets. On the test
    window it drops to -15.6% on 261 bets, so it's noise.
  * Max drawdowns for nonzero weights run from about 13u to about 1,005u (TABLES.md section 7).
* **Agreement with the full-game stream.** Its "model weight selected = 0 at the close" result
  **agrees** with this one. Our splits are fully separate, with no reuse of test data for selection.

### 4. Why "EV > 30%" shows up: it's model error, not edge

These are pure-model bets (w = 1) at the close, across all seasons (TABLES.md section 9):

| Model | Bets | Count | Mean claimed EV | Realized ROI |
|---|---|---|---|---|
| native_frozen | ML, EV > 30% | 12,902 | +86.4% | **-14.4%** |
| native_frozen | ML, ≥ +300 underdogs | 5,676 | +105.7% | **-31.3%** |
| FG1 | ML, EV > 30% | 4,572 | +58.2% | **-23.0%** |
| FG1 | ML, ≥ +300 underdogs | 6,739 | +37.5% | **-25.4%** |

Across every EV band and every family, the realized ROI is negative. The big paper EVs on long
moneyline underdogs, like the Nov 24 Lipscomb +3500 example, are what an uncalibrated model
produces against an efficient close.

### 5. Other bias and calibration notes

* **Totals.** In the test window, every model projects totals 0.8-1.2 points too high. In
  validation they run 0.18-0.36 too low. That's a season-level drift, and nothing was tuned to it.
* **Moneyline calibration.** native_frozen is overconfident on the home side: mean p 0.729 against
  a frequency of 0.620 in the test window, with ECE 0.109. FG1's ML ECE is 0.022.
* **Spread and total calibration.** FG1's spread and total ECE (0.079 and 0.070) are far above the
  market's (0.005).
* **Splits.** Favorite/underdog, home/neutral, spread-band, over/under and price-band breakdowns are
  in TABLES.md sections 5 and 9, each with its n, bias, MAE, RMSE and residual SD.

### 6. Comparison with the full-game stream's own tables

* **Their NATIVE_RECON isn't our `native_frozen`.**
  * Theirs is D1-only, uses schedule-adjusted ratings and daily refits. Its margin MAE is
    9.1-9.3, with a small bias.
  * Ours is the repo's `public_factorial_backtest` reconstruction, which includes every ESPN
    opponent. That difference is why our `native_frozen` shows the HCA defect.
* **FG1 is consistent between the two.** Under this harness's weekly origins, FG1's test-window
  margin MAE is 9.113, against their daily 9.00 for 2025 and 9.13 for 2026.
* **Overlap disclosure.** FG1's hyper-parameters were chosen on their tune seasons 2020-2022, which
  overlap this harness's validation season 2022.
* **Population look-ahead in their driver.** For completed seasons, their D1 proxy uses that
  season's own end-of-season game counts. This harness uses the previous season's D1 set instead,
  which is leak-free.

## Blockers and gaps

1. **CLV can't be computed** until a validated open or pre-tip line source exists. The ESPN opens
   fail validation, so the path is forward DK captures.
2. **The production native model can't be replayed** historically, because no point-in-time CBBD
   ratings exist. Results are for the native formula on reconstructed ratings.
3. **Hosted CI doesn't run these tests yet.** Adding a workflow is outside this stream's file
   ownership. The command is `PYTHONPATH=.:models/cbb python -m unittest research.cbb_backtest.test_cbb_backtest`.
4. **FG1 has to be imported from its own branch** (`PYTHONPATH` includes a checkout of
   `models/cbb/fullgame`) until that branch merges. Without it the FG1 test skips.
5. **Market quality.** 2023 spread and total are quarantined. Pre-2024 closes come from the
   `current` fallback. Coverage only reaches games ESPN lists, at about 91%.
6. **Possessions** are box-score estimates. The **D1 proxy** is 15+ finals in the previous season.

## Reproduce

```
python -m research.cbb_backtest.espn_odds_collect --ids ids.txt --out espn_odds_all.jsonl.gz   # ids: completed game_ids from the schedules
PYTHONPATH=.:models/cbb:<fullgame checkout> python -m research.cbb_backtest.harness \
  --root <sdv parquet dir incl. 2018> --odds espn_odds_all.jsonl.gz --out out/ \
  --seasons 2019 2020 2021 2022 2023 2024 2025 2026 --reps 1000 \
  --model FG1=research.cbb_backtest.fg1_adapter:build_fg1
python -m research.cbb_backtest.make_results out/ out/TABLES.md
PYTHONPATH=.:models/cbb python -m research.cbb_backtest.hca_repair_selection
```

The row-level paired forecasts for identical rows, with market columns, are in
`results/run3_final/rows/identical_rows_{season}.csv`.
