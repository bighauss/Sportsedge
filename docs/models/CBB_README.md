# SportsEdge CBB "Run It" Model (2026-11-15) — all weights are UNTESTED starting values

Free data only: barttorvik.com (T-Rank). KenPom is paid and is NOT used.
The Nov 2026 games are in the **2027** barttorvik season (season = year the season ends).

## Free barttorvik URLs
- Team table (adj eff, tempo, four factors, 3P): https://barttorvik.com/2027_team_results.csv  (JSON: https://barttorvik.com/2027_team_results.json)
  Column headers of this CSV have changed over the years. Check the header row, then rename to the names below (the loader already accepts adjoe/adjde/adj_t, efg%/efgd%, tor/tord, orb/drb, ftr/ftrd, 3pr, 3p%/3pd%).
- Interactive table with four factors: https://barttorvik.com/trank.php?year=2027  (page has a CSV/export link; add `&csv=1` to try a direct download)
- Preseason priors: https://barttorvik.com/trank.php?year=2027&begin=20261101&end=20261101  (or the preseason projections page); save adjoe/adjde/adj_t as pre_adjoe/pre_adjde/pre_adj_t
- Players: https://barttorvik.com/getadvstats.php?year=2027&csv=1 (no header row; map columns to player, team, mpg (Min%×40/100 if needed), usg, and compute pts40/reb40/ast40/tpm40 = per-game × 40 / mpg)
- Schedule/results backup: https://www.sports-reference.com/cbb/ (Share & Export → Get table as CSV)
- Injuries: team sites / beat reporters (no free structured feed); type into injuries.csv by hand.

## Phone export steps (no computer)
1. Open the CSV URL in Safari → Share → Save to Files (or open in Google Sheets app via Drive upload).
2. In Google Sheets, rename headers to the schema below, File → Download → CSV.
3. Put teams.csv, players.csv, games.csv, injuries.csv, odds.csv, props.csv in one folder; run `python3 sportsedge_cbb_model.py <folder> <outdir>` (needs any Python runner, e.g. a free Colab notebook or a Claude session).

## Input schemas
- teams.csv: team, games, adjoe, adjde, adj_t, efg_o, efg_d, tov_o, tov_d, orb_o, orb_d, ftr_o, ftr_d, three_pa_rate, three_p_o, three_p_d, [pre_adjoe, pre_adjde, pre_adj_t, venue_hca, altitude]  (percent stats as 0-100)
- players.csv: player, team, mpg, usg, pts40, reb40, ast40, tpm40
- games.csv: game_id, home, away, neutral, away_tz_diff, away_b2b, home_b2b
- injuries.csv: team, player, status(out/doubtful/questionable), role(top2/rotation; blank = auto by usage rank)
- odds.csv: game_id, market(ml/spread/total/team_total_home/team_total_away/h1_total/h1_spread), side(home/away/over/under), line (spread from the side's view), price_american, opp_price_american
- props.csv: game_id, player, stat(pts/reb/ast/tpm), line, over_price, under_price

## Method
- Team pts = poss × (0.5 × ratings PPP [AdjO×AdjD/lg] + 0.5 × matchup PPP [four factors + 3PA-rate × 3P% vs opp 3P D; stats regressed to league mean k=12, 3P% k=30]).
- Poss = tempoH × tempoA / league tempo (67.5). Early season: current blended with preseason prior, fully faded at 12 games.
- Adjustments: HCA 3.0 default (venue 2–4.5), neutral 0; altitude bonus (BYU, Utah, Colorado, Air Force, Wyoming, New Mexico, Utah St., Colorado St., Denver, Nevada, Weber St.); travel 2+ TZ or road b2b −0.75; top-2 usage out −3, rotation −0.75 (doubtful ×0.6, questionable ×0.25).
- Pricing (normal): margin SD 11, total SD 11 × sqrt(poss/67.5), team total SD 8, 1H total = 0.47 × total SD 8, 1H spread SD 6.8.
- EV: raw = p×dec−1; blend p = 0.30 model + 0.70 no-vig market. Ranked by blend EV, only +EV kept. Stars: ≥8%=5, ≥5%=4, ≥3%=3, ≥1.5%=2, else 1.
- Props: minutes × per-40 rate, elasticity to team projection 0.6 (3PM 0.5, also × opp 3P D), then 70/30 with market-implied mean.
- Filter: drop unders with line below projection, overs with line above. Same-direction plays in one game listed as stacks.

## Test
`python3 test_cbb.py` (network disabled, stdlib only) → prints card and ALL TESTS PASSED.

## Limitations
Untested weights; no backtest. Matchup-leg coefficients are hand-set. Normal-distribution pricing; no correlation pricing for stacks. barttorvik column names/URLs should be verified on first real export. Player prop SDs are rough fractions of the mean.
