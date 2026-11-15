# DFS Item 4: Point-in-time NFL inputs and historical Showdown replay

Claimed by ChatGPT in issue #56. RESEARCH / PAPER only. This change does not
modify the accepted Showdown simulator, the PIT-CIN game JSON or owner lineups.

## Capture contract

Archive before kickoff:

- PBP CSV exported from nflreadpy.load_pbp([season]); the source loader in
  sportsedge/data/loaders.py can also obtain nflverse PBP.
- A roster CSV with columns player_name,team,gsis_id,position (explicit
  GSIS-to-DK full-name binding; no fuzzy IDs). Every QB/RB/WR/TE in the
  template must have an ID.
- Template Showdown game JSON with market, injury, weather, kickers and DST
  assumptions still supplied from authenticated, separately recorded sources.
- Optional NGS receiving CSV (coverage diagnostics only, not a scoring boost).

Create an input_manifest.json in the same folder, like this example
(the timestamps are illustrative and not evidence of an actual snapshot):

    {
      "kickoff_utc": "2026-11-16T01:20:00Z",
      "game_date_local": "2026-11-15",
      "template": {"path": "template.json", "sha256": "ACTUAL_SHA256",
                   "captured_at_utc": "2026-11-15T17:00:00Z"},
      "pbp": {"path": "pbp.csv", "sha256": "ACTUAL_SHA256",
              "captured_at_utc": "2026-11-15T17:00:00Z"},
      "roster": {"path": "roster.csv", "sha256": "ACTUAL_SHA256",
                 "captured_at_utc": "2026-11-15T17:00:00Z"}
    }

Hashes must be accurate lowercase hexadecimal SHA256 values. Files must
exist and match, paths must stay inside the snapshot directory, and capture
times must precede kickoff. The explicitly supplied local game date (not UTC date, since US night games
can start the following UTC day) prevents a same-game lookahead bug.
The PBP for target teams must not include the
target game or later matches.

## Build research inputs

    python models/nfl_dfs/build_game_inputs.py path/to/input_manifest.json --lookback 5 --min-games 3 --out path/to/auto_RESEARCH.json

The builder averages attempts, interceptions and touchdown rates across
prior regular-season games, extracts player target/carry shares and estimated
catch/yardage efficiencies, shrinks catch and rush estimates toward observed
team baselines, and writes transparent source/coverage metadata. It leaves
unverified market/weather/injuries/FG accuracy/DST parameters unchanged.
It never writes the official game inputs automatically and NEVER consumes
DK AvgPointsPerGame or provider fantasy-point scoring.

NGS weekly rows may exclude lower-usage players and are currently recorded
for identity and coverage diagnostics only. Adding an NGS-to-points multiplier
requires independently calibrated forward evidence.

## Historical replay and grading

Archive a JSON object containing a non-empty slates array. Each slate has
tag, kickoff_utc, config, salaries, results and engine. The first three files
are objects with path, sha256 and captured_at_utc. Config and DK salaries
must be pre-kickoff, results must be postgame. The results CSV requires all
fields in backtest_showdown.RESULT_HEADER and an explicit player row even
when actual production is zero. Engine has sha256 of the actual
showdown_mc.py bytes and a capture time before kickoff.

    python models/nfl_dfs/backtest_showdown.py path/to/archive.json --sims 20000 --seed 7 --out path/to/grades.json

The default refuses replay if exact model SHA and pregame model timestamp
are absent. A non-as-of reconstruction is allowed only with the explicit
--allow-reconstruction flag and is labelled NOT_FORWARD_TEST.

Metrics: player MAE/RMSE; actual scores for mean-ranked and top simulated
shortlist-opt-rate lineups; regret relative ONLY to the filtered shortlist.
No real ownership, field, contest rank, paid entry, prize or ROI claims.

## Testing

    python models/nfl_dfs/test_item4.py
    python models/nfl_dfs/test_showdown_mc.py
    python models/nfl_dfs/test_public_nfl_gamelogs.py

These tests use synthetic examples, not a verified historical slate corpus.
The item remains PAPER until real snapshots and out-of-sample evidence exist.
