# SportsEdge — locked risk policy (research-only)

Policy ID: `SPORTSEDGE_RISK_V2_1_OWNER_LOCK_2026-11-15`  
Source of authority: `docs/rules/RUN_IT_V2_1_MANDATORY_RESTORATION.md`, not a later unapproved candidate.  
Decision: **v2.1 is the binding risk specification.** Previous R1 candidate defaults (4u/day, 1u/game, 0.75u/signal, flat 1u grading) are superseded. The model-selection label **v2.2** in `nfl/audit/AUDIT_NFL_2026-11-15.md` is a *research candidate* adding a six-point market-gap HOLD; it is **not** a separately adopted cash-risk schedule and does not change this lock. No verifiable alternative v2.2 per-game cap was supplied, so no unsupported number is silently inferred. Any future stricter approved cap must receive its own reviewed versioned amendment.

## Exact binding calculation

- Evaluation is **PAPER / 0u**: `approved_stake_u = 0`, `official_counted = 0`. Any nonzero quarter-Kelly output is named `diagnostic_u` and is not an authorization to bet.
- Market blend: `p_blend = 0.30 * p_model + 0.70 * p_market_novig`. No independently verified no-vig market probability = no stake diagnostic. For push-capable outcomes, use win/loss/push probabilities rather than a binary approximation.
- Initial diagnostic size = one quarter of full Kelly converted from bankroll dollars to units; initial band **0.25u–1.5u** only when a strictly positive blended EV, authentic exact quote, independent model evidence and all essential inputs are present. EV <= 0 or missing input = 0u. LOW confidence halves the initial size and drops one star. Negative aggregate comparable CLV on the sport's *last 50 eligible closes* applies another half-size modifier.
- Absolute caps: **5u per America/Chicago capture/decision date across all sports/runs; 2u per game; 3u per correlated theme**. All actual liability counts, even when several correlated legs are one decision cluster. A game held for Monday but quoted Sunday counts toward the Sunday daily budget. Never reset by rerun or by market relabeling.
- Source/eligibility: 90-minute injury/lineup lock, confirmation gates, price movement repricing, all-market inventory including uncaptured/unsupported markets, strict source/market/time identity. No independently priced SGP without a joint distribution and quoted combined payout. No auto-wager, withdrawal or production execution.
- Never modify or retroactively re-grade frozen v5 or historical records to optimize policy. A risk-rule change requires a new policy ID, diff, tests, independent review and prospective-only effective date. Do not relabel retrospective 2026 research as verified PIT.

## Enforcement and outstanding evidence

`research/risk/v21_risk_contract.py` is the existing *diagnostic* implementation and remains untouched. It is not wired as a proven end-to-end live release guard. `research/freezes/verify_code_freezes.py` pins the audited source version(s) as code baseline(s), but does not prove quote origins. Gate A–E and Issue #10 remain open; no official eligibility follows from the policy lock, CI or pinned hashes.

Hard release state: `PAPER_0U` until authenticated original DK and independent second-book receipts, verified point-in-time team/player inputs, registered chronology, genuine matched CLV, the full risk ledger, and signed promotion review are available. Fail closed rather than translate a missing fact into approval.
