# RISK_POLICY.md — SportsEdge stricter-of-v2.1/v2.2 lock

**Policy ID:** `SPORTSEDGE_STRICT_V21_V22_20261115_R1`  
**Scope:** NFL, CFB, CBB, NBA, MLB, NHL, PGA; ALL market families.  
**State:** PAPER / **0 approved units**, 0 official-counted selections, no auto-betting.  
**Effective in proposed code:** only when this version is merged, tested, reviewed and deliberately used; this file does not certify a real-money release.

## Authority and conflict resolution

- Existing public baseline: `docs/rules/RUN_IT_V2_1_MANDATORY_RESTORATION.md`, `research/risk/v21_risk_contract.py`.
- Owner-directed v2.2 addendum in private Drive: `2026-11-15_1920CT_CLAUDE_to_ALL_RUN-IT-STANDARD_v2.2_ADOPTED_addendum.md`. Its owner-adoption claim was contested in a peer audit. The owner's November 15 execution instruction here explicitly selects **the stricter protection whenever v2.1 and v2.2 disagree**.
- **The v2.2 statement “NO per-game unit cap” is NOT adopted.** Keep the stricter v2.1 aggregate **2u per-event maximum**, including all correlated legs. This does not turn a multi-leg cluster into a single unbounded risk position.
- Cap order: **0u official until A–E** > reject unsupported/unknown or incomplete evidence > 12-point gap HOLD > v2.2 dog cap and low-confidence shrink > v2.1 quarter-Kelly, caps and stop conditions. The strictest applicable bound wins, not the most recent wording.
- No silent changes: a different risk limit, sizing rule, model weight or adoption judgment requires a new policy ID, separate diff, unseen-data test and explicit owner sign-off. Historical originals remain untouched.

## Numeric and operational requirements

| Guard | Locked decision |
| --- | --- |
| Market-specific official permission | **0u, PAPER only** until genuine A–E evidence and signed promotion |
| Maximum total daily exposure (Chicago decision date) | **5u** across all sports |
| Maximum total per event / correlated game | **2u**, sum full actual liability of ALL legs |
| Maximum theme exposure | **3u** in the same risk ledger |
| Initial v2.1 stake diagnostic | 0.25u–1.5u band on push-aware quarter-Kelly; subsequent reductions may take it below 0.25u |
| Base probability blend | v2.1 30% independently verified model + 70% independent no-vig market; never claim fitted skill |
| Missing ratings half | Explicitly identified half-only model: shrink raw model p halfway toward no-vig p **before** 30/70 blend; force LOW confidence. Missing essential PIT/source feature still BLOCKS, rather than being excused as LOW |
| Model/market disagreement | **>12 percentage points raw or post-shrink = HOLD / 0u**; >3 points flagged for investigation; do not let shrink hide an original >12-point gap |
| Moneyline underdog price >= +200 | At most **0.25 diagnostic units**; remains capped until 50 independently auditable settled dog-ML CLV observations and separate policy release |
| Negative comparable CLV over latest 50 | Halve v2.1 diagnostic size per sport; unmatched closes NEVER counted |
| LOW confidence | Halve diagnostic size and reduce displayed stars if applicable; never infer eligibility from low confidence alone |
| Injury/lineup change | T–90 snapshot; material change requires reprice or kill; do not use late/after-start lines |
| Data/settlement/correlation | Explicit event, player/team IDs, market/period/line/side, settlement, source and clock; SGP requires a validated joint price |
| Missing information | Keep market family visible as blocked/NO_DATA/NO_PRICE/NO_MODEL/NO_PROVENANCE, not silently omitted |

The `research/risk/strict_v21_v22.py` overlay is **diagnostic only** and defaults to fail-closed for unknown ratings-half or critical as-of feature status. A self-declared `features_asof_verified` field is NOT independent authentication. `sportsedge/odds/card_gate.py` also sanitizes caller claims and always refuses an official card. Existing v5 model bytes and historical predictions are unchanged.

## Release gate

GitHub Issue [#10](https://github.com/bighauss/Sportsedge/issues/10) is the blocking source of truth. Each market needs authentic independent odds receipts (Gate A), PIT feature lineage (B), three leak-free registered calibration cycles (C), >=200 independently matched settled CLV triples (D), and fully connected v2.1/v2.2 risk and settlement audits (E), plus the documented 100-card and five-day evidence thresholds and signed promotion. Synthetic tests and local SHA-256s never satisfy an external authenticity gate.

**Current release status:** none independently certified; **PAPER / 0u**. Market/odds discovery and research projections are separate from wager eligibility.
