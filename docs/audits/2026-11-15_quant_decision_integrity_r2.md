# SportsEdge Quant Eightpack: decision integrity and paired-market subject audit (R2)

**Status:** Research-only `PAPER / 0u`, no production model or wager changes. The historical v5 engine, prediction results, provider quotes and settlement files remain untouched.

## Three reproduced accounting risks

1. **Same selection across multiple price-capture times:** Prior `research/audit/quant_evidence.py replay` incorporated two qualified rows for the same `sport/event/book/period/market/side/line/player/team/stat` if `captured_utc` differed, even with different `selection_id` and odds. Their combined flat-1u paper ROI was not a valid count of distinct *decisions*. New policy quarantines **every occurrence**, not arbitrarily the first or last. Merely changing captured odds does not prove another wager was placed.
2. **Duplicate ID and same-instant canonical selection:** Prior code included the first qualifying row and rejected later duplicates, making ROI order-dependent. New policy preserves and quarantines *all* duplicates, recording original CSV row numbers. It also continues to quarantine same-instant opposite selections (PR #129) and leaves distinct alternate lines / genuinely different books as separate *paper research rows*. There is no execution attestation.
3. **Mismatched opponent odds for player/team markets:** Prior market no-vig validation compared event, period, market, side and line, but could accept the UNDER for *another player or team* as the paired quote at the same threshold. Now player props / ATTD / TD2+ / first basket / home runs require the same player ID, and team totals require the same team ID. If a stat is supplied, both sides must match. `DK`, `Draft Kings`, and `DraftKings` normalize identically. Unknown/blank subject identity fails closed.

## One canonical paper-accounting policy

`quant_foundation.py ledger` previously reimplemented permissive arithmetic rather than calling the strict `quant_evidence.py replay`. It now delegates to the same replay, retaining the legacy field names (`qualified_graded_n`, `roi_flat_1u`, `net_units`, `unverifiable`, etc.) but requires the stronger as-of, fitted-before-forecast and after-start settlement timestamps. Mirrored selections and repeated decisions do not contribute to either CLI's ROI, units, drawdown, Brier, log loss or calibration. Rejected rows are visible in `unverifiable` and `rejected_qualified_or_invalid`, never silently deleted.

This is a **conservative research quarantine**, not an assertion that a user cannot deliberately place two separate bets on the same line at different times. To certify multiple real executions, add independently authenticated, immutable transaction IDs with original book receipts and a separate preregistered accounting contract. Do not infer executions from repeated quote snapshots.

## Test evidence and non-changes

- `python -m unittest discover -s research/audit -p 'test_quant_*.py' -q`: **64** synthetic cases passed.
- `python -m unittest discover -s research/audit -p 'test_g18_*.py' -q`: **14** synthetic cases passed.
- `python -m unittest discover -s research/audit -p 'test_printed_card_*.py' -q`: **7** synthetic cases passed.
- **85 local tests in total**, Python stdlib only; GitHub CI must pass separately on the exact proposed head commit.

**Still blocked:** Actual original November 9 CBB picks/board/finals, original November 11 full-precision probabilities and DK quotes, independently authenticated source publication/offer clocks, walk-forward per-market calibration and provider authorization. None of the 85 synthetic tests independently authenticates a historical source or demonstrates profitable +EV performance. `PAPER / 0u` remains mandatory.
