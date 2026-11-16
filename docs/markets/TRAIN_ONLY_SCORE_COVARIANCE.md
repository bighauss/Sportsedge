# Training-only joint score-error covariance → team-total simulations

**Research-only** enhancement to the five-sport score scenario generator.
Previously, the generator independently sampled regulation total-score error
and score-margin error. That is a **zero-correlation assumption**, not an
established sporting fact. For home/away team totals, the relationship matters:
home score is approximately (total + margin) / 2, away is (total − margin) / 2.

## Data source and exact fit

The existing `sportsedge/markets/score_dispersion_fit.py` accepts a PRIVATE
source ledger of 50+ **original** frozen pregame forecast/final pairs across at
least seven dates, all from the same model SHA; checks original file SHA, prior
feature/forecast/model fit clocks, postevent final publish/capture clocks,
duplicate event identity and complete original denominator; refuses one bad
record rather than dropping losing results.

This change also estimates **Pearson rho** from *paired* margin and total
residuals on those identical original training games. Correlation is returned
only when the historical sample passes all existing fail-closed checks and
|rho| is strictly below 0.999. Zero variance, perfect positive or negative
correlation, future leaked inputs and invalid rows cannot silently produce
new covariance assumptions. No separate optimizer or market prices enter.

The report now exposes:
- `margin_total_residual_correlation` (value or null when BLOCK);
- `correlation_status: TRAIN_ONLY_RESEARCH_NOT_FORWARD_CALIBRATED`;
- unchanged `fitter_model_sha256`, private raw bytes SHA, fit cutoff and
  original accepted/blocked counts;
- unchanged `approved_stake_u=0`, `release_gate_cleared=false`.

These operator-provided historical timestamp claims and checksum strings are
**not independently authenticated**. Proper release still requires actual
provider receipts, reproducible forward holdouts, full offered-book inventory,
no-vig benchmarks, exact CLV and independent gate acceptance.

## Simulator and output

For a score-only Gaussian scenario, let `z1,z2` be independent standard-normal
random variables:

```text
total = projected_total + sd_total * z1
margin = projected_margin + sd_margin * (rho*z1 + sqrt(1-rho²)*z2)
home = (total + margin)/2
away = (total - margin)/2
```

The integer/nonnegative score guards and period allocation remain in force.
In particular, this is not an estimated joint player prop/TD/SGP dependence
model and does not model overtime or extra innings. The score clipping at
zero changes exact empirical dependence from the latent rho, so
`margin_total_correlation` should never be described as the guaranteed
realized-score correlation.

The original `DistributionInput` default remains **rho=0**, preserving
the previous RNG-draw path byte-for-byte when no actual training fit is
provided. `scenario_spec_sha256` binds the fitted correlation and exact
generator implementation to every simulation and downstream research
disagreement.

The existing private CLI optional `dispersion_fit_ref` now derives and uses
both score residual SDs **and** their paired rho from the same frozen
historical source. No user-entered `margin_total_correlation` is allowed on
that source-fit path. Legacy manually entered widths retain rho=0 and are
clearly marked:

```text
margin_total_correlation_used
margin_total_correlation_source
  = TRAIN_ONLY_SAME_GAME_RESIDUALS_UNCALIBRATED
    | LEGACY_ZERO_ASSUMPTION_UNCALIBRATED
margin_total_correlation_forward_calibrated = false
```

The fitted values are not promoted to an official pricing configuration.
All risk, cards and current 0u release holds remain unchanged.

## Tests / nonpromotion

The new `test_score_covariance_fit.py` tests independent manual Pearson
recomputation from identical prior originals, source tampering, late finals,
perfectly correlated degenerate residuals, invalid correlation parameters,
legacy zero replay, changed source/code fingerprints, simulated positive and
negative dependence, derived home-team total sensitivity, no manual override
on source-fit path and the unchanged 0u research runner.

```sh
python -m unittest -v \
  sportsedge.markets.test_score_covariance_fit \
  sportsedge.markets.test_score_dispersion_fit \
  sportsedge.markets.test_period_share_fit \
  sportsedge.markets.test_scenario_lineage \
  sportsedge.markets.test_cli \
  sportsedge.markets.test_edge_discovery
```

After genuine source access, fit on earlier games and measure **untouched
future** team-total and full-game probability Brier/log loss/coverage, full
original offered price denominator, same-market opening/taken/closing lines
and calibration against market-only baselines. Keep model-only, market-only
and preregistered blends separate; no fixed 30/70 blend is certified here.

Frozen `sportsedge_v5.py`, historical picks, risk and settlement unchanged.
