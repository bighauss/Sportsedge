# SportsEdge CFB RUN IT model (2026-11-15, Claude)

Files: `sportsedge_cfb_model.py` (model, stdlib only), `test_cfb_model.py` (end-to-end test, network off),
`make_samples.py` (writes the synthetic sample inputs), `samples/` (synthetic data, fake numbers, real CFBD field names).

Run: `python3 make_samples.py && python3 test_cfb_model.py`, or `python3 sportsedge_cfb_model.py samples/inputs.json out/`
-> `out/cfb_card.csv` and `out/cfb_card.md`. `inputs.json` maps input names to file paths (CSV or JSON).
All weights are UNTESTED starting values (see constants at the top of the .py).

## Method (same as the NFL RUN IT standard)
- Team points = 50% existing ratings model (offense.rating / defense.rating) + 50% advanced-stats matchup.
- Matchup: EPA(PPA)/play split rush/pass weighted by pass rate, plus success rate, explosiveness, havoc,
  points per scoring opportunity, field position. Each stat regressed to league mean with k = 6 games.
- Early season: talent composite + returning production shift the regression anchor, fading linearly to zero at week 6.
- Adjustments: QB out -5.5 (clamped -4 to -7, `impact` column overrides), star skill -1.5, OL starter -0.75,
  2+ DBs out = opponent +1.5; home field 2.5 by default (per-stadium 1.5-4 from venues file), neutral 0;
  away team 2+ time zones -0.5; short week (<6 days) -0.5; altitude 5000 ft+ home +1.0;
  weather only when `isForecast` is true and the roof is open: wind 15+ mph = -2 total, heavy rain -2, snow -3.
- Tempo: the average of both teams' plays/game sets the play count, so it drives the total.
- Pricing (Normal): margin SD 15.5, total SD 15, team total SD 11, 1H = 0.5 x full game with SD 11.
  Markets: ML, spread, total, both team totals, 1H spread, 1H total.
- EV: raw = p*decimal-1; blend uses p_blend = 0.30*model + 0.70*no-vig market. Ranked by blended EV, stars
  5/4/3/2/1 at >=8/5/3/1.5/>0 %, FIRE marker on 4-5 stars.
- Props: usage share x team volume (plays x pass/rush rate, small game-script nudge) x efficiency x opponent
  rush/pass PPA factor; mean blended 70% model / 30% market-implied mean (line shifted by the no-vig over probability).
- Filter: drops unders whose line is below the projection and overs whose line is above it. Same-signal stacks
  (same game + same team side, or same game + points up/down) are flagged `STACK xN`.
- SP+/FPI/Sasser/Corbie go in `crosscheck` and are only displayed, never used in the projection.

## Free data: collegefootballdata.com (CFBD)
Key: go to https://collegefootballdata.com/key, enter an email, and the free key is emailed to you
(free tier has a monthly call limit). Send it as the header `Authorization: Bearer YOUR_KEY`.
Base URL: `https://api.collegefootballdata.com`. On a phone, save the JSON responses
(e.g. with the free API explorer at https://apinext.collegefootballdata.com) and point `inputs.json` at them.

| Input | Endpoint |
|---|---|
| games | `GET /games?year=2026&week=12&seasonType=regular&classification=fbs` |
| advanced | `GET /stats/season/advanced?year=2026&excludeGarbageTime=true` |
| talent | `GET /talent?year=2026` |
| returning | `GET /player/returning?year=2026` |
| ratings (stand-in) | `GET /ratings/sp?year=2026` (also `/ratings/fpi`, `/ratings/elo`) |
| lines | `GET /lines?year=2026&week=12` (spread, overUnder, homeMoneyline, awayMoneyline) |
| teams | `GET /teams/fbs?year=2026` (location.timezone, location.elevation) |
| venues | `GET /venues` (elevation) + your own hfa column |
| weather | `GET /games/weather?year=2026&week=12` (Patreon tier on CFBD; otherwise a free forecast source with windSpeed, precipitation_type, isForecast=true) |
| usage | `GET /stats/player/season?year=2026` or cfbfastR play-by-play -> shares |
| plays (optional) | `GET /plays?year=2026&week=N` / cfbfastR for custom splits |

Things CFBD does not give free: prices for team totals, 1H, and props (add them from your sportsbook as the flat
columns listed in the .py docstring), injuries (manual file), and days of rest (derive from the schedule).
Field names are listed in the module docstring; CSV inputs use dotted headers such as `offense.rushingPlays.ppa`.
