# G5–G8 — standalone SportsEdge portfolio correlation and stress auditor

**Research only. PAPER / 0u. No changes to the production engine, model weights, selection rules, prior predictions, or settlement history.**

This code fills a distinct gap alongside the existing PR lanes: #79 (as-of feature dates), #75 (TAKE/CLOSE receipt archive), #68 (independently verified settlement/CLV), #71 (G2/G3 calibration), #74 (NFL walk-forward), and #78 (duplicate top-edge intake). It is **not** a replacement for any of them. A price/hash/provider/timestamp field supplied by a caller is only a *claim*: no evidence is authenticated by local checks. Never put source snapshots, betting receipts, or private ledger data in public GitHub.

## Usage

```bash
cd research/risk
python -m unittest test_portfolio_stress_audit -v
python portfolio_stress_audit.py /private/complete_frozen_ledger.csv \
  --output /private/NEW_stress_report.json --bootstrap 2000
```

The result path is create-only. The input CSV should be an externally frozen, complete **one-row-per-original-qualifying-selection** historical ledger. It must contain the following required columns:

`bet_id,event_id,sport,market_key,market,direction,model_version,rules_version,model_sha256,rules_sha256,universe_sha256,universe_complete_claim,quote_sha256,rules_effective_utc,model_asof_utc,quote_observed_utc,quote_captured_utc,selected_utc,kickoff_utc,book,price_american,stake_units,stake_basis,evaluation_split,result,settled_utc,settlement_source_a,settlement_source_b`

Optional: `player_id,quarterback_id,theme_id,commission_rate`.

- All timestamps must include a UTC offset; `selected_day_ct` is derived using the **America/Chicago** timezone, including daylight saving transitions.
- `market_key` MUST be the exact canonical *sport / event date / participants / period / market / selection / line / player identity*. These semantics require an independent upstream identity check; this script only compares keys, not provider catalog identities. Alternate lines are not arbitrarily collapsed into one market.
- `universe_complete_claim=TRUE`, `evaluation_split=OOS`, original pregame rule/model times, quote observed/captured before the selection/kickoff, non-stale original American prices, and SHA256-formatted IDs are required. Claims are not proof of genuinely complete prospective selection logs.
- `stake_basis=PAPER_FLAT` or `EXECUTED_CLAIM`, both explicitly NOT externally authenticated. Multiple stake bases in the same file are **never pooled** into one ROI/variance/bootstrapped return; performance is reported separately by basis.
- `result=WIN|LOSS|PUSH|VOID|PENDING`. Settled results need two distinct *claimed* settlement source IDs, and a final timestamp after kickoff. Those IDs are not authenticated merely because their strings differ. No `LIKELY WIN`, inferred player stats, missing finals, or altered bets are silently accepted.
- Returns use original recorded odds with fixed units risked; winner-only commission is optional and applied to winning profit. `PUSH` is a zero-return selection that counts in the risked-units denominator; `VOID` is zero return and does **not** count in that denominator; `PENDING` stays in the population and is excluded from realized returns until settled.

Provider event IDs may repeat between sports. Game clustering and exposure use the namespaced identity `(sport, event_id)`; report keys use `SPORT:event_id`, never a bare provider ID.

## Output interpretation

1. All rejected rows are preserved with indexed reasons; **all duplicate IDs and duplicate canonical selections are rejected** regardless of source order.
2. Reports separate sport, model/rules version, market, direction, selected month, player and theme; counts of *distinct settled events* are crucial when interpreting many same-game alt lines.
3. `event_stake_units`, CT decision-day stakes, overlapping themes, and the exposure-concentration proxy are descriptive, not a numerical covariance estimate or a statistically valid effective sample size.
4. The **game bootstrap** resamples each whole game together so same-game selections are never treated as independent. The additional **connected-theme bootstrap** joins events that explicitly share `theme_id`, limiting spurious certainty when a risk theme spans multiple games. Both refuse CIs for fewer than 30 distinct settled nonvoid games/blocks. Even with 30 blocks, resampling assumes sufficient stationarity/exchangeability; a return CI excluding zero is **not** proof of model skill.
5. The empirical sample variance is of per-game **net unit totals** (not bet-level returns or an inferred covariance matrix). Drawdown is a deterministic hypothetical settlement-order series, **not** a real staking/exposure chronology. Bootstrap drawdown remains highly path-dependent.
6. The payout haircuts (0%, 5%, 10%) represent *deliberately degraded winnings* for sensitivity. They are NOT executable price forecasts, sportsbook vig verification, book-limit analysis, or valid CLV substitutes.
7. `resample_fraction_roi_nonpositive` is only a descriptive bootstrap stability statistic—**not** a null-hypothesis p-value or the probability the model's genuine edge is zero.

## Remaining release blockers

- Original private raw quotes and independently attested pregame observation times; a local hash string alone proves nothing about source origin or prior availability.
- A frozen manifest proving all candidates and losses were retained, all qualifying rules preregistered, and each card's model SHA matches the prediction-producing code.
- The actual original settlement feed, original complete odds board and exact line/period/player mapping, with true provider lineage; no retrospectively inferred results.
- At least 30 independent *settled, nonvoid* game/theme blocks to report provisional bootstrap intervals, and substantially more truly forward games for durability claims.
- Real execution limits, commissions, slippage, near-close price availability and cross-book independent comparisons; no promotion based on this auditor.

**Run only in a restricted workspace with synthetic tests or private verified inputs. The output always says `PAPER_STRUCTURAL_RESEARCH_NOT_PROVIDER_AUTHENTICATED`.**