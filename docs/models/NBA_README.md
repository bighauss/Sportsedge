# SportsEdge NBA RUN IT model (2026-11-15, Claude)

Files: `sportsedge_nba_model.py` (model, stdlib only), `test_sportsedge_nba_model.py` (end-to-end test),
`sample/*.csv` (synthetic inputs, NOT real stats or odds).
Run: `python3 test_sportsedge_nba_model.py` or `python3 sportsedge_nba_model.py sample out` -> `out/nba_card.csv` + `out/nba_card.md`.
Column specs for every CSV are in the docstring at the top of the .py. ALL WEIGHTS ARE UNTESTED STARTING VALUES (all at the top of the .py).

## Method (mirrors the NFL RUN IT standard)
- Team efficiency: ORtg/DRtg/pace regressed to league mean (k = 20 games), then 60% season / 40% last 15.
- Stats points = (own ORtg + opp DRtg - league) / 100 x avg pace + four-factor matchup edge (capped +-3).
- Margin = 50% existing ratings model (`rating` column) + 50% stats margin.
- Adjustments: home court +2.0; injuries = on/off net x minutes share x pace x (1 - 40% replacement) x status prob
  (OUT 1, DOUBTFUL .75, QUESTIONABLE .40, PROBABLE .10); B2B home -1.5 / road -2.5; 3-in-4 -1.0;
  away at DEN/UTA -1.0; time zones -0.3/h beyond 1h (cap -1.0).
- Pricing (normal): margin SD 12.5, total 18, team total 11; 1H mean 0.49x (SD x0.71), 1Q 0.245x (SD x0.50). Whole-number lines get push probability.
- EV raw = p x dec - 1 (push-aware); p_blend = 0.30 model + 0.70 no-vig; ranked by blended EV, stars 5/4/3/2/1 at >=6/4/2.5/1/0%, FIRE on top 3 with 4+ stars. Only blended EV > 0 kept.
- Props: minutes (injured minutes redistributed 60% same position / 40% team, cap 40; starters cut 3%/pt of |spread| over 10, cap 15%) x per-minute rate x usage bump x opp positional factor x pace; mean blended 70% model / 30% market-implied mean.
- Filter drops overs with line above projection and unders with line below. `stack` flags picks sharing one signal (same team side, or same game over/under direction).

## Free data sources and export steps (phone-friendly: copy tables into Google Sheets, File > Download > CSV)
| CSV | Source | Steps |
|---|---|---|
| teams.csv ortg/drtg/pace | https://www.nba.com/stats/teams/advanced | Season = current, Season Type = Regular; copy OFFRTG, DEFRTG, PACE, GP. For `_l15` set "Last N Games = 15". |
| teams.csv four factors | https://www.nba.com/stats/teams/four-factors (offense) and https://www.nba.com/stats/teams/opponent (defense) | eFG%, TOV%, OREB%, FTA RATE; opponent page for opp_*. Convert % to decimals. Alternate: https://www.basketball-reference.com/leagues/NBA_2027.html ("Advanced Stats" table has both, Share & Export > Get table as CSV). |
| teams.csv rating | existing SportsEdge ratings model (or basketball-reference SRS column on the same page) | points vs average, neutral court |
| games.csv | https://www.nba.com/schedule ; rest flags from https://www.basketball-reference.com/leagues/NBA_2027_games.html | mark b2b / 3-in-4 by date; tz shift = hours between team home zone and venue |
| injuries.csv | Official report: https://official.nba.com/nba-injury-report-2026-27-season/ (PDF, updated through the day) | status per player; minutes = season MPG |
| injuries.csv on_off_net | https://www.pbpstats.com/on-off/nba/player or https://www.basketball-reference.com/leagues/NBA_2027_play-by-play.html ("On-Off" net per 100) | |
| players.csv | https://www.nba.com/stats/players/traditional (Per Mode = Per Minute... use "Per 36" and divide by 36) and https://www.nba.com/stats/players/advanced (USG%) | confirmed starters: https://www.nba.com/players/todays-lineups or team socials ~30 min before tip |
| positional_defense.csv | https://www.nba.com/stats/teams/opponent-shooting / build from basketball-reference "Opponent" tables; free DvP pages (e.g. https://www.fantasypros.com/daily-fantasy/nba/fanduel-defense-vs-position.php) | factor = allowed / league avg for that position |
| odds.csv, props.csv | sportsbook app lines (copy manually) or free tier of https://the-odds-api.com (500 req/month) | American prices |

Note: the 2026-27 season year in basketball-reference URLs is `NBA_2027`.

## Honest limitations
- No real data was used; the sample is synthetic and only tests code paths. Nothing is backtested or calibrated.
- Four-factor scale (40 pts per unit edge), injury replacement 40%, status probabilities, usage bump (50% of lost usage), prop SDs, segment ratios (1Q = 0.245) and star cutoffs are guesses.
- Normal approximation for props (3PM/AST are discrete, skewed); no player correlation for PRA beyond summing means.
- Minutes redistribution needs the FULL rotation in players.csv; a thin roster (like the sample) piles minutes onto few players.
- Weather/roof do not apply in the NBA; travel is approximated via time zone + altitude only (no mileage).
- Raw EV against model-only p will look huge when the model disagrees with market; trust blended EV.
- Drive/phone: the code cannot run on an iPhone directly; it needs any Python 3 runner (e.g. a free online Python, or the Claude/ChatGPT code tools).
