# SportsEdge RUN IT policy — historical v2.2 addendum with later stricter-cap direction (2026-11-15 CT)

**Current selected game cap: 2u (stricter-of-v2.1/v2.2 directive).** The owner later instructed the team to adopt the **stricter** of the documented v2.1/v2.2 per-game risk limits and freeze it. v2.1 had **2u/event**; the prior v2.2 addendum had **no event cap**. Thus **2u/event** is the selected stricter limit, not 1u and not unlimited. This file preserves the earlier dated v2.2 addendum for audit, not as a superseding cap authorization. No owner directive authorizing a new 1u cap has been established. See [RISK_POLICY.md](../../RISK_POLICY.md) and [Gate E current decision trace](../evidence/CARD_POLICY_VERSION_CONFLICT_HOLD.md).

**Status: HISTORICAL ADDENDUM PLUS ADDITIVE GUARDS; NOT LIVE BETTING APPROVAL.** The policy controls cover **all sports and all offered markets** for research labels and future risk implementation. Engine `engine/sportsedge_v5.py`, historical forecasts/odds, and all previous ledgers remain unchanged. **All outputs remain PAPER / 0u; no automated wagers or certified markets.** Only an independently reviewed release can change that.

## Original authority and precedence

On Nov 15, 2026 at approximately 19:15 Central, the owner adopted the v2.2 proposal. Original preserved owner-adoption handoff: [RUN IT STANDARD v2.2 ADOPTED](https://drive.google.com/file/d/1TAgJXaXTo-4M-MJxWWoOp0rPw5mNdmeM/view). It explicitly **adds to** v2 + NGS + v2.1 and **overrides the conflicting 2u-per-game cap**. Do not interpret an agent's statement or this public document as an independent cryptographic signature.

**Chronological precedence:** v2.2 was adopted as an addendum at about 19:15 CT. A later owner direction selected the **stricter** documented per-game cap, making **SPORTSEDGE_STRICT_V21_V22_20261115_R1** the selected research risk policy with the **2u event ceiling**. Preserve the original v2.2 source and its no-cap language as historical evidence; don't rewrite earlier selections or backfill prior staking decisions. Neither v2.1 diagnostics nor the v2.2 standalone preview can certify release; live card and ledger policy Gate E remains OPEN.

For historical reading, v2.2 originally proposed overriding the conflicting cap. **That clause is superseded by the newer stricter-owner directive**; other additive v2.2 rules remain evaluated alongside nonconflicting mandatory v2.1 rules: quarter-Kelly from the 30/70 blend, 5u per CT decision day, 3u per theme, confidence adjustments, T-90 locks, lineup/price-movement repricing, 50 matched negative-CLV half-sizing, prop participation minimums, and risk/audit footer. **The historical v2.2 addendum had no per-game cap, but the current selected strict policy retains 2u per event.** A correlation cluster cannot be used to evade the actual aggregate cap. A cluster is not permission to ignore actual daily or theme exposure.

## v2.2 changes — order of operations

1. **Ratings-half missing:** when the ratings half of a 50/50 team projection is explicitly absent, shrink its independently sourced model probability toward an independently sourced, same-line, paired no-vig market probability: `effective_model_p = 0.5 * original_model_p + 0.5 * no_vig_market_p`. Do this **before** `blended_p = 0.30 * effective_model_p + 0.70 * no_vig_market_p`. Mark LOW confidence. If the remaining model, source, quote, or participant is missing/unauthenticated, **block**, not silently replace it with market-only probabilities. Do not use a missing-ratings flag as a loophole for missing essential inputs.
2. **Gap guard:** an absolute model-vs-no-vig probability gap **greater than 12 percentage points** is a **0u gap hold**, even if arithmetic EV is positive. To avoid suppressing a large pre-shrink disagreement, future integration must retain both original and effective gaps and block if either is above 12pp; this is a conservative implementation decision requiring explicit review if changed. An independently measured projection-versus-market difference above 3 **points** gets a visible flag; this is not the same unit as a probability gap. Missing points-scale comparison must be labelled unavailable, never fabricated.
3. **Long dog ML:** a moneyline underdog quoted **+200 or higher** has a **maximum hypothetical 0.25u** until 50 **independently matched, graded** dog-moneyline CLV observations establish positive aggregate CLV. An unverified claimed count or aggregate cannot lift the cap. With current Gate A–E HOLD, **approved stake remains 0u regardless**.
4. **Correlation:** all entries sharing an event get one correlation-cluster identity. **Historical proposal had no 2u per-game maximum; the later stricter owner instruction retains the current 2u per-event actual liability limit.** Daily 5u and theme 3u remain. Preserve unique original decisions and all mirrored/alternate rows without double-counting.
5. **All markets:** show per-event/per-family offered/captured/priced/blocked/not-observed status and reason. Grade props including 0u research rows; do not promote a synthetic source or an unavailable quote.
6. **Pregame evidence:** ratings half, pace, weather, confirmed inactives and market/time-specific roster inputs at the T-90 decision lock; unresolved essential source evidence is a hold. Never invent publication or observation timestamps.
7. **Footer:** every new research card states the **selected strict v2.1/v2.2 policy ID** and which historical v2.2 addendum checks were applied, original model SHA, quote/source receipt clocks, applied holds, risk-decision provenance and **PAPER / 0u**. Review after 50 genuinely graded observations per sport; no automatic refitting or promotion.

## Acceptance gates — unchanged and all OPEN

**A:** independently authenticated, source-distinct DK + secondary original two-sided offers, exact event/market/period/line/participant identities and original UTC receipt; manual permissioned collection is allowed but a manually entered number or hash is **not** independent provider authentication. No reverse-engineered or guessed BestBook APIs. Free Odds API quota is insufficient for full all-market production.

**B:** source-frozen, event-specific, pregame input provenance; missing/late/unverified QB, player, injuries, pace, weather or lineup evidence blocks the dependent market.

**C:** as-of walk-forward calibration with source-publication chronology, frozen model/config, preserved losses and excluded rows; three clean preregistered cycles.

**D:** same-market genuinely sourced TAKE/CLOSE price receipts, 200 settled matched comparisons with no-vig CLV, no fabricated close.

**E:** integrate the **owner-selected stricter 2u/event** cap together with additive v2.2 safeguards across the actual candidate/card/ledger flow, test all risk and duplicate controls, then capture 100 clean consecutive real-slate cards. A stand-alone policy test or a new 1u or no-cap proposal is NOT Gate E evidence; full end-to-end review is required.

Whole-program: at least five full continuous real-slate days, 200 qualified settled selections, independent review and explicit signed per-market promotion. All markets remain blocked from official release, even if a standalone script passes synthetic tests.

## Immediate deterministic checks

`research/risk/v22_policy_guard.py` is an isolated **read-only research preflight**, not a live stake calculator. It must (a) retain v2.2 version and 0u, (b) report both gap stages, (c) hold large gaps, (d) disclose missing ratings LOW, (e) retain the +200 dog cap when evidence is missing, and (f) have no game-cap field in its normative caps. It cannot authenticate a source and cannot turn a single self-attested flag into acceptance. Review its tests separately from the original v2.1 historical code.

**Follow-on engineering, not silently included in this historical addendum:** route all card writers and risk ledgers through the selected stricter versioned policy, store immutable policy choice with each original decision, independently validate matched CLV for the long-dog threshold, and update Gate E wording/code/tests in a separately reviewed PR. Keep Gate E **OPEN** until that is complete.
