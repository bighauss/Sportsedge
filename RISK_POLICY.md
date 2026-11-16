# RISK_POLICY.md — SportsEdge 2026-11-15 locked safety policy

**Effective date: 2026-11-15 (America/Chicago).**  
**Policy ID:** `SPORTSEDGE_RISK_2026_11_15_LOCK_V1`.  
**Status:** binding safety policy for all research lanes; execution remains **PAPER / 0u**.

## Conflict resolution: v2.1 versus the proposed v2.2 risk cap

- The owner-restored v2.1 document sets **2.00u per game**, **5.00u per Central decision day**, **3.00u per correlated theme**.
- The previously documented stricter R1 candidate sets **1.00u per game**, 4.00u/day and 0.75u/signal, but the *actual* v2.2 NFL report only documents a six-point disagreement HOLD; it does **not** establish a verified alternative v2.2 per-game numerical cap. Do not mislabel the R1 values as independently verified v2.2 values.
- **Conservative decision: lock the stricter demonstrated game cap, 1.00u per event/game.** All other owner-restored v2.1 parameters remain binding: 5.00u per CT decision day and 3.00u correlated-theme maximum. A selection must meet **every** limit; the 1.00u game cap is an additional tightening over v2.1, not a relaxation or quiet replacement of its other safety gates.
- This supersedes the earlier `RISK_POLICY_LOCK.md` draft's 2u game statement. Frozen v5 and historical decisions are not rewritten. The NFL v2.2 model candidate is not promoted.

> **No silent changes. Any future change requires explicit PR + version bump.**

## Sizing and release

Initial research sizing: **quarter Kelly** from blended probability 30% independently modeled + 70% independently verified no-vig market, priced at the originally timestamped DK offer, with an initial 0.25–1.5u band if positive EV. Then apply required LOW-confidence and trailing-50-comparable-CLV half-size modifiers. Explicitly model pushes, SGP dependence and actual correlated exposure. A 1.5u initial diagnostic can be capped to at most **1.0u total for its game**; never rescale the 1u cap per leg or per card. True exposure sums across independent legs, markets, reruns, and all sports on the CT quote/decision date.

Every accepted candidate requires identified pregame quote/source, model, lineup and time-chain, T−90 injury lock, all-market inventory, full settlement contract, duplicate-bet prevention, verified risk ledger and signed A–E Truth Gate. No credential, API response, model code SHA, or unvalidated input flag alone grants a real bet.

Until independently verified A–E evidence exists **all approved stakes are zero and all selections remain non-counted**, irrespective of nonzero `diagnostic_u` or passing synthetic tests.

## Code enforcement

`research/risk/v21_risk_contract.py` is an offline research diagnostic. Its `CAP_GAME` must equal **1.00** under this lock; additionally enforce the same cap in any later production aggregator, ledger and execution entrypoint before claiming safety certification. The numeric scope is game/event aggregate, not just a market ticket. Keep both CI proof and risk-ledger observations. No production execution currently certified.

Tag requested after final reviewed policy commit: `risk-policy-lock-2026-11-15`. A Git tag is not a Git branch; do not claim it exists until the ref `refs/tags/risk-policy-lock-2026-11-15` actually resolves to the lock commit.
