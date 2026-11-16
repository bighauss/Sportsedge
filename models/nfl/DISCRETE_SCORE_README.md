# NFL point-in-time discrete score distribution R1

**Research only / PAPER_HOLD_0U.** This does not turn a projected score into a verified sportsbook edge. It models a set of possible integer final scores from **paired residuals of earlier, archived pregame predictions**. The 2018–2025 evaluation must still be independently source-attested and preregistered. Do not rebuild old "pregame" forecasts from today's revised data.

## Design

- Each historical row contains **a frozen pregame score forecast** (with observed/freeze/start timestamps, exact event/team IDs and model version SHA), the actual final score, and the original result availability time. All rows must be complete and valid; no missing-data imputation.
- Before projecting a target game, retain only observations with the **same model code/version SHA** where the historical kickoff predates the target's forecast freeze **and the result was available before that freeze**.
- Preserve the paired home/away forecast-error residuals, add each historical residual pair to the target's frozen home/away expected points, clip at zero and round to integer scores. This preserves the empirical joint error structure, including game total and margin dependence, instead of assuming independent home/away errors or a Gaussian spread.
- Use exact empirical frequencies for **home win / NFL tie / away win**, signed home spread cover/push/loss, game total over/push/under and separate team totals. The mass at margins 3 and 7 is **measured**, not hard-coded.
- Require at least 50 earlier matched residual pairs by default; no result or only a no-model status with fewer. This 50-game threshold is an **engineering default**, not an established calibration sample.
- Offer lines are supplied separately using exact event ID and a claimed observed timestamp no later than the forecast. Missing line is **NOT_CAPTURED**, not "not offered." No sportsbook odds, no EV, no units and no claim of authenticated quote data.
- No 1H, 1Q, player props, touchdown/first touchdown, alternate ladders or SGP pricing. They are explicitly **NO_MODEL** rather than silently approximated using full-game residuals.
- NFL ties need a **book-specific** settlement rule: this module reports three-way win/tie/loss frequencies but refuses to decide whether a two-way moneyline pushes on a tie.

### Inputs

Target forecast JSON:

```json
{
  "game_id":"GAME_ID",
  "home_id":"HOME_ID",
  "away_id":"AWAY_ID",
  "kickoff_utc":"2026-12-01T21:00:00Z",
  "forecast_asof_utc":"2026-12-01T18:00:00Z",
  "source_observed_utc":"2026-12-01T17:00:00Z",
  "model_sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "projected_home":24.1,
  "projected_away":21.6
}
```

The example dates and teams are **fictional schema examples**, not statements about real game schedules or evidence.

History JSON: array of objects with **all** of the above target keys plus `final_utc`, `result_available_utc`, `final_home`, `final_away` (nonnegative integer final scores). Use only genuinely archived pregame records; a local SHA does not prove the archive existed before kickoff.

Optional lines JSON (all keys required; use `null` for unavailable lines):

```json
{
  "game_id":"GAME_ID",
  "observed_at_utc":"2026-12-01T17:30:00Z",
  "home_spread":-3.0,
  "game_total":46.5,
  "home_team_total":24.5,
  "away_team_total":21.5
}
```

Home spread is signed **from the home team's perspective**: home -3 means a home win by exactly three is a push. Positive total lines are displayed unchanged (over if actual points > line; under if < line). **This is not a real quote receipt**.

### Run

```sh
python models/nfl/discrete_score_pit.py \
  --target /private/actual_frozen_forecast.json \
  --history /private/past_frozen_forecasts_and_grades.json \
  --lines /private/actual_asof_game_lines.json \
  --out /private/nfl_discrete_paper.json
python -m unittest discover -s models/nfl -p 'test_discrete_score_pit.py' -v
```

The output is create-only, includes local byte hashes and the denominator/exclusion census and always says `PAPER_HOLD_0U`, `approved_stake_u=0`.

## Validation still required

The empirical residual distribution can be *overconfident or miscalibrated*. Period-specific effects, opponents, home/away differences and score ceilings are not learned here. The simulated score grid is not a possession/drive-level football simulation and contains no learned player correlations. Before public probability display or wagering, perform rolling seasons, leave-out future observations, probability scoring/calibration, a market-only fair-probability benchmark, proper exact-line and book-specific push settlement, and timestamp-authenticated original quotes. Explicitly test whether this residual method improves over simple Gaussian, market-only and opponent-aware alternatives. Failure must remain visible. Follow GitHub issue #10 gates A–E for official promotion.
