# Projection research index — 2026-11-15

**RESEARCH ONLY — PAPER / 0u — NO EXECUTED BETS VERIFIED**

The source scripts are already tracked on `main`; do not duplicate or modify their frozen copies:

- [NFL projection recomputation gate](../r5/nfl/sportsedge_nfl_projection_recompute_r1.py) — Git blob `bf639267cb478f04a9eac3242190dbc0365a99b2`
- [Projection overlay](../r5/nfl/sportsedge_projection_overlay_r1.py) — Git blob `b0207e5f61071f7db14bdeaaa2c6b17e1ef56ff5`

The recomputation gate checks `SPORTSEDGE_NFL_RIDGE_R1` forecast consistency from external ratings inputs. It does not establish that ratings were sourced independently or captured before the event. The overlay is a candidate-only join; it does not authorize production or wagers.

**Private Drive-only inputs and archives:** the November 15 daily card, the November 12 one-game projection CSV, the underlying odds board, source receipts, historical picks and graded records. Do not commit them to this public repository. The card's stated unit sizes are paper sizing, not verified executed bets.

**Release blockers:** independently authenticated provider quotes and receipt bytes, pregame ratings with source publication timestamps and hashes, current player/injury/lineup inputs, full v2.1 enforcement, rolling-origin calibration against market-only baselines, matched close prices/CLV and independent reproduction. Missing inputs remain NO_PRICE/NO_MODEL or PAPER.

**Validation status:** prior smoke checks were reported in a private handoff; no real-data reproducibility or profitability is established by this index. Frozen v5 remains the engine of record.
