# CBB disagreement shrinkage — preregistration (2026-11-18)

**Status:** candidate research, PAPER/0u; no real PIT input corpus, no authenticated book/close, no live weights, no formula adoption.

## Prior frozen hypothesis
Current model probabilities may be overconfident exactly where the independent projection diverges most from the book. For each **binary no-push** CBB FG/1H market decision, calibrate the originally emitted model probability only with the original **decision-time**, two-sided de-vigged market probability:

```
p_candidate = p_market_decision + exp(-a - b*abs(p_model-p_market_decision))*(p_model-p_market_decision)
a >= 0; b >= 0
```

Coefficients are not pre-selected. Candidate grid `a=(0,.1,.3,.6,1.0)`, `b=(0,2,5,10,20)` is frozen **before** unseen evaluation, using log-loss on the chronological earlier-training fold. This shape never amplifies model/market disagreement. **Closing prices never enter this formula or the fit**, only independent holdout scoring.

## Data and leakage contract
Exact JSON per decision: event, family, period, side, line/settlement, explicit venue, frozen model and prior hashes, source published/captured clocks, model fit cutoff, independent decision quote, independently captured close quote, official final and its postgame publication/capture clocks, full precision `p_model,p_prior,p_market_decision,p_market_close`, settled binary outcome.

The input schema rejects extra market/feature fields, postgame timestamps leaking into decision estimates, incomplete/hypothetical source hashes, duplicate exact decisions (all copies quarantined), unresolved grades and potentially pushable integer spread/total lines. All timestamps and SHA shapes are **caller claims**, never external source authentication.

## Evaluation contract
- Train only rows with released/captured finals strictly before an immutable fit cutoff.
- Holdout forecasts strictly on or after cutoff, no retroactive fitting.
- At least 180 distinct training events and 50 distinct holdout events **per family**, chronological 80/20 inner train/validation. Training folds cannot use outcomes released after validation begins.
- Report untouched holdout Brier/log-loss for candidate, old model, prior model, **decision-time** market and independent **close** market, identical events. Slices by direction, probability-gap band and venue, plus descriptive event-cluster normal-approximation 95% intervals.
- No claim of stronger tail calibration for alt totals, SGP or props; they are excluded.
- No acceptance from this script. Final rule must preregister and meet Brier/log-loss versus BOTH frozen prior and market-close, with family-wise multiplicity adjustment `alpha=0.05/k`, independent replication and explicit promotion. Existing >=6 score-point disagreement guard remains unchanged.

## CLI
```bash
python research/audit/cbb_disagreement_shrinkage_shadow.py /private/cbb_forward_decisions.json \
  --cutoff-utc 2026-11-18T00:00:00Z \
  --report /private/new_disagreement_shadow_report.json
```
Private inputs and create-only report stay outside public Git checkout. This is not a replacement for true witnessed Torvik-vintage and official original quote captures. Issue #329.
