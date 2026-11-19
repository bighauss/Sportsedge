# CBB availability efficiency modifier — preregistered shadow candidate (2026-11-18)

**Owner authorization:** fit and research-test availability modifier. **Not authorized:** model adoption, price release, official bets, retroactive feature repair, historical card overwrites. Frozen v5 remains unchanged. A–E OPEN; PAPER/0u.

## Hypothesis / treatment
Starting from an **independently frozen Torvik no-market score projection** and registered event/venue, the pregame *expected* unavailable team minutes can explain scoring residuals. An OUT status with a previously frozen planned-minute estimate contributes lost minutes. ACTIVE contributes zero. QUESTIONABLE/DOUBTFUL/PROBABLE/UNKNOWN never receive arbitrary 0.25/0.5 probabilities; those events are blocked until separately fitted participation models exist.

For each side, independently adjust projected offensive efficiency in points per 100 possessions by two TRAIN-estimated coefficients:

`delta_points = possessions / 100 * (beta_own * own_OUT_minutes / 200 + beta_opp * opponent_OUT_minutes / 200)`

The no-absence case is exactly the old Torvik forecast. No sportsbook odds, spread, implied winner, total or close enters the fit. Outputs are **diagnostic score scenarios only**.

## Required private data
One record per event with unique event/team/player IDs; Torvik frozen score, possessions, archive hash, publication/capture times; official conference availability original receipt hashes, player statuses, pregame planned minutes and per-player as-of times; verified venue; confirmed event final and postgame publication/capture time. Exact schema is enforced in the Python file. Six-conference eligibility is a policy allowlist supplied to the runner; names are **not inferred**. An allowlist, SHA, or `venue_verified` boolean is a claimed internal receipt, not independent external authentication. Missing official reports, missing full census, unresolved player states, after-freeze publications, duplicate IDs or unknown conference are excluded and disclosed.

## Precommitted evaluation
- Fit cutoff is frozen as a UTC command argument **before viewing holdout**. Training outcomes must have been captured before this cutoff. A partial historical game whose final is unavailable at the cutoff is excluded, not retrospectively added.
- Holdout contains only prospective forecasts frozen after cutoff; minimum release path 100 training events and 50 untouched holdout events.
- Ridge options are fixed `0.01,0.1,1,10,100`; select within chronological earlier 80%/later 20% training split, requiring earlier finals published before validation forecasting. Refit selected candidate on full eligible training only.
- Report paired holdout point MAE/RMSE vs no-modifier Torvik, venue slices, all rejected input rows and source hash. **No market-close baseline or probabilities are assessed by this script.** Those are mandatory later independent evaluations on identical games and conditional families; this script alone cannot pass Gate C or establish +EV.
- Prohibit production integration and prop pricing. Further support requires strict per-market posterior calibration, event-cluster intervals, full original provider authenticities and separately reviewed candidate adoption.

## Running (private archive outside public checkout)
```bash
python research/audit/cbb_availability_shadow_fit.py /private/cbb_availability_events.json \
  --conferences 'VERIFIED_CONF_1,VERIFIED_CONF_2' \
  --cutoff-utc 2026-11-18T00:00:00Z \
  --report /private/new_shadow_fit_result.json
```

The example conference tokens are placeholders, **not** admission claims or certified conferences. Fitted results are create-only and remain outside public GitHub. If adequate PIT originals are unavailable, the honest result is `INSUFFICIENT_PIT_TRAIN_OR_UNTOUCHED_HOLDOUT`. No coefficients or backtest edge may be invented.

Issue #323; separate freeze PR #321; original-receipt Gate A PR #314.