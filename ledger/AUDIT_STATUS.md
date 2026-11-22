# Calibration audit status (reviewed 2026-11-22)

## Audit eligibility: ZERO
- No verified prospective `ledger/prediction_log.csv` rows currently exist on `main`. No RUN IT has demonstrated durable pre-kickoff persistence of model probability, both quoted sides, source/capture clocks, and the corresponding no-vig market probability. Therefore **n=0** for prospective calibration, edge-bucket ROI, Brier, and log loss. Do not backfill missing model probabilities from later runs.
- `seed_2026-11-15.csv` is a **retrospective transcription** of `ledger/grades_2026-11-15.md`, not a validated forward prediction log. It has no model probability, quote receipt, provider/event ID, source timestamps, kickoff clock, or original immutable capture.
- The source document reports 17 W/L selections, 4-13 and approximately -49.9% flat-1u ROI; the six +185 to +380 MLs were reportedly 1-5. **These are provisional descriptive figures, not verified performance or proof of an edge/bias.** Keep all 17 rows out of the prospective calibration sample and any eligibility threshold.
- **Settlement quality exceptions:** Beck 180+ passing yards and Mendoza 190+ passing yards are marked losses using *team net passing yards*, not verified individual player passing box scores. Those are not reliable player-prop settlements (sacks and statistical definitions can differ). The NM(State) @ SDSU event identification is explicitly assumed in the source. All three require source-level resolution; preserve the original transcribed rows and notes, but exclude these outcomes from verified-grade counts pending receipts.
- Passing CI for this docs/data PR does **not** validate the underlying event identity, original odds, quote times, player-stat outcomes, or prospectivity.

## Next implementation gate (logging only; frozen v5 unchanged)
1. Route the actual production RUN IT entrypoints to a trusted logging step; a standalone wrapper alone is insufficient.
2. Record independently verified **event-level** scheduled start, selection timestamp, original quote capture time, immutable quote/provider ID, run/model ID, exact bet identity including market/period/player/team/line/side, and each offered side. Validate the model probability is finite and in [0,1].
3. Compute no-vig probability only from the matched two-sided contemporaneous quotes (or mark unavailable); don't imply missing market prices are valid zeros.
4. Persist original pregame records immutably across runners, with encryption where required, idempotency, crash recovery, and explicit fail-closed/logging-failure statuses.
5. Prove all of this on a fresh-runner synthetic rehearsal and then an authenticated prospective input capture before counting real predictions.

## Pre-registered research (not a production threshold)
Once **at least 200 independently verified, forward-logged and graded rows** have accrued, examine the 10%+ versus 2-5% model-minus-market disagreement groups, including sample sizes, market mix, uncertainty intervals, paired market baselines, and selection dependence. This is an *evaluation checkpoint*, not automatic permission to add a cap or claim positive EV. Any selection-rule change requires a separate explicitly approved candidate and untouched out-of-sample confirmation.

**Release status: PAPER / 0u. No model, thresholds, formulas, or selection rules changed.**
