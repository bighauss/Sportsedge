# CBB player residual bundle (research only)

Use the public-replay runner with `--adapters fullgame,halves,players --player-bundle /private/player-bundle.json` plus the existing slate, board, cache and other adapter flags. The bundle is hashed into the frozen output. This is not a provider capture or a validated model.

Schema: `CBB_PLAYER_RESIDUAL_BUNDLE_V1`.
- targets: array of event_id, team_id, player_id, tip_utc, frozen_utc, means (PTS, REB, AST, 3PM), model_version.
- history: array of forecast (same shape), observed_final_utc, actual (same four integer stats), participated (boolean).
- IDs use the same provider namespace as the slate; no fuzzy name joins.
- Quote CSV must carry player_id, player_team_id, dk_event_id, both prices and explicit totals_order (over_under/under_over or yes_no). Provider crosswalk and quote provenance must be independently checked; IDs in a CSV alone are not authentication.
- At least 20 same-player, same-team, same-model prior residual vectors are required. No assumed timestamps or variance. DNP excluded; conditional-on-participation estimates remain unvalidated. Do not use a same-game result as history.
- Exact ESPN player finals now support conditional W/L/push diagnostics for positive-minute participants; matching event/team/score and player identity required. Box hashes recorded. Missing, duplicate, DNP and mismatched rows withheld. No sportsbook settlement or player ROI until contract/DNP rules verified. Conditional calibration reported separately. Half score grading is paper only, with tied half ML and H2 withheld. No CLV claims without a matching pre-tip close.

No current player forecasts, residual corpus, availability feed or authenticated quote data are included. This is a research integration interface, not a claim that current slate props are ready.


## Generate matchup-aware research forecasts

`python models/cbb/cbb_player_matchup_forecast.py --finals /private/observed-finals.json --targets /private/roster-candidates.json --out /private/player-bundle.json`

Finals input: array of event_id, home_id, away_id, tip_utc, observed_final_utc, possessions, team_stats keyed by team ID (PTS/REB/AST/3PM), players (team_id, player_id, minutes, stats). Use only genuine observation timestamps and verified event/team/player crosswalks; never derive an observation time from tip. Targets: event_id, team_id, player_id, opponent_id, tip_utc, frozen_utc. Candidates are not confirmed active players.

The fixed research challenger uses the latest ten eligible appearances (minimum five), player minutes and per-minute production, recent team pace, and opponent per-possession allowed rates shrunk toward the prior league average. This is an unvalidated heuristic, not a fitted opponent-specific usage model. Historical forecast cutoffs are reconstructed just before tip and clearly labeled CHRONOLOGICAL_REPLAY_NOT_PROSPECTIVE; only earlier observed finals enter each forecast. Metrics include paired MAE, RMSE and bias against recent-player averages for all eight stat families. Do not select model parameters on the reported evaluation set.

Inputs are hashed. Replay may be slow on a full multi-season corpus; minimum twenty same-team/player/version residuals for pricing can leave many players unpriced. No real-data run or validated improvement is asserted. Existing cached box scores without actual observation receipts cannot demonstrate historical availability; collect timestamped sources rather than backdating.


## Native runner integration and real-board replay

The frozen native card supports opt-in research extensions via
`--pipeline-out <output> --pipeline-adapters halves,players --pipeline-halves-path <models/cbb> --pipeline-player-bundle <json>`.
The native player bundle must explicitly declare `identity_namespace: "CBBD"`.
No cross-provider identity mapping is inferred. This label alone does not
authenticate the bundle, verify current participation, or authorize a wager.
The native overlay verifies the parent card digest and zero-stake status,
preserves the input hashes, and labels its output research rather than prospective.

The CBB real-board retrospective pipeline workflow pins the Nov 25 DK board
revision 2899f92c16b268ab5f7522ed14a7323cbddfeb4d and halves revision
d6ccd412993f1e7000cd8ffd28f35337bb29e659. It requests public ESPN inputs,
reconstructs the 17:25Z freeze, verifies the paper policy and active half
adapter, and retains summary and audit artifacts only. It does not use CBBD
secrets, touch the ledger, or supply a player bundle that does not exist.
The team-total holds, missing player prices, unknown availability, and
retrospective input timing remain visible. A successful hosted job is an
integration replay, not a genuine live slate run or proof of market edge.
