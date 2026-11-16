# Quant Eightpack — mirrored qualified selections cannot count toward PAPER ROI

**Date:** November 15, 2026 (CT). **Scope:** research-only `research/audit/quant_evidence.py`; no change to frozen `engine/sportsedge_v5.py`, existing historical picks, graded outcomes, CLV, accepted production probabilities, or betting admission. **Status:** `PAPER / 0u`.

## Reproduced defect in the prior merged replay

The previous `replay()` recognized candidate opposite-side groups **after** adding rows into the paper ledger and return/performance calculations. Its warning counter also matched the raw line string, so HOME -3.5 / AWAY +3.5 (the ordinary opposite spread pair) did not match. It reported both sides as eligible. This could pollute a hypothetical ROI even when the original board was merely two-sided prices, not independently qualified selections.

A self-contained synthetic case using two CBB FG spread selections, same event/book/capture/model timestamp, HOME -3.5 W at -110 and AWAY +3.5 L at -110 demonstrated the old behavior:

- `eligible=2`, `possible_opposite_side_selection_groups=0` and paper `roi=-0.045455`.
- **This is a synthetic bug reproduction**, *not* a claim about historical game results or wagers.

## Correction (fail closed)

- Detect opposite HOME/AWAY spread lines by **absolute handicap magnitude**; TOTAL/TEAM_TOTAL/prop OVER/UNDER and YES/NO markets use identical threshold; ML blank and numeric zero are canonical aliases.
- Group only selections at the same sport/event/game start, book (normalizing `DK` / `DraftKings` and `FD` / `FanDuel`), period, market, player, team, statistic and **capture instant**. Distinguish home and away team totals that happen to share a threshold. Different capture times are not automatically treated as the same mirrored board.
- If qualified opposites coexist, **quarantine both from ROI, net units, max drawdown, Brier, log loss, per-market summaries and the qualified ledger**. Keep them in the rejected-row census with their original CSV line and reason `MIRRORED_QUALIFIED_PAIR_QUARANTINED`.
- Reject nonfinite market handicap text (e.g., `NaN`) instead of allowing it into the canonical selection identity.
- Report `mirror_quarantined_rows` and `possible_opposite_side_selection_groups`; preserve original source row count and all reasons.

This errs on the side of not certifying a same-instant hedged portfolio without a separately verified executed-bet identifier. Exact signed execution records and the definition of a truly qualified selection are still needed to prove historical betting performance.

## Verification

Locally with Python 3.13:

```bash
python -m unittest discover -s research/audit -p 'test_quant_*.py' -q
python -m unittest discover -s research/audit -p 'test_g18_*.py' -q
python -m unittest discover -s research/audit -p 'test_printed_card_*.py' -q
```

**51 + 14 + 7 = 72 tests pass** (previous suite: 63). Nine new targeted tests cover mirrored spreads, bookmaker aliases, different capture clocks, independent same-threshold team totals, team-total opposites, ML blank/zero aliases and nonfinite lines. Existing data integrity, EV, receipt and calibration tests remain unchanged.

## Historical evidence remains open

- No original 2026-11-09 496-row picks/board/finals file was recovered. Do not report the claimed G-18 flip count as independently reproduced.
- No original full-precision Nov 11 model records were recovered to explain the two printed EV differences.
- A hash/capture field alone is not proof that a sportsbook actually offered a wager at that point in time. Official historical ROI and all-market live bet promotion remain blocked (`PAPER / 0u`).
