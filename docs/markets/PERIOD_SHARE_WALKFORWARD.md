# Period-share walk-forward evaluation — research only

This module evaluates whether SportsEdge's **empirical regulation-period
scoring proportions**, fitted from earlier games, forecast scoring timing
better than a fixed uniform-per-period baseline on games held out in time.
It does not test the sport's full score/prop projection, joint scoring
dependence, or any bookmaker expected value.

## What is new

`sportsedge/markets/period_share_walkforward.py` loads a PRIVATE original
JSONL ledger in the same strict format accepted by
`sportsedge/markets/period_share_fit.py` (see
[Train-only period shares](TRAIN_ONLY_PERIOD_SHARES.md)).

- Validates **every** original input row and retains the total denominator.
  Malformed/duplicate/corrupt/unsettled/future-final rows BLOCK the entire
  report. The one full-ledger fit executed for input validation is NEVER used
  as a prediction.
- Sorts games by exact regulation start time and leaves **all events with the
  same start time in the same holdout cohort**.
- At each holdout start, selects training **only** from events that started
  earlier AND whose final score was captured strictly before that start.
  A result published late cannot influence earlier folds even if the game
  itself occurred first.
- Reconstructs the training subset using the exact saved JSONL row bytes
  (not a re-encoded future-enriched projection), and reruns the existing
  original train-only fitter at each fold. Previous holdout events may
  enter the next training fold only after their results have arrived.
- Requires a minimum of 50 prior events across seven dates, at least
  20 held-out games per fold and at least three chronological folds before
  returning its descriptive research review state. Incomplete remaining
  cohorts are counted as `short_tail_games_not_scored`, not used to tune.
- Returns training sample counts, last available final timestamp, original
  training subset SHA, fitted model SHA, observed holdout period scoring
  points, and any games where regulation total scoring was zero.
- Uses **per-scoring-point negative log probability** of the period in
  which scoring occurred as a descriptive metric:
  `-sum_i observed_period_points_i * log(train_period_share_i) / total_points`.
  Compares this with the **fixed uniform** baseline `log(number_of_periods)`.
  Negative `model_minus_uniform_logloss` means better on the held-out data.
  Zero-point games are retained in the original and holdout denominators;
  they contribute no scoring points to the log-loss numerator or denominator.
- This is an aggregate scoring-timing diagnostic, **not** statistically
  independent Bernoulli trials; its log loss is not a calibrated outcome
  probability or a measure of successful betting decisions.

## Supported periods

| Sport | Original and evaluated regulation periods |
| --- | --- |
| NFL, CFB, NBA | Q1, Q2, Q3, Q4 |
| Men's CBB | **H1 and H2 only**; quarter bets remain unsupported |
| MLB | I1–I9; regulation scores only, not extra innings |

Original score and result receipts must separate overtime/extra innings
from regulation, and every period reconciles exactly to each game's
original regulation score. No period is filled with an invented projection.

## Private CLI

```sh
python -m sportsedge.markets.period_share_walkforward \
  --input /private/original_regulation_periods.jsonl \
  --out /private/period_share_heldout_report.json \
  --sport CBB \
  --evaluation-asof-utc 2026-11-16T04:00:00Z
```

The original ledger must have captured finals **before** the evaluation
cutoff; the cutoff cannot be a future date, and the output file is
create-only. Keep original licensed data, event IDs and scores outside the
public repository. Only sanitized fold diagnostics are emitted.

Tests (all **synthetic**, no external source account or live pricing):
```sh
python -m unittest -v \
 sportsedge.markets.test_period_share_walkforward \
 sportsedge.markets.test_period_share_fit \
 sportsedge.markets.test_score_dispersion_fit \
 sportsedge.markets.test_scenario_lineage \
 sportsedge.markets.test_cli
```

## Acceptance boundaries

A green synthetic test, positive out-of-sample period log-loss improvement
over uniform, and a self-reported original score SHA do **not** independently
prove publication timestamps or source authenticity. They also do not validate
uncertainty tails, score-event correlation, injury/lineup adjustments,
full-game or prop odds, authentic DK and second-book price availability,
no-vig CLV, return on investment, or profitability.

Any decision about model adoption must pre-register the selection criteria,
verify external timestamps and original source rights, evaluate authentic
forward point-in-time games, compare against market-only baselines when
original prices exist, and separately clear A–E risk/release gates.
This module NEVER updates `sportsedge_v5.py`, periods, fitted weights,
RUN IT cards or original historical records. All markets remain PAPER / 0u.
