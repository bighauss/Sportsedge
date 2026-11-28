# Backtest harness: model vs no-vig market, with selection-bias control

PAPER research only. Any lane can feed it one CSV of **pregame-captured** priced selections.

`event_id,date,market,selection,line,model_p,push_p,price,opp_price,outcome[,close_price,close_opp_price]`
- `model_p`: model P(win), unconditional. `push_p`: model P(push), 0 on half-point lines.
- `price` / `opp_price`: DraftKings American odds for this side and the opposite side.
- `outcome`: W / L / P / V. Voids are dropped and counted.
- Malformed rows are rejected and counted by reason. Duplicate (event, market, selection, line) rows are refused.

Run: `python research/backtest_harness/harness.py rows.csv --k 20 --block event`

## Reports
| Output | Meaning |
|---|---|
| `model`, `market_novig` | Brier, log loss and ECE on decided rows. Model is conditioned on no push. |
| `paired_*_model_minus_market` | Per-row loss difference with a **block bootstrap** 95% CI. Blocks are events (or dates), so same-game selections are not treated as independent. Negative = model better. |
| `flat_stake_ev_gt_threshold` | Flat 1u ROI, units and max drawdown for EV > threshold (push returns the stake). |
| `clv_diagnostic` | Mean EV at the no-vig close. A diagnostic only, not proof of profit. |
| `selection_bias` | Shuffles `model_p` within each market (zero true edge, same EV spread), takes the top-k by EV, and repeats 500×. Reports observed top-k EV **net of the null's expected fake edge**, plus realized ROI vs the null with a p-value. |
| `power` | Intra-block correlation, design effect, effective n and **minimum detectable ROI** (α .05 two-sided, power .80). |

## Real data in the repo (Nov 28 2026): none qualifies
- `research/claude_nfl_20261114/claude_20261115_model_probability_only_PUBLIC.csv`: 152 NFL model
  probabilities. **No DK prices, no opposite-side prices, no outcomes**, and timestamps are
  `FILE_NAME_NOT_PROVIDER_AUTHENTICATED`.
- `ledger/seed_2026-11-15.csv`: 17 graded plays with prices. **No model_p, no opposite-side
  prices**, and props were graded from team totals.

To run the harness on real data, the RUN IT path must save every priced selection *before
kickoff* (model_p, push_p, both DK sides, capture time) and the grader must later add the outcome
from box scores. Without that log, no model-vs-market claim can be made.
