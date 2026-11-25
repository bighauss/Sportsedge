# FG1C production-compatible refit (PAPER/0u, NON_COUNTED)

Coefficients: `models/cbb/halves/coefficients_halves_fg1c_v1.json` (sha256 `d5a6643d…d60e52`).
This file does **not** replace `coefficients_halves_v1.json`.

Inputs: FG1 walk-forward JSON from `models/cbb/fullgame` (PR #534), then the same chronological early/late de-bias as FG1C, with `--train-until 2025`. Source file hashes: `results/fg1c_projections_source_manifest.json`. 22,212 FG1C rows for 2022–2025; 2020–2021 have no FG1C forecast because the de-bias needs two prior seasons. Join to the halves dataset: 20,904 games.

Training window: seasons 2022–2025 only (20,904 games). **2026 is not in the training window.** Dev-fold scores below use coefficients fit on seasons < S, on the *identical* games that have an FG1C forecast.

| Season | n | H1 margin MAE PIT / FG1C | H1 margin bias PIT / FG1C | H1 total MAE PIT / FG1C | H1 total bias PIT / FG1C | H2 margin MAE PIT / FG1C | H2 total MAE PIT / FG1C |

|---|---|---|---|---|---|---|---|
| 2023 | 5177 | 7.482 / 7.334 | -0.618 / 0.375 | 7.816 / 7.788 | 0.071 / 0.468 | 7.123 / 6.972 | 9.478 / 9.453 |
| 2024 | 5355 | 7.315 / 7.185 | -0.844 / -0.186 | 7.905 / 7.834 | 0.347 / 0.274 | 7.249 / 7.167 | 9.525 / 9.452 |
| 2025 | 5421 | 7.554 / 7.380 | -0.570 / 0.079 | 8.029 / 7.928 | 0.424 / 0.104 | 7.072 / 6.957 | 9.370 / 9.315 |

FG1C is slightly sharper on these overlapping rows, and the PIT projector carries a negative margin bias on this (mostly D1) subset. This is a dev-fold comparison, not a 2026 test, and not a promotion claim. Totals bias is smaller under FG1C in 2024–2025 but is **not** used to rewrite v1 (see TOTALS_BIAS.md).

