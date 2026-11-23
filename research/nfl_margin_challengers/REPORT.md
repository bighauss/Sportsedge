# NFL margin challengers: QB adjustment and EPA (items #4 and #6)

Status: RESEARCH / PAPER, 0u. No engine files or weights changed. Needs Isaac's approval before anything is promoted.

## Data (free nflverse, downloaded Nov 23 2026)
- Schedules: nflverse-data release `schedules/games.csv` (scores, `spread_line` = closing home spread, `home_qb_id`/`away_qb_id` = actual starter).
- Play-by-play: nflverse-data release `pbp/play_by_play_{2017..2025}.csv.gz` (epa, qb_dropback, passer/rusher `id`).
- 2017 is used only as history for early 2018 weeks.

## Method (walk-forward, weekly, pregame only)
At each week, as-of = 1h before that week's first kickoff; only games that finished before then are used (last 400 days).
- **A** points ridge: `engine/sportsedge_ratings_v0_2.fit/project`, NFL config unchanged (lg 22.5, hca 1.6, ridge 5, half-life 45d), no priors file.
- **B** A + beta * (home QB adj - away QB adj). QB adj = starter's prior EPA/dropback minus team's season-to-date dropback EPA (last season if < 100 dropbacks), shrunk n/(n+300). Uses the starter listed for that game (known pregame most weeks; a small lookahead risk on late QB changes). beta fit on train.
- **C** `models/nfl/epa_ridge_pit.build_ratings` (repo code, default half-life 21d, ridge 30) -> net EPA/play diff (pass 0.58 / rush 0.42) -> points via OLS (HFA + slope) fit on train.
- **D** w*A + (1-w)*C, w fit on train by MSE.
Train 2018-2022 (n=1372), test 2023-2025 once (n=855, incl. playoffs). Train fits: C = 36.2 pts per EPA/play + 1.25 HFA; QB beta = 5.8; D weight on A = 1.00 (C adds nothing on train).

## Test results 2023-2025
| model | MAE | bias (actual-pred) | slope actual~pred | RMSE |
|---|---|---|---|---|
| market spread_line | 9.79 | +0.81 | 1.15 | 12.72 |
| A points ridge | 10.40 | +0.78 | 1.20 | 13.39 |
| B A + QB | 10.40 | +0.79 | 1.27 | 13.39 |
| C EPA ridge | 10.56 | +1.10 | 1.07 | 13.57 |
| D blend (=A) | 10.40 | +0.78 | 1.20 | 13.39 |

ATS vs closing spread (pushes excluded), by |model - spread|:
| model | 3-5 | 5-7 | >7 | all >3 |
|---|---|---|---|---|
| A | 98-102 (49.0%) | 45-41 (52.3%) | 25-20 (55.6%) | 168-163 (50.8%) |
| B | 88-112 (44.0%) | 44-37 (54.3%) | 23-21 (52.3%) | 155-170 (47.7%) |
| C | 101-105 (49.0%) | 41-48 (46.1%) | 38-29 (56.7%) | 180-182 (49.7%) |
| D | same as A | | | |

## Read
- No challenger beats the market; none beats A on MAE. All ATS buckets are within noise of 50% (break-even at -110 is 52.4%).
- C (EPA) has the best calibration slope (1.07 vs A 1.20) but worse MAE. Slope > 1 for all models here means margins are too compressed (consistent with the Week 11 0.71 finding) -- a stretch factor on A is a cheaper fix to test next.
- QB adjustment did not help on these settings (starter is usually already reflected in recent team results; 13 test games had a starter with no NFL dropbacks -> adj 0).
- Recommendation: keep A as production; do not adopt B/C/D. Optional next test: margin stretch k on A fit on train.

Reproduce: download the files above into DATA_DIR (schedule saved as `sched.csv`) and run
`python research/nfl_margin_challengers/run_challengers.py DATA_DIR` (writes predictions.csv beside the script).
