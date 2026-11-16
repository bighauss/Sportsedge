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
- **Recovered after this original audit (PR #149):** The ORIGINAL November 9 `board.csv` revision `0Bz5GGyFPXJYyTGFSZ3dlZzlIMW8vY0pmVHNldlZxdXVMT3hvPQ`, Drive ID `1Kqqneaz-fvCfSF2z8eOm6z7d468KRHSh`, was created **Nov 10 02:17:44.831Z**, with **248 two-sided board rows**, SHA256 `922f6a10b1c038a15ba0469d344b5015b767dca6c41a791110aa083fd9027ea4`. The original `CARD_2026-11-09_LATE_CBB_CHATGPT.md`, Drive ID `1SG4rLd9C-lb7cvxMglDje-3ebqbdriUj`, was archived Nov 10 02:22:24.393Z; **150 CARD + 59 MODEL-DOUBTED** printed selections. Independently checking original revisions gives **209/209 unique original board-row matches**, zero missing or ambiguous, consistent with merged PR #149. This is original FILE-lineage evidence, **not** an upstream DraftKings quote/authenticity attestation or count of official bets.
- **Retrospective G-18 census only:** The G1 independent source-closure report documents **70 changed labels (35 L→W / 35 W→L)** when the old versus corrected grader is applied to a **retrospective 496-entry** `portable_nov9` census. This corroborates the bug's manifestation on the retrospective representation; the previously reported **180 affected team-total rows** and the 70 label changes are **not** an exact raw original `picks.csv` replay.
- **Still not independently replayable:** The exact original Nov 9 496-entry `picks.csv` and original `run7_finals.json` bytes with definitive source receipt/hashes were **not recovered**. A saved 209-row printed card is not the full 496-side engine output. Do not assert the original 496-row clean-room grader report passed or apply retrospective corrections to frozen records.
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

1. Preserve the now-recovered original Nov 9 board **revision** and printed card separately, but still obtain exact original **496-row `picks.csv`**, original finals `run7_finals.json`, their original SHA/publish receipts and model draws. Never replace original files with retrospective `census.json` or the 209 printed selections.
2. Re-run from a private, stable workspace using those original bytes and inspect every discrepancy, including per-game and per-family counts. The existing 70 changes refer to a retrospective census until this occurs.
3. Authenticate final scores and source clocks; distinguish 1H and FG; independently verify actual decisions and pregame offered odds.
4. Recompute calibration from original frozen qualified decisions only after clearing mirror/selection and point-in-time gates. No retroactive weight adjustment or promotion to official bets.

## Private replay safeguards (updated R5)

Original odds, pick selections and per-row grade overlay must **never** be
written to public Git. The G18 CLI now refuses both lexical and real/symlinked
input or output paths inside the public checkout and refuses symlink aliases;
private reports are created exclusively with `0600` permissions, fsynced, and
removed if the initial write or fsync fails. Existing reports cannot be
overwritten; original input bytes are SHA-pinned and unchanged. Synthetic
regression tests cover public/symlink path refusal, original-row retention,
create-only writes, and fsync rollback. The hash/clock contract still does
**not** independently verify a sportsbook provider or final-score authority.
