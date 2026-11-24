# NFL totals challenger backtest (2026-11-23) — research only, NEEDS ISAAC APPROVAL

Data (free, real): nflverse/nfldata `data/games.csv` (scores, closing total_line, roof, temp, wind), nflverse-data `stats_team_week_{2016..2026}.csv` (plays = pass att + carries + sacks). No invented data.
Walk-forward: each game projected only from games on earlier dates. k / ridge lambda / pace+weather coefficients / blend weight tuned on 2018-22 only; test 2023-25 run once; 2026 shown separately.
Methods: A = Week 11 card method (season PF/PA regressed to 22.5, k=8). B = same, k tuned. C = ridge off/def ratings (half-life 45d, 400d window). D = best of B/C + pace (regressed plays/game) + weather (wind x outdoor, freezing outdoor, dome). E = market close + w*(D - market).
*Weather is OBSERVED game-day temp/wind = upper bound on what a forecast could add.

## Verdict
- No standalone model beats the closing total (test MAE 10.51-10.56 vs market 10.12). Model-vs-market O/U edges >3 pts are not profitable on test (all methods ~45-51% overall) and lost badly in 2026.
- Pace adds nothing; weather adds ~0.03 MAE even with observed weather.
- Recommended challenger: E — anchor totals on the market total, add only 0.10 x (model - market). Equals market MAE on test. Do not fire totals bets off model-vs-market gaps; props/period lines should inherit the market-anchored total.
- No engine files or weights changed. E never moves more than ~1 pt off market, so it produces no 3+ pt edges (0 in buckets below).

## Results
Tuned on 2018-22: best k=4, best ridge lam=10, D base=pf_k4
D coefs [int, pace_sum, wind_mph, freezing_outdoor, dome]: [1.102, -0.108, -0.231, 0.547, 1.671]
D_pace coefs [int, pace_sum]: [0.365, -0.086]
Train MAE: pf_k8=10.97, pf_k4=10.95, rd_l10=11.02, D_pace=10.96, D_full=10.88, E_blend=10.60, line=10.60

### TEST 2023-2025 (n=855)

| method | MAE | bias (pred-act) | slope act~pred | sd(pred) |
|---|---|---|---|---|
| A current k=8 PF/PA | 10.51 | -0.23 | 1.36 | 1.81 |
| B PF/PA k=4 | 10.51 | -0.25 | 1.01 | 2.40 |
| C ridge lam=10 | 10.56 | -0.19 | 0.80 | 2.77 |
| D base+pace | 10.55 | +0.21 | 0.98 | 2.40 |
| D base+pace+weather* | 10.52 | +0.39 | 0.99 | 2.95 |
| E market+0.1*(D-mkt) | 10.12 | -0.95 | 1.05 | 4.06 |
| MARKET close | 10.12 | -1.10 | 1.00 | 4.29 |

O/U vs closing line at -110 (pushes excluded); edge = model - line

| method | bucket | n | hit% | ROI% |
|---|---|---|---|---|
| A current k=8 PF/PA | 3-5 | 176 | 55.7 | +6.3 |
| A current k=8 PF/PA | 5-7 | 84 | 38.1 | -27.3 |
| A current k=8 PF/PA | 7+ | 45 | 55.6 | +6.1 |
| A current k=8 PF/PA | 3+ | 305 | 50.8 | -3.0 |
| B PF/PA k=4 | 3-5 | 179 | 51.4 | -1.9 |
| B PF/PA k=4 | 5-7 | 67 | 40.3 | -23.1 |
| B PF/PA k=4 | 7+ | 42 | 54.8 | +4.5 |
| B PF/PA k=4 | 3+ | 288 | 49.3 | -5.9 |
| C ridge lam=10 | 3-5 | 169 | 43.2 | -17.5 |
| C ridge lam=10 | 5-7 | 70 | 47.1 | -10.0 |
| C ridge lam=10 | 7+ | 43 | 46.5 | -11.2 |
| C ridge lam=10 | 3+ | 282 | 44.7 | -14.7 |
| D base+pace | 3-5 | 172 | 51.2 | -2.3 |
| D base+pace | 5-7 | 74 | 44.6 | -14.9 |
| D base+pace | 7+ | 54 | 50.0 | -4.5 |
| D base+pace | 3+ | 300 | 49.3 | -5.8 |
| D base+pace+weather* | 3-5 | 190 | 45.3 | -13.6 |
| D base+pace+weather* | 5-7 | 85 | 52.9 | +1.1 |
| D base+pace+weather* | 7+ | 44 | 54.5 | +4.1 |
| D base+pace+weather* | 3+ | 319 | 48.6 | -7.2 |

### 2026 to date (n=162)

| method | MAE | bias (pred-act) | slope act~pred | sd(pred) |
|---|---|---|---|---|
| A current k=8 PF/PA | 11.39 | -0.89 | 0.62 | 1.48 |
| B PF/PA k=4 | 11.45 | -0.72 | 0.35 | 2.20 |
| C ridge lam=10 | 11.62 | -0.47 | -0.20 | 2.93 |
| D base+pace | 11.45 | -0.24 | 0.35 | 2.15 |
| D base+pace+weather* | 11.48 | +0.60 | 0.45 | 2.69 |
| E market+0.1*(D-mkt) | 10.46 | -0.98 | 1.31 | 4.24 |
| MARKET close | 10.41 | -1.16 | 1.25 | 4.55 |

| method | bucket | n | hit% | ROI% |
|---|---|---|---|---|
| A current k=8 PF/PA | 3+ | 80 | 42.5 | -18.9 |
| B PF/PA k=4 | 3+ | 77 | 40.3 | -23.1 |
| C ridge lam=10 | 3+ | 87 | 36.8 | -29.8 |
| D base+pace | 3+ | 77 | 39.0 | -25.6 |
| D base+pace+weather* | 3+ | 81 | 43.2 | -17.5 |

(Full 2026 bucket breakdown printed by the script.)

Reproduce: `python3 nfl_totals_backtest.py games.csv DIR_WITH_ts_YYYY.csv` (~40s).
