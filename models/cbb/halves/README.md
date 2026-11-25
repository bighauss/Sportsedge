# `models/cbb/halves`: CBB first- and second-half pricing (PAPER/0u, NON_COUNTED)

Research model v1 (`cbb-halves-v1-research`). It isn't validated for staking. Every output carries
`label=PAPER_0U`, `counting=NON_COUNTED` and `approved_stake_u=0`.

## Files
- `halves_model.py`: stdlib-only projection and integer-outcome distributions (no network).
- `halves_pricing.py`: push-aware pricing for spread, total, moneyline and both team totals.
- `coefficients_halves_v1.json`: fitted on seasons 2019–2025 (37,263 games). Season 2026 was
  held out untouched and scored once. Built by `research/cbb_halves/fit_halves.py --stage test`.
- `test_halves.py`: runtime contract tests. Run from `models/cbb` with `python -m unittest -v halves.test_halves`.

## Interface for the runner
```python
import sys; sys.path.insert(0, "models/cbb")
from halves import halves_model as HM, halves_pricing as HP

coef = HM.load_coefficients()                       # verifies label, records sha256
d = HM.project_period("H1", fg_home=76.1, fg_away=68.4, coefficients=coef,
                      min_games=6,        # optional: fewest games either team has played this season
                      fg_poss=69.0,       # optional: pregame possessions; enables the "pace" total variant
                      fg_margin_sd=None,  # optional: residual SD of YOUR full-game margin model (see below)
                      fg_total_sd=None)
q = HP.price_half_market(d, market="SPREAD", side="home", line=-3.5, american=-115)
# q -> p_win, p_push, p_loss, fair_american, ev_per_unit, break_even, label fields, coefficients_sha256
```
Periods. **Pregame** and **halftime-adjusted** products are separate, labelled outputs (`kind`):

| period | kind | what it is |
|---|---|---|
| `H1` | PREGAME | first half |
| `H2` | PREGAME | second half including overtime (verify the book's rule) |
| `H2REG` | PREGAME | regulation second half only |
| `HT_H2` | HALFTIME_ADJUSTED | second half incl. OT, conditioned on the realized H1 score (+ optional `h1_poss`) |
| `HT_H2REG` | HALFTIME_ADJUSTED | regulation second half, conditioned on the H1 score |

Pregame periods refuse an H1 score (`PREGAME_PERIOD_MUST_NOT_SEE_H1_SCORE`). Halftime periods
require one (`HALFTIME_REQUIRES_H1_SCORE`).

Markets: `SPREAD` (home or away; the line is from that side's view), `TOTAL`, `TEAM_TOTAL_HOME` and
`TEAM_TOTAL_AWAY` (over or under), and `MONEYLINE` (home, away or tie). `MONEYLINE` requires
`tie_rule`, one of `TIE_PUSH`, `TIE_LOSES` or `THREE_WAY`. There's no default, because the book's
settlement rule for a tied half has to be stated. Lines must be on the 0.5 grid. Integer lines get
an explicit push probability from the integer PMF. EV = p_win·(decimal−1) − p_loss, with no cap,
floor or shrink. Fair odds are push-aware (p_win / (p_win + p_loss)). Errors raise `HalvesHold(reason)`.
`price_half_board_row(row)` takes a flat dict (period, market, side, line, american, fg_home,
fg_away, …).

## How it was fitted (see `research/cbb_halves/PROTOCOL.md`, `RESULTS.md`)
- Data: 43,522 games from public sportsdataverse ESPN play-by-play, 2019–2026, rebuilt with
  source and output sha256s. The 6,297-game H1 set reported in #57 wasn't found, and this isn't it.
- Inputs at fit time: a point-in-time sequential efficiency projector (`research/cbb_halves/pit_fullgame.py`)
  that only sees games before the projection date.
- Mean: OLS of the half target on FG projections (and pace, and, for halftime, the H1 score, |H1 margin|
  and H1 possessions). SD: heteroscedastic, log σ linear in |M|, T, early season (and |H1 margin|).
  Shape: normal or an empirical quantile table, chosen per target on dev folds 2021–2025.
- `fg_margin_sd` and `fg_total_sd` rescale the SDs when the runner's full-game model has a different
  residual SD from the fitting projector (13.56 margin, 17.25 total on the training seasons):
  var = var_fit + β²(sd_new² − sd_fit²), floored at the conditional noise. β and the noise SD are in the file.

## Known defects and limits (also in the PR)
1. **Totals under-projected in the 2026 test window.** Bias was +1.10 (H1), +1.38 (H2) and +1.12 (HT_H2), and
   overs hit 53.4% at the H1 model line against 50.0% predicted. The dev folds showed the same drift (H1 bias +0.82 and +0.89 in
   2024 and 2025). The fitted intercept lags rising scoring. Fixing it after seeing the test can't be claimed as
   test-validated, so it needs a fresh forward window (season 2027).
2. Favorites slightly underperform the H1 margin projection (−0.27 points; covered 47.8% at the model line
   against 50% predicted).
3. The means are calibrated to the fitting projector's scale. Feeding a sharper (e.g. market-blended)
   full-game projection changes the optimal slope. Re-fit on that model's chronological projections
   before any promotion.
4. There are no historical half-market prices, so there's no ROI, CLV or market-relative calibration.
5. Halftime adjustment is a modest improvement (H2 total MAE 9.85 → 9.67, margin 7.59 → 7.57 on test).
   It isn't a live in-play model (no clock, fouls or lineup).
6. Joint correlation between margin and total or across periods isn't modelled. Each market is priced
   from its own marginal distribution.


## Joint distributions (`halves_joint.py`)
Univariate marginals are unchanged. A copula on (margin, total) and a 4x4 Gaussian copula
on pregame (H1 margin, H1 total, H2 margin, H2 total) sit in
`coefficients_halves_joint_v1.json`, fitted on 2019–2025 after the kind was chosen on
2021–2025 folds. Season 2026 was not used for that choice or fit; any 2026 joint metric
is a secondary re-use.

```python
from halves import halves_joint as HJ
joint = HJ.load_joint()
d = HJ.project_period_joint("H1", 76.1, 68.4, min_games=6, fg_poss=69.0, joint=joint)
# d["joint"] has kind, rho or grid; d["pmf"] is still the v1 marginal
draw = HJ.sample_h1_h2(h1_dist, h2_dist, joint, rng)
```

## Production-compatible refit
Do not overwrite `coefficients_halves_v1.json`. To retarget the means at the FG1/FG1C
challenger (PR #534, branch `grok-cbb/fullgame-ev-20261125`):

```
python research/cbb_halves/import_fullgame_forecasts.py \
    --wf-dir <walk-forward JSON dir> --tag fg1t --engine FG1 --debias \
    --train-until 2025 --seasons 2020-2025 --out /tmp/fg1c_proj.csv
python research/cbb_halves/fit_halves.py --cache <sdv cache> --stage refit \
    --projections /tmp/fg1c_proj.csv --train-until 2025 \
    --out-coefficients models/cbb/halves/coefficients_halves_fg1c_v1.json \
    --source-label FG1C
```

`--train-until 2025` is required. The refit stage refuses to include 2026 in training
and refuses to overwrite the v1 file. Totals bias is not corrected on the test season
(see `research/cbb_halves/TOTALS_BIAS.md`).
