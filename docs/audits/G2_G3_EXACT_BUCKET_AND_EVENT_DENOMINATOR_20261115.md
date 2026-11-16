# G2/G3 disagreement calibration — exact bucket and independent-game guard

**Scope:** frozen-data **research audit only**, not SportsEdge model changes.
No original 2026 prediction, quote, result, grade or v5 parameter is modified.
This file documents the independent guard implemented in
`models/audit_disagreement_calibration.py` and tested in
`models/test_audit_disagreement_calibration.py`.

## Why this matters

The former disagreement classifier first rounded the absolute
`model_p - market_p` difference to four decimals. That shifted some
genuinely sub-threshold disagreements into the next bin:

| Input gap | Earlier classification | Correct classification |
| --- | --- | --- |
| 4.996 percentage points | 5–10pp | 0–5pp |
| 9.996 percentage points | 10–20pp | 5–10pp |
| 19.996 percentage points | 20pp+ | 10–20pp |
| exactly 10pp, e.g. 0.6–0.5 | 10–20pp | 10–20pp |

The implementation now uses **unrounded probabilities**, with only
a 1e-12 floating-point tolerance for exact decimal subtraction boundaries.
No retrospective pick qualification/risk approval is recalculated.

The earlier G2/G3 overall and bucket summaries reported only **n
selections**. For the recovered November 9 printed card, **209 selections
belong to only three actual games**, primarily correlated alt lines.
Wilson intervals based on 209 independent Bernoulli trials are therefore
misleading. Every new summary now reports `unique_events`,
`insufficient_unique_events_30`, and `event_dependent_selections`.
When more than one selection belongs to any source event, the
unclustered `observed_wilson_95` is **NULL**, not a fabricated interval.
ROI remains explicitly **descriptive hypothetical selection-level ROI**,
never a distinct-game ROI, observed wager ROI, or source-authenticated CLV.

## Run

The original `models` audit CSV fields remain unchanged. An
event ID must represent the same game across alt markets.

```bash
python -m unittest discover -s models -p 'test_audit_disagreement_calibration.py' -v
python models/audit_disagreement_calibration.py /private/g2_frozen.csv \
  --output /private/g2_research_only.json
```

All dataset inputs must come from the original frozen prediction and
original price/settled game source, not a postgame reconstructed card.
The script's JSON is **NOT** approved for external publication if it
contains private market prices or user-specific bets.

## CLI original-source privacy and file integrity

The G2/G3 audit CLI is now fail-closed for `--output`: it refuses input
and output paths inside the public repository (including symlinks), refuses
truncated or overlong CSV rows and duplicate original headers, and records
the **exact original CSV bytes SHA-256** in the output. That SHA records
local file identity, not upstream provider authentication.

New detailed JSON output is created **once** (never overwritten) using
exclusive creation permissions `0600`, flushed to disk before reporting
success, and deleted on a partial write failure. If the destination exists,
the tool fails without changing it. The user must keep the original CSV and
report in a private, access-controlled directory outside the public clone.

Example:

```bash
python models/audit_disagreement_calibration.py \
  /private/frozen_g2_predictions.csv \
  --output /private/g2_output_NEW_NAME.json
```

When `--output` is absent the tool still prints research data on stdout;
the operator is responsible for not copying private odds/picks into public
issues, PRs, CI logs or chat.

## Remaining blockers

Even after the boundary and independent-event correction:
- The supplied `market_p` and `source_sha256` fields do not
  independently authenticate original bookmaker prices.
- The caller must establish whether reported probabilities represent
  unconditional settlement probability. For **first-half CBB moneylines**
  original v1 printed `P(win | no tie)`, while EV required
  `P(win)`, `P(loss)` and `P(push)`. That original conditional
  `model_p` must NOT be inserted into a binary Brier/calibration
  CSV as though it were unconditional.
- A game-clustered confidence interval is not supplied here. Additional
  registered forward games and a pre-specified cluster analysis are
  necessary before meaningful confidence claims.
- 30 unique games is only a **small-sample flag**, not a betting
  promotion threshold. The independent Issue #10 A–E requirements
  remain unpassed. **PAPER / 0u.**
