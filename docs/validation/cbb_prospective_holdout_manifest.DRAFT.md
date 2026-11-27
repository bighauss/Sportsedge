# CBB prospective holdout manifest - DRAFT (UNLOCKED)

Status: DRAFT. Not locked. PAPER / 0u / NON_COUNTED. No model coefficients, features, pins or results are changed by this document. Tracks #57.

This manifest becomes binding only when (a) every TBD below is filled, (b) it is committed on its own, (c) an independent reviewer signs on #57, and (d) its git commit SHA and sha256 are recorded. Scoring may begin only on games whose DraftKings capture timestamp is AFTER that commit time.

## 1. Why a new holdout
Prior #563 results (retrospective, mixed-book ESPN thresholds, unauthenticated timing, 2023 spread/total quarantined, reconstructed features, previously inspected seasons) are diagnostics only. Reported by ChatGPT on #57 from job 140781285533 / run 46081502136 at b90f47d9: common cohort 36,658 events; spread n=31,381 (334 pushes, 5,277 held); total n=31,292 (186 pushes, 5,366 held); all spread models under-predict pushes (observed 0.010643; native 0.007826). Those seasons are NOT reusable as untouched.

## 2. Cohort definition (to lock)
- Sport: CBB only for this manifest. CFB and NFL get separate manifests.
- Source: DraftKings only, from existing authorized captures. Capture directory/path: TBD (owner of captures to supply).
- Eligible event: has a frozen DK capture taken before scheduled tip-off, with capture timestamp, DK event ID, and original evidence file hash.
- Markets: moneyline, spread, total first (full game); halves, team totals and props enter only after their own independent projection and identity checks pass.
- Exclusions fixed in advance: events with missing/duplicate IDs, one-sided prices, or capture within TBD minutes of tip-off; every exclusion is counted and reported.

## 3. Freeze procedure (per event, before kickoff)
Record, append-only, with sha256 of each artifact: DK event ID; all paired prices (both sides) per market; thresholds/lines; capture UTC timestamp; raw capture file hash; model projection receipt produced BEFORE market comparison (hash of the input features); model identity (git SHA and pin hash). Outcomes are attached only after final scores, from a separately named source, never edited into the frozen record.

## 4. Models under test (to lock)
Frozen native; raw; regularized; schedule-adjusted; plus baselines below. Pre-named primary challenger: TBD (must be chosen before scoring; if more than one is reported as primary, Holm correction across them). No refits during the holdout; coefficients locked by git SHA: TBD.

## 5. Baselines on identical matched cohorts
- Rating-only regression fit on training seasons only (spec TBD).
- Historical league base rates (home win rate, push rate by line type).
- Market-implied CONDITIONAL probabilities from paired DK prices after de-vigging (method TBD, fixed in advance). No market push probability is invented; compare conditional-on-no-push where the market is the benchmark, and report unconditional W/P/L only for model rows.

## 6. Metrics and statistics (to lock)
Brier (3-class and conditional), log loss with fixed clipping, MAE and RMSE of margin/total vs outcome, calibration curves (equal-count bins, bin count TBD) with counts, per-season and per-month tables, sample sizes at every cut. Paired block bootstrap (blocks by calendar date or team-week, reps TBD, seed TBD) for differences vs each baseline; report 95% intervals. Multiple-comparison handling: Holm over pre-registered primary comparisons.

## 7. Push correction protocol
Fit any push adjustment on training seasons only, by line type (integer vs half) and market; validate on a disjoint later season; then evaluate on this prospective holdout without refit. Report predicted vs observed push rate with intervals.

## 8. Minimum evidence before any statement of edge
TBD sample size per market from a power calculation; interval for improvement over the market-implied baseline excludes zero after correction; calibration acceptable on locked bins. Even then: PAPER/0u, no stars, promotion requires separate owner approval.

## 9. Governance
One writer per branch. Independent reviewer signs on #57 before lock. No self-certification. No change to frozen model files.

## 10. Open items (blockers)
- Capture path and format of existing authorized DK captures: TBD.
- De-vig method and tip-off cutoff: TBD.
- Sample-size target and power calculation: TBD.
- Reviewer sign-off: pending.
