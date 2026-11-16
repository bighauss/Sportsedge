# Nov 11 CBB formatted card — corrected push-aware EV reconciliation

**Current forensic conclusion (updated Nov 15 CT / Nov 16 UTC): NO established arithmetic error from the displayed November 11 card.** The two previously flagged EV differences were **conditional-versus-unconditional probability comparisons** on first-half moneylines. Those are PUSH-SENSITIVE; the original simulation aggregate is required to resolve their EV exactly. This document explicitly supersedes the binary-only classification in Issue #80 and the original draft of PR #119. Historical card text, original prices, and v5 formulas are **not modified**.

## Sources and code-path proof

- Saved formatted card: `picks_2026-11-11_1934CT_CBB_late_v5_plain.csv`, Google Drive file ID `1tSPOPxP988zFTZOF1HGPOBHEIaZKU-bu`, heading `Wed Nov 11 2026, 19:34 CT`, `sportsedge_v5`, `PAPER/0u`. The local retrieved text export has **8,215 bytes**, SHA256 `82a98fcbe427cfea75bb722cfdc51f0f697810d2d4093feefaa4ff44da00c97f`. The file is a **formatted report**, not a provider-signed quote receipt or original p_win/p_loss/p_push array.
- Original frozen engine: repository `engine/sportsedge_v5.py` at blob `e7f282e2ece2506227fed1681aab9c33607e50bc`. `wl(d)` returns unconditional `pw=P(win)` and `pl=P(loss)` from simulation comparisons (values of zero are **pushes**). `cond(pw,pl)` computes `pw/(pw+pl)` when decided. `emit()` prints `model_p=cond(w,l)` but computes `ev=w*payout(price)-l` where `payout` is the net profit multiple.
- Consequently, for a positive-moneyline two-sided push-settled market with decimal gross odds `D`, displayed conditional probability `p_cond` and push probability `q`, **EV = (1−q) × (p_cond × D − 1)**. A mismatch between `p_cond×D−1` and the displayed EV is **not automatically a calculation error**; one must recover the original `pw`, `pl`, and `push` frequencies.
- Recovery of original Nov9 portable `sportsedge.py` in merged PR #149 independently shows the same `cond` + EV design. This does not establish Nov11 simulation authenticity.

## Complete card census and corrected arithmetic

Original text has **65 CARD rows** under the normal card section, **10 MODEL-DOUBTED** rows separately flagged for engine input checks, **75 displayed selections**, not 75 independently qualified wagers. Its header states 188 priced sides, which cannot be independently authenticated from this printout alone.

| Selection | Book odds as printed | Displayed conditional p | Printed EV | Binary-only EV from displayed p | Approx push range consistent with rounding | Status |
|---|---:|---:|---:|---:|---:|---|
| Card #24 **1H UTSA ML** | +470 | 21.1% | +19.7% | +20.270% | **1.18–4.40%** | **PUSH-AWARE, ORIGINAL DRAWS REQUIRED** |
| Card #32 **1H California ML** | +200 | 38.6% | +15.1% | +15.800% | **3.19–5.64%** | **PUSH-AWARE, ORIGINAL DRAWS REQUIRED** |

The approximate ranges allow **independent display rounding** of both model percentage and EV to one decimal place. They are math implications, NOT verified outcomes or actual push probabilities. The other **73 rows** have no recognized push-capable market in the source text and are **within binary display rounding tolerance**. Neither positive EV nor accurate probability calibration is certified by this test. The reconstructed checker also keeps separately flagged integer-score lines (push-capable) and quarter lines (potential nonbinary settlement) **out of binary anomaly classification**.

## Implementation, private output and test contract

`research/audit/printed_card_ev_audit.py` now has three distinct statuses:

1. `BINARY_NO_EXACT_PUSH_FOR_DISCRETE_CBB_SCORE`: only these can become `anomalies` if their displayed EV deviates beyond available numeric rounding.
2. `PUSH_AWARE_FIRST_HALF_ML` or `PUSH_AWARE_INTEGER_LINE`: `ev_math_inconsistent_beyond_rounding=null`; requires original `pw/pl` simulation draws. A displayed-number-implied push range is included **only when mathematically defined**.
3. `NON_BINARY_ALTERNATE_SETTLEMENT_UNVERIFIED`: do not assert binary EV verification for quarter-point/half-win settlement from a text line.

The parser maintains separate CARD versus MODEL-DOUBTED counts, all accepted row summaries and parse problems, source SHA256, and a `PAPER_0U` status. CLI now refuses original text/report paths **inside public checkout**, including symlink aliases, writes a **0600 create-only** JSON report with flush + fsync, and removes any partial report on failure. It does NOT rewrite the engine, source card or historical picks.

```bash
python research/audit/printed_card_ev_audit.py \
  /private/sportsedge/original_cbb_nov11_formatted_card.txt \
  --report /private/sportsedge/nov11_push_aware_report.json
python -m unittest discover -s research/audit -p 'test_printed_card_*.py' -v
```

**Local verification:** **122 synthetic standard-library tests** across the research audit suite (93 Quant +14 G18 +15 printed EV). Also ran the new parser on the actual retrieved card: 65 main, 10 model-doubted, **0 confirmed binary display anomalies**, **2 1H ML push-sensitive unresolved**, zero parse/count problems. GitHub exact-head CI must pass before merge.

## Remaining evidence and independent model gates

The original November 11 full precision `pw`, `pl`, `p_push`, quote source/observation time, period settlement, and current provider two-sided offers are required for a verified replay; one cannot reverse-engineer actual simulation draws from rounded output. Preserve the original displayed numbers and the prior audit as an historical superseded conclusion, not an erased record. Source authenticity, opportunity existence, point-in-time features, booked closing lines, calibration, independent forward acceptance and profitable ROI remain **UNVERIFIED / PAPER 0u**.
