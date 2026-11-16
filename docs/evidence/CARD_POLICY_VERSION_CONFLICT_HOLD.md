# Gate E: historical v2.2 no-game-cap addendum superseded by later 2u stricter owner instruction

**As of November 15, 2026 Central — PAPER / 0u; no market certification or wager permission.**

## Preserve both original instructions in chronological order

1. At approximately 19:15 CT on November 15, the owner adopted the [RUN IT v2.2 addendum](https://drive.google.com/file/d/1TAgJXaXTo-4M-MJxWWoOp0rPw5mNdmeM/view). It proposed the game as a correlation cluster **without a per-game cap**, kept 5u/day and 3u/theme, added the missing-ratings half shrink, >12-percentage-point probability gap hold, and provisional +200 dog ML 0.25u cap.
2. **Later**, the owner explicitly directed: **"Adopt the stricter of v2.1 / v2.2 per-game risk cap and freeze it; no silent changes."** The documented v2.1 cap is **2u/event**, compared with v2.2's unlimited game cap. Accordingly, the **selected current policy is `SPORTSEDGE_STRICT_V21_V22_20261115_R1`, 2u/event**. There is no original owner authorization to invent a **1u/event** cap; that would require its own explicit later amendment. See [`RISK_POLICY.md`](../../RISK_POLICY.md).
3. Original v2.2 addendum text remains immutable historical context. The selected strict overlay includes additive rules from v2.2 but **does not** silently import the superseded no-cap clause. Past original decisions keep their original policy version and stakes; no retrospective repricing.

## Actual active card gate after this correction

`sportsedge/odds/card_gate.py::gate_candidate` records the candidate's declared `rules_version`, the **selected** and **executing** `SPORTSEDGE_STRICT_V21_V22_20261115_R1`, and the **historical** `RUN_IT_V2_2_ADOPTED_20261115` preflight version. A missing, older no-cap, unrecognized, or fictitious policy is explicitly reason-coded `SELECTED_STRICT_POLICY_VERSION_MISSING_OR_MISMATCHED`. The historical addendum's model/market gap preflight still runs for diagnostic transparency, but provider/model/quote verification booleans are forcibly false—no caller's self-attestation satisfies authenticity.

- Every reason-coded original decision includes `SELECTED_POLICY`, `EXECUTED_POLICY`, and `HISTORICAL_V22_ADDENDUM` identities, including in the **private tamper-evident** `EvidenceChain`. This records local provenance, not an external signed policy acceptance.
- The selected strict **2u per-event** cap, 5u/day and 3u/theme are still research exposure ceilings. The old 1u proposal is NOT a legitimate alternative to apply without a new signed owner instruction.
- `GATE_E_STRICT_CARD_LEDGER_NOT_CERTIFIED` is always reported because original sportsbook sources, lineup/source chronology, complete cross-market card bookkeeping, genuine CLV and independent external sign-off have not been verified. A self-reported PASS or mocked PAPER from *both* diagnostics **cannot** bypass it.
- Current card result **always remains `BLOCK`, `card=null`, `official_counted=0`, `approved_stake_u=0`, `gate_e_v22_connected=false`**. `risk_policy_conflict` flags a missing/mismatched candidate policy ID, not a claim that the owner has not resolved the per-game cap. Correctly declared strict ID is still BLOCK because Gate E and Gates A–D are open.

## Remaining integration and evidence before any official market

Wire the selected strict policy and additive v2.2 risk adjustments end-to-end into the real candidate/card/ledger pipeline with independent source/price/lineup evidence and complete offered/not-captured/block inventory. Enforce same-day Chicago 5u, per-theme 3u, **per-event aggregate 2u**, original-price push-aware probability/EV, duplicate selection IDs, T-90 locks, +200 dog CLV evidence, and risk-version snapshots on every original decision. Separately preregister and grade all original forward outcomes and blocked rows. Never mutate frozen v5 or original historical predictions to improve a backtest.

Software checks do not establish bookmaker quote authenticity. [Issue #10](https://github.com/bighauss/Sportsedge/issues/10) still requires independent original DraftKings+distinct sportsbook source receipts, PIT lineup/feature provenance, three registered forward calibration cycles, 100 consecutive real-slate compliant cards, 200 genuinely matched settled CLV comparisons, five full days, and independent signed per-market owner promotion. No automatic betting.

## Offline tests

```sh
python -m unittest sportsedge.odds.test_issue10_offline -v
```

Synthetic tests verify stricter 2u ID precedence, missing/older/fabricated policy versions, source-flag sanitization, a policy decision remaining BLOCK even if diagnostic output is mocked to PAPER, and selected/executed/older-addendum labels retained in a private original decision hash chain. They do not prove provider source clocks or profitable EV.
