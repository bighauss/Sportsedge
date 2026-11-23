# NFL usage-based props challenger (research)

`usage_backtest.py`: mean = team volume (EWMA of prior team weeks, half-life 3) x player share (EWMA, regressed toward player's season share, k=2) x efficiency (regressed toward position mean: yds/target k=40, catch rate k=40, yds/carry k=60, yds/att k=150).
Walk-forward: each week uses only prior weeks of the same season; players need >=3 prior games with the team. Baseline (B) = player's prior-week season average. Same player-weeks for both.

Data: nflverse `player_stats_2023.csv`, `player_stats_2024.csv`, `stats_player_week_2025.csv` (REG season; 2025 through games played as of the 2026-11-23 pull). Run:
`python usage_backtest.py ps_2023.csv ps_2024.csv stats_player_week_2025.csv preds.csv`

## Result (MAE vs actual)
| stat | n | A usage | B season avg | gain |
|---|---|---|---|---|
| passing_yards | 1325 | 66.63 | 67.92 | 1.9% |
| receiving_yards | 10172 | 18.06 | 18.38 | 1.7% |
| receptions | 10172 | 1.36 | 1.38 | 1.4% |
| rushing_yards | 4365 | 18.43 | 18.58 | 0.8% |

Usage beats the baseline in every stat and every season (2023/24/25), but only by ~1-2%.

## Limits
- Historical prop lines are not freely available (nflverse has none), so no hit-rate / CLV / ROI test vs the book: MAE only. Whether it beats the market's implied mean is untested.
- Team volume here is a trailing EWMA; live it should come from the projections builder (pace, script, total).
- No opponent adjustment yet.
