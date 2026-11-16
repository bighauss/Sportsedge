# NFL point-in-time score conversion R1

**Research only — every output is PAPER_HOLD_0U.** This module is stacked on the EPA-Ridge point-in-time feature builder in PR #121. It must not be merged or relied upon independently of the required source feature module.

## What this does

Learn the map from offensive EPA and opposing defense-allowed EPA (passing and rushing, 4 real features per team) to scored points. A six-parameter ridge regression fits one intercept, four learned EPA weights and a fitted home indicator. It uses **only prior games whose results were available before the target's frozen forecast**. There is no hard-coded EPA-to-points multiplier, QB/weather adjustment, market price, margin simulation or stake.

The output reports projected *research-only* team scores and margins, plus walk-forward MAE and RMSE against a simple historical home/away mean points baseline. This baseline is **NOT** a sportsbook comparison. No probabilistic win/cover/over bets are priced.

The supplied snapshots and their timestamps are caller assertions. To claim genuine historical pregame predictions, an independent archive must prove the bytes and source publication time were available before each forecast cutoff. Downloading today and backdating `forecast_asof_utc` is prohibited.

## Exact-ID EPA snapshot adapter

Use `feature_snapshot_bridge_pit.py` to turn a saved upstream EPA ratings JSON into score-model CSV features without fuzzy team lookup or silently inserted zeros. Provide a JSON **list** of events with `game_id`, `home_team`, `away_team`, `kickoff_utc` and `forecast_asof_utc` using exact IDs from the rating source. The adapter requires the rating source observation, rating calculation and event freeze all to precede kickoff; one rating artifact can populate only games for which all four offensive/defense feature families exist.

```sh
python models/nfl/feature_snapshot_bridge_pit.py \
  --ratings /private/nfl_epa_ratings_paper.json \
  --events /private/verified_matchups.json \
  --out /private/archived_nfl_pregame_features.csv

python -m unittest discover -s models/nfl -p 'test_feature_snapshot_bridge_pit.py' -v
```

The adapter computes the local rating-artifact SHA256 and writes a *new* CSV. It cannot authenticate claimed archive dates and is **not** an invitation to backdate a present-day rating artifact. Store the artifact and input events with independent observation receipts before kickoff.

## Exact input schemas

`--features` CSV: exactly one row per real game, captured before that game's kickoff, with **these exact columns and no odds/results**:

```text
game_id,home_team,away_team,kickoff_utc,forecast_asof_utc,source_observed_utc,epa_ratings_sha256,home_off_pass,home_def_allow_pass,home_off_rush,home_def_allow_rush,away_off_pass,away_def_allow_pass,away_off_rush,away_def_allow_rush
```

- UTC timestamps must be offset-aware; `source_observed_utc <= forecast_asof_utc < kickoff_utc`.
- `epa_ratings_sha256` is a 64-hex SHA256 digest of the actual *archived EPA rating artifact* (as `sha256:<64hex>`), not an API key and not proof of publication.
- `off` fields use offensive EPA above average; `def_allow` fields are opponent defense-allowed EPA above average. Do **not** reverse the defense sign.
- The upstream PBP builder's research `units.pass.offense_above_average_epa`, `units.rush.offense_above_average_epa`, etc. can populate these fields **only from a truly saved as-of rating snapshot**. A current snapshot cannot represent earlier games.

`--results` CSV: one row per game, including every prior training game and optionally later games to grade:

```text
game_id,home_score,away_score,final_utc,result_available_utc
```

- The result's `final_utc > kickoff_utc` and `result_available_utc >= final_utc`. Verify availability from a trustworthy provider.
- The target's own result is only used **after prediction** for evaluation. For game G, the training universe contains ONLY games H where H kicked off before G's freeze and the H result was already available at G's freeze.

## Example

```sh
python models/nfl/score_walkforward_pit.py \
  --features /private/authenticated_nfl_pregame_features.csv \
  --results /private/authenticated_nfl_results.csv \
  --out /private/nfl_score_walkforward_paper.json \
  --min-train-games 32 \
  --ridge 25

python -m unittest discover -s models/nfl -p 'test_score_walkforward_pit.py' -v
```

The default sample threshold 32 games and ridge 25 are **unvalidated engineering settings**. For an honest 2018–2025 comparison, choose hyperparameters using nested earlier seasons, freeze them, then score held-out years. Report errors per season, bootstrap confidence intervals by game/week, and compare against a saved contemporaneous no-vig market baseline *only when real two-sided pregame quote receipts exist*.

Output is create-only; input CSV hashes are preserved in the audit report. No original game scores, captures, odds or engine v5 code are modified.

## Next feature gate

- Validate date-specific player/QB availability, lineup states, rest/travel, historical weather forecasts and possession pace with independent source records.
- Add game-correlated residuals and final-score **distributions**; learn push masses at exact numbers (3/7) from historical samples rather than treating margins as continuous.
- Evaluate probabilities by NFL market and settlement convention: ML, spread, total, team total, 1H, 1Q, props and touchdowns are **separate** models.
- Compare against genuine pregame, market-only no-vig and matched closing quote baselines. Keep no-provenance/unsupported markets in the all-market inventory.
- No official +EV, stars, units, or production promotion without authenticated point-in-time data and walk-forward acceptance.
