# Joint (margin, total) and H1–H2 dependence (PAPER/0u, NON_COUNTED)

Generated from `joint_dev_report.json`, `joint_final_report.json` and `joint_secondary_2026.json`.

Joint coefficients sha256 `700af30eca3507eaa9fe6701d2d908c98ba4ce28562809d66d2ad5d0bd24efbf`. v1 means/SDs were not modified.

Copula kind was chosen on rolling-origin folds 2021–2025. Final correlations were fit on 2019–2025 only.

## Dev-fold kind choice (mean joint log score, lower is better)

| Period | Chosen | Gaussian | Independent | Empirical |
|---|---|---|---|---|
| H1 | gaussian | 7.4310 | 7.4333 | 9.6837 |
| H2 | independent | 7.5734 | 7.5734 | 9.7232 |
| H2REG | gaussian | 7.4766 | 7.4767 | 9.7158 |
| HT_H2 | gaussian | 7.5516 | 7.5517 | 9.7262 |
| HT_H2REG | independent | 7.4521 | 7.4521 | 9.6895 |

The empirical grid lost clearly (likely a coarse unit-square histogram, not used). Margin–total residual correlation is small; Gaussian and independence are nearly tied. The useful structure is H1–H2, especially totals (~+0.13), consistent with pace carrying over the break, and a slight negative H1–H2 margin residual correlation (~−0.08).

## Fitted H1–H2 correlations (2019–2025)

| Pair | Fitted rho |
|---|---|
| H1_MARGIN:H2_MARGIN | -0.0825 |
| H1_MARGIN:H2_TOTAL | 0.0094 |
| H1_TOTAL:H2_MARGIN | 0.0336 |
| H1_TOTAL:H2_TOTAL | 0.1337 |

## SECONDARY RE-USE of season 2026 (n=6,259). Not a first untouched test.

The 2026 window was already scored once for the univariate model. These joint numbers are reported only as a reuse.

| Period | Kind | Fitted ρ | Realized ρ | Joint log score | Independence log score |
|---|---|---|---|---|---|
| H1 | gaussian | 0.07461 | 0.0610 | 7.4735 | 7.4751 |
| H2 | independent | 0.0 | 0.0160 | 7.6183 | 7.6183 |
| H2REG | gaussian | 0.01415 | 0.0259 | 7.5211 | 7.5213 |
| HT_H2 | gaussian | -0.01061 | 0.0084 | 7.5964 | 7.5962 |
| HT_H2REG | independent | 0.0 | 0.0154 | 7.4943 | 7.4943 |

H1–H2 realized (2026 reuse) vs fitted:

| Pair | Fitted | Realized (2026 reuse) |
|---|---|---|
| H1_MARGIN:H2_MARGIN | -0.0825 | -0.0987 |
| H1_MARGIN:H2_TOTAL | 0.0094 | 0.0198 |
| H1_TOTAL:H2_MARGIN | 0.0336 | 0.0342 |
| H1_TOTAL:H2_TOTAL | 0.1337 | 0.1413 |
