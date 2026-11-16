# SportsEdge per-sport / per-market release-gate register
**As assessed 2026-11-15 Central / 2026-11-16 UTC. Read-only engineering record.**

**Official released markets: NONE. Approved unit stakes: 0.** All five acceptance gates A–E remain **OPEN** for *each* market below. A model's existence or a passing synthetic test is not a market promotion. The frozen v5 engine and original historical outcomes stay immutable. These are evidence statements, not estimates of team strength, edge, win rate, ROI or profitability.

## Per-sport market inventory and next technical blocker

| Sport | Priority | Main FG sides / totals / ML | Team totals | Player props | Periods | Specialty / alternates / SGP | Primary next blocker |
|---|---|---|---|---|---|---|---|
| NFL | 1 | RESEARCH | RESEARCH | UNCALIBRATED | UNCALIBRATED | TD/first TD/2+ TD and SGP BLOCK | Original pre-event PBP/EPA and lineup/quote chain, freeze and forward score+prop distributions |
| CBB | 2 | RESEARCH | RESEARCH | UNCALIBRATED | UNCALIBRATED | First basket, alternates/SGP BLOCK | Genuine Torvik as-of releases, original quote/grade ledger, prospective frozen finals and #175 receipts |
| CFB | 3 | RESEARCH | UNCALIBRATED | UNCALIBRATED | UNCALIBRATED | TD, alts/SGP BLOCK | Permissioned CFBD as-of ratings/roster, complete DK quotes, chronological evaluation |
| NBA | 4 | RESEARCH | UNCALIBRATED | UNCALIBRATED | UNCALIBRATED | First basket, alts/SGP BLOCK | Real lineup/availability/minutes/usage and empirical prop tails, authentic book receipts |
| MLB | 5 | RESEARCH | UNCALIBRATED | UNCALIBRATED | UNCALIBRATED | NRFI/YRFI/HR/F5, alts/SGP BLOCK | Actual 2026 pregame starter/lineup/Statcast snapshots, inning outcomes and quoted markets |
| NHL | 6 | STANDALONE RESEARCH | UNCALIBRATED | UNCALIBRATED | UNCALIBRATED | First goal, alts/SGP BLOCK | Confirmed goalies, MoneyPuck as-of, source-proven quotes and pricing-kernel integration |
| PGA | 7 | TOURNAMENT SIM RESEARCH | N/A | N/A | ROUNDS UNCALIBRATED | Outrights/top finishes/matchups/FRL/DFS BLOCK | Authorized real DataGolf original response, actual pre-event odds and empirical forward calibration |

This matrix is *not* an offered-market inventory for any particular sportsbook slate. **NOT OFFERED can only be asserted from an authenticated complete event/market inventory**. A market absent from our capture is **NOT CAPTURED / OFFER UNKNOWN**, never silently treated as unavailable or zero value. The current five-sport pricing orchestrator does not cover NHL or PGA; its standalone model files do not make those markets release eligible.

## The gate matrix — applies independently to EVERY listed sport/market combination

| Gate | Current state | Minimum evidence to change state | Known gap |
|---|---|---|---|
| A — Authenticated odds | OPEN | Real two-sided DK original offers, matched independent upstream original second book, exact quote event/market/period/line/player identity, observed and captured UTC and original SHA; 100 consecutive real-slate cards without missing admitted prices | No independently authenticated DK/second-book end-to-end feed. An aggregator displaying DK does not count as an independent second source |
| B — True pregame inputs | OPEN | Freeze every used QB/team/player/weather/tempo/injury/status source before decision, 95% complete independent PIT packages on multi-day real slates; all incomplete rows blocked | Public retrospective season releases cannot prove an older prediction's historical availability |
| C — Chronological calibration | OPEN | Frozen coefficients/selection rules; three preregistered leakage-free walk-forward cycles; market-only and independent-only baselines; original W/L/P/exclusion census and uncertainty | Synthetic tests and retrospectively recomputed scorecards are not forward validation |
| D — Closing-line integrity | OPEN | 200 independently auditable settled identical-selection TAKE/CLOSE pairs (ideally open/take/close triples); no-vig CLV and retained unmatched rows | No verified matched original closes at required scale |
| E — Connected guards | OPEN | One versioned end-to-end v2.2 candidate-to-card/ledger policy with duplicates/locks/market controls, 100 consecutive compliant real slates and signed release record | The existing v2.1 research gate has 2u/game while adopted v2.2 explicitly has no game unit cap; #186 is an isolated paper-policy candidate, not wired production certification |

Whole-program release also needs **at least 5 full continuous days** meeting gates, **200 settled selections**, independent review and explicit signed **per-market** promotion. No automatic wagers.

## This week's ordered checklist (one factual status per item)

1. **Gate A authorized source path — BLOCKED ON UPSTREAM ACCESS.** Code for permissioned raw exports and The Odds API research captures already exists. Do not depend on the $0 Odds API for full-slate, all-market production; its quota cannot cover the target. Prefer directly licensed/documented DK original exports and a distinct second-book original source. User-authorized manual lines can be archived as **MANUAL_UNVERIFIED / PAPER** with typed CT and UTC observation/capture, exact market key, source and quote disposition; a screenshot, manually entered number or local hash does not authenticate the upstream book. Never guess DK/BestBook endpoints, scrape behind login, copy provider secrets to public GitHub, or claim an automatic DK feed is connected. **Credential/permission setup is a user-controlled step.**
2. **Policy lock — PR #186 review in progress.** Owner-adopted v2.2 source [Drive handoff](https://drive.google.com/file/d/1TAgJXaXTo-4M-MJxWWoOp0rPw5mNdmeM/view). Research 0u remains; actual card gate must be reconciled with v2.2 in its own tested PR, not silently accept the stale 2u cap as v2.2.
3. **CBB G-18 — PARTIAL REPRODUCTION ONLY.** Historical original board 248 quote rows and saved 209 printed selections have a 209/209 join. The separate 496-priced-side file and contemporaneous original `run7_finals.json` were **not located** in the currently searched shared Drive files; a 496-row retrospective census cannot replace them. G18 70 flipped grades remain historically unconfirmed until original bytes recovered. No re-simulation with current v5 may be presented as the original forecast. [Current forensic note](https://github.com/bighauss/Sportsedge/issues/80).
4. **CBB original-to-final integrity — CODE MERGED, SOURCE NOT YET ATTESTED.** [PR #175](https://github.com/bighauss/Sportsedge/pull/175) now merged; raw provider payload and manifest join required, tampered or suppressed derived finals blocked. This does not obtain a CBBD account, prove external publication time or re-create original missing Nov 9 grading files.
5. **NFL and CBB freeze/grade — PARTIAL SOFTWARE, NOT COMPLETED CLEAN FORWARD SET.** Use original before-kickoff model/source/odds package and after-game separate authenticated score receipts. Never treat published-after-game revisions as originally available. Keep previously failed/blocked rows in denominator. NFL real public weekly/NGS/PBP archives help future capture but are not event-specific frozen history.
6. **Next untouched forward set — OPEN.** NFL first, CBB second; evaluate model score and no-vig market Brier/log loss, MAE, original-price push-aware paper units, signed direction bias, game-cluster confidence intervals and comparable CLV. No parameter tuning on that holdout; any tuning creates a new version and a new future holdout.
7. **Other sports — RESEARCH IN PARALLEL, NO RELEASE SHORTCUT.** CFB → NBA → MLB → NHL → PGA, with same A–E evidence contract; special/prop/period markets gate independently of game lines.

## Daily repeatable evidence flow

**Before games:** authenticate and archive source/quote bytes privately, immutable event/family coverage census, freeze model and all inputs with exact as-of timestamps. **After games:** independently capture actual outcome, grade every frozen selection at the original price and 0u or original disclosed paper stake, retain all blocked/missing/losing records. **Periodically:** run pre-registered forward evaluator, report every A–E gate as OPEN/PASS with the actual supporting attestation, route reviewed code changes through CI and independent review. Never rewrite historical outcomes to improve ROI.

### Scope and limits

- A matrix entry `RESEARCH` means code exists for computations, not proven probabilities, available real quotes or an eligible bet.
- No connected/verified paid or free provider credentials, DraftKings user access, authorized BestBook export or signed promotion record was established by this review.
- Retain original quotes/results in private source storage; public GitHub contains only sanitized code/fixtures/metadata.
- This document is dated and must not be cited as today's live odds or real-time market inventory without a fresh independent capture.
