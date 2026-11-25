# RUN IT CBB full pipeline: Nov 25, 2026 research runs (PAPER / 0u, NON_COUNTED)

`models/cbb/cbb_run_it_pipeline.py` runs capture -> validate -> project -> simulate -> price -> rank -> card ->
freeze -> grade -> audit in one command. Nothing here is validated or promoted. Frozen production coefficients
are untouched; the frozen model is the default projection.

## Integrated streams (read from their branches, files not modified)
| Stream | Branch @ head | How it is used |
|---|---|---|
| DK integration | grok-cbb/dk-integration-20261125 @ ed855c58 | `models/cbb/dk/derived/2026-11-25/runner_board.csv` (sha256 acdeb2cd..., byte-identical), `models/cbb/lines/dk_team_crosswalk_2026-11-25.csv` (matching pass 3) |
| Halves | grok-cbb/halves-20261125 @ 4ce5bbdc | `halves.halves_model.project_period` + `halves.halves_pricing.price_half_market` for 1H and 2H pregame (`--adapters halves --halves-path`) |
| Full-game challenger | grok-cbb/fullgame-ev-20261125 @ 3003e772 | `fullgame` FG1C per-game projection, `fullgame.pricing.line_probs/ml_probs/ev_audit`, `cbb_pricing.logit_blend` from that branch (loaded under a private module name; the runner's own cbb_pricing is untouched) (`--adapters fullgame --fullgame-root ...`) |

Card views per game: **FROZEN** (default), **CHALLENGER** (FG1C, research), **MARKET** (DK no-vig), **HYBRID** (logit blend
of challenger and market at the fullgame stream's validation-selected weights: open ML 0.125 / spread 0 / total 0.125;
at the close validation chose 0 for every market). Team-total hybrid weight 0.125 is a runner assumption (no separate
validation). Every priced side keeps frozen, challenger and hybrid probabilities and EVs. EV > 30% is flagged
(`FROZEN_EV_GT_30_PCT`, `EV_GT_30_PCT` from `ev_audit`), never capped.

## Runs (both on the same unauthenticated owner-PDF board, ESPN public inputs)
| Run | Freeze | Kind | Slate games | Projected (frozen / challenger) | Priced sides | Rejections | EV>30% frozen / challenger / hybrid |
|---|---|---|---:|---:|---:|---:|---:|
| replay_1240Z | 06:40 CT | REPLAY_RECORD_NOT_PROSPECTIVE | 69 | 59 / 57 | 482 | 126 | 53 / 6 / 0 |
| prospective_now | 11:25 CT | PROSPECTIVE | 62 (8 started before as-of) | 55 / 53 | 440 | 147 | 51 / 6 / 0 |

Prospective run, mean model minus market: frozen-on-public-inputs margin +0.87, total **+2.78** (OVER_UNDER_IMBALANCE flag,
46 over vs 20 under +EV selections); challenger margin -0.34, total +0.83. That is the Nov 24 inflated-EV pattern
reproduced by the frozen formula on the public reconstruction, and the challenger removes most of it.

## Reproduce
```
python models/cbb/cbb_run_it_pipeline.py --mode public-replay --date-ct 2026-11-25 \
  --board <dk branch>/models/cbb/dk/derived/2026-11-25/runner_board.csv --board-captured-utc 2026-11-25T12:40:00Z \
  --as-of now --season 2027 --raw-dir <private ESPN cache> --out <out> \
  --team-crosswalk <dk branch>/models/cbb/lines/dk_team_crosswalk_2026-11-25.csv \
  --adapters halves,fullgame --halves-path <halves checkout>/models/cbb \
  --fullgame-root <fullgame checkout>/models/cbb --challenger-games <fg data>/games_2027.csv \
  --challenger-finals <fg data>/season_finals.json [--no-fetch] [--no-grade]
```
`--mode grade --card <pipeline_card.json>` grades a frozen card from ESPN finals later.

## Known defects / gaps (left open)
- Team totals (FG and 1H): every row REJECTED `TOTALS_ORDER_UNVERIFIED`; the DK board carries no over/under order for them.
- Player props: `NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED` (players stream not landed). 2H halftime-adjusted: `NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE`.
- Frozen projections here use a public ESPN ratings reconstruction, not CBBD ratings; frozen totals run high (+2.8).
- The challenger inputs (`games_2027.csv`, `season_finals.json`) are sportsdataverse-derived files on the research box, not committed; their sha256 is recorded in the card.
- Half moneylines assume TIE_PUSH (DK settlement not verified). Halves totals run ~1.1-1.4 low on held-out 2026 data.
- Stars: `n/a uncalibrated` everywhere. CLV: unavailable (no later close board captured).
- Board provenance: UNAUTHENTICATED_PDF; no authenticated DK capture exists yet.
