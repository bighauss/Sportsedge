# CBB prospective holdout manifest - DRAFT (UNLOCKED)

Status: DRAFT. Not locked. PAPER / 0u / NON_COUNTED. No model coefficients, features, pins or results are changed by this document. Tracks #57. No NBA/NHL. No uncalibrated stars.

This manifest becomes binding only when (a) every remaining TBD is filled, (b) it is committed on its own, (c) an independent reviewer signs on #57, and (d) its git commit SHA and sha256 are recorded. Prospective enrollment may begin only after (a)-(d).

## 1. Why a new holdout
Prior #563 results (retrospective, mixed-book ESPN thresholds, unauthenticated timing, 2023 spread/total quarantined, reconstructed features, previously inspected seasons) are diagnostics only. Reported by ChatGPT on #57 from job 140781285533 / run 46081502136 at b90f47d9: common cohort 36,658 events; spread n=31,381 (334 pushes, 5,277 held); total n=31,292 (186 pushes, 5,366 held); all spread models under-predict pushes (observed 0.010643; native 0.007826). Those seasons are NOT reusable as untouched.

## 2. Capture source (decided)
DraftKings only. Existing authorized captures are posted by Muse on issue #57 (example comment IDs 7228878917, 7228879344, 7228879921, 7228880376, 7228880629). Muse captures only when instructed. These existing records are used ONLY to develop and test the ingestion format (original evidence preserved unchanged; normalized to structured CSV/JSON). Every game in those records is previously observed and is EXCLUDED from the prospective holdout. New prospective games require new, instructed captures after lock.

## 3. Eligibility and capture cutoff (decided)
- Sport: CBB only. CFB and NFL get separate manifests.
- Primary market: full-game moneyline. Spread and total are secondary.
- Quote used: the latest eligible PAIRED quote (both sides, same market, same line) captured between 60 and 15 minutes before scheduled tip-off.
- Required: verified pregame status, verified DK event identity, capture and publication timestamps. Missing any one excludes the event.
- Every exclusion is counted and reported by reason (no pair, outside window, identity unverified, in-play, timestamp missing, duplicate).

## 4. Freeze procedure (per event)
Record append-only with sha256 of each artifact: DK event ID; both sides' prices and thresholds; capture UTC timestamp; raw capture hash; model projection receipt produced BEFORE market comparison (input-feature hash); model git SHA and pin hash. Outcomes attached only after final scores from a separately named source, never edited into the frozen record.

## 5. Models, primary and secondary endpoints (decided)
- Primary comparison: schedule-adjusted model, full-game moneyline win probability, versus DraftKings no-vig probability. Primary endpoint: paired difference in conditional Brier score (model minus DK no-vig) on identical events. Moneyline has no push, so conditional equals unconditional here.
- Secondary candidates: regularized and schedule-adjusted for spreads and totals, scored on conditional (no-push) and, for model rows only, 3-class W/P/L. No market push probability is invented.
- Other comparators on identical cohorts: frozen native, raw, rating-only regression fit on training seasons only, historical league base rate.
- Multiplicity: the single primary hypothesis is tested at alpha=0.05. Secondary comparisons are pre-registered in a fixed list (TBD, enumerated at lock) with Holm correction within the secondary family. Anything not listed is exploratory and labeled so.
- No refits during enrollment; coefficients and feature versions locked by git SHA: TBD.

## 6. De-vig (decided)
Primary: proportional normalization of paired implied probabilities. Sensitivity only: power method and Shin method. Sensitivity results never replace the primary.

## 7. Statistics (to lock)
Brier and log loss (fixed clipping), MAE and RMSE of margin/total, calibration curves (equal-count bins, bin count TBD) with counts, per-month tables, n at every cut. Paired block bootstrap (blocks by calendar date or team-week; reps and seed TBD) for the primary difference with 95% interval.

## 8. Sample size and stopping rule (decided procedure, numbers TBD)
Required n computed at 90% power, two-sided 5% significance, with dependence-aware variance estimated from TRAINING data only (block bootstrap of paired Brier differences). The minimum meaningful improvement (in Brier points) and a fixed stopping rule (fixed n or fixed end date, whichever the calculation specifies) are written here BEFORE lock. No early stopping for favorable results; no interim peeks that change the plan. Values: TBD pending the training-data calculation by the analysis owner.

## 9. Push correction protocol
Fit any push adjustment on training seasons only by line type (integer vs half) and market; validate on a disjoint later season; then evaluate prospectively without refit. Report predicted vs observed push rate with intervals.

## 10. Governance
One writer per branch. Independent review on #57 required before enrolling any prospective game. No self-certification. No change to frozen model files. A statement of edge additionally requires the primary interval to exclude zero at the locked n, acceptable calibration, and separate owner approval for any promotion.

## 11. Remaining TBD before lock
- Minimum meaningful improvement, required n, stopping date (training-data calculation).
- Pre-registered secondary comparison list and bootstrap parameters.
- Locked git SHA of coefficients/features.
- Ingestion format tested on the Muse example captures (normalized CSV/JSON schema).
- Independent reviewer sign-off.
