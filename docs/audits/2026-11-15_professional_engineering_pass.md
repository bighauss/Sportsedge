# SportsEdge — professional engineering hardening

**Audit date:** November 15, 2026 (Central Time)  
**Scope:** Claude Nov 14 NFL all-market *research* runner, historical R2 repair, RUN IT v2.1 audit boundary  
**Release state:** `PAPER / 0u` — no model or betting promotion

## Executive decision

SportsEdge has substantial source code and a reproducible frozen engine, but **synthetic test coverage and archived R2 picks do not establish accurate probabilities, independently authenticated odds, or positive expected value**. We preserved the original frozen v5 engine and the exact 2026-11-14 R2 calculations, and added a **new, explicitly separate** `v21_fail_closed_repair.py` research auditor. It reads historic rows; it does not update them or place bets.

### Reproduced defects in archived R2

| Priority | Prior defect | In this PR |
| --- | --- | --- |
| P0 | `NO_MKT` flags did **not** prevent a high-probability row from receiving `r2_keep=1`. | No market probability -> explicit `MARKET_PROBABILITY_MISSING_OR_INVALID`, no blended probability/EV, always `PAPER_HOLD_0U`. |
| P0 | Period `ANCHOR`/`PERIOD_DERIVED` was annotated but **not** blocked by the `r2_keep` filter (where the other R2 conditions were met). | Any non-independent `ANCHOR` is held; derived periods explicitly flagged. |
| P0 | `NaN` and other nonfinite inputs propagated through legacy pooling, and invalid prices could crash the run. | Strict Decimal ranges and American odds validation; every malformed row retained with a reason. |
| P1 | Historical logarithmic pooling and current v2.1 **linear** 30/70 probability blend could be confused. | Separate `v21_linear_win_p` column; legacy R2 files/formulas unchanged. |
| P1 | Two-outcome EV was presented for potentially push-capable markets without explicit push mass. | `v21_binary_ev_illustrative` is visibly distinct from `v21_push_aware_ev`; the latter remains blank without explicit settlement type and valid win/loss/push probabilities. |
| P1 | Missing event identity, time-as-of, independent no-vig source, and quote authenticity were not surfaced in old R2 output. | New fields/flags check all these; even asserted evidence does **not** authorize staking. |
| P1 | Audit output risked overwriting or partially writing a report. | Exclusive-create outputs, failure cleanup, input SHA-256, original rows untouched. |

## Full November 15 replay — unchanged historical source

Source: `FT_R2_picks_2026-11-15_NFL_2229CT_injadj.csv`; SHA-256:
`700e133f63bd61715a57873e48e452b5c906828d1de87a53593937532bf80be1`.

- Input rows: **152**; annotated output rows: **152**; missing/dropped rows: **0**.
- **17** show greater than 15 percentage point disagreement between model and supplied market probability.
- **152** have no independently authenticated capture / event ID / quote time in the old CSV. A file name or upload time is not evidence that a book offered that price pregame.
- **152** lack independently documented settlement rules/push probabilities in this source. Their binary EV can be shown **only as an illustrative calculation**; no push-aware EV is admitted.
- **0** approved wagers; `v21_approved_stake_u` is `0` on every row. The original 11 R2 keep flags are **not** reinterpreted as v2.1 approvals.

The two 2026-11-15 privately archived outputs are kept on SportsEdge Drive rather than committed to the public GitHub repository.

## Deterministic test receipt

```sh
cd research/claude_nfl_20261114
python test_recovery.py -q                  # unchanged original 7
python test_v21_fail_closed_repair.py -q    # 33 new tests
python -m compileall -q .
```

Test assertions cover preserved historical source hashes, missing no-vig probability, anchor period, NaN/infinity, malformed odds, genuine win/loss/push EV, absent source receipts, uncertain event and player identity, quote time, model-as-of time, mixed books, duplicate rows, and no-overwrite behavior. None uses live network data.

## Professional pipeline architecture

| Stage | Contract | Failure behavior |
| --- | --- | --- |
| 1. Quote intake | Event + market + period + line + side + DK two-way prices + source observation | `NO_VERIFIABLE_QUOTE`; preserve raw data privately |
| 2. Snapshot lock | Model SHA, features available as-of, roster/goalie/injuries, exact event start | `NO_ASOF_EVIDENCE`; no retrospective backfill |
| 3. Projections | Market-specific distributions, identity binding, quality/uncertainty metadata | `NO_VALIDATED_MODEL`; not merely `LOW` stars |
| 4. Probability + EV | 30% model / 70% independent no-vig market per v2.1; push-aware settlement; realistic price/fee | `NO_PAYOUT_OR_PUSH_MODEL`; diagnostic binary EV not executable |
| 5. Gates + risk | Timestamped line reprice, T−90 inactives, matchup gaps, CLV, quarter-Kelly, 5u/day / 2u/game / 3u/theme | `PAPER / 0u`; risk contract never bypasses data gates |
| 6. Audit | Immutable selection ID, model/quote hashes, graded outcome, all pushes and losses, CLV | Do not edit historical picks or rewrite performance |
| 7. Promotion | Locked forward holdout, pre-registered market thresholds, reviewer approval, passing GitHub CI | Stay `PAPER / 0u` |

**Every market is shown in the coverage report**, including unsupported/missing ones; none gets invented probability or source data. ATTD/first TD/2+ and same-game parlays require appropriate count/joint distributions, not historical TD shares alone. The current public repository does not offer a validated all-market, real-money execution system.

## Release checklist (still open)

1. Independently authenticated, timestamped DK + independent comparison-book quotes with exact event/period/player IDs.
2. Fresh raw 2026 player curves, official inactives and complete 32-team TD stats, tied to original source hashes; no week-10 leakage into pregame.
3. Chronological fold evaluation and prospective market-by-market calibration, including largest-edge autopsies, Brier/log loss, closing-line value and correlated uncertainty.
4. End-to-end enforcement of the existing RUN IT v2.1 mandatory rules with a cross-sport, cross-run exposure ledger; no automatic execution from a research calculation.
5. Explicit owner review of release conditions; don't loosen a threshold just to obtain picks or pass a fixture.

## Audit note on the old runner

`nfl_full_slate.py` still calls the **original legacy** `se_repair_layer.py`; this PR **does not silently replace or rewrite that frozen research history**. For an archived R2 result, run the **separate** auditor on the stored `picks_r2.csv`. Any future production orchestrator must use fail-closed source/authentication and v2.1 gates, not the old `r2_keep` column. The code tests therefore establish **read-only audit reliability**, not live card readiness.
