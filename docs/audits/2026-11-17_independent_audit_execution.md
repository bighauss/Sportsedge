# SportsEdge independent audit execution — 2026-11-17

**Status:** Audit candidate only; no official releases or evidence-based model promotion.

**Source baseline:** bighauss/Sportsedge main \`8d258203e0a090330885fbb9bbbb9dd5b186523a\`, repository source/model tests, read-only Drive \`EDGE_AUDIT.md\`, corrected G-18 calibration report, and November 15 NFL grade publication. All source-date and original-bookmaker authenticity gaps remain.

## Scope of the first patch (PR #292)

1. Fail closed on same-name CBB prop collisions across event teams; optional \`team\` and \`player_id\` must match the event's roster record. Out-of-event or missing players generate auditable dropped reasons instead of first-match pricing.
2. Independent read-only selected-decision grader calculates win/loss/push using the original American odds and explicit stake units. Missing stake is not silently replaced by 1u; duplicate bet IDs are all excluded; pending rows are not settled; 0u paper rows do not contribute real P/L.
3. A synthetic nine-row test reproduces the November 15 NE@DET *published arithmetic inconsistency*: six one-unit losses plus three wins at -105/-126/-107 are approximately -3.32u, not the published -4.32u. This is not a signed raw-wager replay.
4. CI runs the standalone CBB synthetic test suite and seven independent grade tests. The historic predicted probabilities, weights, frozen v5 engine, previous grades and original capture records are not altered.

## Exact audit limitations

- The standalone CBB model's CSV \`player\` name alone cannot authenticate a player; this candidate merely avoids known false matches and supports optional external stable IDs.
- The grader operates only on the selected-decision CSV supplied to it; it does not prove that a sportsbook quote was available, reconstruct missing bets, independently authenticate a bookmaker, or prove the census is complete.
- The historical G-18 team-total grading defect needs separately archived correct grading; never mutate old cards. The old 496 priced rows from three CBB games are not 496 independent wagers.
- Odds-derived ANCHOR, untested sport coefficients, model-vs-market disagreement thresholds, correlated SGP distributions and 30/70 blend remain research hypotheses, not proven +EV.
- The Gate A-E accepted forward sample still requires permitted original sources, point-in-time source publications, chronological calibration, genuine closes and end-to-end v2.1 guard evidence.

## Test matrix for following candidates — no baseline changes

| Priority | Candidate | Historical check | Untouched forward acceptance |
|---|---|---|---|
| P0 | All sports PIT leakage and stable identity | Rebuild from published <= captured <= model frozen < kickoff original input snapshots; reject future/ambiguous row injections | Zero future leakage or silent player/event mapping on newly frozen authentic slates |
| P0 | Grading, stake/ROI, G-18 | Regrade original selections with exact market settlement; reconcile all report subtotals and duplicate/mirror rows | Independent grade runs match event-clustered official records, no missing losses |
| P1 | CBB standalone vs v5 distributions | Freeze both models and compare full-board Brier, log loss, residual variance and interval coverage by period/market | Beat no-vig baseline without extreme tail miscalibration |
| P1 | MLB starter/lineup and book pairing | Remove starter/lineup, cross-pair two different books or lines; verify rejected candidate | Authenticated roster and exact same-book opposite offer required |
| P1 | NBA/NHL props identity | Duplicate same-name players and game IDs; verify no cross-event joins | Verified stable roster/team/player IDs, usage, minutes and starters |
| P1 | Anchor and market blending | Compare frozen independent-only, market-only and the recorded blends on same PIT games | Improvement in proper scoring rules vs no-vig market across complete event clusters |
| P2 | Complexity ablations | Remove one feature family at a time on chronological training folds; never retune on holdout | Retain only repeatable calibrated improvements |
| P2 | Selection and directional bias | Include all attempted and blocked rows; audit dog/favorite and over/under Brier, log-loss and CLV by clustered event | No cherry-picking from alternate price ladders or 0u paper portfolio |

**Acceptance principle:** a new formula/weight/feature or market release needs a new versioned candidate, preregistered evaluation, untouched unseen period, independent review and explicit authorization. Green synthetic tests alone are not predictive proof.

## Usage

\`\`\`bash
python models/cbb/test_cbb.py
python -m unittest discover -v -s research/audit -p 'test_grade_reconciliation.py'
python research/audit/grade_reconciliation.py /private/selected_decisions.csv --claimed-net-u=-4.32
\`\`\`

Required selected-decision CSV columns: \`bet_id,event_id,price_american,stake_u,outcome\` (W/L/P/PENDING). The private CSV is not committed to this public repository. A nonzero CLI exit marks blocked rows or a report-total discrepancy.
