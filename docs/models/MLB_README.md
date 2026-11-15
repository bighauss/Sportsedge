# SportsEdge MLB RUN IT model — README (2026-11-15, Claude)

Files: `sportsedge_mlb_model.py` (model), `test_sportsedge_mlb_model.py` (end-to-end test),
`sample_inputs/*.csv` (synthetic data — fake players, fake odds; for testing only).

Run: `python3 sportsedge_mlb_model.py <folder_with_csvs>` -> writes `mlb_card.csv` and `mlb_card.md`
into that folder. Test: `python3 test_sportsedge_mlb_model.py`. Standard library only.
(Isaac is phone-only: run it in any free Python environment, e.g. a free Colab notebook
or GitHub Actions on the bighauss account — upload the CSVs and the .py.)

**ALL WEIGHTS ARE UNTESTED STARTING VALUES** (dict `W` at the top of the module). Not backtested.

## Method (same as NFL RUN IT standard)
1. Team runs = 50% existing ratings model (`away_rating_runs`/`home_rating_runs` in games.csv)
   + 50% advanced-stats matchup. All stats regressed to league mean with k = 60 games
   (batters: PA / 4.1 = games; pitchers: BF / 22 = games).
2. Matchup: lineup xwOBA vs today's starter (batter xwOBA by pitch type weighted by starter's
   pitch usage, platoon split regressed at 400 PA, barrel%/hard-hit%/bat speed nudges),
   weighted by PA per slot 4.6 -> 3.8. Starter quality = xERA blended with K%-BB% and CSW%,
   velo-trend and times-through-order penalties; starter share = IP/start; bullpen = xFIP
   + fatigue (pitches last 3 days over 120).
3. Adjustments: park factor by handedness, temp +1% runs per 10F above 70 (open roof only),
   wind out/in 0.7%/mph, altitude excess, umpire runs/game, opponent OAA + catcher framing,
   rest (0 days) and time-zone travel.
4. Pricing: negative binomial per team (var = 1.6 x mean) -> ML (extra-inning ties split 52/48
   home), run line, total, team totals, F5 ML/total, NRFI/YRFI (1st-inning NB, var ratio 2.2).
5. Props: pitcher Ks = BF x log5(pitcher K%, lineup K%) x whiff adj (binomial); outs; batter
   hits / TB / HR from regressed BA/ISO/HR rate x matchup x park. Model mean blended 70/30 with
   market-implied mean (solved from no-vig over price).
6. EV: raw = model_p x dec - 1; blended p = 0.30 model_p + 0.70 no-vig p. Ranked by blended EV,
   stars 5/4/3/2/1 at >=8/5/3/1.5/0%. Flames on 4-5 star plays.
7. Filter: drop unders with line below projection, overs with line above projection.
   Same-signal stacks (e.g. game over + YRFI + batter overs in one game) flagged `STACK xN`.

## Free data sources & export steps (column names the loader expects are in the module docstring)
- **Pitchers (Statcast)** — https://baseballsavant.mlb.com/leaderboard/custom?type=pitcher
  Pick columns xera, xwoba, k_percent, bb_percent, csw (or whiff_percent), p_throws; click
  "Download CSV". Pitch mix / whiff by pitch: https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats
  (type=pitcher) and https://baseballsavant.mlb.com/leaderboard/pitch-arsenals (usage %) — pivot to
  `usage_FF`, `whiff_FF` ... columns. Velo trend: player page "Velocity" tab or
  https://baseballsavant.mlb.com/statcast_search (game logs, last 3 starts).
- **Batters (Statcast)** — https://baseballsavant.mlb.com/leaderboard/custom?type=batter
  (xwoba, xslg, barrel_batted_rate, hard_hit_percent, k_percent, pa). Bat speed:
  https://baseballsavant.mlb.com/leaderboard/bat-tracking . xwOBA vs pitch type:
  https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats?type=batter (pivot to `xwoba_FF`...).
  Platoon splits: Statcast Search filtered by pitcher hand, or FanGraphs splits
  https://www.fangraphs.com/leaders/splits-leaderboards (Export Data).
- **Bullpen / BF per start / GS** — FanGraphs leaders https://www.fangraphs.com/leaders/major-league
  (Pitching, split Relievers / Starters, "Export Data"). Bullpen pitches last 3 days: MLB StatsAPI
  boxscores https://statsapi.mlb.com/api/v1/game/{gamePk}/boxscore (sum pitchesThrown of relievers).
- **Schedule, probable starters, confirmed lineups, umpires** — MLB StatsAPI (free JSON):
  https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,lineups,officials
- **Park factors by handedness** — https://baseballsavant.mlb.com/leaderboard/statcast-park-factors
  (set Bat Side L, then R; download CSV).
- **OAA / catcher framing** — https://baseballsavant.mlb.com/leaderboard/outs_above_average (team view)
  and https://baseballsavant.mlb.com/catcher_framing . Download CSV, sum to team.
- **Umpire run impact** — https://umpscorecards.com (umpires page; use runs/game "favor"/total impact).
- **Weather** — https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&temperature_unit=fahrenheit&wind_speed_unit=mph
  (free, no key). Convert wind direction to out/in/cross using park orientation.
- **Odds** — copy from the sportsbook app into odds.csv / prop_odds.csv (American odds), or the
  free tier of https://the-odds-api.com (500 requests/month).

## Honest limitations
- Weights/constants are untested guesses; no backtest or calibration yet; synthetic sample only.
- Teams' run distributions are independent (no correlation); ML tie split is a constant.
- F5 and first-inning are run-share scalings, not an inning-by-inning simulation.
- K prop uses fixed BF (binomial), which understates variance from early hooks; outs uses a
  normal approximation. Hits/TB assume a constant 8.5% walk rate.
- Pitch-type matchup ignores count/location; leash and TTO use only BF/start.
- Wind direction requires manual out/in/cross; "pace" has no real MLB equivalent (not modeled).
