# CBB full-game P0: inflated EV root causes and the FG1C challenger

**Status: RESEARCH CHALLENGER, PAPER / 0u, NON_COUNTED. Nothing here is validated or promoted.**
The frozen production model (`cbbd_native_score_model.py`, `sportsedge_cbb_model.py`) and the RUN IT
pricing defaults (`cbb_pricing.DEFAULT_CONFIG`: SD 12.5/17, linear blend w=0.25) are **unchanged**.
The card is not rewired; the runner workstream owns that integration.

Every number below comes from `python -m fullgame.run_eval` / `fullgame.nov24_diagnosis` /
`fullgame.make_report` (the reproduction steps are at the end). Full tables: `evidence/tables.md`; machine-readable: `evidence/summary.json`;
Nov 24 row-level re-pricing: `evidence/nov24_rows.json`. Improvement ablations: `evidence/improve_tables.md` and `evidence/improve_summary.json`.

## Data and splits (fixed before evaluation)
- Games: public sportsdataverse ESPN schedule plus team box, seasons 2019-2027 (2027 = Nov 1-25, 2026). Both teams
  D1 (>= 15 finals in the season; for 2027, the 2026 D1 set). Possessions are FGA - OREB + TO + 0.475 FTA.
- Venues: `HOME_VERIFIED` means the game's venue_id equals the home team's ESPN home venue_id. Home court applies **only** there.
  NEUTRAL and UNVERIFIED (non-neutral flag but venue mismatch or missing) get 0.
- Odds (research only, **not an admitted source**): ESPN core-API closing and opening quotes, DraftKings preferred (2026-27),
  else ESPN BET (2024-25). Live-odds provider excluded. 2023 payloads put prices in the point-spread field,
  so those spreads and totals are rejected with a reason code (2023 is ML only). Because evaluation is at the close, CLV = 0 by construction.
  ROI is a diagnostic.
- Splits: FG1 hyper-parameters tuned on **2020-2022** only (12-config grid; criterion margin RMSE + 0.5 * total RMSE;
  chosen carry 0.85, ridge 4 games, recency half-life 40 days, HCA prior weight 400). Residual distributions,
  de-bias regressions and the ML tail fit for season S use **seasons < S only**. Nine-weight blend: selected on
  **2024-25**, scored once on **2026-27**.

## Engines compared on identical rows
RAW (native formula, raw season-to-date ratings), REG (raw shrunk by 12 games), NATIVE_RECON (native formula on
current-season schedule-adjusted ratings with mean-residual HCA, the closest public replay of the frozen model),
SA (schedule-adjusted ridge, current season), FG1 (SA + previous-season prior + recency form + jointly fitted HCA
with a multi-season prior + possessions ridge), FG1C (FG1 + chronological linear de-bias of margin and total,
early (<5 games) and later phases separately).

## Root causes of the Nov 24 inflated EV (card run 45452279760: 48 of 167 rows > +30%, reproduced exactly)
1. **Projection, not SD, is the primary cause.** The card's own SDs (12.5/17) are *wider* than the chronologically
   fitted residual SDs (margin 11.1-13.2, total 16.6-17.9 by phase). Re-pricing the card's means with the fitted
   t-distributions gives **52** rows over 30%, not fewer. The card's margins are compressed against the market:
   OLS card margin on market margin has slope **0.784**. The mean absolute gap to the market margin is **4.68** pts (FG1C 2.45).
   On the 13 favourites of 15+, the card's mean margin is 17.1 vs the market's 21.3 (actual 31.1). That makes every big
   home favourite "model-best away" (Lipscomb +3500: card home margin about +14.6 against -25.5).
2. **Home-court inflation from current-season-only ratings.** The card used HCA **8.45** pts (n 843). On the same
   pre-Nov-24 2027 D1 finals, current-season adjusted ratings plus the native mean-residual rule give **7.48** pts
   (15.55 if non-D1 finals are included). Early-season schedules are unbalanced (strong teams host buy games),
   so team strength leaks into "HCA". FG1 with a previous-season prior and a multi-season HCA prior gives **3.98** pts.
3. **No market-conditional calibration.** Even a better independent model can't be priced as if it were the truth against
   the market. Historically (Table B), the independent FG1C still shows hundreds of >30% rows per season at the
   close, with **negative flat ROI in every season and market except 2027 totals (+0.8% on 32 bets)** and Brier
   worse than the no-vig market. The rows where the model disagrees with the market are mostly model error.
   Selecting rows by EV is a winner's curse.
4. **Longshot tails.** ML underdogs at +1000 or longer win **3.24%** (SE 0.39) vs a model 6.42% and no-vig 5.65% (Table D).
   An outcome-only logit tail recalibration fitted chronologically gives slope 0.97-1.00 (no material change).
   The model's ML probabilities are calibrated against outcomes overall (ECE 0.009-0.019), and the tail error is a
   conditional-on-market selection effect. The linear probability blend (w=0.25) lets the longshot model probability
   dominate (Lipscomb blend EV +83.5%). A logit blend does not (`cbb_pricing.logit_blend`).
5. Secondary: the native frozen model and REG over-predict home margin (bias -0.5 to -1.6). Totals projections are
   over-dispersed (actual-on-forecast slope 0.72-0.93), which drives the over/under extremes. FG1C de-biases the totals level.

## What changed (challenger only)
- `fullgame/ratings.py`: point-in-time engines (stdlib), verified-venue HCA, D1-only fitting, prior carry-over, recency.
- `fullgame/pricing.py`: phase-specific Student-t residual distributions fitted on chronological forecast residuals
  (location = de-bias), **push-aware integer lines**, ML tie-mass split, fair odds, outcome-only ML tail recalibration,
  `ev_audit` (**flag only, never caps or alters EV**).
- `fullgame/evaluate.py`, `run_eval.py`, `backtest.py`, `nov24_diagnosis.py`, `make_report.py`, `espn_odds.py`, `sdv_loader.py`.
- `cbb_pricing.py` (additive only): `OWNER_BLEND_WEIGHTS` (the owner's nine: 100/0, 87.5/12.5, 75/25, 62.5/37.5, 50/50, 37.5/62.5, 25/75, 12.5/87.5, 0/100), `logit_blend`, `ev_sanity_audit(card)`
  (flags only), `EV_AUDIT_THRESHOLD`, and `parse_american` (exact quote contract: int or signed whole-number string; rejects floats including `110.0`, fractional strings, bools and malformed tokens; never truncates).
  `DEFAULT_CONFIG` is untouched. The obsolete `CANDIDATE_BLEND_WEIGHTS` grid and the ledger's handwritten `(0, 25, 50, 60, 75, 80, 90, 95, 100)` copy were removed; every consumer uses `OWNER_BLEND_WEIGHTS` only (the ledger percent form is derived). A source test fails if another grid appears.
  `fullgame.pricing.decimal_odds` and `_rung` go through the contract. `cbb_run_it.py` reports the 100/0 independent-EV slot by weight, not by last-cell position.

## Before / after headline (identical rows)
- Nov 24 card, same 167 rows at the card's prices: EV>30% **48 -> 13** (FG1C independent) **-> 0** (validation-selected weights).
  EV>10% 116 -> 46 -> 0. Margin MAE vs actual 10.47 -> 9.94 (market 9.60). Total MAE 14.46 -> 14.34 (market 13.85).
- 2026 season, identical market rows at the close, BEFORE (NATIVE_RECON + RUN IT constants) -> AFTER (FG1C + fitted pricing):
  EV>30% spread 471 -> 270, total 475 -> 284, ML 764 -> 485. Brier spread 0.2614 -> 0.2575, total 0.2640 -> 0.2599,
  ML 0.1928 -> 0.1903 (market 0.2499 / 0.2500 / 0.1846).
- Identical-row projection accuracy (Table A), 2026: margin MAE NATIVE_RECON 9.34 -> FG1C 9.13, RMSE 11.84 -> 11.59,
  total MAE 13.93 -> 13.68, ML log loss 0.5528 -> 0.5461. FG1/FG1C is best of the six engines in every season 2023-2027.

## Bias evidence (Table C), honest status
- Spread favourite/underdog: |p - rate| <= 0.010, within about 1.4 SE every season: **no detectable bias**.
- **Remaining defects:**
  - ML favourites are under-predicted by 0.6-2.4 pp (2025: -0.024, SE 0.006, significant).
  - Over probability at market lines exceeds the over rate by 2.4-2.9 pp in 2025-26 (significant), even though the
    FG1C total residual is about 0 (+0.12/+0.20). The bias is market-relative.
  - Favourite-oriented margin residual is +0.4 to +0.65 pts (favourites slightly under-projected).
  - 2027 early-season total residual is +2.30 (SE 0.54). The de-bias regression pulls early totals toward a league
    mean that 2027 scoring exceeds.
- These are **not** fixed. The owner's "no bias" requirement is not met for ML favourites or totals.

## Nine weights (Table E)
At the close, all three markets select model weight **0.0** on validation 2024-25. At the open, spread selects 0.0,
and total and ML select 0.125. On the untouched 2026-27 test window, the open-line total gains 0.0004 log loss over
market-only, and the open-line ML at 0.125 is **worse** than market-only (0.5241 vs 0.5236). **Conclusion: the
independent model shows no reliable information beyond the market at either the open or the close.** The EV of an
independent projection is not a calibrated edge, and the calibrated research EV is about the market's negative vig.
This is evidence for the P2 blend workstream, not a promotion.


## Improvement pass (rest, travel, neutral, early, longshot, side bias)

A second, protocol-preserving pass tried to close the gap to the market and the remaining side bias.
Opponent-adjusted offensive and defensive efficiency was already the FG1/SA specification (`eff = mu + off_i + def_j + h*s`).
This pass adds pre-game rest, a coarse travel/neutral-site adjustment, an early-season residual term, and
outcome-only longshot / favourite maps. Coefficients were **frozen on 2020-22**. 2023-25 is validation.
**2026-27 is a confirmatory reuse of an already-used window, not a fresh holdout.** Every named variant is
scored on identical rows; failures are kept in the tables. Full grid: `evidence/improve_tables.md`.

Tune-window residual fits on 14,393 FG1 rows (actual − FG1), ridge λ=1:

- **Rest** (sensible, largest terms): home back-to-back −3.59 margin pts, away back-to-back +2.96 (home-team margin).
- **Neutral site:** −1.88 pts on the total.
- **Travel** (coarse city/state proxy): small (about 0.03–0.08 pts per 100 miles).
- **Early season** (<5 games): +0.89 margin, −0.99 total.

Validation 2023-25, identical rows (n=16,843):

| engine | margin MAE | total MAE |
|---|---:|---:|
| FG1 | 9.044 | 13.142 |
| FG1C | 9.043 | 13.094 |
| FG2_rest | 9.040 | 13.127 |
| FG2_travel | 9.043 | 13.131 |
| FG2_neutral | 9.050 | 13.117 |
| FG2_early | 9.043 | 13.128 |
| FG2 (all context terms) | 9.036 | 13.120 |
| FG2C (FG2 + chronological de-bias) | 9.036 | 13.083 |

Confirmatory reuse 2026-27 (n=6,694): margin MAE FG1 9.425 → FG2C 9.414; total MAE FG1 13.824 → FG2C 13.748 (FG1C 13.766).
The gains are real but small (hundredths of a point). **The market still has the better Brier on every market in every validation and reuse season.**
Examples, auxiliary ESPN close quotes (model vs market Brier):

- 2025 validation, FG2C: spread 0.2593 vs 0.2499, total 0.2572 vs 0.2499, ML 0.1831 vs 0.1784 (n=5,643 / 5,644 / 5,534).
- 2026 reuse, FG2C: spread 0.2597 vs 0.2500, total 0.2596 vs 0.2500, ML 0.1873 vs 0.1802 (n=5,574 / 5,591 / 5,399).

### Failures that are left in the open
- **Longshot map did not transfer.** On 2020-22, FG2 model tails were *under*-confident (p≤0.05: model 0.030 vs rate 0.077, n=26, thin).
  That is the opposite direction of the later +1000-dog finding (win rate 3.24% vs model 6.42%). Applying the frozen map
  slightly *worsened* moneyline Brier on 2023-26. The tail defect is not stable enough to correct from the tune window.
- **Favourite bump did not transfer.** The 2020-22 outcome-only bump was −0.74 pp (the model slightly over-predicted its
  own favourites). In 2025 the market-line ML-favourite bias is still about −2.1 to −2.2 pp; applying the frozen bump
  made it worse (−2.7 pp). The bias is not stationary between tune and validation.
- **Over bias at market lines is unchanged** (about +2.4 to +2.7 pp in 2025-26, significant). A −1.6 pp shift fit at the
  model's *own* total on 2020-22 was not applied as a market-line correction, because that would have used the market as
  an input to the independent probability. The independent total residual is near zero after FG1C/FG2C; the over bias is
  market-relative and is not fixed.
- No variant, including the combined FG2C plus both maps, beats the market Brier on spread, total or moneyline.

## Remaining gaps
- Roster availability: no legitimate point-in-time public injury/availability source is shipped with this challenger, so it is not modeled. The production gate already blocks a missing injuries role.
- Returning minutes / roster continuity: player box scores exist for some seasons, but there is no dated preseason roster or transfer snapshot that would let returning minutes be computed without using current-season appearances (leakage). Early-season ratings still use the previous-season carry prior only.
- Travel miles are a coarse proxy (same-city 0, same-state 120, otherwise haversine of region centroids), not surveyed road distance.
- 2027 is thin (1,050 FG1 rows / 435 identical market rows in the first report, early season). Early-phase error is the largest (phase-0 margin SD 13.2).
- ESPN historical odds are an auxiliary comparator only, not execution prices or CLV evidence. The card's 6:30 AM captures aren't comparable to the closing lines.
- Offline unit tests live in `fullgame/test_fullgame.py` (35 tests) and run in `.github/workflows/cbb-fullgame.yml` via `cd models/cbb && python -m unittest -v fullgame.test_fullgame`. They use committed fixtures and do not need the network.
- Not wired into `cbb_run_it.py` (WS3). The integration contract is `pricing.line_probs` / `ml_probs` / `ev_audit`,
  `cbb_pricing.logit_blend`, `ev_sanity_audit`, plus an FG1C (or FG2C) forecast per game.

## Reproduce
```
python3 -m fullgame.sdv_loader --root DATA --out DATA/games --seasons 2019 ... 2026      # then: --seasons 2026 2027 --in-progress-last
python3 fullgame/fetch_espn_odds.py 2027 2026 2025 2024 2023   # writes the odds cache (OUT path at top of file)
python3 -m fullgame.backtest --games DATA/games --out DATA/wf --engines RAW REG NATIVE_RECON SA --tag base
python3 -m fullgame.backtest --games DATA/games --out DATA/wf --engines FG1 --tag fg1t --params '{"carry":0.85,"carry_pace":0.7,"lam":4,"lam_pace":4,"half_life":40,"hca_lam":400}'
python3 -m fullgame.run_eval --wf DATA/wf --odds DATA/odds --out eval_report.json
python3 -m fullgame.make_report --eval eval_report.json --nov24 nov24_rows.json --out fullgame/evidence
python3 -m fullgame.improve_eval --games DATA/games --sched DATA --wf DATA/wf --odds DATA/odds --out fullgame/evidence
```
(run from `models/cbb`; nov24_rows.json from `nov24_diagnosis.run` with the open-line selected weights.)
