# Calibration audit status (updated 2026-11-22)

- prediction_log.csv: still EMPTY. No "run it" has logged model_p / no-vig market_p, so the calibration audit (edge buckets, Brier, log loss vs no-vig market) cannot run yet.
- seed_2026-11-15.csv: the only graded card (17 W/L plays, prices only, NO model_p). 4-13, flat-1u ROI -49.9% (n=17, SMALL SAMPLE).
  - Long-shot MLs (+185 to +380): 1-5, ROI -52% (n=6). Price-implied ~27% avg; hit 17%. Matches the Nov 15 long-shot ML concern but far too small to conclude.
- Needed (logging, not a model change): each "run it" calls ledger/prediction_log.log_run() with one row per priced side, both sides of each market so no-vig market_p is computable.
- Pre-registered test at n>=200 graded rows: if ROI and Brier in the 10%+ edge bucket are worse than the 2-5% bucket, propose a disagreement cap on a NEEDS ISAAC APPROVAL branch.
