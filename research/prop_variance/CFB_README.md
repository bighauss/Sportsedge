# CFB player-prop variance: walk-forward calibration (Nov 28 2026)

PAPER research only. This is CFB-specific and refits nothing from the NFL study. Lines are
proxies, not sportsbook lines, so this measures distribution calibration, not edge vs DraftKings.

## Data (free, no API key)
- `sportsdataverse/cfbfastR-data` at commit `caa61040`, file `player_stats/csv/player_stats_<season>.csv`
  (play-level player attributions), 2014–2025. Digests are in `CFB_INPUT_SHA256SUMS`. The data is not committed.
- Aggregated to 252,464 player-games. Plays are de-duplicated by (play_id, role).
- Totals come from play-by-play, not official box scores. Penalty-nullified or missing plays can
  make them differ. Sacks are excluded from pass attempts.

## Method
- Forecast: EWMA (α 0.35) of the player's **prior** eligible games (pass ≥15 attempts, rush ≥5
  carries, rec ≥3 targets), after ≥3 of them. Order is strictly season/week/game.
- Train 2014–2021. **Untouched holdout 2022–2025.**
- Compared: the pinned CFB `PROP_SD_FRAC` normal (0.28/0.45/0.50/0.40), a power-law normal fit on
  train only, and the empirical train ratio Y/f by forecast bin.

Reproduce: `python research/prop_variance/fit_cfb_prop_variance.py <dir with player_stats_*.csv>`

## Holdout results (2022–2025)
| Stat | n | Mean f | RMSE | Median Y/f | Pinned frac | Implied frac | ECE pinned | ECE power | ECE empirical | Log loss pinned → best |
|---|---|---|---|---|---|---|---|---|---|---|
| pass_yds | 4,547 | 204.9 | 84.9 | 0.99 | 0.28 | **0.41** | 0.053 | **0.025** | 0.026 | 0.652 → 0.626 (emp) |
| rush_yds | 12,551 | 56.4 | 39.7 | 0.91 | 0.45 | **0.70** | 0.061 | 0.044 | **0.020** | 0.680 → 0.654 (emp) |
| rec_yds | 15,615 | 49.0 | 35.5 | 0.91 | 0.50 | **0.73** | 0.056 | 0.047 | **0.016** | 0.680 → 0.652 (emp) |
| receptions | 15,616 | 3.95 | 2.09 | 0.96 | 0.40 | **0.53** | 0.032 | 0.023 | **0.018** | 0.648 → 0.646 (emp) |

**Signed P(over) bias of the pinned model** (predicted − actual) at line = 0.75f / 0.90f / 1.00f / 1.10f / 1.25f:
- pass_yds +8.1 / +5.8 / +0.9 / −3.3 / −8.5: too narrow both ways
- rush_yds **+10.6 / +7.9 / +5.2** / +1.7 / −3.5
- rec_yds **+9.7 / +7.5 / +5.5** / +2.7 / −1.7
- receptions +3.8 / +4.2 / +3.3 / +1.3 / −2.2

## Findings
1. The pinned CFB SDs are far too narrow: implied fractions are 0.41 / 0.70 / 0.73 / 0.53. CFB
   is *wider* than NFL, so NFL numbers must not be transferred.
2. Rush and receiving yards are right-skewed (median 0.91f). The symmetric pinned normal overstates
   **overs at or below projection by 5–11 pts**.
3. The empirical skewed distribution is best on Brier and log loss for every stat, and on ECE for
   3 of 4. For pass_yds the train power-law normal has a slightly lower ECE.
4. Even the empirical model still shows a small +1–3 pt over bias on the 2022–2025 holdout, so
   the distribution drifts across seasons. Any production fit needs rolling refits and a
   drift check. It must not be a single frozen table.
5. DNP and in-game injury are unobserved, so true downside is larger than shown.
