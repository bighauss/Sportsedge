# Stage 2 supplement — legacy MLB status claims and wager lineage

**Research only; no independent release, odds provenance, official wager validation, or production engine change.**

The connected canonical Google Sheet `SportsEdge_v1_9_Canonical_Live` was read on 2026-11-21 CT. Its `MARKET_STATUS` tab contains **20 populated market rows**: `VALIDATED=10`, `CAUTION=1`, `BLOCKED=5`, `UNBUILT=4`. All **20** report `Live_Output_Ready=FALSE`. The ten `VALIDATED` rows cite forms of historical OOS analysis, but **that sheet is a status assertion, not original holdout predictions, odds receipts or independently reproduced calibration evidence**. Historical validation (even if genuine) and live output authorization are different gates. A `VALIDATED`/Historical OOS label must never be presented as `OFFICIAL`, an executable betting selection, or admission to the prospective ROI denominator.

The original `ACTUAL_LEDGER` has 7 MLB actual wager rows totaling $90.19 recorded stake, -$73.57 recorded profit, with one win and six losses. Of these, **three are parlays: one 2-Pick and two 3-Pick**. One **3-Pick** uses `+395 boosted` as noncanonical American-odds text, and its note states a +30% promotion. Two different pitcher-K bets show the identical placed-time text `2026-08-07 5:21:29 PM`: a flag for original slip/clock confirmation, not evidence of misconduct. The previously published Stage 2 auditor correctly reports raw monetary outcomes but initially omitted `MARKET_STATUS` from its tab inventory and did not break out parlay leg labels or shared placement clocks.

This *unmerged candidate* updates only the read-only Stage 2 research audit: `MARKET_STATUS` is an optional CSV in `TABS`, self-declared `VALIDATED` and `Live_Output_Ready` statuses are counted separately, unknown readiness is not treated as true, `authenticated_official_ready_rows` and `approved_stake_u` remain zero, and ledger totals report parlay label counts, boosted price text, and duplicate placement-time groups. **No source fields are overwritten; missing original receipts and probability snapshots cannot be repaired by a status label**.

Run from a private directory with exported original tab bytes; never commit the owner workbook, raw screenshot receipts or other sensitive records to public GitHub:

```bash
python research/audit/sportsedge_stage2_readonly_audit.py --folder /private/tabs
python -m unittest discover -s research/audit -p 'test_quant_*.py' -v
```

The script emits only a create-only or stdout JSON *research report*. Seven actual MLB wagers are a descriptive real-bet ledger, not seven vetted model predictions; 4,999 `MODEL_OUTPUTS` `GATED` rows and 496 mirrored CBB price-side rows are not additional independent wagers. The 2:15 PM Nov 15 NFL eight-row pregame card is yet another separate **PAPER / 0u** cohort, not combinable with these MLB wagers. The frozen SportsEdge v5 engine, all prior results and originals remain unchanged. Independent reviewer and Gate #10 evidence remain required before any release.
