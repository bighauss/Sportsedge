# Train-only regulation-period scoring shares → SportsEdge research simulations

This optional research adapter replaces hand-entered **period allocation shares**
with aggregate regulation-period proportions from earlier permitted original
score breakdowns. It does **not** fit full-game score means/variances, validate
period-specific variance or correlation, authenticate historical source
timestamps, produce real +EV or release any betting market. Every candidate
remains **PAPER / 0u**.

## Sport support — do not fabricate a period

| Sport | Current simulator source periods | Train-only period fitting |
|---|---|---|
| NFL | Q1–Q4, **regulation only**, no modeled OT | YES, observed quarters |
| CFB | Q1–Q4, **regulation only**, no modeled OT | YES, observed quarters |
| NBA | Q1–Q4, **regulation only**, no modeled OT | YES, observed quarters |
| MLB | I1–I9, **regulation only**, no modeled extra innings | YES, observed innings; include zero-home-runs in unplayed bottom-ninth as score 0 |
| CBB men | Actual game uses **two 20-minute halves**, H1/H2 | YES, observed official H1/H2 halves; never invent 1Q–4Q markets |

The model now supports **native two-half CBB scenarios** when a prior
H1/H2 source passes the research-only fitter. First-half/second-half
settlement uses actual H1/H2 keys; first-quarter/second-quarter markets
are explicitly rejected for NCAA men's CBB. For backwards compatibility,
four synthetic CBB bins are still accepted only in the **legacy uncalibrated
research path**. They are NOT actual game quarters; do not use them as proof
of first-half calibration or as a substitute for H1/H2 originals.

## Input (private, exact source key contract)

`period_share_fit.py` reads one JSON object per line; every row is retained.
Required fields and their interpretation:

- `sport` is **NFL/CFB/CBB/NBA/MLB**; `event_id` is stable and unique;
- `game_start_utc`, `final_published_utc`, `final_captured_utc`
  must be explicit UTC Z timestamps in that order and final capture must
  precede the **fit cutoff**;
- `source_original_sha256` is a claimed hash of the original final score
  source (not independently authenticated);
- `settlement_scope` is exactly `REGULATION_ONLY`;
- `periods` contains Q1–Q4, H1/H2 (men's CBB), or I1–I9, each an array of
  **[home points, away points]** (integer, nonnegative). No `OT`,
  `EXTRA` or imputed missing periods;
- `regulation_home`, `regulation_away` are exact summed *regulation*
  results; both must match all period score components. Full-game
  extra-time totals may not be substituted.

A **synthetic** NFL training row (not proof of any historic data):

```json
{
  "sport":"NFL","event_id":"SYNTHETIC-EXAMPLE-1",
  "game_start_utc":"2026-10-04T17:00:00Z",
  "final_published_utc":"2026-10-04T20:20:00Z",
  "final_captured_utc":"2026-10-04T20:25:00Z",
  "source_original_sha256":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "settlement_scope":"REGULATION_ONLY",
  "periods":{"Q1":[7,3],"Q2":[7,10],"Q3":[3,7],"Q4":[7,3]},
  "regulation_home":24,"regulation_away":23
}
```

An actual original receipt SHA and independently confirmed provider
publication/capture evidence is still necessary for Gate B. A valid-looking
JSONL or SHA value is **not** that proof.

## Training process

For every accepted event, sum home and away **regulation-only** points in
each period, then set period-share = period points divided by all period
points across training events. Zero total score or a period receiving zero
points across the entire training sample is rejected, rather than
backfilled with an invented period prior.

The fitter accepts only a ledger with:
- ≥50 prior regulation results from ≥7 different event dates;
- Every final published and captured **before** the fit cutoff;
- Unique event identity after whitespace/case normalization; duplicates
  quarantine **every** copy, not just the second;
- All original rows present, correctly typed and period-to-regulation
  reconciled. Even one malformed, missing, duplicate or late row makes
  the **entire** fit unusable for RUN IT.
- A source-file byte digest, a separate deterministic fitter code+parameters
  hash, and explicit blocked-row counts/reasons.

This is a **pooled count proportion**, not a conditional period distribution.
It does not account for first-half game state, possession, starting pitcher,
home batting opportunities, drive-specific interactions, point clustering,
overtime, or correlation between periods and total points. It must be
walk-forward evaluated separately before any claim of period accuracy.

## Private standalone use

```sh
python -m sportsedge.markets.period_share_fit \
  --input /private/original_regulation_periods.jsonl \
  --sport NFL \
  --fit-asof-utc 2026-11-15T18:00:00Z \
  --out /private/nfl_period_fit_20261115.json
```

Input and output **must be outside the public repo**. Output is exclusive
create-only. Actual licensed source results, tokens, player IDs, team roster
and private archive data must not be published.

## RUN IT integration

The five-sport research CLI now accepts optional `period_fit_ref`:

```json
{
  "period_fit_ref": {
    "path": "/private/original_regulation_periods.jsonl",
    "raw_sha256": "sha256:REPLACE_WITH_64_HEX_DIGITS",
    "fit_asof_utc": "2026-11-15T18:00:00Z"
  }
}
```

That reference is one field within an existing full research manifest.
Keep `projection` or `projection_ref`, `markets`, original quote receipts
and a source-supported `distribution`. With `period_fit_ref`:

- Provide `distribution.sport` and `distribution.status`, plus
  `sd_margin`, `sd_total`, `model_sha256`, `training_end_utc` if **not**
  using `dispersion_fit_ref`. With a score fit, the latter four fields
  are derived from the score-ledger fit.
- **Omit** `distribution.period_shares`; manually overriding the fitted
  period weights in the same run is an error.
- The original period-data file SHA is verified before parsing; the
  training set is recomputed and must report zero blocked rows and ≥50
  prior results across ≥7 days; fit cutoff must strictly precede the
  projected event's frozen as-of date.
- The actual train-only shares and **period fitter model SHA** enter
  `DistributionInput`, then the full `scenario_spec_sha256` fingerprint.
  Changing the period source therefore changes the simulated scenario
  provenance even if the final ratios happen to be numerically equal.

RUN IT reports `period_fit_status`, `period_fit_accepted_n`,
`period_fit_source_sha256`, `period_fit_model_sha256`, and still marks
`period_share_calibration_verified=false`, `official_counted=0`,
`approved_stake_u=0`, `card=null`.

## Next validation

A pre-registered unseen sample, stratified by sport/market and with
period-specific payout/settlement handling, must demonstrate performance
against a market-only and simple timing baseline. Period shares alone do
not certify period-score variance, first-half splits, player-period props,
NRFI/YRFI or +EV; genuine DK and second-original-book receipts remain
unconnected. All per-market Gates A–E remain OPEN.

Run offline regression suite:

```sh
python -m unittest -v sportsedge.markets.test_period_share_fit \
  sportsedge.markets.test_score_dispersion_fit \
  sportsedge.markets.test_scenario_lineage \
  sportsedge.markets.test_edge_discovery \
  sportsedge.markets.test_cli
```
