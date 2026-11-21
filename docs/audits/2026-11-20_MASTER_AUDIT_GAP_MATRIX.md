# Master SportsEdge audit gap matrix — 2026-11-20 CT

**Research-only; frozen v5 unchanged; all official markets PAPER/0u.** This is a source-aware inventory as of inspected main `15ed244640595193fe8fe339bf71ce624d073043`, the cited open PRs and historical Drive audit summaries. A green synthetic unit test does **not** certify a prospective betting edge.

## Core constraints

1. Every non-market adjustment requires documented effect size, date-vintage, uncertainty and sample count; no narrative-only adjustments.
2. Every training/feature/roster/odds/selection decision must be provably available **as of original decision UTC**; later reconstructions are not contemporaneous source attestations.
3. No offer becomes certified +EV until original independent book quotes, exact no-vig pairing, fitted/calibrated model probability and market-specific admission pass.
4. Do not edit original odds, decisions, grades, models or frozen `engine/sportsedge_v5.py`; corrected ledgers and alternative model candidates are new immutable versions, forward-tested and owner-approved.

## Scope and independent validation

| Module | Current state | Existing implementation / evidence | Missing proof and independent acceptance |
|---|---|---|---|
| P1.1 Largest-edge stress | PARTIAL | `research/audit/pregame_edge_audit.py`; [draft #355](https://github.com/bighauss/Sportsedge/pull/355) supplies flagged-claim top20 and independent-game concentration | Recover original frozen provider/forecast bytes for full historical census; test top 20 without result filtering; independent case-by-case error classification |
| P1.2 Leakage detective | PARTIAL | `quant_evidence.py`, `quant_capture_preflight.py`, [draft #347](https://github.com/bighauss/Sportsedge/pull/347), stacked [draft #351](https://github.com/bighauss/Sportsedge/pull/351) | Original signed/observed published clocks, effective qualification rules, selected UTC and quote-age proof; exact-head tests and independent review |
| P1.3 Calibration | PARTIAL | Brier/log loss, [draft #348](https://github.com/bighauss/Sportsedge/pull/348) matched-row paired Brier | Same **decided** quote-matched observations for both models; event-clustered uncertainty with preregistered minimum events; three clean chronological cycles |
| P1.4 CLV | PARTIAL | Read-only ledger and close matching scaffolds | 200 settled source-authenticated original offer/selection/closing triples; verify same market/line/period and no imputed closes |
| P1.5 Performance/drawdown | PARTIAL | `quant_evidence.py`, `quant_foundation.py`, historical Nov9 G-18 corrected ledger | Reconstruct unique preregistered selection denominator; keep all losses, mirror priced rows and blocked predictions; true original grades and settlement |
| P1.6 Bias/feature importance | RESEARCH | Historical residual and sport analyses | Chronological locked ablations against simple model, no-vig close; stratified effect size/CI by sport, market, team, player, direction |
| P2 Independent game projections | PARTIAL | NFL/CFB/CBB projection bridges, #340 and #343 merged | Real pre-start features, independent scores/TTs/per-period score distribution, market-agnostic model calibration and completeness census |
| P3 Prop / joint probabilities | PARTIAL | Historical player mean research #345/#346; [open #330](https://github.com/bighauss/Sportsedge/pull/330) joint Brier evaluator | Original player roster/activity, full pregame line-specific probabilities, jointly frozen predictions and outcomes, paired sample OOS validation |
| P4 Fair odds, no-vig, EV, alts | PARTIAL | Odds arithmetic / push-aware scenario pricer | Original book dual-sided prices, exact settlement, historical key-number mass, independent secondary source and same-line matching |
| P5 Rest, injury, weather, travel | RESEARCH | Sport/venue/availability intake guards | Pre-registered lift/effect-size and time-vintage by sport with no postgame injury/lineup contamination |
| P6 Exposure and bankroll | PARTIAL | Recovered v2.1 `card_gate`, risk diagnostics | Complete candidate-to-card invocation proof, daily/game/theme caps, correlated portfolio simulation, 100 clean cards |
| P7 Live/prediction markets | RESEARCH | Isolated research | Authentic source latency, fair settlement and market-specific forward calibration; no live emission |
| P8 RUN IT operations | PARTIAL | `run_it_research.py`, screenshot handoff #344, full-slate research matrix | Live original permissioned capture, private immutable archives, all-family coverage ledger, independent final-grade and 100 clean end-to-end runs |

## Independent historical forensic observations

- Saved `census.json` has **716 priced records**: 496 portable Nov9, 102 Nov4 morning Lane A, 65 Nov9 CBB, 24 Nov4 PM CBB, 23 Nov4 AM CBB, 6 Nov9 Lane A. These are not 716 independently qualified bets.
- The top **20** by stored claimed EV span **7 games**; 9 Mississippi Valley–Washington and 6 Rice–Stanford **(15 of 20)**. Source model input defects and alt ladders explain why these are not 20 independent edges.
- Naive `p × decimal - 1` differs from 6/716 stored EV records. Two opposite ±3 spread rows have a common ≈2.037 pp residual plausibly due to pushes; four 1H ML rows require original tied-period/settlement probabilities. **No correction applied**.
- Nov11 preserved card (65 CARD + 10 DOUBTED) has two rounded-display discrepancies beyond rounding tolerance: 1H UTSA ML +470 and 1H California ML +200. Before claiming an EV calculation defect, inspect unrounded W/P/L and push treatment.
- **Binding G-18 correction:** Nov9 180 TT rows used wrong game-total grader and 70 of 496 graded rows flip in corrected ledger. The original all-row top 0.9–1.0 model-p bucket is **underconfident** after corrected grading (mean forecast 0.9309, realized 1.0000), reversing the earlier buggy top-bucket overconfidence claim. These results reflect **3 games** and pre-home-court-fix projection code; not a valid calibrator.

## Execution gates / dependency order

- **Now:** Hold independent-approval-required drafts #347/#348/#349/#351/#330 until review issues and exact-head CI are resolved. #351 is stacked on #348. No self-review counts as independent.
- **P1 release:** Complete adversarial top-20 forensic claimed-edge checks, source and selection-time guard regressions, no outcome-based removal; preserve source bytes.
- **P1 calibration:** Clean-room G-18 grade reconciliation; exact-row matched market Brier vs model; correlated outcomes clustered by event, *not priced rung*.
- **P2/P3:** Real permissioned pregame data packages, independent sport-specific score and stat distributions, explicit `NO_MODEL` and `NOT_CAPTURED` for missing families.
- **Forward acceptance:** Issue [#10](https://github.com/bighauss/Sportsedge/issues/10) Gate A–E remains the only path to any market release. Its 100-card / 200 close / five-day / three clean cycle requirements and signed independent acceptance stay intact.

## Boundary

This document does not incorporate private original quote bytes into public GitHub. No provider login, odds API key, source authority or grading result may be invented. No real historical profitability or certified picks claimed.
