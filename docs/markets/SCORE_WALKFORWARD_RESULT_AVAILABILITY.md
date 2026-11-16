# Gate C score residual walk-forward — original-final availability hardening

This fixes a real historical leakage risk in the older
`sportsedge/markets/chronological_calibration.py` scorer. Previously a game
was eligible for training solely because its kickoff occurred before the next
holdout's first kickoff. Its **final result might not have been published or
captured until after that holdout started**, introducing unavailable outcomes
into the estimated margin/total residual SD. That can make out-of-sample
probability scoring look better than it was prospectively.

The existing `FrozenGame` now requires:
- Frozen pregame source/model fit timestamps strictly before that game's
  kickoff, same as before.
- `final_published_utc` strictly **after** event start.
- `final_captured_utc` at or after original publication and not in the
  future. Neither is optional for a valid research audit.
- Exact historical-event identity, forecast SHA, nonnegative scores.

The scorer constructs each fold's training set using BOTH conditions:
`training_game.start_at_utc < fold_start` AND
`training_game.final_captured_utc < fold_start`.
A final captured at the exact fold boundary is too late. Each holdout contains
whole equal-start event cohorts. Earlier holdout results can enter later
training only **after the actual result capture timestamp** has passed.

Each fold reports the latest training-final capture time (strictly earlier
than the first holdout), sample counts, estimated residual SD, score errors
and descriptive probability Brier/logloss. The report retains the original
input-game census, pre-eligibility seed count, scored holdout count, and
unscored short-tail count.

This module is RESEARCH ONLY. Its error-derived Gaussian probabilities are
not independently calibrated, and its hashes/timestamps are self-declared
until original provider receipts are separately witnessed. No genuine
authenticated price, same-line baseline, actual ROI or CLV is supplied.

Tests:

```sh
python -m unittest -v sportsedge.markets.test_chronological_calibration
```

The tests supply synthetic immutable pregame/final clocks, deliberately
late-published scores, same-start cohorts, bad/missing finals, duplicate
event aliases and too-few-fold conditions. No historical prediction,
locked v5 engine, original card, model weights, risk policy, settlement or
live betting access is altered. All markets remain **PAPER / 0u** until
original data provenance and Gates A–E are independently certified.

See `docs/markets/PERIOD_SHARE_WALKFORWARD.md` for the parallel
regulation-quarter/half/inning timing audit and Issue #10 for release gates.
