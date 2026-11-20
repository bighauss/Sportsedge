# NFL / CFB / CBB independent player-stat mean builder (research only)

**Status: PAPER / 0u.** Source publication claims, player identity, rate quality, variance fitting and current sportsbook availability are not independently certified. This module is a **working deterministic projection transformation**, not proof that the real pregame source capture/validation loop is running. It does not touch frozen v5 or historical forecasts.

Implementation: `sportsedge/markets/player_projection_builder.py`  
Tests: `sportsedge/markets/test_player_projection_builder.py`

## What it does

Receives privately archived point-in-time feature data with **two independently estimated inputs per player/stat**: projected opportunities and previously fitted production **per opportunity**, plus a separately trained standard deviation. It computes `expected_stat = opportunities × rate_per_opportunity`, keeps all rejects in a census, and writes a forecast CSV in the format already consumed by `player_forecast_intake.py`. There are **no bookmaker or no-vig fields** in this projection source.

| Sport | Supported independent opportunity recipes |
| --- | --- |
| NFL and CFB | Passing yards/completions/passing TD/INT per pass attempt; pass attempts per team dropback; rushing yards/rushing TD per individual rush; rush attempts per team rushing play; receiving yards/receptions/receiving TD per player target; targets per team pass attempt |
| CBB | Points, rebounds, assists, made threes, steals, blocks, turnovers per projected minute |

A usage estimate (targets, attempts, minutes) and a per-unit efficiency rate must each be **actually derived from earlier data**. The builder cannot verify that upstream derivation. A supplied SD is not automatically validated. Missing/unsupported formulas (e.g. NFL longest reception; CBB PRA, double-double, triple-double) are listed as `NO_INDEPENDENT_STAT_RECIPE`, not silently filled or priced. Rushing and receiving volume minimums follow existing `PlayerMoment.validate` research guards.

## Private input contract (illustrative synthetic values, NOT real player data)

```json
{
  "schema": "sportsedge-three-sport-player-opportunities-v1",
  "sport": "CBB",
  "event_id": "SYNTHETIC-1",
  "home_id": "HOME",
  "away_id": "AWAY",
  "event_start_utc": "2026-11-21T18:00:00+00:00",
  "forecast_asof_utc": "2026-11-21T17:00:00+00:00",
  "trained_until_utc": "2026-11-18T17:00:00+00:00",
  "source_published_utc": "2026-11-20T11:00:00+00:00",
  "source_captured_utc": "2026-11-20T12:00:00+00:00",
  "source_snapshot_sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "source_id": "CBB_HOOPR",
  "frozen_roster": {"PLAYER-1": "HOME"},
  "players": [
    {
      "player_id": "PLAYER-1",
      "team_id": "HOME",
      "stat": "POINTS",
      "opportunity_unit": "MINUTES",
      "opportunities": 30,
      "rate_per_opportunity": 0.5,
      "standard_deviation": 5,
      "confirmed_active": true
    }
  ]
}
```

Save a real, permissioned, authenticated input outside the public repository and run:

```sh
python -m sportsedge.markets.player_projection_builder \
  /private/event_features.json \
  /private/event_player_forecasts.csv \
  /private/event_player_census.json
```

Both outputs must be new, private paths; they are **create-only**. The census includes rejected rows, exact forecast-file SHA256 and model-code SHA256. The builder refuses duplicate JSON fields, invalid/future clocks, unmatched roster identities, bookmaker-derived/extra fields, nonfinite values and unconfirmed athletes.

Pass the resulting CSV into an existing per-event RUN IT research manifest as:

```json
"player_file": {
  "path": "/private/event_player_forecasts.csv",
  "raw_sha256": "<census.file_sha256>",
  "odds_observed_at_utc": "<actual independent sportsbook observation UTC>"
}
```

The parent manifest must also include exactly matching roster IDs, home/away team IDs, and a matching frozen team projection. The existing intake will reject inconsistent source/file hashes, identities, volume and timestamps. Player-stat distributions generated downstream are still provisional Gaussian sketches; the CSV alone does **not** establish calibrated conditional or joint prop probabilities.

## Remaining work for Issue #341 completion

1. Automated permitted PIT feeds and independently audited pregame player/team/volume/rate/source observations for **every game**, including availability, player participation and exact publication times.
2. Data-trained, unseen-game-validated opportunity and rate estimators, player-level dispersion and joint team/player covariance; preregistered baselines and calibration comparisons per sport/stat.
3. Connect this player output to the complete event-by-event RUN IT scheduling/market census. Every offered player prop absent from the producer must be visibly `NO_MODEL`/`NO_DATA`, not silently skipped.
4. Independently authenticate original DK quotes, exact side/line/settlement and source chain; close hard gates A–E separately before any real-money output.

Do not report this research capability as full live projection coverage or independently proven +EV.

## Direct RUN IT research integration (optional private feature reference)

The `sportsedge.markets.cli` runner may now accept a **single** `player_features_ref` for NFL, CFB or CBB directly alongside the genuine team `projection_ref`. It does not need an intermediate player CSV or manual data copy. It refuses use alongside `player_file` and refuses fallback to a caller-invented team projection. It verifies exact sport, event, home/away IDs, roster-ID census, team forecast freeze time, source-file byte SHA256 and pregame quote observation time before passing an in-memory CSV through the existing intake and score/player simulation.

Example **fragment** in an event research manifest, alongside a real `projection_ref`, two-sided market receipts, `distribution`, `roster_ids` and `markets`:

```json
"player_features_ref": {
  "path": "/private/observed_nfl_event_player_features.json",
  "raw_sha256": "sha256:<actual full original file digest>",
  "odds_observed_at_utc": "<actual UTC pregame original sportsbook observation>"
}
```

The `player_features_ref` file must follow the synthetic schema illustrated above but contain **real** source-frozen, independent opportunities/rates/SDs rather than illustrative numbers. Only NFL, CFB, CBB are supported by this direct route. CBB and CFB team models use their point-in-time frozen feature manifests; NFL uses the reconstructed opponent-adjusted rating forecast source. Mixed-feature identity, missing freeze evidence, lookahead, poststart quotes and unsigned/mismatched file hashes are rejected. No bookmaker lines are used to estimate a player mean.

Every research report exposes `player_projection_producer` and `player_projection_builder_census`, including the submitted/produced/blocked quantities. Full-slate outputs retain the same per-event census. This describes **code-path readiness only**. The separate independently authenticated market-family matrix and A–E evidence requirements remain unsatisfied without actual original pregame receipts and forward calibration.

Integration tests are synthetic for all three sports:
`python -m unittest sportsedge.markets.test_player_features_run_it -v`.
