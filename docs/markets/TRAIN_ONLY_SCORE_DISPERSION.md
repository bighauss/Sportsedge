# SportsEdge train-only score residual fitting

This adds an **optional** source-locked score variance fit to the existing
five-sport `sportsedge.markets.cli` research pricer. It does **not** train
team-score predictions, calibrate prop tails, fit quarter shares, authenticate
sportsbook prices, make betting recommendations, or enable official staking.

## Why this is necessary

Earlier `DistributionInput.sd_margin` and `sd_total` were operator-entered
guess widths. A model can produce plausible point means while using wrong
variance; then its spread, total and moneyline probabilities (and supposed
edge) will be wrong.

The new `score_dispersion_fit.py` estimates sample residual standard
deviation separately for margin and total, from fully completed **earlier**
games only:

- Margin residual = (actual home − actual away) − (predicted home − predicted away).
- Total residual = (actual home + actual away) − (predicted home + predicted away).
- Use sample SD after all source/forecast/result clock checks.
- Do not use bookmaker lines, final scores after fit cutoff, or the current
  game's score to fit its own probability distribution.
- No automatic hyperparameter tuning or selection of best-looking historical
  wins; every input record is counted, and any invalid or missing row causes
  the entire fit to BLOCK rather than silently disappear.

A fit is usable **for PAPER research only** when it has at least 50 distinct
event records across at least 7 different start dates, all from one exact
forecast model SHA, zero rejected rows, original file bytes SHA check, strictly
pre-cutoff final publication/capture, and statistically non-degenerate
residual widths. These are structural prerequisites, **not** strong proof of
calibration or profitability.

The user-supplied timestamps, original record hashes and model hashes are
still just operator-asserted source metadata until an independent upstream
chain is captured and verified. Fit outcome remains
`TRAIN_ONLY_WIDTHS_READY_RESEARCH_NOT_CALIBRATED`. A genuine scored
unseen holdout and same-event bettor price comparisons remain necessary.

## Private original training data (JSONL)

One row per historical original pregame forecast and final receipt, strict
keys only; every timestamp is UTC `YYYY-MM-DDTHH:MM:SSZ`:

```json
{
  "sport": "CBB",
  "event_id": "EXAMPLE_GAME_1",
  "start_utc": "2026-10-05T20:00:00Z",
  "forecast_asof_utc": "2026-10-05T17:00:00Z",
  "model_trained_until_utc": "2026-10-04T20:00:00Z",
  "features_published_utc": "2026-10-05T15:00:00Z",
  "features_captured_utc": "2026-10-05T15:15:00Z",
  "final_published_utc": "2026-10-06T01:00:00Z",
  "final_captured_utc": "2026-10-06T01:10:00Z",
  "projection_home": 75.5,
  "projection_away": 69.2,
  "final_home": 78,
  "final_away": 71,
  "model_sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "feature_sha256": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "forecast_sha256": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "final_sha256": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
}
```

This example is **synthetic, not an authenticated historic capture**.

Never place actual original receipts or licensed records on public GitHub.
Only use private, permitted data. Standard Python CLI creates an exclusive,
non-overwriting private fit report:

```sh
python -m sportsedge.markets.score_dispersion_fit \
  --input /private/frozen_scores.jsonl \
  --sport CBB \
  --cutoff-utc 2026-11-15T19:00:00Z \
  --out /private/cbb_score_fit.json
```

The report includes exact source SHA, fitter code/spec SHA, accepted/rejected
sample counts and reason codes, unique date count, one training model hash and
sample SDs if structurally clean. It contains no raw event names or final scores.

## Wire into RUN IT

To use a **previously completed** valid training ledger directly during
RUN IT, keep the normal frozen `projection` or `projection_ref`, exact
DK two-sided `markets` and `simulation_count` in the private input manifest.
Replace the old manually entered score widths with this explicit
`distribution` and `dispersion_fit_ref`:

```json
{
  "distribution": {
    "sport": "CBB",
    "period_shares": [0.25, 0.25, 0.25, 0.25],
    "status": "UNCALIBRATED_RESEARCH"
  },
  "dispersion_fit_ref": {
    "path": "/private/frozen_scores.jsonl",
    "raw_sha256": "sha256:REPLACE_WITH_REAL_64_CHARACTER_HEX_DIGEST",
    "fit_asof_utc": "2026-11-15T19:00:00Z"
  }
}
```

This excerpt belongs within an event manifest, not as a complete runnable
manifest. `fit_asof_utc` MUST precede the projected game's pregame freeze;
all included original finals must have been published and captured even
earlier; and the training row `model_sha256` must match the new projection's
`model_sha256`. The sample period shares are a **placeholder only** and must
not be mistaken for a calibrated temporal score profile. You must provide
an independent, defensible period-share training provenance separately.

The runner requires the original file digest to match, recomputes the fit
from original private bytes, refuses changed/late/duplicate/mixed-model or
missing records, then feeds only the fitted `sd_margin`, `sd_total`,
fitter code+data hash and fit time into the existing `DistributionInput`.
The normal `distribution` path remains for legacy uncalibrated research.

Each output is tagged with:
- `dispersion_fit_status`: research-only or not trained;
- `dispersion_fit_accepted_n`, `dispersion_fit_source_sha256`, and
  `dispersion_fit_model_sha256`;
- `period_share_calibration_verified: false`;
- Existing exact `scenario_spec_sha256` and `edge_signal` lineage;
- **`approved_stake_u:0`, `official_counted:0`, `card:null`.**

No values are automatically adopted as official parameters. Source-to-price
verification, walk-forward holdout score calibration, market-only benchmarks,
independent book origination, CLV and Gate A–E release remain blocked.

## Regression tests

```sh
python -m unittest -v sportsedge.markets.test_score_dispersion_fit \
  sportsedge.markets.test_edge_discovery \
  sportsedge.markets.test_scenario_lineage \
  sportsedge.markets.test_cli
```

The tests include synthetic late finals, later captured injury/features,
lookahead model fit, mixed model hashes, duplicate all-copies rejection,
missing receipts, nonfinite/malformed/duplicate-key JSON, sample dates,
source SHA tampering, fake manual widths and cross-model reuse.
