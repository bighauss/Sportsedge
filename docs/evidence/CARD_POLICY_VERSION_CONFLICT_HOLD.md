# Gate E: conflicting adopted v2.2 and strict-v2.1 card policy — HOLD

**2026-11-15 CT — source-integrity engineering note; PAPER / 0u, NOT release approval.**

## Confirmed conflicting original instructions

1. The user-owner's privately saved November 15 ~19:15 CT [RUN IT v2.2 adopted handoff](https://drive.google.com/file/d/1TAgJXaXTo-4M-MJxWWoOp0rPw5mNdmeM/view) says the game is a **correlation cluster, NOT a per-game unit cap**. It retains 5u/day and 3u/theme, adds the conditional ratings-half shrink, >12 percentage-point model-market gap hold and +200 dog moneyline 0.25u diagnostic cap until 50 real CLV-grade observations.
2. Public repo [`RISK_POLICY.md`](../../RISK_POLICY.md) records a competing **stricter-of-v2.1/v2.2** instruction, retaining the **2u per-event** aggregate cap. Existing `research/risk/strict_v21_v22.py` uses the old cap in its v2.1 base and advertises `SPORTSEDGE_STRICT_V21_V22_20261115_R1`. The policy archive must not silently rewrite historical decisions. The separate newly merged `research/risk/v22_policy_guard.py` is a **PAPER-only preview**, explicitly **not connected to actual card/ledger risk**.

These are inconsistent normative decisions for new v2.2 cards. A green synthetic test on either standalone rule file does NOT establish Gate E conformance. Until the owner’s final, explicit version precedence is reliably documented and a separately reviewed end-to-end revision is accepted, choose **HOLD / 0u**, not a guessed 2u or unlimited exposure. No production staking has been authorized.

## Live fail-closed behavior after this repair

The sole `sportsedge/odds/card_gate.py::gate_candidate` path now:

- Continues to run the established strict v2.1/v2.2 research diagnostic without altering its historic 2u behavior.
- Also evaluates adopted v2.2 as an **unverified** preflight. Every caller-supplied `source_receipt_verified`, `independent_model_verified`, `model_freeze_verified`, or `independent_quote_chain_verified` claim is forced to false, regardless of the input; it is not an authentication engine.
- Records **selected** `RUN_IT_V2_2_ADOPTED_20261115`, **executed** `SPORTSEDGE_STRICT_V21_V22_20261115_R1` and the caller's original declared `rules_version` separately. Missing/wrong version is explicitly flagged. Raw/effective probability gaps are labeled **unattested** and are not actionable model conclusions.
- Adds `GATE_E_V22_CARD_LEDGER_NOT_CONNECTED` and `EXECUTING_STRICT_GAME_2U_CAP_CONFLICTS_WITH_SELECTED_V22` to original decision reason codes, which are also persisted in the private tamper-evident `EvidenceChain` without modifying its on-disk schema.
- **Always returns `status=BLOCK`, `card=null`, `official_counted=0`, `approved_stake_u=0`, `risk_policy_conflict=true`, `gate_e_v22_connected=false`**, including when both diagnostic functions are forged to return PAPER. Never infer permission from self-reported evidence.

## Requirements for a real Gate E implementation

First establish a single latest owner-approved policy ID and precisely resolve the 2u per-game conflict with the existing strict policy record. Then create a separate isolated PR to wire that selected policy to the actual card generator, total 5u/day and 3u/theme correlation-aware ledgers, original quoted decision/observed clocks, missing-half and wide-gap rule order, low-confidence sizing, long-dog 50-original-CLV proof, T-90 lineup lock, all-market census, push-aware settlement, original decision-hash history, and signed per-market release review.

Even a correct end-to-end Gate E implementation is **not** proof of Gates A–D: genuine original independent DK+second book provider receipts, contemporaneously available features, 3 preregistered calibration cycles, 100 consecutive real-slate compliant cards, 200 matched settled CLV and independent explicit owner promotion are still missing. All uncertified markets remain PAPER/0u, no automatic wagers.

## Deterministic synthetic regression

```sh
python -m unittest sportsedge.odds.test_issue10_offline -v
```

The tests cover original source/selection mismatches, v2.2 declared/unknown/missing rules, both policy diagnostics forged to PAPER, externally unverified v2.2 probability-gap calculations and the private decision-chain conflict record. CI tests software behavior only. No original prediction, sportsbook quote, frozen v5 model, old wager ledger, provider key, or historical result has been changed.
