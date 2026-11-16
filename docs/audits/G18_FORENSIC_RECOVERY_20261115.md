# SportsEdge — November 9, 2026 CBB G-18 forensic source recovery

**Research only / PAPER / 0u**. No model, historical grades, or recorded stakes were changed.

## New independently retrievable evidence

The historical script `grade_nov9.py` is stored in Drive file
`1sg6xX4M635FdWHv7mD5b-rWHUwvKxIbo`, MIME `text/plain`.
Drive's revision listing returned two **different file revisions**:

| Drive revision | Modified UTC | Finding |
| --- | --- | --- |
| `0Bz5GGyFPXJYyN0FBT09nUUx0VVM2d1RyaUR1L2tWUDZPZXFVPQ` | 2026-11-10 03:56:32.194Z | Earlier saved source: `if fam.endswith("TOTAL")` precedes `if fam.endswith("TEAM_TOTAL")`. Original G-18 defect reproducible by rule inspection. |
| `0Bz5GGyFPXJYyMFlFRUt4WVlpV211MU1jNTNvUHNCMHQ4QytBPQ` | 2026-11-11 16:14:04.922Z | Later source: `if fam in ("TOTAL", "1H_TOTAL")` precedes team-total branch. This removes the suffix shadowing defect. |

The file named `grade_nov9_fixed.py` was separately saved on November 11, but currently reading just `grade_nov9.py` returns its *later corrected revision*. A reviewer cannot reproduce the historical root cause using only the current file bytes.

The old suffix check captures both `TEAM_TOTAL` and `1H_TEAM_TOTAL`. A team-total UNDER against Washington's 77 points, at line 82.5, would win. Against the **game** total (Washington 77 + Mississippi Valley 64 = 141), it loses. Synthetic tests independently demonstrate this difference and both first-half and full-game families.

## Scope of what is verified vs still claimed

- **Verified:** the faulty dispatch existed in the earlier Drive revision. It was edited later. The independent code-path reproduction and 14 synthetic assertions are testable.
- **Not independently verified:** the prior EDGE_AUDIT.md report says 180 team-total rows were affected and 70/496 rows would change. We did **not** have the original Nov 9 `picks.csv`, original `board.csv`, or `run7_finals.json` bytes available for a clean-room replay. A targeted Drive search for those exact filenames returned no accessible matching file. Accordingly the **180 / 70 / 496 are previously reported claims**, not findings reproduced in this work.
- **Unverified:** individual final score provider provenance; original model calibration results; historical executable wager ROI; true independent sportsbook quote receipts; exact line availability. No corrected calibration coefficients are adopted.

## Independent offline replay

`research/audit/g18_forensic_replay.py` is intentionally not an import of either legacy grader or its already-corrected copy. It validates original game/team/market identity; grades full/first-half ML, spreads, game totals and team totals; retains every original row; reports old-vs-corrected labels and every unresolved/missing-final row; includes input SHA256; and writes create-only JSON. No inferred pregame status, wager qualification, bankroll, or ROI is calculated.

```bash
python research/audit/g18_forensic_replay.py \
  /private/original_nov9_picks.csv /private/run7_finals.json \
  --expected-picks-sha256 <hash-verified-from-original-archive> \
  --expected-finals-sha256 <hash-verified-from-original-archive> \
  --report /private/g18_cleanroom_results.json
python -m unittest discover -s research/audit -p 'test_g18_*.py' -v
```

Expected **audit check** from historical narrative: 496 original priced rows, 180 team-total-family rows and 70 changed grades, exclusively team totals. These figures should be tested against the actual original bytes. A mismatch should trigger new investigation, **not** force edits to make the report match old claims. Do not include mirrored alternate-market prices as independent selected bets. Keep original grades and any superseding corrected views side by side with SHA references.

## Remaining blockers

1. Obtain exact archived original Nov 9 picks, board, finals and original model output; preserve original provider bytes and hashes.
2. Re-run from a private, stable workspace and inspect every discrepancy, including per-game and per-family counts.
3. Authenticate final scores and source clocks; distinguish 1H and FG; independently verify actual decisions and pregame offered odds.
4. Recompute calibration from original frozen qualified decisions only after clearing mirror/selection and point-in-time gates. No retroactive weight adjustment or promotion to official bets.
