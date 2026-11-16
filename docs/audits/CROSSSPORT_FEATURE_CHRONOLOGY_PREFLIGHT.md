# Cross-sport feature publication / no-lookahead preflight

**Research only — PAPER / 0u, never a betting authorization.**

Use this in the **private data workspace** before running the historical top-20
or calibration tools. No actual odds, player data, model inputs, source snapshots
or grading ledgers belong in this public repository.

## Inputs

Two immutable, already-frozen CSVs with **UTC** timestamps:

- Predictions: `selection_id,sport,event_id,market,model_asof_utc,quote_captured_utc,kickoff_utc,model_sha256,quote_sha256`
- Features: `selection_id,feature_id,published_utc,captured_utc,source_sha256`

`selection_id` is a unique *original* prediction identity, not a value
reconstructed from the eventual result. Each feature is joined by this exact
ID and may appear only once for that ID. One price/line/period variant must
never borrow another variant's feature manifest.

The code blocks future-published injuries, projections, team statistics or
other features; impossible publication/capture order; model-after-quote or
quote-after-kickoff times; duplicate predictions; duplicate feature versions;
absent features; malformed hashes; and non-UTC timestamps. It **retains**
every blocked prediction and any orphan features with explicit reasons.

Run:

```bash
python research/audit/feature_chronology_preflight.py \
  /private/frozen_predictions.csv /private/frozen_feature_manifest.csv \
  --output /private/new_chronology_report.json
python research/audit/test_feature_chronology_preflight.py
```

The output is create-only and uses `chronology_consistent_unverified`, not
`authenticated`, `verified` or `bet_approved`. The original files are
never modified; the script does not use results or other postgame information.

## Remaining hard gates

1. A 64-character hash **format** does not prove the original file bytes were
   checked; verify the frozen source against actual private bytes separately.
2. A locally asserted publication date, quote timestamp, provider identifier
   or bookmaker label is not external authentication or independent WORM.
3. This is a feature-clock sanity check, not a proof the quoted betting price
   was available or the projected probability was calibrated.
4. For player props, the independent player/team/status/roster binding check
   remains required. A feature merely matching `selection_id` is insufficient.
5. Combine with PR #75's private TAKE/CLOSE quote source checks, PR #68's
   event/result ledger, PR #71's G2/G3 audit and PR #74's chronological
   out-of-sample evaluator after independent source and exact-head review.
6. Never alter historical probabilities or use postgame outcomes to choose
   candidate thresholds. Unresolved source evidence means non-counted PAPER.

No production models, stake controls or cards are modified by this proposal.
