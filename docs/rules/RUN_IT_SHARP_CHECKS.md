# RUN IT — Sharp Check Add-ons

**Added:** 2026-11-21 (owner request)
**Applies to:** every "run it", every sport (NFL, CFB, CBB, NBA, MLB, NHL), every market, props included.

## Rule zero

**These supplemental checks never block, hide or delay an otherwise eligible pick.** Every "run it" still attempts the full card
(the NE@DET Munich format: Game Card + Prop Card ranked by EV, stars, flames, Key Inputs strip).
These add-ons only annotate context and may nudge the presentation rating by at most one star.
A missing *supplemental* input is shown as "n/a" and never by itself removes an eligible candidate.
Essential model/identity/price/time/provenance deficiencies remain governed by existing fail-closed
eligibility rules: show the market in the coverage/research inventory with a reason and PAPER / 0u,
never invent win probability, EV, stars, or stakes. Preserve the frozen model and original cards.

## Added to the Key Inputs strip (per game)

1. **Schedule spot** — rest days each side, back-to-back / 3-in-4 / short week, previous game
   (blowout or OT grind), look-ahead or letdown spot next game, time zones crossed. Tag: edge A / edge B / neutral.
2. **Line movement** — open → current for side and total, and the direction relative to our pick
   (with us / against us).
3. **Public side** — the side the public is likely on (brand, national TV, recent streak) only as qualitative sentiment unless timestamped bet % is available. Record actual percentage or "n/a"; contrarian flag only if
   sourced public percentage and point-in-time line movement substantiate it.
4. **Motivation** (late season) — playoff and seeding stakes, eliminated or locked teams, rivalry or revenge. Context only; no points added
   without data.

## Added under each top play (flamed or 4★+)

5. **Why is the line here** — one line: the sourced explanation or clearly labeled hypothesis for what differs from our number; otherwise "n/a".
6. **Case against** — the 1–2 strongest reasons the play loses. If the case against is clearly stronger
   than the case for, drop one presentation star; never remove an otherwise eligible pick on this qualitative check alone.

## Added to the card footer

7. **Correlation flag** — list plays that win or lose together (e.g. side + same-team overs, total +
   QB yards). Note combined exposure and flag unvalidated co-hit claims as hypotheses. This add-on imposes no new unit cap; the existing independent v2.1 exposure and sizing contract is not modified by a docs-only add-on. An owner-directed removal of those caps requires a separately versioned risk-policy reconciliation and tests.
8. **Price check** — only compare timestamped, available prices for the same event, market, line, period and settlement terms. Flag if the listed price is more than 10 American-odds cents worse than a verified alternative. A better price outside the owner-approved execution book is informational, not automatically actionable.

## Weekly (not part of daily runs)

9. **Bet autopsy / leak finder** — grade every graded pick by process vs. result (A unlucky / B missed
   something / C bad process). ROI and CLV are split by sport and market (sides, totals, props). Output 3 actionable rules.
   Produces research proposals for recalibration; never silently changes weights, frozen baselines, historical predictions or production logic. Any adoption needs point-in-time walk-forward validation and a versioned change. Never blocks daily research coverage.

Source: owner-supplied 50-prompt sharp-bettor guide (prompts #5, #6, #11, #14, #15, #16, #22, #9, #41–44).

## Compatibility and implementation status

- This change is **documentation only**. It does not implement card rendering, feeds, quote comparison, correlation estimation, weekly grading or scheduling.
- Where a supplemental annotation conflicts with a core price/identity/provenance/actionability gate, the core gate wins. An ineligible play stays visible as a reason-coded research/coverage row, not an actionable wager.
- Existing `RUN_IT_V2_1_MANDATORY_RESTORATION.md` sizing, caps, line-movement kill/reprice, and forward-evidence rules remain in effect until explicitly superseded by a separately versioned and tested risk-policy change. This add-on never applies a new cap on its own.
- Missing opening lines, real public splits, competitor quotes, or historical close observations are reported as "n/a"; no retroactive data filling or narrative certainty.
