# Owner decision: canonical migration and RUN IT v2.1 acceptance status
**Decision date:** 2026-11-16 CT  
**Repository:** `bighauss/Sportsedge`  
**Coordination:** [Agent relay #57](https://github.com/bighauss/Sportsedge/issues/57)  
**Gate tracker:** [Hard gates A–E #10](https://github.com/bighauss/Sportsedge/issues/10)

## 1. Canonical repository: clean move; preserve evidence

`bighauss/Sportsedge` is the active engineering repository. Do **not** wait for the suspended/unavailable historical `isaacrome21-sys/SportsEdge` account, fabricate that repository's history, or rewrite the new repo's Git history to imply restored ancestry.

Retain all verifiable legacy artifacts, original captured bytes, ZIP exports, SHA-256 manifests, and point-in-time data in access-controlled archival storage, with exact source attribution and uncertainty labels. Historical material is not automatically authenticated by copying it into this repository. Import specific verified, non-sensitive code or docs via reviewed PRs and annotate origin. Never publish private sportsbook boards, account credentials, personal data, or confidential receipts.

Connector-based GitHub read/write is the current agent workflow. A stale local `gh` login is an independent environment issue, not evidence the connector failed. Reauthentication of local CLI requires authorized interactive login; do not reuse tokens from the old account.

## 2. RUN IT v2.1: binding policy/specification, not certified implementation

`docs/rules/RUN_IT_V2_1_MANDATORY_RESTORATION.md` **stands** as the owner's required rulebook alongside the sport-specific v2 standards. It is **not** evidence that software implements or enforces those rules end-to-end.

Required controls include:

- All-event/all-offered-market inventory with explicit unoffered/unverified/unmodeled/refused categories.
- Blend, raw and blended EV, push-aware quarter-Kelly and fail-closed 0u treatment when inputs are missing.
- Exposure caps of 5u/day, 2u/game, 3u/correlated theme; independent correlation/SGP evaluation.
- HIGH/MEDIUM/LOW confidence with documented adjustments, T-90 injury locks, lineup/goalie verification, material quote movement reprice/kill.
- Negative CLV size reduction on the last 50 **matched eligible** closes, prop opportunity minimums, and sport-specific numerical override logic.
- Immutable forecast/card evidence, code/rule version stamps, sources, capture times, exclusions and grade at recorded units.

**Important:** the stated coefficients, interpolation weights, regression windows and quantitative cutoffs are owner-specified *starting assumptions*; they have not thereby demonstrated predictive validity or positive EV. Validate on prospective, chronologically frozen evidence. Testing or tuning must never rewrite original historical predictions.

## 3. Release state and guardrails

- Frozen record engine: `engine/sportsedge_v5.py` SHA-256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`. Do not silently modify.
- The README and `docs/MIGRATION.md` explicitly say v2.1 is **not yet enforced end-to-end**.
- All not-yet-certified markets: **PAPER / 0u**. No official +EV or live-wager claim merely from synthetic green CI, third-party projected hit rates, or source reconstruction.
- Issue #10 Gate A–E is the release acceptance authority: original sportsbook-source evidence, genuine pregame point-in-time inputs, chronological calibration, authenticated matched closes and complete v2.1 guard enforcement; per-market independent review and signed promotion required.

## 4. Agent execution rules

All agents use `bighauss/Sportsedge` and coordinate directly in #57; the phone-only owner should not have to relay messages. Make isolated PRs with adversarial tests; reference actual files, exact observations, timestamps and gate status. Keep the controls as binding requirements while identifying any present noncompliance as work-to-do, not a certification. No agent may unilaterally weaken a hard gate to make the slate appear ready.

This decision clarifies repo governance and acceptance semantics only. It does not change model weights, bets, quoted odds, frozen predictions, archived evidence or stakes.
