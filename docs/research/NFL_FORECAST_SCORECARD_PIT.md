# NFL research forecast scorecard: ridge vs Elo-style vs EPA challenger

**Status: research/PAPER 0u.** No engine, published card, historical forecast, selection, price, staking rule or official model is changed by this PR. All input examples below are synthetic schemas, not observed 2026 games.

## Critical actual repository capability

`models/nfl/epa_ridge_pit.py` is an **EPA team-effects feature builder**. The current code explicitly outputs `projected_points=None`, `market_ev=None` and `approved_stake_u=0`. It does **not** predict scores, totals, margins or winning probabilities. The "current NFL ridge forecast" is therefore **NOT_AVAILABLE** until a separately validated, preregistered score/distribution mapping consumes frozen `epa_ridge_pit` features and generates a real pregame forecast. Naming EPA features `ridge` cannot fill this gap.

### What is now executable

1. `forecast_scorecard_pit.py`: read-only matched **three-model** evaluator. Inputs are frozen, previously emitted model predictions. For each matchup, require a pregame ridge scoring model, Elo-style baseline and independent EPA challenger with authentic capture/provenance. Missing or late rows are explicitly blocked. Only games where **all three models were eligible before the same kickoff** enter **all three** Brier/log-loss/MAE denominators. Numeric scores have **zero** official model authority or stakes.
2. `elo_baseline_pit.py`: simple independently written **Elo-style** baseline using final scores from an earlier, already observed file. No external downloads or live-state reuse. It outputs home-win probability, a **research-only** margin derived from an uncalibrated 25 Elo-points/point conversion, and a historical-total-average prior. K=20, home advantage=65 Elo points, no offseason regression, no opponent/player injury adjustments. These are **unvalidated defaults** and NOT an exact FiveThirtyEight forecast. A full Elo ablation/fit remains to be done against earlier seasons.
3. Tests (synthetic/offline): matched denominators, no peek after kickoff, source clock and SHA requirements, missing models, duplicate game rejection, tie handling, non-finite predictions, zero official stake, and Elo cutoff, history and reproducibility. The main `tests.yml` calls `models/nfl_dfs/test_item4.py`; the new test-only method invokes both suites without changing workflow files.

## Exact CSV contracts

The **final outcome file** is not used to build forecasts. Only the postgame scorecard reads it. `games.csv`:

```csv
game_id,season,week,home,away,kickoff_utc,final_available_utc,home_score,away_score
SYNTHETIC_G1,2026,11,Alpha,Beta,2026-11-15T18:00:00Z,2026-11-16T00:00:00Z,24,20
```

The **archived pregame forecast file** must include **all three** methods per game, frozen before each kickoff. `forecasts.csv`:

```csv
game_id,model,forecast_utc,source_available_utc,training_cutoff_utc,model_version_sha256,input_sha256,home_margin,total,home_win_prob
SYNTHETIC_G1,ridge,2026-11-15T17:00:00Z,2026-11-15T16:00:00Z,2026-11-14T20:00:00Z,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,4.0,44.0,0.80
SYNTHETIC_G1,elo,2026-11-15T17:00:00Z,2026-11-15T16:00:00Z,2026-11-14T20:00:00Z,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,2.0,40.0,0.60
SYNTHETIC_G1,epa,2026-11-15T17:00:00Z,2026-11-15T16:00:00Z,2026-11-14T20:00:00Z,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,3.0,43.0,0.70
```

All the 64-character `a`/`b` SHA examples are **synthetic placeholders**; a matching shape is not proof of source custody. For real forecasts require verifiable original provider bytes, data availability/publication evidence, run/version hash and timestamped saved predictions. Do not create present-day reconstructions and falsely label them as pregame.

`model` values: `ridge`, `elo`, `epa`. Each (game_id, model) must be unique. `training_cutoff_utc <= source_available_utc <= forecast_utc < kickoff_utc` is mandatory, with aware time offsets, and model/input SHA-256 recorded. Scores use `home_margin = home_points - away_points`; `home_win_prob` must be strictly between 0 and 1. A tied NFL final is blocked from binary win-probability evaluation rather than silently treated as a win/loss.

## Running the evaluator

```bash
python models/nfl/forecast_scorecard_pit.py \
  --games /private/nfl_games_settled.csv \
  --forecasts /private/nfl_frozen_forecasts.csv \
  --out /private/nfl_paired_scorecard_NEW.json
```

Output is **create-only** (no overwrite) and includes:
- total games, paired games, blocked games, per-model pregame eligibility and reason-coded excluded events;
- **same denominator** MAE/RMSE of predicted home margin and game total for the three methods;
- **same denominator** Brier score and logarithmic loss for binary home wins;
- ten 10-percentage-point calibration buckets per model, count and predicted/observed rate;
- `INSUFFICIENT_PAIRED_SAMPLE` if fewer than 100 complete games (change via `--min-paired` for research sensitivity only). Large samples are descriptive and do not automatically authorize a model.

No ROI/CLV results, DK prices, injury adjustment, promotions, EV or bet cards are generated.

## Optional strict Elo-style baseline builder

The `history.csv` is a previously frozen source-archive of **settled games only** with exactly the same columns as `games.csv`; each `final_available_utc` must precede `--source-observed-utc`. The frozen source observation itself must precede **every target forecast timestamp**. If the file contains a game that ended later, the entire archive is rejected rather than pretending its score was available earlier.

`targets.csv`:

```csv
game_id,season,week,home,away,kickoff_utc,forecast_utc
SYNTHETIC_G1,2026,12,Alpha,Beta,2026-11-15T18:00:00Z,2026-11-15T17:00:00Z
```

```bash
python models/nfl/elo_baseline_pit.py \
  --history /private/nfl_predecision_history.csv \
  --targets /private/nfl_future_targets.csv \
  --source-observed-utc 2026-11-15T16:00:00Z \
  --out /private/nfl_elo_forecasts_NEW.csv
```

The example clock is fictional. Outputs are the `elo` rows and `.audit.json` sidecar. A team unseen in history or an insufficient sample stays blocked. No NFL forecast is generated when source availability cannot be verified. This is a **simple baseline**, not a fitted/verified betting model.

## Not done and cannot be claimed

- No authentic nflverse 2010-2026 point-in-time snapshots have been downloaded or certified in this PR. CI regression tests use only invented fixtures; **green tests do not show predictive performance**.
- The current NFL ridge stage does not output scores or probabilities, so ridge and EPA challenger rows must first be **built and frozen separately** using exclusively earlier game data, with training separate from test.
- No true market fair-price Brier comparison until authenticated pregame two-sided odds and consensus/no-vig methodology are provided. This is the next baseline to add after point-in-time custody.
- No confidence intervals, nested model fitting, prospective release, or proof of a profitable edge. These are separate research milestones.
- Keep NFL sides, totals, team totals, props and moneylines blocked/unpriced wherever an independent calibrated model is absent. This PR **never** changes frozen v5.

## Validation and CI

```bash
python -m unittest discover -s models/nfl -p 'test_forecast_scorecard_pit.py' -v
python -m unittest discover -s models/nfl -p 'test_elo_baseline_pit.py' -v
```

After implementation, audit the exact PR head in GitHub Actions and examine the individual test log (not only the aggregate green status). Adopt only after prospective calibration on the same held-out games against market/no-vig and simpler baselines, preregistered before outcomes.
