# SportsEdge independent player-prop joint calibration audit

**Research only — PAPER / 0u. No production model, price, grade, capture, or historical prediction modifications.**

## Verdict — November 20, 2026

Connected historical source review found **zero verifiable event-matched player prop pairs** with BOTH a frozen pregame line-specific individual probability and player-level final grade. Consequently the verified historical co-hit deviations and joint-versus-independence Brier improvements are **not estimable**. Zero qualifying pairs is an evidence-assembly count, not a claim of zero actual correlations or zero historical forecasts.

Source screening: NFL game-level scenario candidate workbook has 152 nonempty rows and no player-specific rows; live canonical `MODEL_OUTPUTS!F2:L5000`, `SHADOW_LEDGER!D2:G5000` and archived `Prop_Candidates` have no eligible player probabilities; actual ledger has seven decided real-money wagers, including two MLB individual props without the corresponding frozen probabilities; NFL week 5–9 retrospective has 2,258 point-forecast records and 1,819 final stat matches, **not** prop-line event probabilities and not verified original-before-kickoff published vintages; NBA Nov 11 136 output rows were `ANCHOR`, not independent probability evidence. Legacy NFL QB team-passing-yard proxy grades are disallowed. Source IDs/details remain in the private research archive; do not publish confidential boards or player-specific receipts.

## Files and usage

- `research/audit/prop_joint_correlation.py`: Python 3 standard-library-only, read-only checker, pair builder and event-cluster bootstrap Brier calculation.
- `research/audit/test_prop_joint_correlation.py`: synthetic tests. Never treat synthetic Brier as real-world calibration.

```bash
python research/audit/prop_joint_correlation.py --self-test
python research/audit/test_prop_joint_correlation.py
python research/audit/prop_joint_correlation.py --predictions /path/to/private/frozen_player_props.csv \
  --joint-predictions /path/to/private/frozen_joint_props.csv --out /path/to/private/audit_outputs
```

`--joint-predictions` optional. Keep private betting records, original quote bytes, user slips, API keys and player-level source receipts **outside the public repo**. All original input CSVs remain untouched. Outputs: `coverage.json`, `excluded.csv`, `pair_rows.csv`, `relationships.csv`.

## Contract and safety controls

`predictions.csv` requires:

`event_id,sport,event_start_utc,snapshot_id,asof_utc,leg_id,player_id,team_id,stat,side,period,line,predicted_p,result,result_source`

Optional `model_mode=PROJECTION|INDEPENDENT_MODEL|FROZEN_PROJECTION` can be specified; ANCHOR and other non-independent modes are rejected. **Caution:** absence of `model_mode` does NOT prove independence; it remains a manual verification obligation. A `result_source` enum is necessary but not evidence of independent provider attestation. Do not certify data merely because a CSV supplies timestamps or a provider name: immutable raw source payloads, original SHA256, upstream publication timestamps, custody trail and exact roster/market identity must be independently checked before a historical validation claim.

Optional `joint_predictions.csv` requires:

`event_id,snapshot_id,leg_id_a,leg_id_b,asof_utc,joint_p`

Both legs must share event and snapshot, decision timestamp must precede real start, player ID+team must bind; duplicate or ragged CSV, conflicting event identity, later forecasts, missing final result, team-stat proxies, nonfinite/invalid probabilities, out-of-bounds joint p and orphaned joint rows are refused or separately counted. First eligible snapshot per unordered same-game market pair is selected, so restated later snapshots do not inflate evidence. Same-player opposite and nested/stat-threshold ladders are classified as structural, not evidence of fitted stochastic covariance. Grouping is by relationship, sport, stat, side and period; cross-player pairs form empirical candidates only.

For each eligible pair: outcome both-win is `y_A*y_B`, independence baseline is `p_A*p_B`. Empirical deviation is `mean(y_A*y_B - p_A*p_B)`; all-pair independence Brier is separate from **matched-subset** independence and frozen joint Brier. Frozen joint p must itself be an original pregame forecast, not retrospectively imputed or tuned. Confidence intervals resample **games/events**, not pairs; small sample `n<30` or `<10` events is explicitly tagged, `n<100` or `<30` events preliminary. Even a confidence interval excluding 0 remains exploratory pending pre-registered multiple-testing control and unseen chronological confirmation.

## Stacked audit-hardening corrections (research candidate)

The evidence guard also rejects a complete event whenever a stable player ID changes teams or the same settled market changes result across pregame snapshots; an earlier valid-looking snapshot does **not** excuse inconsistent later records. Both mismatches are preserved in the refusal census. Nominal event-clustered 95% intervals are deliberately withheld unless at least **30 distinct games** support the particular paired comparison; smaller samples remain exploratory even when a descriptive co-hit or Brier score is computed. These checks do not independently authenticate the provider or retrospectively certify an edge.

## Parallel evidence recovery tracks

- NFL: week-level means are not prop-line probabilities; recover immutable preseason/weekly game time and threshold curves, stable GSIS IDs, individual QB/WR/RB final stats.
- CFB and CBB: locate exact event, player and stat/period IDs; freeze prospectively if no original historical probabilities exist. Never reconstruct original forecasts after finals.
- NBA: roster binding, reported minutes and participation vintage, same-game PTS/AST/REB/PRA exact-player probabilities; quarantine ANCHOR-only rows and traded-player collisions.
- MLB: pitching/hitting player-specific thresholds, true batting order/starting status and genuine pregame probability sources; do not count multigame parlays as same-game correlation.
- Quant validation: compare frozen joint distribution to independent baseline only on identical eligible pairs; inspect marginal calibration and event/game-script dependency; use untouched future blocks, holdout by game/date and report all refused rows.

Coordination: GitHub issue #57; underlying related issues #190, #191, #192, #193, #194, #80 and P0 gate #10. Draft implementation requires independent GitHub code review; tests alone do not grant any source authentication or betting authorization.