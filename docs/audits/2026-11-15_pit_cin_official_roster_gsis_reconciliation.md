# PIT@CIN — independent roster+GSIS reconciliation, Nov 15, 2026

**Status: PAPER / 0u — not final inactives, not contest-ready.**

Sources: [official Bengals/Steelers game program for Nov 15, 2026](https://static.clubs.nfl.com/image/upload/bengals/jejonxuefz744qbou1cp), with active-roster section and separately designated practice squad; and the 2026 nflverse player-week archive captured Nov 15 before kickoff. Original compressed nflverse weekly SHA256: 379dd8008d9e1d9d6c2994df2ee2fcfc04da1cf4ad47c8198a6e8798ea9ca860. Original owner DK salary CSV remains PRIVATE. Its AvgPointsPerGame column is never consumed.

## Reproduced reconciliation of 50 QB/RB/WR/TE DK FLEX players

| Decision category | Players | Interpretation |
|---|---:|---|
| Historical same-team GSIS identity found | 34 | Candidate ID, not final active |
| Active published program roster, compatible historical role/identity | 27 | Research features possible, final inactives still unverified |
| Program practice squad, DK IR/OUT or not on program roster | 17 | No automatic projection or lineup eligibility |
| Published roster but no prior same-team 2026 player-week stats | 4 | No borrowing stats or inventing zero |
| DK fantasy position vs historical NFL position mismatch | 2 | Block ordinary RB/TE statistical modeling |

The last four decision categories total 50; the historical ID count overlaps them. **Zero live-entry approvals** are made.

## Evidence-backed examples

- DK Lew Nichols / nflverse Lew Nichols III: same-team PIT RB GSIS ID 00-0038409; official program lists Lew Nichols #31. Explicit alias candidate, not proof of final active status.
- DK Mitch Tinsley / nflverse Mitchell Tinsley: CIN WR GSIS ID 00-0038839; official program lists Mitch Tinsley #82. Explicit alias candidate, not proof of final active status.
- DK Riley Nowakowski is a PIT **fullback** in nflverse and the game program (GSIS 00-0041398), although DK salary eligibility is RB. Do not substitute traditional RB usage.
- DK William Wagner is a CIN **long snapper** (GSIS 00-0040379), although DK salary eligibility is TE. Do not model TE receiving.
- Marquez Valdes-Scantling is on the Pittsburgh **practice squad** in the official program. His recorded 2026 nflverse games are with **LAC**, not PIT; don't import the old-team role to a PIT active projection.
- Michael Pittman Jr. is DK-designated **IR** and absent from the active game-program roster; a historical name abbreviation cannot reinstate him.
- Joe Flacco, Will Howard, Drew Allar and Cam Grandy are listed on their team's program roster but lack prior 2026 same-team player-week appearances. Do not infer individual game role distributions.

## Software

- models/nfl_dfs/reconcile_official_roster.py reads frozen pre-kickoff SHA-256-checked nflverse weekly CSV(.gz), official-roster transcription and DK CPT/FLEX owner CSV. Explicit aliases only. One-to-one stable GSIS; no fuzzy matching. Separate historical ID, roster bucket, fantasy-role and final inactive gates. Every output is RESEARCH_ONLY_WAITING_FINAL_INACTIVES and can_enter_contest=false.
- models/nfl_dfs/test_reconcile_official_roster.py verifies eight synthetic failure/success paths (hash tampering, late capture, PS/IR, role mismatches, no observed records, non-approved alias, duplicates).
- .github/workflows/tests.yml includes the new dedicated DFS identity checks.

Inputs remain private. The public official program is **not a final official inactives report**. Declared hash and URL validate local consistency, not independent upstream authenticity. This research audit does not authorize a new PIT@CIN DFS lineup, a sportsbook bet, model-calibration graduation or a profit claim.
