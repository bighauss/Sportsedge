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
