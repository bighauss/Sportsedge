# NFL player-prop variance: walk-forward calibration (Nov 28 2026)

PAPER research only. These are proxy lines, not sportsbook lines; this measures the
**shape and width of the outcome distribution**, not edge vs DraftKings.
**NFL only.** CFB must be fitted separately on CFB player data (not yet available here;
CFBD requires an API key in this session).

## Data
Public nflverse weekly player stats (`player_stats_2018..2024.csv.gz`,
`stats_player_week_2025.csv.gz` saved as `ps_2025.csv.gz`), REG+POST. Input digests are in
`INPUT_SHA256SUMS`. The data is not committed.

## Method
- Point forecast: EWMA (alpha 0.35) of the player's **prior** eligible games only, after
  at least 3 of them. Eligibility thresholds: pass 15 attempts, rush 5 carries, rec 3 targets.
- Fit on 2018–2022. Score on **untouched 2023–2025**.
- Proxy thresholds at f×{0.75, 0.90, 1.00, 1.10, 1.25}, rounded to .5.
- Three distributions compared: SportsEdge fixed SD fraction (`PROP_SD_FRAC`), a fitted
  power-law normal, and the empirical train ratio Y/f by forecast bin.

Reproduce: `python research/prop_variance/fit_nfl_prop_variance.py ps_*.csv.gz`

## Holdout results (2023–2025)
| Stat | n | Mean f | RMSE | Current frac | Implied frac | ECE fixed | ECE power-normal | ECE empirical | Log loss fixed → empirical |
|---|---|---|---|---|---|---|---|---|---|
| pass_yds | 1,619 | 229.3 | 75.8 | 0.28 | 0.33 | 0.027 | 0.029 | **0.006** | 0.621 → 0.604 |
| rush_yds | 3,054 | 52.5 | 32.0 | 0.45 | 0.61 | 0.057 | 0.051 | **0.014** | 0.671 → 0.657 |
| rec_yds | 7,285 | 44.9 | 31.6 | 0.50 | 0.70 | 0.060 | 0.055 | **0.013** | 0.679 → 0.654 |
| receptions | 7,285 | 4.0 | 2.07 | 0.40 | 0.52 | 0.039 | 0.030 | **0.015** | 0.650 → 0.647 |

**Direction of the error (fixed fraction, holdout):** for lines at or below the forecast, the
model overstates P(over):
- rush_yds: +9.1 / +7.6 / +6.4 pts at 0.75f / 0.90f / 1.00f
- rec_yds: +10.0 / +8.4 / +6.3 pts
- receptions: +5.1 / +5.1 / +4.2 pts
- pass_yds: +4.0 / +3.2 / −0.2 pts

The median outcome is 0.89f (rec) and 0.91f (rush). The distribution is right-skewed, so a
symmetric normal centred on the mean makes **overs look better than they are**. Widening
the SD alone (the power-law fit) barely helps. The shape has to change.

## Findings / required changes
1. Replace the symmetric normal with a skewed, empirically calibrated distribution per
   stat (ratio quantiles here; a fitted gamma/negative-binomial is the next candidate).
2. Until then, treat prop **overs** at or below projection as biased by 4–10 pts.
3. Non-participation (DNP or in-game injury) is not in this data, so real downside is
   *larger* than shown.
4. Correction to an earlier #57 estimate: pass_yds width was overstated (+18% measured, not +37%).
