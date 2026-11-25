# CBB rolling-origin backtest: tables (generated from `run3_final`)

Status: RESEARCH_PAPER_0U, label NON_COUNTED, official_counted=0, approved_stake_u=0.
Generated 2026-11-25T17:29:46.737660+00:00 UTC. Identical rows: 35791 of 47124 games. Models: native_frozen, raw, regularized, sched_adj, native_hca_repaired, FG1.
Splits: {'test': [2025, 2026], 'train': [2019, 2020, 2021], 'validation': [2022, 2023, 2024]}. Blend weights (independent share): [1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0] - source: Owner spec Nov 25 2026 (t26u item 6): 100/0, 87.5/12.5, 75/25, 62.5/37.5, 50/50, 37.5/62.5, 25/75, 12.5/87.5, 0/100.
Leakage: 175 origins checked, 0 violations; blend selection seasons [2022, 2023, 2024], test seasons [2025, 2026].
Market quarantine: {'2023': ['spread', 'total']}. CLV: BLOCKED_OPEN_LINES_FAIL_VALIDATION. Bootstrap: {'cluster': 'game date', 'reps': 1000}.

## 1. Coverage by season
| season | admitted_finals | with_possessions | rows | forecast_native_frozen | forecast_raw | forecast_regularized | forecast_sched_adj | forecast_native_hca_repaired | forecast_FG1 | all_builtin_forecast | market_any | market_spread | market_total | market_ml | market_open_any |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2019 | 6049 | 6047 | 6049 | 4790 | 4790 | 4790 | 4790 | 4790 | 5282 | 4790 | 5378 | 5375 | 5363 | 5133 | 0 |
| 2020 | 5767 | 5757 | 5767 | 4538 | 4538 | 4538 | 4538 | 4538 | 5032 | 4538 | 5313 | 5313 | 5312 | 5114 | 0 |
| 2021 | 4285 | 4280 | 4285 | 3138 | 3138 | 3138 | 3138 | 3138 | 3655 | 3138 | 3840 | 3839 | 3706 | 3736 | 0 |
| 2022 | 5966 | 5963 | 5966 | 4704 | 4703 | 4703 | 4703 | 4703 | 4714 | 4703 | 5419 | 5419 | 5419 | 5385 | 0 |
| 2023 | 6222 | 6220 | 6222 | 4906 | 4906 | 4906 | 4906 | 4906 | 5252 | 4906 | 5828 | 0 | 0 | 5670 | 0 |
| 2024 | 6243 | 6240 | 6243 | 4930 | 4930 | 4930 | 4930 | 4930 | 5383 | 4930 | 5754 | 5754 | 5752 | 5496 | 0 |
| 2025 | 6292 | 6285 | 6292 | 5022 | 5022 | 5022 | 5022 | 5022 | 5404 | 5022 | 5763 | 5763 | 5762 | 5647 | 0 |
| 2026 | 6300 | 6299 | 6300 | 5033 | 5033 | 5033 | 5033 | 5033 | 5416 | 5033 | 5749 | 5706 | 5734 | 5507 | 0 |

Providers per season (selected sportsbook row per game):

- 2019: {"Unibet": 5344, "consensus": 34}
- 2020: {"DraftKings": 5069, "Unibet": 231, "consensus": 13}
- 2021: {"Caesars Sportsbook (New Jersey)": 714, "DraftKings": 2958, "Unibet": 164, "consensus": 4}
- 2022: {"Caesars Sportsbook (Colorado)": 201, "Caesars Sportsbook (New Jersey)": 29, "DraftKings": 5142, "Unibet": 46, "consensus": 1}
- 2023: {"DraftKings": 5420, "ESPN BET": 406, "SugarHouse": 1, "Unibet": 1}
- 2024: {"BetfairSportsbook": 1, "Caesars Sportsbook (Colorado)": 21, "Caesars Sportsbook (New Jersey)": 11, "DraftKings": 5326, "ESPN BET": 368, "SugarHouse": 10, "Unibet": 17}
- 2025: {"ESPN BET": 5763}
- 2026: {"Draft Kings": 4805, "ESPN BET": 944}

## 2. Point accuracy on identical rows (pred - actual)
### TRAIN
| model | target | n | mae | rmse | bias | residual_sd |
|---|---|---|---|---|---|---|
| native_frozen | margin | 11898 | 10.140 | 12.797 | 4.036 | 12.144 |
| native_frozen | total | 11898 | 13.662 | 17.260 | 0.688 | 17.246 |
| raw | margin | 11898 | 10.052 | 12.806 | 0.491 | 12.797 |
| raw | total | 11898 | 14.081 | 17.788 | 0.731 | 17.773 |
| regularized | margin | 11898 | 9.348 | 11.861 | 0.118 | 11.860 |
| regularized | total | 11898 | 13.603 | 17.183 | 0.714 | 17.168 |
| sched_adj | margin | 11898 | 9.323 | 11.822 | 0.290 | 11.819 |
| sched_adj | total | 11898 | 13.634 | 17.213 | 0.685 | 17.199 |
| native_hca_repaired | margin | 11898 | 9.534 | 12.095 | 0.074 | 12.095 |
| native_hca_repaired | total | 11898 | 13.662 | 17.260 | 0.688 | 17.246 |
| FG1 | margin | 11898 | 8.937 | 11.343 | 0.451 | 11.334 |
| FG1 | total | 11898 | 13.354 | 16.849 | 0.660 | 16.836 |

### VALIDATION
| model | target | n | mae | rmse | bias | residual_sd |
|---|---|---|---|---|---|---|
| native_frozen | margin | 13950 | 10.448 | 13.104 | 4.884 | 12.160 |
| native_frozen | total | 13950 | 13.364 | 16.978 | -0.305 | 16.975 |
| raw | margin | 13950 | 10.018 | 12.674 | 0.754 | 12.652 |
| raw | total | 13950 | 13.771 | 17.463 | -0.233 | 17.462 |
| regularized | margin | 13950 | 9.386 | 11.877 | 0.412 | 11.870 |
| regularized | total | 13950 | 13.303 | 16.911 | -0.316 | 16.908 |
| sched_adj | margin | 13950 | 9.422 | 11.941 | 0.513 | 11.930 |
| sched_adj | total | 13950 | 13.333 | 16.946 | -0.359 | 16.942 |
| native_hca_repaired | margin | 13950 | 9.542 | 12.062 | 0.364 | 12.057 |
| native_hca_repaired | total | 13950 | 13.364 | 16.978 | -0.305 | 16.975 |
| FG1 | margin | 13950 | 8.936 | 11.300 | 0.349 | 11.294 |
| FG1 | total | 13950 | 13.095 | 16.643 | -0.184 | 16.642 |

### TEST
| model | target | n | mae | rmse | bias | residual_sd |
|---|---|---|---|---|---|---|
| native_frozen | margin | 9943 | 10.876 | 13.702 | 5.222 | 12.668 |
| native_frozen | total | 9943 | 13.691 | 17.338 | 0.947 | 17.312 |
| raw | margin | 9943 | 10.241 | 13.042 | 0.628 | 13.027 |
| raw | total | 9943 | 14.076 | 17.824 | 1.205 | 17.784 |
| regularized | margin | 9943 | 9.658 | 12.381 | 0.162 | 12.380 |
| regularized | total | 9943 | 13.620 | 17.257 | 0.903 | 17.234 |
| sched_adj | margin | 9943 | 9.730 | 12.498 | 0.249 | 12.495 |
| sched_adj | total | 9943 | 13.613 | 17.249 | 0.815 | 17.230 |
| native_hca_repaired | margin | 9943 | 9.799 | 12.567 | 0.100 | 12.567 |
| native_hca_repaired | total | 9943 | 13.691 | 17.338 | 0.947 | 17.312 |
| FG1 | margin | 9943 | 9.113 | 11.622 | 0.347 | 11.617 |
| FG1 | total | 9943 | 13.346 | 16.901 | 0.895 | 16.877 |

### ALL
| model | target | n | mae | rmse | bias | residual_sd |
|---|---|---|---|---|---|---|
| native_frozen | margin | 35791 | 10.465 | 13.173 | 4.696 | 12.308 |
| native_frozen | total | 35791 | 13.554 | 17.172 | 0.373 | 17.168 |
| raw | margin | 35791 | 10.091 | 12.821 | 0.631 | 12.806 |
| raw | total | 35791 | 13.959 | 17.672 | 0.487 | 17.665 |
| regularized | margin | 35791 | 9.449 | 12.014 | 0.245 | 12.011 |
| regularized | total | 35791 | 13.491 | 17.098 | 0.365 | 17.094 |
| sched_adj | margin | 35791 | 9.475 | 12.059 | 0.366 | 12.054 |
| sched_adj | total | 35791 | 13.511 | 17.120 | 0.314 | 17.117 |
| native_hca_repaired | margin | 35791 | 9.611 | 12.216 | 0.194 | 12.214 |
| native_hca_repaired | total | 35791 | 13.554 | 17.172 | 0.373 | 17.168 |
| FG1 | margin | 35791 | 8.985 | 11.404 | 0.383 | 11.398 |
| FG1 | total | 35791 | 13.251 | 16.784 | 0.396 | 16.779 |

## 3. Clustered (by date) bootstrap 95% CIs, ALL identical rows
| model | metric | n | estimate | ci95_lo | ci95_hi | delta_vs_native | delta_ci95_lo | delta_ci95_hi |
|---|---|---|---|---|---|---|---|---|
| native_frozen | mae_margin | 35791 | 10.465 | 10.347 | 10.579 | 0.000 | - | - |
| native_frozen | bias_margin | 35791 | 4.696 | 4.471 | 4.913 | - | - | - |
| native_frozen | mae_total | 35791 | 13.554 | 13.437 | 13.653 | 0.000 | - | - |
| native_frozen | bias_total | 35791 | 0.373 | 0.180 | 0.577 | - | - | - |
| native_frozen | logloss_minus_market_ml | 34863 | 0.081 | 0.076 | 0.086 | - | - | - |
| native_frozen | logloss_minus_market_spread | 30486 | 0.090 | 0.083 | 0.096 | - | - | - |
| native_frozen | logloss_minus_market_total | 30538 | 0.028 | 0.025 | 0.031 | - | - | - |
| raw | mae_margin | 35791 | 10.091 | 9.976 | 10.209 | -0.374 | -0.455 | -0.275 |
| raw | bias_margin | 35791 | 0.631 | 0.453 | 0.800 | - | - | - |
| raw | mae_total | 35791 | 13.959 | 13.840 | 14.074 | 0.405 | 0.371 | 0.444 |
| raw | bias_total | 35791 | 0.487 | 0.288 | 0.691 | - | - | - |
| raw | logloss_minus_market_ml | 34863 | 0.059 | 0.054 | 0.064 | - | - | - |
| raw | logloss_minus_market_spread | 30486 | 0.077 | 0.070 | 0.083 | - | - | - |
| raw | logloss_minus_market_total | 30538 | 0.045 | 0.041 | 0.049 | - | - | - |
| regularized | mae_margin | 35791 | 9.449 | 9.353 | 9.548 | -1.016 | -1.095 | -0.936 |
| regularized | bias_margin | 35791 | 0.245 | 0.040 | 0.443 | - | - | - |
| regularized | mae_total | 35791 | 13.491 | 13.378 | 13.589 | -0.063 | -0.076 | -0.052 |
| regularized | bias_total | 35791 | 0.365 | 0.174 | 0.568 | - | - | - |
| regularized | logloss_minus_market_ml | 34863 | 0.037 | 0.034 | 0.040 | - | - | - |
| regularized | logloss_minus_market_spread | 30486 | 0.044 | 0.040 | 0.049 | - | - | - |
| regularized | logloss_minus_market_total | 30538 | 0.025 | 0.022 | 0.028 | - | - | - |
| sched_adj | mae_margin | 35791 | 9.475 | 9.369 | 9.576 | -0.990 | -1.070 | -0.908 |
| sched_adj | bias_margin | 35791 | 0.366 | 0.149 | 0.579 | - | - | - |
| sched_adj | mae_total | 35791 | 13.511 | 13.400 | 13.611 | -0.043 | -0.056 | -0.029 |
| sched_adj | bias_total | 35791 | 0.314 | 0.124 | 0.518 | - | - | - |
| sched_adj | logloss_minus_market_ml | 34863 | 0.035 | 0.032 | 0.038 | - | - | - |
| sched_adj | logloss_minus_market_spread | 30486 | 0.046 | 0.041 | 0.051 | - | - | - |
| sched_adj | logloss_minus_market_total | 30538 | 0.026 | 0.023 | 0.029 | - | - | - |
| native_hca_repaired | mae_margin | 35791 | 9.611 | 9.509 | 9.712 | -0.854 | -0.928 | -0.773 |
| native_hca_repaired | bias_margin | 35791 | 0.194 | -0.013 | 0.397 | - | - | - |
| native_hca_repaired | mae_total | 35791 | 13.554 | 13.437 | 13.653 | -0.000 | -0.000 | 0.000 |
| native_hca_repaired | bias_total | 35791 | 0.373 | 0.180 | 0.577 | - | - | - |
| native_hca_repaired | logloss_minus_market_ml | 34863 | 0.045 | 0.042 | 0.048 | - | - | - |
| native_hca_repaired | logloss_minus_market_spread | 30486 | 0.052 | 0.048 | 0.058 | - | - | - |
| native_hca_repaired | logloss_minus_market_total | 30538 | 0.028 | 0.025 | 0.031 | - | - | - |
| FG1 | mae_margin | 35791 | 8.985 | 8.905 | 9.064 | -1.479 | -1.559 | -1.402 |
| FG1 | bias_margin | 35791 | 0.383 | 0.242 | 0.520 | - | - | - |
| FG1 | mae_total | 35791 | 13.251 | 13.140 | 13.350 | -0.303 | -0.341 | -0.261 |
| FG1 | bias_total | 35791 | 0.396 | 0.213 | 0.593 | - | - | - |
| FG1 | logloss_minus_market_ml | 34863 | 0.013 | 0.012 | 0.015 | - | - | - |
| FG1 | logloss_minus_market_spread | 30486 | 0.017 | 0.015 | 0.020 | - | - | - |
| FG1 | logloss_minus_market_total | 30538 | 0.014 | 0.012 | 0.016 | - | - | - |

## 4. Probability metrics (Brier, log loss, ECE)
### VALIDATION
| family | model | basis | n | brier | log_loss | ece | mean_p | freq |
|---|---|---|---|---|---|---|---|---|
| ml | native_frozen | identical rows | 13950 | 0.2156 | 0.6227 | 0.1038 | 0.7258 | 0.6220 |
| ml | raw | identical rows | 13950 | 0.2037 | 0.5987 | 0.0353 | 0.6167 | 0.6220 |
| ml | regularized | identical rows | 13950 | 0.1976 | 0.5779 | 0.0239 | 0.6316 | 0.6220 |
| ml | sched_adj | identical rows | 13950 | 0.1974 | 0.5774 | 0.0197 | 0.6328 | 0.6220 |
| ml | native_hca_repaired | identical rows | 13950 | 0.2008 | 0.5853 | 0.0147 | 0.6276 | 0.6220 |
| ml | FG1 | identical rows | 13950 | 0.1882 | 0.5543 | 0.0216 | 0.6292 | 0.6220 |
| ml | MARKET_NOVIG_CLOSE | market rows | 13662 | 0.1855 | 0.5488 | 0.0209 | 0.6047 | 0.6162 |
| spread | native_frozen | identical rows with close line | 8985 | 0.2880 | 0.7874 | 0.1702 | 0.6324 | 0.4918 |
| spread | raw | identical rows with close line | 8985 | 0.2782 | 0.7691 | 0.1349 | 0.5179 | 0.4918 |
| spread | regularized | identical rows with close line | 8985 | 0.2693 | 0.7395 | 0.1102 | 0.5091 | 0.4918 |
| spread | sched_adj | identical rows with close line | 8985 | 0.2698 | 0.7423 | 0.1051 | 0.5140 | 0.4918 |
| spread | native_hca_repaired | identical rows with close line | 8985 | 0.2717 | 0.7467 | 0.1158 | 0.5078 | 0.4918 |
| spread | FG1 | identical rows with close line | 8985 | 0.2582 | 0.7108 | 0.0704 | 0.5104 | 0.4918 |
| spread | MARKET_NOVIG_CLOSE | market rows | 8985 | 0.2500 | 0.6932 | 0.0088 | 0.5003 | 0.4918 |
| total | native_frozen | identical rows with close line | 9046 | 0.2618 | 0.7191 | 0.0854 | 0.5182 | 0.5090 |
| total | raw | identical rows with close line | 9046 | 0.2676 | 0.7334 | 0.1074 | 0.5194 | 0.5090 |
| total | regularized | identical rows with close line | 9046 | 0.2606 | 0.7165 | 0.0844 | 0.5180 | 0.5090 |
| total | sched_adj | identical rows with close line | 9046 | 0.2613 | 0.7179 | 0.0870 | 0.5165 | 0.5090 |
| total | native_hca_repaired | identical rows with close line | 9046 | 0.2618 | 0.7191 | 0.0854 | 0.5182 | 0.5090 |
| total | FG1 | identical rows with close line | 9046 | 0.2562 | 0.7059 | 0.0625 | 0.5211 | 0.5090 |
| total | MARKET_NOVIG_CLOSE | market rows | 9046 | 0.2498 | 0.6928 | 0.0085 | 0.5004 | 0.5090 |

### TEST
| family | model | basis | n | brier | log_loss | ece | mean_p | freq |
|---|---|---|---|---|---|---|---|---|
| ml | native_frozen | identical rows | 9943 | 0.2181 | 0.6276 | 0.1094 | 0.7290 | 0.6195 |
| ml | raw | identical rows | 9943 | 0.2031 | 0.5951 | 0.0375 | 0.6160 | 0.6195 |
| ml | regularized | identical rows | 9943 | 0.1977 | 0.5777 | 0.0287 | 0.6269 | 0.6195 |
| ml | sched_adj | identical rows | 9943 | 0.1979 | 0.5785 | 0.0232 | 0.6278 | 0.6195 |
| ml | native_hca_repaired | identical rows | 9943 | 0.2007 | 0.5844 | 0.0126 | 0.6225 | 0.6195 |
| ml | FG1 | identical rows | 9943 | 0.1874 | 0.5503 | 0.0221 | 0.6315 | 0.6195 |
| ml | MARKET_NOVIG_CLOSE | market rows | 9698 | 0.1837 | 0.5419 | 0.0149 | 0.6088 | 0.6137 |
| spread | native_frozen | identical rows with close line | 9899 | 0.2905 | 0.7947 | 0.1716 | 0.6366 | 0.4952 |
| spread | raw | identical rows with close line | 9899 | 0.2785 | 0.7712 | 0.1305 | 0.5185 | 0.4952 |
| spread | regularized | identical rows with close line | 9899 | 0.2699 | 0.7448 | 0.1065 | 0.5076 | 0.4952 |
| spread | sched_adj | identical rows with close line | 9899 | 0.2704 | 0.7498 | 0.1044 | 0.5124 | 0.4952 |
| spread | native_hca_repaired | identical rows with close line | 9899 | 0.2718 | 0.7515 | 0.1149 | 0.5061 | 0.4952 |
| spread | FG1 | identical rows with close line | 9899 | 0.2596 | 0.7140 | 0.0785 | 0.5103 | 0.4952 |
| spread | MARKET_NOVIG_CLOSE | market rows | 9897 | 0.2499 | 0.6929 | 0.0048 | 0.4999 | 0.4951 |
| total | native_frozen | identical rows with close line | 9924 | 0.2645 | 0.7254 | 0.0979 | 0.5335 | 0.4950 |
| total | raw | identical rows with close line | 9924 | 0.2707 | 0.7424 | 0.1126 | 0.5371 | 0.4950 |
| total | regularized | identical rows with close line | 9924 | 0.2629 | 0.7219 | 0.0912 | 0.5329 | 0.4950 |
| total | sched_adj | identical rows with close line | 9924 | 0.2628 | 0.7216 | 0.0909 | 0.5309 | 0.4950 |
| total | native_hca_repaired | identical rows with close line | 9924 | 0.2645 | 0.7254 | 0.0979 | 0.5335 | 0.4950 |
| total | FG1 | identical rows with close line | 9924 | 0.2584 | 0.7109 | 0.0703 | 0.5343 | 0.4950 |
| total | MARKET_NOVIG_CLOSE | market rows | 9920 | 0.2499 | 0.6930 | 0.0053 | 0.5001 | 0.4949 |

## 5. Bias splits (ALL identical rows)
| model | dimension | cell | target | n | bias_pred_minus_actual | mae | rmse | residual_sd |
|---|---|---|---|---|---|---|---|---|
| native_frozen | actual_ou | went_over | total | 15281 | -12.578 | 13.360 | 17.436 | 12.075 |
| native_frozen | actual_ou | went_under_or_push | total | 15444 | 13.520 | 13.854 | 17.053 | 10.393 |
| native_frozen | market_fav_persp | favorite | margin | 30772 | 0.216 | 10.463 | 13.185 | 13.183 |
| native_frozen | market_fav_persp | underdog | margin | 30772 | -0.216 | 10.463 | 13.185 | 13.183 |
| native_frozen | model_fav | away_fav | margin_home_persp | 3774 | 2.651 | 10.245 | 13.034 | 12.762 |
| native_frozen | model_fav | home_fav | margin_home_persp | 32017 | 4.937 | 10.491 | 13.189 | 12.230 |
| native_frozen | ou_vs_market | model_over | total | 18031 | 3.706 | 13.763 | 17.309 | 16.908 |
| native_frozen | ou_vs_market | model_under | total | 12694 | -3.955 | 13.388 | 17.152 | 16.690 |
| native_frozen | spread_band | 0-3 | margin_fav_persp | 7788 | 0.334 | 10.533 | 13.174 | 13.170 |
| native_frozen | spread_band | 12.5-20 | margin_fav_persp | 3911 | -0.421 | 10.200 | 12.912 | 12.905 |
| native_frozen | spread_band | 20+ | margin_fav_persp | 1234 | -4.782 | 11.363 | 14.408 | 13.591 |
| native_frozen | spread_band | 3.5-7 | margin_fav_persp | 10601 | 0.665 | 10.554 | 13.291 | 13.274 |
| native_frozen | spread_band | 7.5-12 | margin_fav_persp | 7238 | 0.629 | 10.243 | 12.966 | 12.950 |
| native_frozen | venue | home_court | margin_home_persp | 31887 | 5.412 | 10.560 | 13.276 | 12.123 |
| native_frozen | venue | home_court | total | 31887 | 0.119 | 13.536 | 17.161 | 17.160 |
| native_frozen | venue | neutral | margin_home_persp | 3904 | -1.156 | 9.686 | 12.300 | 12.245 |
| native_frozen | venue | neutral | total | 3904 | 2.445 | 13.696 | 17.267 | 17.094 |
| raw | actual_ou | went_over | total | 15281 | -12.515 | 13.679 | 17.786 | 12.638 |
| raw | actual_ou | went_under_or_push | total | 15444 | 13.718 | 14.340 | 17.710 | 11.201 |
| raw | market_fav_persp | favorite | margin | 30772 | 0.413 | 10.107 | 12.845 | 12.838 |
| raw | market_fav_persp | underdog | margin | 30772 | -0.413 | 10.107 | 12.845 | 12.838 |
| raw | model_fav | away_fav | margin_home_persp | 10927 | -3.522 | 10.350 | 13.174 | 12.694 |
| raw | model_fav | home_fav | margin_home_persp | 24864 | 2.457 | 9.978 | 12.663 | 12.423 |
| raw | ou_vs_market | model_over | total | 17913 | 4.785 | 14.241 | 17.938 | 17.288 |
| raw | ou_vs_market | model_under | total | 12812 | -5.080 | 13.691 | 17.478 | 16.723 |
| raw | spread_band | 0-3 | margin_fav_persp | 7788 | 0.139 | 9.843 | 12.419 | 12.418 |
| raw | spread_band | 12.5-20 | margin_fav_persp | 3911 | 0.218 | 10.542 | 13.382 | 13.380 |
| raw | spread_band | 20+ | margin_fav_persp | 1234 | -2.321 | 12.679 | 15.976 | 15.806 |
| raw | spread_band | 3.5-7 | margin_fav_persp | 10601 | 0.605 | 9.966 | 12.635 | 12.620 |
| raw | spread_band | 7.5-12 | margin_fav_persp | 7238 | 0.996 | 9.924 | 12.705 | 12.666 |
| raw | venue | home_court | margin_home_persp | 31887 | 0.790 | 10.046 | 12.747 | 12.722 |
| raw | venue | home_court | total | 31887 | 0.205 | 13.914 | 17.627 | 17.626 |
| raw | venue | neutral | margin_home_persp | 3904 | -0.667 | 10.461 | 13.413 | 13.396 |
| raw | venue | neutral | total | 3904 | 2.793 | 14.325 | 18.038 | 17.820 |
| regularized | actual_ou | went_over | total | 15281 | -12.553 | 13.301 | 17.382 | 12.024 |
| regularized | actual_ou | went_under_or_push | total | 15444 | 13.480 | 13.788 | 16.958 | 10.289 |
| regularized | market_fav_persp | favorite | margin | 30772 | -1.714 | 9.464 | 12.045 | 11.923 |
| regularized | market_fav_persp | underdog | margin | 30772 | 1.714 | 9.464 | 12.045 | 11.923 |
| regularized | model_fav | away_fav | margin_home_persp | 8190 | 1.177 | 9.515 | 12.023 | 11.966 |
| regularized | model_fav | home_fav | margin_home_persp | 27601 | -0.032 | 9.429 | 12.011 | 12.011 |
| regularized | ou_vs_market | model_over | total | 18168 | 3.530 | 13.655 | 17.173 | 16.807 |
| regularized | ou_vs_market | model_under | total | 12557 | -3.804 | 13.388 | 17.166 | 16.739 |
| regularized | spread_band | 0-3 | margin_fav_persp | 7788 | -0.210 | 9.142 | 11.469 | 11.467 |
| regularized | spread_band | 12.5-20 | margin_fav_persp | 3911 | -4.274 | 9.836 | 12.627 | 11.881 |
| regularized | spread_band | 20+ | margin_fav_persp | 1234 | -11.179 | 14.135 | 17.588 | 13.579 |
| regularized | spread_band | 3.5-7 | margin_fav_persp | 10601 | -0.730 | 9.266 | 11.681 | 11.658 |
| regularized | spread_band | 7.5-12 | margin_fav_persp | 7238 | -1.777 | 9.103 | 11.686 | 11.550 |
| regularized | venue | home_court | margin_home_persp | 31887 | 0.415 | 9.438 | 12.001 | 11.994 |
| regularized | venue | home_court | total | 31887 | 0.110 | 13.472 | 17.084 | 17.084 |
| regularized | venue | neutral | margin_home_persp | 3904 | -1.145 | 9.536 | 12.119 | 12.065 |
| regularized | venue | neutral | total | 3904 | 2.444 | 13.643 | 17.213 | 17.039 |
| sched_adj | actual_ou | went_over | total | 15281 | -12.636 | 13.366 | 17.430 | 12.005 |
| sched_adj | actual_ou | went_under_or_push | total | 15444 | 13.450 | 13.761 | 16.949 | 10.314 |
| sched_adj | market_fav_persp | favorite | margin | 30772 | -1.459 | 9.488 | 12.086 | 11.997 |
| sched_adj | market_fav_persp | underdog | margin | 30772 | 1.459 | 9.488 | 12.086 | 11.997 |
| sched_adj | model_fav | away_fav | margin_home_persp | 8278 | 1.065 | 9.495 | 12.039 | 11.991 |
| sched_adj | model_fav | home_fav | margin_home_persp | 27513 | 0.155 | 9.468 | 12.066 | 12.065 |
| sched_adj | ou_vs_market | model_over | total | 17966 | 3.544 | 13.735 | 17.283 | 16.916 |
| sched_adj | ou_vs_market | model_under | total | 12759 | -3.843 | 13.323 | 17.058 | 16.619 |
| sched_adj | spread_band | 0-3 | margin_fav_persp | 7788 | -0.089 | 9.095 | 11.382 | 11.382 |
| sched_adj | spread_band | 12.5-20 | margin_fav_persp | 3911 | -3.916 | 10.006 | 12.801 | 12.188 |
| sched_adj | spread_band | 20+ | margin_fav_persp | 1234 | -12.221 | 15.075 | 18.598 | 14.019 |
| sched_adj | spread_band | 3.5-7 | margin_fav_persp | 10601 | -0.427 | 9.223 | 11.642 | 11.634 |
| sched_adj | spread_band | 7.5-12 | margin_fav_persp | 7238 | -1.285 | 9.066 | 11.643 | 11.572 |
| sched_adj | venue | home_court | margin_home_persp | 31887 | 0.508 | 9.483 | 12.073 | 12.063 |
| sched_adj | venue | home_court | total | 31887 | 0.064 | 13.493 | 17.107 | 17.107 |
| sched_adj | venue | neutral | margin_home_persp | 3904 | -0.800 | 9.404 | 11.943 | 11.916 |
| sched_adj | venue | neutral | total | 3904 | 2.361 | 13.656 | 17.220 | 17.058 |
| native_hca_repaired | actual_ou | went_over | total | 15281 | -12.578 | 13.360 | 17.436 | 12.075 |
| native_hca_repaired | actual_ou | went_under_or_push | total | 15444 | 13.520 | 13.854 | 17.053 | 10.393 |
| native_hca_repaired | market_fav_persp | favorite | margin | 30772 | -1.774 | 9.624 | 12.245 | 12.116 |
| native_hca_repaired | market_fav_persp | underdog | margin | 30772 | 1.774 | 9.624 | 12.245 | 12.116 |
| native_hca_repaired | model_fav | away_fav | margin_home_persp | 8658 | 0.210 | 9.640 | 12.192 | 12.190 |
| native_hca_repaired | model_fav | home_fav | margin_home_persp | 27133 | 0.189 | 9.601 | 12.223 | 12.222 |
| native_hca_repaired | ou_vs_market | model_over | total | 18031 | 3.706 | 13.763 | 17.309 | 16.908 |
| native_hca_repaired | ou_vs_market | model_under | total | 12694 | -3.955 | 13.388 | 17.152 | 16.690 |
| native_hca_repaired | spread_band | 0-3 | margin_fav_persp | 7788 | -0.210 | 9.246 | 11.594 | 11.592 |
| native_hca_repaired | spread_band | 12.5-20 | margin_fav_persp | 3911 | -4.452 | 10.111 | 12.969 | 12.181 |
| native_hca_repaired | spread_band | 20+ | margin_fav_persp | 1234 | -11.684 | 14.643 | 18.179 | 13.927 |
| native_hca_repaired | spread_band | 3.5-7 | margin_fav_persp | 10601 | -0.753 | 9.391 | 11.827 | 11.803 |
| native_hca_repaired | spread_band | 7.5-12 | margin_fav_persp | 7238 | -1.818 | 9.252 | 11.864 | 11.724 |
| native_hca_repaired | venue | home_court | margin_home_persp | 31887 | 0.359 | 9.602 | 12.205 | 12.200 |
| native_hca_repaired | venue | home_court | total | 31887 | 0.119 | 13.536 | 17.161 | 17.160 |
| native_hca_repaired | venue | neutral | margin_home_persp | 3904 | -1.156 | 9.686 | 12.300 | 12.245 |
| native_hca_repaired | venue | neutral | total | 3904 | 2.445 | 13.696 | 17.267 | 17.094 |
| FG1 | actual_ou | went_over | total | 15281 | -12.554 | 12.969 | 17.082 | 11.584 |
| FG1 | actual_ou | went_under_or_push | total | 15444 | 13.502 | 13.628 | 16.618 | 9.688 |
| FG1 | market_fav_persp | favorite | margin | 30772 | -0.695 | 8.988 | 11.417 | 11.396 |
| FG1 | market_fav_persp | underdog | margin | 30772 | 0.695 | 8.988 | 11.417 | 11.396 |
| FG1 | model_fav | away_fav | margin_home_persp | 9122 | 0.961 | 9.044 | 11.427 | 11.387 |
| FG1 | model_fav | home_fav | margin_home_persp | 26669 | 0.185 | 8.965 | 11.396 | 11.395 |
| FG1 | ou_vs_market | model_over | total | 20006 | 2.322 | 13.333 | 16.849 | 16.688 |
| FG1 | ou_vs_market | model_under | total | 10719 | -2.778 | 13.238 | 16.852 | 16.621 |
| FG1 | spread_band | 0-3 | margin_fav_persp | 7788 | -0.137 | 8.928 | 11.170 | 11.169 |
| FG1 | spread_band | 12.5-20 | margin_fav_persp | 3911 | -1.750 | 8.937 | 11.473 | 11.339 |
| FG1 | spread_band | 20+ | margin_fav_persp | 1234 | -5.094 | 10.724 | 13.602 | 12.612 |
| FG1 | spread_band | 3.5-7 | margin_fav_persp | 10601 | -0.226 | 9.017 | 11.420 | 11.418 |
| FG1 | spread_band | 7.5-12 | margin_fav_persp | 7238 | -0.663 | 8.743 | 11.235 | 11.215 |
| FG1 | venue | home_court | margin_home_persp | 31887 | 0.494 | 8.971 | 11.385 | 11.374 |
| FG1 | venue | home_court | total | 31887 | 0.138 | 13.235 | 16.781 | 16.780 |
| FG1 | venue | neutral | margin_home_persp | 3904 | -0.527 | 9.100 | 11.559 | 11.547 |
| FG1 | venue | neutral | total | 3904 | 2.503 | 13.384 | 16.806 | 16.619 |

## 6. HCA diagnostics (home-court identical rows)
| model | season | n_home_court_rows | mean_hca_applied | mean_pred_margin | mean_actual_margin |
|---|---|---|---|---|---|
| native_frozen | 2019 | 3954 | 8.61 | 9.01 | 4.37 |
| native_frozen | 2020 | 4160 | 9.17 | 9.59 | 4.65 |
| native_frozen | 2021 | 2705 | 6.48 | 6.76 | 3.08 |
| native_frozen | 2022 | 3814 | 9.09 | 9.47 | 3.89 |
| native_frozen | 2023 | 4216 | 9.75 | 10.02 | 4.50 |
| native_frozen | 2024 | 4367 | 9.83 | 10.22 | 4.40 |
| native_frozen | 2025 | 4310 | 10.11 | 10.57 | 4.64 |
| native_frozen | 2026 | 4361 | 10.47 | 11.04 | 4.58 |
| raw | 2019 | 3954 | 4.50 | 5.23 | 4.37 |
| raw | 2020 | 4160 | 4.49 | 5.39 | 4.65 |
| raw | 2021 | 2705 | 2.26 | 2.85 | 3.08 |
| raw | 2022 | 3814 | 4.09 | 4.88 | 3.89 |
| raw | 2023 | 4216 | 4.80 | 5.39 | 4.50 |
| raw | 2024 | 4367 | 4.53 | 5.33 | 4.40 |
| raw | 2025 | 4310 | 4.40 | 5.38 | 4.64 |
| raw | 2026 | 4361 | 4.43 | 5.62 | 4.58 |
| regularized | 2019 | 3954 | 4.50 | 4.94 | 4.37 |
| regularized | 2020 | 4160 | 4.49 | 4.97 | 4.65 |
| regularized | 2021 | 2705 | 2.26 | 2.57 | 3.08 |
| regularized | 2022 | 3814 | 4.09 | 4.54 | 3.89 |
| regularized | 2023 | 4216 | 4.80 | 5.15 | 4.50 |
| regularized | 2024 | 4367 | 4.53 | 4.96 | 4.40 |
| regularized | 2025 | 4310 | 4.40 | 4.93 | 4.64 |
| regularized | 2026 | 4361 | 4.43 | 5.06 | 4.58 |
| sched_adj | 2019 | 3954 | 4.50 | 5.11 | 4.37 |
| sched_adj | 2020 | 4160 | 4.49 | 5.06 | 4.65 |
| sched_adj | 2021 | 2705 | 2.26 | 2.85 | 3.08 |
| sched_adj | 2022 | 3814 | 4.09 | 4.62 | 3.89 |
| sched_adj | 2023 | 4216 | 4.80 | 5.21 | 4.50 |
| sched_adj | 2024 | 4367 | 4.53 | 5.03 | 4.40 |
| sched_adj | 2025 | 4310 | 4.40 | 4.97 | 4.64 |
| sched_adj | 2026 | 4361 | 4.43 | 5.09 | 4.58 |
| native_hca_repaired | 2019 | 3954 | 4.50 | 4.89 | 4.37 |
| native_hca_repaired | 2020 | 4160 | 4.49 | 4.92 | 4.65 |
| native_hca_repaired | 2021 | 2705 | 2.26 | 2.54 | 3.08 |
| native_hca_repaired | 2022 | 3814 | 4.09 | 4.48 | 3.89 |
| native_hca_repaired | 2023 | 4216 | 4.80 | 5.07 | 4.50 |
| native_hca_repaired | 2024 | 4367 | 4.53 | 4.92 | 4.40 |
| native_hca_repaired | 2025 | 4310 | 4.40 | 4.87 | 4.64 |
| native_hca_repaired | 2026 | 4361 | 4.43 | 5.00 | 4.58 |
| FG1 | 2019 | 3954 | 3.76 | 4.75 | 4.37 |
| FG1 | 2020 | 4160 | 4.00 | 4.98 | 4.65 |
| FG1 | 2021 | 2705 | 3.35 | 4.04 | 3.08 |
| FG1 | 2022 | 3814 | 3.58 | 4.50 | 3.89 |
| FG1 | 2023 | 4216 | 3.83 | 4.71 | 4.50 |
| FG1 | 2024 | 4367 | 3.99 | 5.02 | 4.40 |
| FG1 | 2025 | 4310 | 3.90 | 5.01 | 4.64 |
| FG1 | 2026 | 4361 | 3.89 | 5.20 | 4.58 |

## 7. Nine blend weights - every weight evaluated independently (VALIDATION and TEST)
p = w * p_independent + (1 - w) * p_market_novig_close. ROI = flat 1u on the positive-EV side at the close price; max drawdown in units, chronological.

### VALIDATION
| model | family | w_independent | n | log_loss | brier | close_n_bets | close_roi | close_units | close_max_dd_u |
|---|---|---|---|---|---|---|---|---|---|
| native_frozen | ml | 1.0000 | 13662 | 0.6311 | 0.2188 | 12017 | -0.0787 | -946.3114 | 946.3114 |
| native_frozen | ml | 0.8750 | 13662 | 0.6090 | 0.2110 | 11785 | -0.0801 | -944.1788 | 944.1788 |
| native_frozen | ml | 0.7500 | 13662 | 0.5918 | 0.2042 | 11493 | -0.0823 | -946.2552 | 946.2552 |
| native_frozen | ml | 0.6250 | 13662 | 0.5783 | 0.1984 | 11106 | -0.0842 | -934.6670 | 938.3039 |
| native_frozen | ml | 0.5000 | 13662 | 0.5677 | 0.1937 | 10564 | -0.0870 | -918.6628 | 918.6628 |
| native_frozen | ml | 0.3750 | 13662 | 0.5595 | 0.1901 | 9791 | -0.0886 | -867.6627 | 872.1471 |
| native_frozen | ml | 0.2500 | 13662 | 0.5537 | 0.1875 | 8411 | -0.0896 | -753.7616 | 760.9455 |
| native_frozen | ml | 0.1250 | 13662 | 0.5501 | 0.1859 | 5426 | -0.1029 | -558.2395 | 569.4695 |
| native_frozen | ml | 0.0000 | 13662 | 0.5488 | 0.1855 | 0.0000 | - | 0.0000 | 0.0000 |
| native_frozen | spread | 1.0000 | 8985 | 0.7874 | 0.2880 | 8476 | -0.0630 | -533.7225 | 538.9967 |
| native_frozen | spread | 0.8750 | 8985 | 0.7607 | 0.2792 | 8388 | -0.0634 | -531.5680 | 537.9330 |
| native_frozen | spread | 0.7500 | 8985 | 0.7407 | 0.2715 | 8269 | -0.0616 | -509.0417 | 515.4544 |
| native_frozen | spread | 0.6250 | 8985 | 0.7252 | 0.2650 | 8089 | -0.0607 | -490.6134 | 498.5354 |
| native_frozen | spread | 0.5000 | 8985 | 0.7133 | 0.2597 | 7796 | -0.0598 | -466.1709 | 475.8164 |
| native_frozen | spread | 0.3750 | 8985 | 0.7045 | 0.2555 | 7330 | -0.0558 | -408.7616 | 419.2772 |
| native_frozen | spread | 0.2500 | 8985 | 0.6983 | 0.2525 | 6334 | -0.0567 | -359.1132 | 379.0527 |
| native_frozen | spread | 0.1250 | 8985 | 0.6946 | 0.2507 | 3453 | -0.0342 | -118.1222 | 149.1712 |
| native_frozen | spread | 0.0000 | 8985 | 0.6932 | 0.2500 | 0.0000 | - | 0.0000 | 0.0000 |
| native_frozen | total | 1.0000 | 9046 | 0.7191 | 0.2618 | 7492 | -0.0508 | -380.9196 | 390.9669 |
| native_frozen | total | 0.8750 | 9046 | 0.7125 | 0.2590 | 7251 | -0.0519 | -376.6522 | 383.9216 |
| native_frozen | total | 0.7500 | 9046 | 0.7071 | 0.2567 | 6938 | -0.0529 | -366.7796 | 376.3095 |
| native_frozen | total | 0.6250 | 9046 | 0.7027 | 0.2546 | 6504 | -0.0588 | -382.2722 | 392.5416 |
| native_frozen | total | 0.5000 | 9046 | 0.6991 | 0.2529 | 5900 | -0.0611 | -360.2222 | 369.8968 |
| native_frozen | total | 0.3750 | 9046 | 0.6964 | 0.2516 | 4930 | -0.0570 | -281.1711 | 298.3773 |
| native_frozen | total | 0.2500 | 9046 | 0.6945 | 0.2507 | 3281 | -0.0579 | -189.9370 | 201.6541 |
| native_frozen | total | 0.1250 | 9046 | 0.6933 | 0.2501 | 681 | -0.0203 | -13.8515 | 45.6631 |
| native_frozen | total | 0.0000 | 9046 | 0.6928 | 0.2498 | 0.0000 | - | 0.0000 | 0.0000 |
| raw | ml | 1.0000 | 13662 | 0.6060 | 0.2064 | 11681 | -0.0912 | -1065.5984 | 1069.6727 |
| raw | ml | 0.8750 | 13662 | 0.5890 | 0.2015 | 11397 | -0.0939 | -1070.3557 | 1074.0153 |
| raw | ml | 0.7500 | 13662 | 0.5774 | 0.1973 | 11021 | -0.0987 | -1087.3449 | 1092.6788 |
| raw | ml | 0.6250 | 13662 | 0.5685 | 0.1936 | 10455 | -0.1035 | -1081.6619 | 1085.6356 |
| raw | ml | 0.5000 | 13662 | 0.5615 | 0.1907 | 9744 | -0.1016 | -989.5663 | 990.4069 |
| raw | ml | 0.3750 | 13662 | 0.5562 | 0.1884 | 8693 | -0.1022 | -888.0140 | 889.4338 |
| raw | ml | 0.2500 | 13662 | 0.5523 | 0.1868 | 7023 | -0.1151 | -808.0919 | 808.0919 |
| raw | ml | 0.1250 | 13662 | 0.5499 | 0.1858 | 4067 | -0.1514 | -615.9392 | 615.9392 |
| raw | ml | 0.0000 | 13662 | 0.5488 | 0.1855 | 0.0000 | - | 0.0000 | 0.0000 |
| raw | spread | 1.0000 | 8985 | 0.7691 | 0.2782 | 8019 | -0.0549 | -440.5961 | 457.6706 |
| raw | spread | 0.8750 | 8985 | 0.7448 | 0.2717 | 7876 | -0.0556 | -437.8970 | 455.9715 |
| raw | spread | 0.7500 | 8985 | 0.7290 | 0.2660 | 7669 | -0.0555 | -425.6243 | 444.7897 |
| raw | spread | 0.6250 | 8985 | 0.7172 | 0.2611 | 7365 | -0.0553 | -407.4451 | 428.1915 |
| raw | spread | 0.5000 | 8985 | 0.7082 | 0.2572 | 6916 | -0.0545 | -376.6778 | 401.1203 |
| raw | spread | 0.3750 | 8985 | 0.7015 | 0.2541 | 6225 | -0.0549 | -342.0630 | 363.8691 |
| raw | spread | 0.2500 | 8985 | 0.6969 | 0.2519 | 4930 | -0.0505 | -249.0196 | 264.7862 |
| raw | spread | 0.1250 | 8985 | 0.6942 | 0.2505 | 2205 | -0.0329 | -72.4389 | 95.1126 |
| raw | spread | 0.0000 | 8985 | 0.6932 | 0.2500 | 0.0000 | - | 0.0000 | 0.0000 |
| raw | total | 1.0000 | 9046 | 0.7334 | 0.2676 | 7760 | -0.0625 | -484.8223 | 491.6122 |
| raw | total | 0.8750 | 9046 | 0.7228 | 0.2636 | 7558 | -0.0618 | -466.8911 | 473.8905 |
| raw | total | 0.7500 | 9046 | 0.7146 | 0.2601 | 7284 | -0.0615 | -448.1713 | 455.1707 |
| raw | total | 0.6250 | 9046 | 0.7079 | 0.2571 | 6948 | -0.0607 | -421.4611 | 427.4606 |
| raw | total | 0.5000 | 9046 | 0.7026 | 0.2546 | 6439 | -0.0594 | -382.2568 | 387.3867 |
| raw | total | 0.3750 | 9046 | 0.6985 | 0.2527 | 5600 | -0.0616 | -344.9046 | 349.6897 |
| raw | total | 0.2500 | 9046 | 0.6956 | 0.2512 | 4127 | -0.0660 | -272.2045 | 277.8763 |
| raw | total | 0.1250 | 9046 | 0.6937 | 0.2503 | 1231 | -0.0515 | -63.4088 | 83.6917 |
| raw | total | 0.0000 | 9046 | 0.6928 | 0.2498 | 0.0000 | - | 0.0000 | 0.0000 |
| regularized | ml | 1.0000 | 13662 | 0.5845 | 0.2002 | 11548 | -0.1140 | -1316.7252 | 1321.6895 |
| regularized | ml | 0.8750 | 13662 | 0.5769 | 0.1969 | 11273 | -0.1175 | -1324.4949 | 1329.4592 |
| regularized | ml | 0.7500 | 13662 | 0.5703 | 0.1941 | 10945 | -0.1181 | -1292.9523 | 1300.6576 |
| regularized | ml | 0.6250 | 13662 | 0.5646 | 0.1916 | 10484 | -0.1231 | -1290.3453 | 1298.7101 |
| regularized | ml | 0.5000 | 13662 | 0.5598 | 0.1896 | 9868 | -0.1265 | -1248.5975 | 1261.8568 |
| regularized | ml | 0.3750 | 13662 | 0.5558 | 0.1879 | 8906 | -0.1330 | -1184.3385 | 1195.5098 |
| regularized | ml | 0.2500 | 13662 | 0.5526 | 0.1867 | 7359 | -0.1376 | -1012.6956 | 1026.9615 |
| regularized | ml | 0.1250 | 13662 | 0.5502 | 0.1859 | 4390 | -0.1879 | -825.0496 | 844.5696 |
| regularized | ml | 0.0000 | 13662 | 0.5488 | 0.1855 | 0.0000 | - | 0.0000 | 0.0000 |
| regularized | spread | 1.0000 | 8985 | 0.7395 | 0.2693 | 7808 | -0.0453 | -353.8939 | 359.8062 |
| regularized | spread | 0.8750 | 8985 | 0.7267 | 0.2648 | 7608 | -0.0465 | -353.5882 | 360.5005 |
| regularized | spread | 0.7500 | 8985 | 0.7169 | 0.2609 | 7352 | -0.0469 | -344.5199 | 353.1431 |
| regularized | spread | 0.6250 | 8985 | 0.7093 | 0.2576 | 6997 | -0.0502 | -351.4246 | 362.1387 |
| regularized | spread | 0.5000 | 8985 | 0.7033 | 0.2549 | 6481 | -0.0508 | -329.4803 | 342.2421 |
| regularized | spread | 0.3750 | 8985 | 0.6989 | 0.2528 | 5638 | -0.0497 | -280.2976 | 294.2702 |
| regularized | spread | 0.2500 | 8985 | 0.6957 | 0.2513 | 4221 | -0.0446 | -188.0915 | 203.2831 |
| regularized | spread | 0.1250 | 8985 | 0.6939 | 0.2504 | 1488 | -0.0593 | -88.2309 | 101.5948 |
| regularized | spread | 0.0000 | 8985 | 0.6932 | 0.2500 | 0.0000 | - | 0.0000 | 0.0000 |
| regularized | total | 1.0000 | 9046 | 0.7165 | 0.2606 | 7407 | -0.0494 | -365.9233 | 381.1983 |
| regularized | total | 0.8750 | 9046 | 0.7105 | 0.2581 | 7157 | -0.0505 | -361.6560 | 375.5118 |
| regularized | total | 0.7500 | 9046 | 0.7056 | 0.2559 | 6829 | -0.0465 | -317.2252 | 333.2628 |
| regularized | total | 0.6250 | 9046 | 0.7016 | 0.2541 | 6383 | -0.0452 | -288.5297 | 303.0143 |
| regularized | total | 0.5000 | 9046 | 0.6984 | 0.2526 | 5766 | -0.0456 | -262.9386 | 274.3825 |
| regularized | total | 0.3750 | 9046 | 0.6959 | 0.2514 | 4737 | -0.0490 | -232.0490 | 246.1446 |
| regularized | total | 0.2500 | 9046 | 0.6942 | 0.2505 | 3121 | -0.0499 | -155.7213 | 170.9832 |
| regularized | total | 0.1250 | 9046 | 0.6932 | 0.2500 | 628 | -0.0336 | -21.1269 | 51.3903 |
| regularized | total | 0.0000 | 9046 | 0.6928 | 0.2498 | 0.0000 | - | 0.0000 | 0.0000 |
| sched_adj | ml | 1.0000 | 13662 | 0.5835 | 0.1998 | 11251 | -0.1088 | -1224.5314 | 1231.1567 |
| sched_adj | ml | 0.8750 | 13662 | 0.5760 | 0.1966 | 10935 | -0.1105 | -1208.1232 | 1213.3939 |
| sched_adj | ml | 0.7500 | 13662 | 0.5695 | 0.1938 | 10559 | -0.1155 | -1220.0147 | 1225.5271 |
| sched_adj | ml | 0.6250 | 13662 | 0.5640 | 0.1913 | 10072 | -0.1208 | -1216.3996 | 1223.4741 |
| sched_adj | ml | 0.5000 | 13662 | 0.5592 | 0.1893 | 9367 | -0.1291 | -1209.5522 | 1215.0646 |
| sched_adj | ml | 0.3750 | 13662 | 0.5553 | 0.1877 | 8379 | -0.1317 | -1103.3835 | 1108.7478 |
| sched_adj | ml | 0.2500 | 13662 | 0.5523 | 0.1866 | 6693 | -0.1399 | -936.6147 | 947.2298 |
| sched_adj | ml | 0.1250 | 13662 | 0.5501 | 0.1858 | 3805 | -0.1805 | -686.6964 | 688.7964 |
| sched_adj | ml | 0.0000 | 13662 | 0.5488 | 0.1855 | 0.0000 | - | 0.0000 | 0.0000 |
| sched_adj | spread | 1.0000 | 8985 | 0.7423 | 0.2698 | 7628 | -0.0501 | -381.8360 | 391.5269 |
| sched_adj | spread | 0.8750 | 8985 | 0.7283 | 0.2653 | 7430 | -0.0481 | -357.0936 | 365.8755 |
| sched_adj | spread | 0.7500 | 8985 | 0.7180 | 0.2613 | 7186 | -0.0497 | -356.9659 | 364.8387 |
| sched_adj | spread | 0.6250 | 8985 | 0.7100 | 0.2579 | 6785 | -0.0480 | -325.4064 | 333.2792 |
| sched_adj | spread | 0.5000 | 8985 | 0.7039 | 0.2552 | 6235 | -0.0497 | -310.0796 | 317.9524 |
| sched_adj | spread | 0.3750 | 8985 | 0.6992 | 0.2530 | 5369 | -0.0594 | -319.0454 | 326.0090 |
| sched_adj | spread | 0.2500 | 8985 | 0.6960 | 0.2514 | 3884 | -0.0611 | -237.4751 | 244.0678 |
| sched_adj | spread | 0.1250 | 8985 | 0.6940 | 0.2504 | 1359 | -0.0538 | -73.1774 | 85.7611 |
| sched_adj | spread | 0.0000 | 8985 | 0.6932 | 0.2500 | 0.0000 | - | 0.0000 | 0.0000 |
| sched_adj | total | 1.0000 | 9046 | 0.7179 | 0.2613 | 7396 | -0.0509 | -376.5095 | 392.6031 |
| sched_adj | total | 0.8750 | 9046 | 0.7117 | 0.2587 | 7140 | -0.0507 | -361.9269 | 378.2418 |
| sched_adj | total | 0.7500 | 9046 | 0.7065 | 0.2564 | 6812 | -0.0529 | -360.3573 | 375.7003 |
| sched_adj | total | 0.6250 | 9046 | 0.7024 | 0.2545 | 6361 | -0.0517 | -329.0252 | 341.0371 |
| sched_adj | total | 0.5000 | 9046 | 0.6990 | 0.2529 | 5724 | -0.0515 | -294.8904 | 305.6763 |
| sched_adj | total | 0.3750 | 9046 | 0.6964 | 0.2516 | 4774 | -0.0608 | -290.3533 | 302.1268 |
| sched_adj | total | 0.2500 | 9046 | 0.6945 | 0.2507 | 3158 | -0.0621 | -196.1433 | 209.9219 |
| sched_adj | total | 0.1250 | 9046 | 0.6933 | 0.2501 | 636 | -0.0579 | -36.7970 | 68.9427 |
| sched_adj | total | 0.0000 | 9046 | 0.6928 | 0.2498 | 0.0000 | - | 0.0000 | 0.0000 |
| native_hca_repaired | ml | 1.0000 | 13662 | 0.5918 | 0.2034 | 11733 | -0.1103 | -1293.6929 | 1309.9969 |
| native_hca_repaired | ml | 0.8750 | 13662 | 0.5825 | 0.1993 | 11494 | -0.1131 | -1300.4974 | 1313.0208 |
| native_hca_repaired | ml | 0.7500 | 13662 | 0.5744 | 0.1958 | 11199 | -0.1194 | -1336.7493 | 1344.3582 |
| native_hca_repaired | ml | 0.6250 | 13662 | 0.5675 | 0.1928 | 10786 | -0.1216 | -1311.7664 | 1319.4053 |
| native_hca_repaired | ml | 0.5000 | 13662 | 0.5617 | 0.1903 | 10172 | -0.1255 | -1277.0535 | 1279.2805 |
| native_hca_repaired | ml | 0.3750 | 13662 | 0.5569 | 0.1883 | 9280 | -0.1285 | -1192.1699 | 1200.4035 |
| native_hca_repaired | ml | 0.2500 | 13662 | 0.5531 | 0.1869 | 7745 | -0.1423 | -1102.0567 | 1111.4435 |
| native_hca_repaired | ml | 0.1250 | 13662 | 0.5504 | 0.1859 | 4778 | -0.1829 | -873.7827 | 876.0827 |
| native_hca_repaired | ml | 0.0000 | 13662 | 0.5488 | 0.1855 | 0.0000 | - | 0.0000 | 0.0000 |
| native_hca_repaired | spread | 1.0000 | 8985 | 0.7467 | 0.2717 | 7891 | -0.0430 | -339.3567 | 344.3204 |
| native_hca_repaired | spread | 0.8750 | 8985 | 0.7314 | 0.2666 | 7722 | -0.0441 | -340.7141 | 345.6778 |
| native_hca_repaired | spread | 0.7500 | 8985 | 0.7201 | 0.2622 | 7486 | -0.0460 | -344.2720 | 349.2357 |
| native_hca_repaired | spread | 0.6250 | 8985 | 0.7113 | 0.2585 | 7153 | -0.0475 | -339.9645 | 345.1602 |
| native_hca_repaired | spread | 0.5000 | 8985 | 0.7045 | 0.2555 | 6637 | -0.0456 | -302.3405 | 310.7504 |
| native_hca_repaired | spread | 0.3750 | 8985 | 0.6995 | 0.2531 | 5908 | -0.0459 | -271.4035 | 278.0682 |
| native_hca_repaired | spread | 0.2500 | 8985 | 0.6960 | 0.2514 | 4537 | -0.0413 | -187.4839 | 200.6506 |
| native_hca_repaired | spread | 0.1250 | 8985 | 0.6939 | 0.2504 | 1718 | -0.0369 | -63.3944 | 87.7519 |
| native_hca_repaired | spread | 0.0000 | 8985 | 0.6932 | 0.2500 | 0.0000 | - | 0.0000 | 0.0000 |
| native_hca_repaired | total | 1.0000 | 9046 | 0.7191 | 0.2618 | 7492 | -0.0508 | -380.9196 | 390.9669 |
| native_hca_repaired | total | 0.8750 | 9046 | 0.7125 | 0.2590 | 7251 | -0.0519 | -376.6522 | 383.9216 |
| native_hca_repaired | total | 0.7500 | 9046 | 0.7071 | 0.2567 | 6938 | -0.0529 | -366.7796 | 376.3095 |
| native_hca_repaired | total | 0.6250 | 9046 | 0.7027 | 0.2546 | 6505 | -0.0589 | -383.2722 | 393.5416 |
| native_hca_repaired | total | 0.5000 | 9046 | 0.6991 | 0.2529 | 5900 | -0.0611 | -360.2222 | 369.8968 |
| native_hca_repaired | total | 0.3750 | 9046 | 0.6964 | 0.2516 | 4932 | -0.0570 | -281.2620 | 298.4682 |
| native_hca_repaired | total | 0.2500 | 9046 | 0.6945 | 0.2507 | 3281 | -0.0579 | -189.9370 | 201.6541 |
| native_hca_repaired | total | 0.1250 | 9046 | 0.6933 | 0.2501 | 681 | -0.0203 | -13.8515 | 45.6631 |
| native_hca_repaired | total | 0.0000 | 9046 | 0.6928 | 0.2498 | 0.0000 | - | 0.0000 | 0.0000 |
| FG1 | ml | 1.0000 | 13662 | 0.5613 | 0.1908 | 10013 | -0.0917 | -917.8823 | 943.9083 |
| FG1 | ml | 0.8750 | 13662 | 0.5585 | 0.1896 | 9612 | -0.0934 | -897.9196 | 923.4035 |
| FG1 | ml | 0.7500 | 13662 | 0.5561 | 0.1886 | 9085 | -0.0958 | -870.1970 | 895.7521 |
| FG1 | ml | 0.6250 | 13662 | 0.5540 | 0.1877 | 8452 | -0.0952 | -804.5429 | 830.9981 |
| FG1 | ml | 0.5000 | 13662 | 0.5523 | 0.1869 | 7621 | -0.1006 | -766.5707 | 795.3426 |
| FG1 | ml | 0.3750 | 13662 | 0.5509 | 0.1863 | 6374 | -0.0976 | -622.0849 | 654.9779 |
| FG1 | ml | 0.2500 | 13662 | 0.5499 | 0.1859 | 4547 | -0.1078 | -490.2612 | 524.7345 |
| FG1 | ml | 0.1250 | 13662 | 0.5492 | 0.1856 | 1775 | -0.1515 | -268.9246 | 308.1996 |
| FG1 | ml | 0.0000 | 13662 | 0.5488 | 0.1855 | 0.0000 | - | 0.0000 | 0.0000 |
| FG1 | spread | 1.0000 | 8985 | 0.7108 | 0.2582 | 7105 | -0.0401 | -284.6320 | 316.3824 |
| FG1 | spread | 0.8750 | 8985 | 0.7063 | 0.2563 | 6854 | -0.0404 | -276.5717 | 307.5039 |
| FG1 | spread | 0.7500 | 8985 | 0.7026 | 0.2546 | 6484 | -0.0384 | -248.6907 | 281.7801 |
| FG1 | spread | 0.6250 | 8985 | 0.6996 | 0.2532 | 6009 | -0.0365 | -219.6252 | 252.5033 |
| FG1 | spread | 0.5000 | 8985 | 0.6972 | 0.2520 | 5275 | -0.0398 | -209.9906 | 239.9953 |
| FG1 | spread | 0.3750 | 8985 | 0.6954 | 0.2511 | 4230 | -0.0451 | -190.9271 | 210.9298 |
| FG1 | spread | 0.2500 | 8985 | 0.6941 | 0.2505 | 2524 | -0.0417 | -105.3532 | 123.6541 |
| FG1 | spread | 0.1250 | 8985 | 0.6934 | 0.2501 | 434 | -0.0256 | -11.1210 | 21.1577 |
| FG1 | spread | 0.0000 | 8985 | 0.6932 | 0.2500 | 0.0000 | - | 0.0000 | 0.0000 |
| FG1 | total | 1.0000 | 9046 | 0.7059 | 0.2562 | 6832 | -0.0551 | -376.5403 | 376.5403 |
| FG1 | total | 0.8750 | 9046 | 0.7029 | 0.2548 | 6530 | -0.0565 | -369.1074 | 369.1074 |
| FG1 | total | 0.7500 | 9046 | 0.7003 | 0.2535 | 6133 | -0.0555 | -340.2994 | 340.2994 |
| FG1 | total | 0.6250 | 9046 | 0.6981 | 0.2525 | 5573 | -0.0623 | -347.1591 | 347.1591 |
| FG1 | total | 0.5000 | 9046 | 0.6963 | 0.2516 | 4782 | -0.0623 | -297.9204 | 297.9204 |
| FG1 | total | 0.3750 | 9046 | 0.6949 | 0.2509 | 3623 | -0.0558 | -202.0548 | 202.6004 |
| FG1 | total | 0.2500 | 9046 | 0.6938 | 0.2503 | 1908 | -0.0636 | -121.3087 | 133.7844 |
| FG1 | total | 0.1250 | 9046 | 0.6932 | 0.2500 | 141 | 0.0826 | 11.6445 | 12.9301 |
| FG1 | total | 0.0000 | 9046 | 0.6928 | 0.2498 | 0.0000 | - | 0.0000 | 0.0000 |

### TEST
| model | family | w_independent | n | log_loss | brier | close_n_bets | close_roi | close_units | close_max_dd_u |
|---|---|---|---|---|---|---|---|---|---|
| native_frozen | ml | 1.0000 | 9698 | 0.6372 | 0.2216 | 8610 | -0.1135 | -976.8600 | 978.0092 |
| native_frozen | ml | 0.8750 | 9698 | 0.6128 | 0.2130 | 8450 | -0.1133 | -957.5859 | 958.7351 |
| native_frozen | ml | 0.7500 | 9698 | 0.5937 | 0.2054 | 8250 | -0.1123 | -926.6140 | 927.7632 |
| native_frozen | ml | 0.6250 | 9698 | 0.5784 | 0.1990 | 7998 | -0.1151 | -920.2903 | 921.4395 |
| native_frozen | ml | 0.5000 | 9698 | 0.5662 | 0.1937 | 7630 | -0.1180 | -900.5437 | 900.9037 |
| native_frozen | ml | 0.3750 | 9698 | 0.5566 | 0.1895 | 7080 | -0.1219 | -863.2380 | 863.5980 |
| native_frozen | ml | 0.2500 | 9698 | 0.5494 | 0.1865 | 6162 | -0.1260 | -776.6013 | 776.9613 |
| native_frozen | ml | 0.1250 | 9698 | 0.5445 | 0.1845 | 4105 | -0.1674 | -687.0628 | 687.0628 |
| native_frozen | ml | 0.0000 | 9698 | 0.5419 | 0.1837 | 0.0000 | - | 0.0000 | 0.0000 |
| native_frozen | spread | 1.0000 | 9897 | 0.7947 | 0.2905 | 9299 | -0.0417 | -387.5159 | 414.1506 |
| native_frozen | spread | 0.8750 | 9897 | 0.7655 | 0.2810 | 9196 | -0.0419 | -385.5656 | 412.1977 |
| native_frozen | spread | 0.7500 | 9897 | 0.7438 | 0.2728 | 9052 | -0.0416 | -376.7395 | 403.4726 |
| native_frozen | spread | 0.6250 | 9897 | 0.7270 | 0.2658 | 8894 | -0.0405 | -360.1475 | 384.9178 |
| native_frozen | spread | 0.5000 | 9897 | 0.7142 | 0.2601 | 8643 | -0.0392 | -338.6730 | 373.9704 |
| native_frozen | spread | 0.3750 | 9897 | 0.7047 | 0.2556 | 8215 | -0.0402 | -330.0711 | 364.5527 |
| native_frozen | spread | 0.2500 | 9897 | 0.6981 | 0.2524 | 7292 | -0.0450 | -327.8239 | 356.4006 |
| native_frozen | spread | 0.1250 | 9897 | 0.6942 | 0.2505 | 4193 | -0.0545 | -228.5206 | 246.5082 |
| native_frozen | spread | 0.0000 | 9897 | 0.6929 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| native_frozen | total | 1.0000 | 9920 | 0.7256 | 0.2645 | 8098 | -0.0651 | -527.3074 | 555.2778 |
| native_frozen | total | 0.8750 | 9920 | 0.7175 | 0.2613 | 7841 | -0.0640 | -501.4461 | 530.4165 |
| native_frozen | total | 0.7500 | 9920 | 0.7109 | 0.2584 | 7532 | -0.0633 | -477.0897 | 502.4595 |
| native_frozen | total | 0.6250 | 9920 | 0.7055 | 0.2560 | 7085 | -0.0578 | -409.4528 | 435.1078 |
| native_frozen | total | 0.5000 | 9920 | 0.7012 | 0.2539 | 6465 | -0.0614 | -396.7888 | 423.2797 |
| native_frozen | total | 0.3750 | 9920 | 0.6978 | 0.2523 | 5485 | -0.0534 | -293.1466 | 321.6025 |
| native_frozen | total | 0.2500 | 9920 | 0.6954 | 0.2511 | 3875 | -0.0510 | -197.6914 | 228.0578 |
| native_frozen | total | 0.1250 | 9920 | 0.6938 | 0.2503 | 1022 | -0.0669 | -68.3646 | 78.7264 |
| native_frozen | total | 0.0000 | 9920 | 0.6930 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| raw | ml | 1.0000 | 9698 | 0.6039 | 0.2063 | 8214 | -0.1002 | -823.4337 | 824.5829 |
| raw | ml | 0.8750 | 9698 | 0.5866 | 0.2011 | 8006 | -0.1010 | -808.9217 | 810.0709 |
| raw | ml | 0.7500 | 9698 | 0.5743 | 0.1965 | 7738 | -0.1060 | -820.3071 | 822.3066 |
| raw | ml | 0.6250 | 9698 | 0.5646 | 0.1927 | 7399 | -0.1077 | -796.9277 | 799.9107 |
| raw | ml | 0.5000 | 9698 | 0.5570 | 0.1895 | 6908 | -0.1124 | -776.5670 | 779.5310 |
| raw | ml | 0.3750 | 9698 | 0.5509 | 0.1870 | 6210 | -0.1290 | -801.3120 | 804.0871 |
| raw | ml | 0.2500 | 9698 | 0.5464 | 0.1852 | 5122 | -0.1459 | -747.4777 | 750.9392 |
| raw | ml | 0.1250 | 9698 | 0.5434 | 0.1841 | 3004 | -0.2212 | -664.4138 | 667.2826 |
| raw | ml | 0.0000 | 9698 | 0.5419 | 0.1837 | 0.0000 | - | 0.0000 | 0.0000 |
| raw | spread | 1.0000 | 9897 | 0.7713 | 0.2785 | 8694 | -0.0433 | -376.6900 | 413.3665 |
| raw | spread | 0.8750 | 9897 | 0.7457 | 0.2717 | 8524 | -0.0430 | -366.3562 | 403.0130 |
| raw | spread | 0.7500 | 9897 | 0.7292 | 0.2659 | 8302 | -0.0434 | -359.9792 | 402.6205 |
| raw | spread | 0.6250 | 9897 | 0.7169 | 0.2609 | 7988 | -0.0434 | -346.9525 | 395.7717 |
| raw | spread | 0.5000 | 9897 | 0.7077 | 0.2569 | 7521 | -0.0425 | -319.4898 | 365.3860 |
| raw | spread | 0.3750 | 9897 | 0.7009 | 0.2538 | 6781 | -0.0439 | -298.0133 | 342.0305 |
| raw | spread | 0.2500 | 9897 | 0.6963 | 0.2516 | 5409 | -0.0457 | -247.0380 | 282.8291 |
| raw | spread | 0.1250 | 9897 | 0.6937 | 0.2503 | 2529 | -0.0353 | -89.3708 | 110.8769 |
| raw | spread | 0.0000 | 9897 | 0.6929 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| raw | total | 1.0000 | 9920 | 0.7425 | 0.2707 | 8416 | -0.0612 | -515.1644 | 535.5451 |
| raw | total | 0.8750 | 9920 | 0.7291 | 0.2661 | 8237 | -0.0594 | -488.9566 | 511.3373 |
| raw | total | 0.7500 | 9920 | 0.7191 | 0.2620 | 7981 | -0.0550 | -439.0035 | 459.5059 |
| raw | total | 0.6250 | 9920 | 0.7111 | 0.2585 | 7576 | -0.0567 | -429.2553 | 450.0305 |
| raw | total | 0.5000 | 9920 | 0.7048 | 0.2556 | 7083 | -0.0588 | -416.2884 | 436.1112 |
| raw | total | 0.3750 | 9920 | 0.6999 | 0.2533 | 6196 | -0.0565 | -349.8720 | 366.7495 |
| raw | total | 0.2500 | 9920 | 0.6964 | 0.2516 | 4649 | -0.0621 | -288.9267 | 311.0672 |
| raw | total | 0.1250 | 9920 | 0.6941 | 0.2505 | 1629 | -0.0805 | -131.0735 | 143.7458 |
| raw | total | 0.0000 | 9920 | 0.6930 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| regularized | ml | 1.0000 | 9698 | 0.5854 | 0.2007 | 8383 | -0.1306 | -1094.8717 | 1108.1873 |
| regularized | ml | 0.8750 | 9698 | 0.5767 | 0.1970 | 8222 | -0.1324 | -1088.5051 | 1099.1207 |
| regularized | ml | 0.7500 | 9698 | 0.5690 | 0.1937 | 8005 | -0.1332 | -1065.9244 | 1078.0428 |
| regularized | ml | 0.6250 | 9698 | 0.5622 | 0.1909 | 7736 | -0.1344 | -1039.9274 | 1048.9040 |
| regularized | ml | 0.5000 | 9698 | 0.5563 | 0.1885 | 7319 | -0.1417 | -1036.8314 | 1052.8274 |
| regularized | ml | 0.3750 | 9698 | 0.5513 | 0.1866 | 6680 | -0.1473 | -983.7770 | 1007.3185 |
| regularized | ml | 0.2500 | 9698 | 0.5472 | 0.1852 | 5623 | -0.1716 | -964.8607 | 997.4941 |
| regularized | ml | 0.1250 | 9698 | 0.5440 | 0.1842 | 3510 | -0.2376 | -833.8974 | 888.6974 |
| regularized | ml | 0.0000 | 9698 | 0.5419 | 0.1837 | 0.0000 | - | 0.0000 | 0.0000 |
| regularized | spread | 1.0000 | 9897 | 0.7448 | 0.2699 | 8463 | -0.0374 | -316.8856 | 332.4196 |
| regularized | spread | 0.8750 | 9897 | 0.7287 | 0.2651 | 8282 | -0.0378 | -312.9376 | 328.4716 |
| regularized | spread | 0.7500 | 9897 | 0.7176 | 0.2609 | 7988 | -0.0376 | -300.7006 | 316.2346 |
| regularized | spread | 0.6250 | 9897 | 0.7092 | 0.2574 | 7625 | -0.0369 | -281.3058 | 296.0210 |
| regularized | spread | 0.5000 | 9897 | 0.7028 | 0.2546 | 7103 | -0.0345 | -245.1913 | 261.2443 |
| regularized | spread | 0.3750 | 9897 | 0.6982 | 0.2524 | 6212 | -0.0355 | -220.6378 | 237.3087 |
| regularized | spread | 0.2500 | 9897 | 0.6950 | 0.2509 | 4666 | -0.0327 | -152.4813 | 183.6523 |
| regularized | spread | 0.1250 | 9897 | 0.6933 | 0.2501 | 1691 | -0.0508 | -85.9468 | 97.6240 |
| regularized | spread | 0.0000 | 9897 | 0.6929 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| regularized | total | 1.0000 | 9920 | 0.7220 | 0.2630 | 8069 | -0.0557 | -449.2036 | 484.5916 |
| regularized | total | 0.8750 | 9920 | 0.7147 | 0.2600 | 7835 | -0.0559 | -438.0587 | 471.6680 |
| regularized | total | 0.7500 | 9920 | 0.7087 | 0.2574 | 7530 | -0.0563 | -423.6493 | 457.5108 |
| regularized | total | 0.6250 | 9920 | 0.7039 | 0.2552 | 7047 | -0.0555 | -391.0668 | 423.2751 |
| regularized | total | 0.5000 | 9920 | 0.7000 | 0.2533 | 6375 | -0.0530 | -337.6621 | 364.4313 |
| regularized | total | 0.3750 | 9920 | 0.6970 | 0.2519 | 5377 | -0.0504 | -271.0245 | 297.4636 |
| regularized | total | 0.2500 | 9920 | 0.6949 | 0.2509 | 3715 | -0.0431 | -160.0779 | 179.8522 |
| regularized | total | 0.1250 | 9920 | 0.6936 | 0.2502 | 947 | -0.0611 | -57.8499 | 65.5867 |
| regularized | total | 0.0000 | 9920 | 0.6930 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| sched_adj | ml | 1.0000 | 9698 | 0.5855 | 0.2008 | 8141 | -0.1379 | -1122.7105 | 1154.5263 |
| sched_adj | ml | 0.8750 | 9698 | 0.5768 | 0.1970 | 7963 | -0.1394 | -1109.9566 | 1144.8974 |
| sched_adj | ml | 0.7500 | 9698 | 0.5691 | 0.1937 | 7720 | -0.1416 | -1093.0251 | 1121.7658 |
| sched_adj | ml | 0.6250 | 9698 | 0.5623 | 0.1908 | 7423 | -0.1409 | -1045.8250 | 1073.8035 |
| sched_adj | ml | 0.5000 | 9698 | 0.5564 | 0.1885 | 6963 | -0.1494 | -1039.9366 | 1060.0830 |
| sched_adj | ml | 0.3750 | 9698 | 0.5514 | 0.1866 | 6285 | -0.1678 | -1054.4570 | 1066.2937 |
| sched_adj | ml | 0.2500 | 9698 | 0.5473 | 0.1851 | 5228 | -0.1951 | -1020.0364 | 1032.4307 |
| sched_adj | ml | 0.1250 | 9698 | 0.5441 | 0.1842 | 3141 | -0.2647 | -831.5670 | 848.3670 |
| sched_adj | ml | 0.0000 | 9698 | 0.5419 | 0.1837 | 0.0000 | - | 0.0000 | 0.0000 |
| sched_adj | spread | 1.0000 | 9897 | 0.7497 | 0.2704 | 8316 | -0.0470 | -391.2545 | 402.6778 |
| sched_adj | spread | 0.8750 | 9897 | 0.7309 | 0.2655 | 8112 | -0.0474 | -384.8599 | 395.0181 |
| sched_adj | spread | 0.7500 | 9897 | 0.7189 | 0.2613 | 7813 | -0.0458 | -357.6804 | 372.1570 |
| sched_adj | spread | 0.6250 | 9897 | 0.7101 | 0.2578 | 7422 | -0.0447 | -332.0181 | 350.9593 |
| sched_adj | spread | 0.5000 | 9897 | 0.7035 | 0.2549 | 6855 | -0.0504 | -345.7629 | 356.6332 |
| sched_adj | spread | 0.3750 | 9897 | 0.6986 | 0.2527 | 5934 | -0.0516 | -306.0417 | 317.1664 |
| sched_adj | spread | 0.2500 | 9897 | 0.6953 | 0.2511 | 4351 | -0.0546 | -237.3575 | 253.1035 |
| sched_adj | spread | 0.1250 | 9897 | 0.6934 | 0.2501 | 1508 | -0.0160 | -24.1819 | 61.5785 |
| sched_adj | spread | 0.0000 | 9897 | 0.6929 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| sched_adj | total | 1.0000 | 9920 | 0.7217 | 0.2628 | 8006 | -0.0528 | -422.4763 | 456.2492 |
| sched_adj | total | 0.8750 | 9920 | 0.7145 | 0.2599 | 7765 | -0.0544 | -422.4540 | 452.7085 |
| sched_adj | total | 0.7500 | 9920 | 0.7086 | 0.2573 | 7436 | -0.0559 | -415.5694 | 450.2368 |
| sched_adj | total | 0.6250 | 9920 | 0.7038 | 0.2552 | 6981 | -0.0592 | -413.0703 | 442.6953 |
| sched_adj | total | 0.5000 | 9920 | 0.7000 | 0.2534 | 6326 | -0.0560 | -353.9894 | 383.9860 |
| sched_adj | total | 0.3750 | 9920 | 0.6971 | 0.2519 | 5274 | -0.0555 | -292.8414 | 317.5499 |
| sched_adj | total | 0.2500 | 9920 | 0.6949 | 0.2509 | 3638 | -0.0475 | -172.8995 | 195.3339 |
| sched_adj | total | 0.1250 | 9920 | 0.6936 | 0.2502 | 901 | -0.0624 | -56.2592 | 64.4079 |
| sched_adj | total | 0.0000 | 9920 | 0.6930 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| native_hca_repaired | ml | 1.0000 | 9698 | 0.5919 | 0.2037 | 8506 | -0.1218 | -1036.2694 | 1070.5214 |
| native_hca_repaired | ml | 0.8750 | 9698 | 0.5816 | 0.1992 | 8345 | -0.1231 | -1026.9718 | 1060.1237 |
| native_hca_repaired | ml | 0.7500 | 9698 | 0.5725 | 0.1953 | 8121 | -0.1234 | -1001.8625 | 1034.4535 |
| native_hca_repaired | ml | 0.6250 | 9698 | 0.5647 | 0.1920 | 7836 | -0.1267 | -993.0102 | 1026.8266 |
| native_hca_repaired | ml | 0.5000 | 9698 | 0.5579 | 0.1892 | 7422 | -0.1339 | -993.7390 | 1031.3814 |
| native_hca_repaired | ml | 0.3750 | 9698 | 0.5522 | 0.1870 | 6789 | -0.1413 | -959.4921 | 998.3671 |
| native_hca_repaired | ml | 0.2500 | 9698 | 0.5476 | 0.1853 | 5743 | -0.1578 | -906.2209 | 945.4229 |
| native_hca_repaired | ml | 0.1250 | 9698 | 0.5441 | 0.1842 | 3658 | -0.2296 | -839.7169 | 883.3621 |
| native_hca_repaired | ml | 0.0000 | 9698 | 0.5419 | 0.1837 | 0.0000 | - | 0.0000 | 0.0000 |
| native_hca_repaired | spread | 1.0000 | 9897 | 0.7515 | 0.2718 | 8552 | -0.0301 | -257.4286 | 293.8705 |
| native_hca_repaired | spread | 0.8750 | 9897 | 0.7326 | 0.2665 | 8377 | -0.0301 | -252.2212 | 288.4128 |
| native_hca_repaired | spread | 0.7500 | 9897 | 0.7200 | 0.2619 | 8125 | -0.0315 | -255.5931 | 289.2560 |
| native_hca_repaired | spread | 0.6250 | 9897 | 0.7106 | 0.2581 | 7796 | -0.0304 | -237.2847 | 268.9065 |
| native_hca_repaired | spread | 0.5000 | 9897 | 0.7036 | 0.2550 | 7272 | -0.0294 | -214.0416 | 245.7382 |
| native_hca_repaired | spread | 0.3750 | 9897 | 0.6985 | 0.2526 | 6461 | -0.0232 | -149.8774 | 191.9383 |
| native_hca_repaired | spread | 0.2500 | 9897 | 0.6951 | 0.2509 | 4939 | -0.0362 | -178.7907 | 200.9521 |
| native_hca_repaired | spread | 0.1250 | 9897 | 0.6932 | 0.2500 | 1977 | -0.0411 | -81.1688 | 98.3819 |
| native_hca_repaired | spread | 0.0000 | 9897 | 0.6929 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| native_hca_repaired | total | 1.0000 | 9920 | 0.7256 | 0.2645 | 8098 | -0.0651 | -527.3074 | 555.2778 |
| native_hca_repaired | total | 0.8750 | 9920 | 0.7175 | 0.2613 | 7841 | -0.0640 | -501.4461 | 530.4165 |
| native_hca_repaired | total | 0.7500 | 9920 | 0.7109 | 0.2584 | 7532 | -0.0633 | -477.0897 | 502.4595 |
| native_hca_repaired | total | 0.6250 | 9920 | 0.7055 | 0.2560 | 7085 | -0.0578 | -409.4528 | 435.1078 |
| native_hca_repaired | total | 0.5000 | 9920 | 0.7012 | 0.2539 | 6465 | -0.0614 | -396.7888 | 423.2797 |
| native_hca_repaired | total | 0.3750 | 9920 | 0.6978 | 0.2523 | 5485 | -0.0534 | -293.1466 | 321.6025 |
| native_hca_repaired | total | 0.2500 | 9920 | 0.6954 | 0.2511 | 3875 | -0.0510 | -197.6914 | 228.0578 |
| native_hca_repaired | total | 0.1250 | 9920 | 0.6938 | 0.2503 | 1022 | -0.0669 | -68.3646 | 78.7264 |
| native_hca_repaired | total | 0.0000 | 9920 | 0.6930 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| FG1 | ml | 1.0000 | 9698 | 0.5592 | 0.1905 | 7377 | -0.1362 | -1004.7091 | 1004.7091 |
| FG1 | ml | 0.8750 | 9698 | 0.5557 | 0.1891 | 7104 | -0.1390 | -987.6085 | 987.6085 |
| FG1 | ml | 0.7500 | 9698 | 0.5527 | 0.1878 | 6776 | -0.1461 | -990.2407 | 990.2407 |
| FG1 | ml | 0.6250 | 9698 | 0.5500 | 0.1867 | 6364 | -0.1510 | -961.1705 | 961.1705 |
| FG1 | ml | 0.5000 | 9698 | 0.5477 | 0.1858 | 5765 | -0.1607 | -926.4739 | 926.6215 |
| FG1 | ml | 0.3750 | 9698 | 0.5457 | 0.1850 | 4985 | -0.1742 | -868.4571 | 868.4571 |
| FG1 | ml | 0.2500 | 9698 | 0.5441 | 0.1844 | 3765 | -0.2102 | -791.4392 | 791.4392 |
| FG1 | ml | 0.1250 | 9698 | 0.5428 | 0.1840 | 1718 | -0.2951 | -506.9411 | 506.9411 |
| FG1 | ml | 0.0000 | 9698 | 0.5419 | 0.1837 | 0.0000 | - | 0.0000 | 0.0000 |
| FG1 | spread | 1.0000 | 9897 | 0.7141 | 0.2596 | 7713 | -0.0559 | -431.3314 | 445.6404 |
| FG1 | spread | 0.8750 | 9897 | 0.7089 | 0.2574 | 7415 | -0.0531 | -393.9575 | 405.5831 |
| FG1 | spread | 0.7500 | 9897 | 0.7046 | 0.2555 | 7060 | -0.0501 | -353.9602 | 372.8212 |
| FG1 | spread | 0.6250 | 9897 | 0.7011 | 0.2539 | 6553 | -0.0524 | -343.5346 | 352.2181 |
| FG1 | spread | 0.5000 | 9897 | 0.6982 | 0.2525 | 5740 | -0.0586 | -336.5673 | 361.3198 |
| FG1 | spread | 0.3750 | 9897 | 0.6960 | 0.2514 | 4598 | -0.0464 | -213.5081 | 234.7006 |
| FG1 | spread | 0.2500 | 9897 | 0.6944 | 0.2506 | 2848 | -0.0520 | -148.0854 | 156.5621 |
| FG1 | spread | 0.1250 | 9897 | 0.6933 | 0.2501 | 546 | -0.0867 | -47.3115 | 49.2940 |
| FG1 | spread | 0.0000 | 9897 | 0.6929 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |
| FG1 | total | 1.0000 | 9920 | 0.7110 | 0.2585 | 7686 | -0.0522 | -400.9096 | 410.0754 |
| FG1 | total | 0.8750 | 9920 | 0.7069 | 0.2566 | 7368 | -0.0533 | -392.4861 | 401.7736 |
| FG1 | total | 0.7500 | 9920 | 0.7034 | 0.2550 | 6969 | -0.0569 | -396.4797 | 404.9893 |
| FG1 | total | 0.6250 | 9920 | 0.7004 | 0.2536 | 6418 | -0.0584 | -374.6497 | 382.2977 |
| FG1 | total | 0.5000 | 9920 | 0.6980 | 0.2524 | 5589 | -0.0633 | -353.6778 | 358.0922 |
| FG1 | total | 0.3750 | 9920 | 0.6961 | 0.2514 | 4439 | -0.0611 | -271.1959 | 277.7393 |
| FG1 | total | 0.2500 | 9920 | 0.6946 | 0.2507 | 2551 | -0.0683 | -174.3354 | 175.9712 |
| FG1 | total | 0.1250 | 9920 | 0.6936 | 0.2502 | 261 | -0.1559 | -40.7005 | 46.2312 |
| FG1 | total | 0.0000 | 9920 | 0.6930 | 0.2499 | 0.0000 | - | 0.0000 | 0.0000 |

## 8. Blend selection (validation log loss only) -> one-shot TEST report
| model | family | status | selected_w_independent | validation_n | validation_log_loss | test_n | test_log_loss | test_brier | test_market_only_log_loss | test_close_n_bets | test_close_roi | test_close_max_dd_u | clv_status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| native_frozen | ml | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 13662 | 0.5488 | 9698 | 0.5419 | 0.1837 | 0.5419 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| native_frozen | spread | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 8985 | 0.6932 | 9897 | 0.6929 | 0.2499 | 0.6929 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| native_frozen | total | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 9046 | 0.6928 | 9920 | 0.6930 | 0.2499 | 0.6930 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| raw | ml | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 13662 | 0.5488 | 9698 | 0.5419 | 0.1837 | 0.5419 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| raw | spread | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 8985 | 0.6932 | 9897 | 0.6929 | 0.2499 | 0.6929 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| raw | total | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 9046 | 0.6928 | 9920 | 0.6930 | 0.2499 | 0.6930 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| regularized | ml | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 13662 | 0.5488 | 9698 | 0.5419 | 0.1837 | 0.5419 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| regularized | spread | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 8985 | 0.6932 | 9897 | 0.6929 | 0.2499 | 0.6929 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| regularized | total | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 9046 | 0.6928 | 9920 | 0.6930 | 0.2499 | 0.6930 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| sched_adj | ml | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 13662 | 0.5488 | 9698 | 0.5419 | 0.1837 | 0.5419 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| sched_adj | spread | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 8985 | 0.6932 | 9897 | 0.6929 | 0.2499 | 0.6929 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| sched_adj | total | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 9046 | 0.6928 | 9920 | 0.6930 | 0.2499 | 0.6930 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| native_hca_repaired | ml | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 13662 | 0.5488 | 9698 | 0.5419 | 0.1837 | 0.5419 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| native_hca_repaired | spread | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 8985 | 0.6932 | 9897 | 0.6929 | 0.2499 | 0.6929 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| native_hca_repaired | total | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 9046 | 0.6928 | 9920 | 0.6930 | 0.2499 | 0.6930 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| FG1 | ml | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 13662 | 0.5488 | 9698 | 0.5419 | 0.1837 | 0.5419 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| FG1 | spread | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 8985 | 0.6932 | 9897 | 0.6929 | 0.2499 | 0.6929 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |
| FG1 | total | SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST | 0.0000 | 9046 | 0.6928 | 9920 | 0.6930 | 0.2499 | 0.6930 | 0.0000 | - | 0.0000 | BLOCKED_OPEN_LINES_FAIL_VALIDATION |

## 9. Betting splits, pure independent model (w=1) at the close, ALL seasons (diagnostic; includes train/validation/test)
| model | family | dimension | cell | n_bets | roi | units | max_drawdown_u | mean_claimed_ev |
|---|---|---|---|---|---|---|---|---|
| native_frozen | ml | ev_band | 0-10% | 7937 | -0.054 | -428.767 | 430.716 | 0.047 |
| native_frozen | ml | ev_band | 10-30% | 9608 | -0.049 | -474.704 | 484.490 | 0.189 |
| native_frozen | ml | ev_band | ev>30% | 12902 | -0.144 | -1853.234 | 1853.234 | 0.864 |
| native_frozen | ml | fav_dog | favorite | 15343 | -0.021 | -316.115 | 326.455 | 0.167 |
| native_frozen | ml | fav_dog | underdog | 15104 | -0.162 | -2440.590 | 2440.970 | 0.713 |
| native_frozen | ml | price_band | +150..+299 | 5181 | -0.095 | -490.080 | 527.630 | 0.600 |
| native_frozen | ml | price_band | -149..+149 | 8676 | -0.035 | -301.850 | 321.710 | 0.333 |
| native_frozen | ml | price_band | -299..-150 | 6472 | -0.021 | -138.111 | 154.979 | 0.163 |
| native_frozen | ml | price_band | <=-300 | 4442 | -0.012 | -51.844 | 59.013 | 0.064 |
| native_frozen | ml | price_band | >=+300 | 5676 | -0.313 | -1774.820 | 1774.820 | 1.057 |
| native_frozen | spread | ev_band | 0-10% | 5265 | -0.052 | -274.693 | 292.034 | 0.051 |
| native_frozen | spread | ev_band | 10-30% | 11304 | -0.049 | -550.919 | 573.072 | 0.199 |
| native_frozen | spread | ev_band | ev>30% | 12020 | -0.044 | -533.161 | 552.978 | 0.460 |
| native_frozen | spread | side | away | 4150 | -0.026 | -106.411 | 144.965 | 0.187 |
| native_frozen | spread | side | home | 24439 | -0.051 | -1252.362 | 1277.099 | 0.297 |
| native_frozen | total | ev_band | 0-10% | 10907 | -0.057 | -624.101 | 628.355 | 0.048 |
| native_frozen | total | ev_band | 10-30% | 11243 | -0.063 | -705.712 | 713.914 | 0.180 |
| native_frozen | total | ev_band | ev>30% | 2898 | -0.050 | -143.920 | 162.243 | 0.401 |
| native_frozen | total | side | over | 15165 | -0.058 | -878.632 | 884.245 | 0.165 |
| native_frozen | total | side | under | 9883 | -0.060 | -595.101 | 615.788 | 0.121 |
| raw | ml | ev_band | 0-10% | 10131 | -0.053 | -535.759 | 582.161 | 0.045 |
| raw | ml | ev_band | 10-30% | 9689 | -0.054 | -519.699 | 535.803 | 0.183 |
| raw | ml | ev_band | ev>30% | 9527 | -0.183 | -1741.632 | 1744.140 | 0.907 |
| raw | ml | fav_dog | favorite | 13173 | -0.025 | -329.480 | 341.659 | 0.132 |
| raw | ml | fav_dog | underdog | 16174 | -0.153 | -2467.610 | 2468.850 | 0.565 |
| raw | ml | price_band | +150..+299 | 5897 | -0.094 | -552.470 | 578.680 | 0.373 |
| raw | ml | price_band | -149..+149 | 8168 | -0.037 | -304.472 | 352.390 | 0.232 |
| raw | ml | price_band | -299..-150 | 5150 | -0.033 | -169.454 | 189.646 | 0.138 |
| raw | ml | price_band | <=-300 | 4160 | -0.012 | -49.323 | 54.235 | 0.063 |
| raw | ml | price_band | >=+300 | 5972 | -0.288 | -1721.370 | 1721.370 | 0.972 |
| raw | spread | ev_band | 0-10% | 8039 | -0.037 | -294.396 | 337.388 | 0.049 |
| raw | spread | ev_band | 10-30% | 10899 | -0.063 | -683.143 | 715.801 | 0.189 |
| raw | spread | ev_band | ev>30% | 7998 | -0.040 | -320.598 | 335.050 | 0.482 |
| raw | spread | side | away | 11340 | -0.037 | -414.677 | 430.564 | 0.242 |
| raw | spread | side | home | 15596 | -0.057 | -883.460 | 904.569 | 0.228 |
| raw | total | ev_band | 0-10% | 9396 | -0.064 | -599.170 | 606.592 | 0.049 |
| raw | total | ev_band | 10-30% | 11759 | -0.059 | -698.111 | 703.115 | 0.187 |
| raw | total | ev_band | ev>30% | 4892 | -0.083 | -403.951 | 415.716 | 0.424 |
| raw | total | side | over | 15474 | -0.063 | -977.934 | 984.208 | 0.198 |
| raw | total | side | under | 10573 | -0.068 | -723.297 | 735.601 | 0.157 |
| regularized | ml | ev_band | 0-10% | 9069 | -0.064 | -582.673 | 590.144 | 0.046 |
| regularized | ml | ev_band | 10-30% | 9458 | -0.065 | -613.773 | 641.241 | 0.185 |
| regularized | ml | ev_band | ev>30% | 10823 | -0.214 | -2317.632 | 2325.132 | 0.927 |
| regularized | ml | fav_dog | favorite | 8708 | -0.023 | -198.998 | 218.514 | 0.100 |
| regularized | ml | fav_dog | underdog | 20642 | -0.161 | -3315.080 | 3321.940 | 0.549 |
| regularized | ml | price_band | +150..+299 | 7150 | -0.096 | -685.560 | 711.380 | 0.306 |
| regularized | ml | price_band | -149..+149 | 8098 | -0.039 | -314.057 | 340.480 | 0.169 |
| regularized | ml | price_band | -299..-150 | 3792 | -0.022 | -81.749 | 100.732 | 0.086 |
| regularized | ml | price_band | <=-300 | 1307 | 0.002 | 2.209 | 23.648 | 0.041 |
| regularized | ml | price_band | >=+300 | 9003 | -0.270 | -2434.920 | 2441.420 | 0.918 |
| regularized | spread | ev_band | 0-10% | 9404 | -0.041 | -387.852 | 393.052 | 0.048 |
| regularized | spread | ev_band | 10-30% | 11494 | -0.034 | -394.653 | 453.175 | 0.185 |
| regularized | spread | ev_band | ev>30% | 5191 | -0.043 | -221.932 | 227.713 | 0.450 |
| regularized | spread | side | away | 11134 | -0.020 | -221.555 | 265.016 | 0.209 |
| regularized | spread | side | home | 14955 | -0.052 | -782.881 | 792.228 | 0.173 |
| regularized | total | ev_band | 0-10% | 11183 | -0.057 | -636.260 | 643.720 | 0.048 |
| regularized | total | ev_band | 10-30% | 11014 | -0.050 | -549.348 | 560.305 | 0.178 |
| regularized | total | ev_band | ev>30% | 2682 | -0.045 | -121.471 | 152.096 | 0.397 |
| regularized | total | side | over | 15142 | -0.055 | -830.164 | 837.595 | 0.161 |
| regularized | total | side | under | 9737 | -0.049 | -476.915 | 500.389 | 0.116 |
| sched_adj | ml | ev_band | 0-10% | 9943 | -0.040 | -398.936 | 419.258 | 0.046 |
| sched_adj | ml | ev_band | 10-30% | 9237 | -0.104 | -963.354 | 984.630 | 0.184 |
| sched_adj | ml | ev_band | ev>30% | 9283 | -0.211 | -1960.684 | 1970.234 | 1.060 |
| sched_adj | ml | fav_dog | favorite | 9236 | -0.022 | -205.383 | 214.014 | 0.094 |
| sched_adj | ml | fav_dog | underdog | 19227 | -0.162 | -3117.590 | 3125.470 | 0.579 |
| sched_adj | ml | price_band | +150..+299 | 6555 | -0.100 | -657.820 | 670.420 | 0.291 |
| sched_adj | ml | price_band | -149..+149 | 8040 | -0.033 | -268.382 | 298.092 | 0.158 |
| sched_adj | ml | price_band | -299..-150 | 4081 | -0.026 | -105.093 | 118.389 | 0.083 |
| sched_adj | ml | price_band | <=-300 | 1521 | -0.010 | -15.408 | 28.699 | 0.037 |
| sched_adj | ml | price_band | >=+300 | 8266 | -0.275 | -2276.270 | 2283.770 | 1.018 |
| sched_adj | spread | ev_band | 0-10% | 10082 | -0.043 | -433.276 | 457.773 | 0.048 |
| sched_adj | spread | ev_band | 10-30% | 10986 | -0.055 | -608.464 | 631.762 | 0.181 |
| sched_adj | spread | ev_band | ev>30% | 4526 | -0.033 | -148.910 | 182.107 | 0.476 |
| sched_adj | spread | side | away | 9316 | -0.031 | -293.341 | 317.744 | 0.226 |
| sched_adj | spread | side | home | 16278 | -0.055 | -897.309 | 915.463 | 0.155 |
| sched_adj | total | ev_band | 0-10% | 11251 | -0.061 | -691.836 | 700.594 | 0.048 |
| sched_adj | total | ev_band | 10-30% | 10912 | -0.051 | -558.083 | 577.443 | 0.178 |
| sched_adj | total | ev_band | ev>30% | 2615 | -0.056 | -147.178 | 163.179 | 0.399 |
| sched_adj | total | side | over | 14897 | -0.060 | -893.785 | 903.187 | 0.160 |
| sched_adj | total | side | under | 9881 | -0.051 | -503.312 | 534.477 | 0.115 |
| native_hca_repaired | ml | ev_band | 0-10% | 8777 | -0.056 | -492.467 | 511.543 | 0.046 |
| native_hca_repaired | ml | ev_band | 10-30% | 9443 | -0.057 | -535.333 | 569.158 | 0.186 |
| native_hca_repaired | ml | ev_band | ev>30% | 11622 | -0.214 | -2483.821 | 2490.371 | 1.001 |
| native_hca_repaired | ml | fav_dog | favorite | 9005 | -0.022 | -200.921 | 212.361 | 0.109 |
| native_hca_repaired | ml | fav_dog | underdog | 20837 | -0.159 | -3310.700 | 3317.580 | 0.615 |
| native_hca_repaired | ml | price_band | +150..+299 | 7349 | -0.093 | -685.300 | 711.340 | 0.334 |
| native_hca_repaired | ml | price_band | -149..+149 | 8202 | -0.036 | -296.055 | 335.035 | 0.185 |
| native_hca_repaired | ml | price_band | -299..-150 | 3871 | -0.021 | -81.021 | 98.544 | 0.096 |
| native_hca_repaired | ml | price_band | <=-300 | 1484 | -0.012 | -17.675 | 21.260 | 0.046 |
| native_hca_repaired | ml | price_band | >=+300 | 8936 | -0.272 | -2431.570 | 2438.070 | 1.049 |
| native_hca_repaired | spread | ev_band | 0-10% | 8901 | -0.043 | -385.255 | 406.641 | 0.048 |
| native_hca_repaired | spread | ev_band | 10-30% | 11445 | -0.036 | -411.917 | 460.716 | 0.187 |
| native_hca_repaired | spread | ev_band | ev>30% | 6095 | -0.039 | -238.814 | 243.695 | 0.459 |
| native_hca_repaired | spread | side | away | 11525 | -0.025 | -283.499 | 328.702 | 0.224 |
| native_hca_repaired | spread | side | home | 14916 | -0.050 | -752.486 | 781.133 | 0.187 |
| native_hca_repaired | total | ev_band | 0-10% | 10907 | -0.057 | -624.101 | 628.355 | 0.048 |
| native_hca_repaired | total | ev_band | 10-30% | 11242 | -0.063 | -704.712 | 712.914 | 0.180 |
| native_hca_repaired | total | ev_band | ev>30% | 2899 | -0.050 | -144.920 | 163.243 | 0.401 |
| native_hca_repaired | total | side | over | 15165 | -0.058 | -878.632 | 884.245 | 0.165 |
| native_hca_repaired | total | side | under | 9883 | -0.060 | -595.101 | 615.788 | 0.121 |
| FG1 | ml | ev_band | 0-10% | 12163 | -0.072 | -880.705 | 883.586 | 0.043 |
| FG1 | ml | ev_band | 10-30% | 8834 | -0.085 | -753.718 | 785.167 | 0.178 |
| FG1 | ml | ev_band | ev>30% | 4572 | -0.230 | -1049.366 | 1058.666 | 0.582 |
| FG1 | ml | fav_dog | favorite | 8828 | -0.027 | -235.150 | 244.349 | 0.069 |
| FG1 | ml | fav_dog | underdog | 16741 | -0.146 | -2448.640 | 2457.990 | 0.248 |
| FG1 | ml | price_band | +150..+299 | 5893 | -0.095 | -559.600 | 583.300 | 0.186 |
| FG1 | ml | price_band | -149..+149 | 7416 | -0.035 | -262.543 | 292.181 | 0.114 |
| FG1 | ml | price_band | -299..-150 | 3868 | -0.032 | -121.998 | 134.366 | 0.065 |
| FG1 | ml | price_band | <=-300 | 1653 | -0.017 | -28.028 | 37.517 | 0.029 |
| FG1 | ml | price_band | >=+300 | 6739 | -0.254 | -1711.620 | 1720.120 | 0.375 |
| FG1 | spread | ev_band | 0-10% | 12544 | -0.047 | -592.798 | 601.589 | 0.046 |
| FG1 | spread | ev_band | 10-30% | 9708 | -0.049 | -476.110 | 508.182 | 0.172 |
| FG1 | spread | ev_band | ev>30% | 1553 | -0.034 | -53.535 | 74.731 | 0.393 |
| FG1 | spread | side | away | 9617 | -0.035 | -341.321 | 348.450 | 0.122 |
| FG1 | spread | side | home | 14188 | -0.055 | -781.122 | 811.276 | 0.119 |
| FG1 | total | ev_band | 0-10% | 13340 | -0.053 | -708.487 | 737.695 | 0.046 |
| FG1 | total | ev_band | 10-30% | 8919 | -0.052 | -462.896 | 469.157 | 0.167 |
| FG1 | total | ev_band | ev>30% | 770 | -0.019 | -14.811 | 56.328 | 0.366 |
| FG1 | total | side | over | 15864 | -0.054 | -855.245 | 873.845 | 0.114 |
| FG1 | total | side | under | 7165 | -0.046 | -330.949 | 389.672 | 0.081 |
| native_frozen | spread | fav_dog | favorite | 16081 | -0.053 | -855.302 | 871.420 | 0.250 |
| native_frozen | spread | fav_dog | underdog | 12468 | -0.041 | -505.365 | 535.161 | 0.322 |
| raw | spread | fav_dog | favorite | 14167 | -0.057 | -804.297 | 822.107 | 0.232 |
| raw | spread | fav_dog | underdog | 12733 | -0.039 | -494.029 | 530.495 | 0.236 |
| regularized | spread | fav_dog | favorite | 8070 | -0.056 | -449.788 | 463.220 | 0.125 |
| regularized | spread | fav_dog | underdog | 17983 | -0.031 | -551.020 | 595.321 | 0.217 |
| sched_adj | spread | fav_dog | favorite | 9254 | -0.060 | -553.044 | 563.914 | 0.116 |
| sched_adj | spread | fav_dog | underdog | 16307 | -0.039 | -633.239 | 659.083 | 0.218 |
| native_hca_repaired | spread | fav_dog | favorite | 8640 | -0.054 | -468.973 | 494.294 | 0.142 |
| native_hca_repaired | spread | fav_dog | underdog | 17768 | -0.032 | -564.498 | 623.328 | 0.233 |
| FG1 | spread | fav_dog | favorite | 8072 | -0.061 | -490.542 | 510.561 | 0.089 |
| FG1 | spread | fav_dog | underdog | 15704 | -0.040 | -623.936 | 631.458 | 0.136 |

## 10. Calibration bins (ALL)
| family | model | bin | n | mean_p | freq |
|---|---|---|---|---|---|
| ml | native_frozen | 0.000 | 13.000 | 0.077 | 0.077 |
| ml | native_frozen | 1.000 | 82.000 | 0.163 | 0.146 |
| ml | native_frozen | 2.000 | 365 | 0.260 | 0.195 |
| ml | native_frozen | 3.000 | 1037 | 0.356 | 0.266 |
| ml | native_frozen | 4.000 | 2277 | 0.457 | 0.353 |
| ml | native_frozen | 5.000 | 4194 | 0.554 | 0.437 |
| ml | native_frozen | 6.000 | 6477 | 0.654 | 0.525 |
| ml | native_frozen | 7.000 | 8340 | 0.751 | 0.641 |
| ml | native_frozen | 8.000 | 8576 | 0.849 | 0.760 |
| ml | native_frozen | 9.000 | 4430 | 0.937 | 0.894 |
| ml | raw | 0.000 | 710 | 0.057 | 0.225 |
| ml | raw | 1.000 | 1242 | 0.152 | 0.278 |
| ml | raw | 2.000 | 2013 | 0.253 | 0.331 |
| ml | raw | 3.000 | 2985 | 0.354 | 0.431 |
| ml | raw | 4.000 | 3977 | 0.451 | 0.472 |
| ml | raw | 5.000 | 4926 | 0.552 | 0.567 |
| ml | raw | 6.000 | 5534 | 0.650 | 0.640 |
| ml | raw | 7.000 | 5586 | 0.749 | 0.724 |
| ml | raw | 8.000 | 5040 | 0.848 | 0.810 |
| ml | raw | 9.000 | 3778 | 0.949 | 0.908 |
| ml | regularized | 0.000 | 33.000 | 0.070 | 0.091 |
| ml | regularized | 1.000 | 309 | 0.163 | 0.100 |
| ml | regularized | 2.000 | 1043 | 0.258 | 0.215 |
| ml | regularized | 3.000 | 2331 | 0.357 | 0.311 |
| ml | regularized | 4.000 | 4474 | 0.455 | 0.405 |
| ml | regularized | 5.000 | 6654 | 0.552 | 0.536 |
| ml | regularized | 6.000 | 8091 | 0.651 | 0.650 |
| ml | regularized | 7.000 | 7037 | 0.748 | 0.767 |
| ml | regularized | 8.000 | 4484 | 0.844 | 0.875 |
| ml | regularized | 9.000 | 1335 | 0.934 | 0.961 |
| ml | sched_adj | 0.000 | 39.000 | 0.073 | 0.103 |
| ml | sched_adj | 1.000 | 314 | 0.162 | 0.105 |
| ml | sched_adj | 2.000 | 1082 | 0.257 | 0.187 |
| ml | sched_adj | 3.000 | 2368 | 0.354 | 0.315 |
| ml | sched_adj | 4.000 | 4475 | 0.453 | 0.410 |
| ml | sched_adj | 5.000 | 6478 | 0.552 | 0.532 |
| ml | sched_adj | 6.000 | 7674 | 0.651 | 0.657 |
| ml | sched_adj | 7.000 | 7204 | 0.748 | 0.757 |
| ml | sched_adj | 8.000 | 4731 | 0.844 | 0.867 |
| ml | sched_adj | 9.000 | 1426 | 0.932 | 0.956 |
| ml | native_hca_repaired | 0.000 | 52.000 | 0.073 | 0.096 |
| ml | native_hca_repaired | 1.000 | 346 | 0.162 | 0.145 |
| ml | native_hca_repaired | 2.000 | 1111 | 0.257 | 0.249 |
| ml | native_hca_repaired | 3.000 | 2484 | 0.356 | 0.328 |
| ml | native_hca_repaired | 4.000 | 4665 | 0.455 | 0.441 |
| ml | native_hca_repaired | 5.000 | 6615 | 0.553 | 0.543 |
| ml | native_hca_repaired | 6.000 | 7782 | 0.650 | 0.648 |
| ml | native_hca_repaired | 7.000 | 7013 | 0.748 | 0.762 |
| ml | native_hca_repaired | 8.000 | 4319 | 0.843 | 0.859 |
| ml | native_hca_repaired | 9.000 | 1404 | 0.933 | 0.947 |
| ml | FG1 | 0.000 | 116 | 0.069 | 0.043 |
| ml | FG1 | 1.000 | 611 | 0.160 | 0.098 |
| ml | FG1 | 2.000 | 1477 | 0.256 | 0.201 |
| ml | FG1 | 3.000 | 2692 | 0.355 | 0.309 |
| ml | FG1 | 4.000 | 4226 | 0.453 | 0.428 |
| ml | FG1 | 5.000 | 5888 | 0.552 | 0.528 |
| ml | FG1 | 6.000 | 6574 | 0.650 | 0.648 |
| ml | FG1 | 7.000 | 6413 | 0.748 | 0.751 |
| ml | FG1 | 8.000 | 5057 | 0.847 | 0.871 |
| ml | FG1 | 9.000 | 2737 | 0.942 | 0.961 |
| ml | MARKET_NOVIG_CLOSE | 0.000 | 248 | 0.079 | 0.048 |
| ml | MARKET_NOVIG_CLOSE | 1.000 | 1123 | 0.155 | 0.128 |
| ml | MARKET_NOVIG_CLOSE | 2.000 | 1965 | 0.255 | 0.223 |
| ml | MARKET_NOVIG_CLOSE | 3.000 | 2969 | 0.354 | 0.351 |
| ml | MARKET_NOVIG_CLOSE | 4.000 | 4088 | 0.449 | 0.443 |
| ml | MARKET_NOVIG_CLOSE | 5.000 | 5744 | 0.551 | 0.565 |
| ml | MARKET_NOVIG_CLOSE | 6.000 | 5896 | 0.648 | 0.657 |
| ml | MARKET_NOVIG_CLOSE | 7.000 | 5527 | 0.747 | 0.771 |
| ml | MARKET_NOVIG_CLOSE | 8.000 | 4803 | 0.851 | 0.878 |
| ml | MARKET_NOVIG_CLOSE | 9.000 | 2500 | 0.928 | 0.961 |
| spread | native_frozen | 0.000 | 46.000 | 0.076 | 0.457 |
| spread | native_frozen | 1.000 | 195 | 0.156 | 0.477 |
| spread | native_frozen | 2.000 | 478 | 0.257 | 0.479 |
| spread | native_frozen | 3.000 | 1277 | 0.359 | 0.484 |
| spread | native_frozen | 4.000 | 3079 | 0.457 | 0.491 |
| spread | native_frozen | 5.000 | 6807 | 0.556 | 0.495 |
| spread | native_frozen | 6.000 | 9146 | 0.650 | 0.492 |
| spread | native_frozen | 7.000 | 6511 | 0.745 | 0.497 |
| spread | native_frozen | 8.000 | 2552 | 0.840 | 0.505 |
| spread | native_frozen | 9.000 | 397 | 0.926 | 0.514 |
| spread | raw | 0.000 | 442 | 0.058 | 0.464 |
| spread | raw | 1.000 | 911 | 0.154 | 0.491 |
| spread | raw | 2.000 | 1691 | 0.255 | 0.499 |
| spread | raw | 3.000 | 3431 | 0.357 | 0.491 |
| spread | raw | 4.000 | 6641 | 0.454 | 0.497 |
| spread | raw | 5.000 | 8125 | 0.549 | 0.501 |
| spread | raw | 6.000 | 5554 | 0.645 | 0.483 |
| spread | raw | 7.000 | 2494 | 0.741 | 0.504 |
| spread | raw | 8.000 | 864 | 0.841 | 0.487 |
| spread | raw | 9.000 | 335 | 0.940 | 0.496 |
| spread | regularized | 0.000 | 285 | 0.065 | 0.491 |
| spread | regularized | 1.000 | 768 | 0.155 | 0.482 |
| spread | regularized | 2.000 | 1278 | 0.255 | 0.506 |
| spread | regularized | 3.000 | 3304 | 0.359 | 0.464 |
| spread | regularized | 4.000 | 7675 | 0.455 | 0.501 |
| spread | regularized | 5.000 | 9643 | 0.549 | 0.497 |
| spread | regularized | 6.000 | 5723 | 0.643 | 0.497 |
| spread | regularized | 7.000 | 1592 | 0.735 | 0.498 |
| spread | regularized | 8.000 | 205 | 0.829 | 0.507 |
| spread | regularized | 9.000 | 15.000 | 0.926 | 0.400 |
| spread | sched_adj | 0.000 | 414 | 0.062 | 0.476 |
| spread | sched_adj | 1.000 | 864 | 0.152 | 0.485 |
| spread | sched_adj | 2.000 | 1096 | 0.253 | 0.509 |
| spread | sched_adj | 3.000 | 2127 | 0.359 | 0.489 |
| spread | sched_adj | 4.000 | 7060 | 0.458 | 0.490 |
| spread | sched_adj | 5.000 | 11559 | 0.549 | 0.500 |
| spread | sched_adj | 6.000 | 6013 | 0.639 | 0.486 |
| spread | sched_adj | 7.000 | 1190 | 0.735 | 0.507 |
| spread | sched_adj | 8.000 | 155 | 0.828 | 0.619 |
| spread | sched_adj | 9.000 | 10.000 | 0.926 | 0.600 |
| spread | native_hca_repaired | 0.000 | 340 | 0.062 | 0.491 |
| spread | native_hca_repaired | 1.000 | 901 | 0.154 | 0.488 |
| spread | native_hca_repaired | 2.000 | 1505 | 0.256 | 0.482 |
| spread | native_hca_repaired | 3.000 | 3416 | 0.358 | 0.486 |
| spread | native_hca_repaired | 4.000 | 7378 | 0.454 | 0.496 |
| spread | native_hca_repaired | 5.000 | 9023 | 0.549 | 0.499 |
| spread | native_hca_repaired | 6.000 | 5665 | 0.644 | 0.498 |
| spread | native_hca_repaired | 7.000 | 1879 | 0.738 | 0.487 |
| spread | native_hca_repaired | 8.000 | 349 | 0.833 | 0.510 |
| spread | native_hca_repaired | 9.000 | 32.000 | 0.926 | 0.469 |
| spread | FG1 | 0.000 | 8.000 | 0.070 | 0.250 |
| spread | FG1 | 1.000 | 98.000 | 0.168 | 0.429 |
| spread | FG1 | 2.000 | 538 | 0.262 | 0.487 |
| spread | FG1 | 3.000 | 2282 | 0.364 | 0.493 |
| spread | FG1 | 4.000 | 9864 | 0.458 | 0.497 |
| spread | FG1 | 5.000 | 13133 | 0.546 | 0.492 |
| spread | FG1 | 6.000 | 4099 | 0.635 | 0.495 |
| spread | FG1 | 7.000 | 438 | 0.729 | 0.521 |
| spread | FG1 | 8.000 | 25.000 | 0.826 | 0.560 |
| spread | FG1 | 9.000 | 3.000 | 0.940 | 0.667 |
| spread | MARKET_NOVIG_CLOSE | 3.000 | 17.000 | 0.338 | 0.471 |
| spread | MARKET_NOVIG_CLOSE | 4.000 | 9653 | 0.490 | 0.490 |
| spread | MARKET_NOVIG_CLOSE | 5.000 | 20795 | 0.505 | 0.496 |
| spread | MARKET_NOVIG_CLOSE | 6.000 | 21.000 | 0.649 | 0.762 |
| total | native_frozen | 0.000 | 1.000 | 0.092 | 0.000 |
| total | native_frozen | 1.000 | 20.000 | 0.172 | 0.450 |
| total | native_frozen | 2.000 | 321 | 0.270 | 0.498 |
| total | native_frozen | 3.000 | 2946 | 0.364 | 0.510 |
| total | native_frozen | 4.000 | 9320 | 0.456 | 0.507 |
| total | native_frozen | 5.000 | 10832 | 0.548 | 0.493 |
| total | native_frozen | 6.000 | 5331 | 0.641 | 0.503 |
| total | native_frozen | 7.000 | 1501 | 0.737 | 0.492 |
| total | native_frozen | 8.000 | 244 | 0.835 | 0.492 |
| total | native_frozen | 9.000 | 28.000 | 0.939 | 0.536 |
| total | raw | 0.000 | 21.000 | 0.072 | 0.619 |
| total | raw | 1.000 | 134 | 0.169 | 0.455 |
| total | raw | 2.000 | 889 | 0.264 | 0.501 |
| total | raw | 3.000 | 3682 | 0.360 | 0.519 |
| total | raw | 4.000 | 8004 | 0.454 | 0.505 |
| total | raw | 5.000 | 9319 | 0.548 | 0.497 |
| total | raw | 6.000 | 5723 | 0.644 | 0.499 |
| total | raw | 7.000 | 2136 | 0.740 | 0.462 |
| total | raw | 8.000 | 535 | 0.836 | 0.527 |
| total | raw | 9.000 | 101 | 0.935 | 0.465 |
| total | regularized | 0.000 | 1.000 | 0.090 | 0.000 |
| total | regularized | 1.000 | 17.000 | 0.166 | 0.471 |
| total | regularized | 2.000 | 271 | 0.273 | 0.517 |
| total | regularized | 3.000 | 2755 | 0.366 | 0.492 |
| total | regularized | 4.000 | 9432 | 0.456 | 0.509 |
| total | regularized | 5.000 | 11188 | 0.547 | 0.495 |
| total | regularized | 6.000 | 5222 | 0.640 | 0.498 |
| total | regularized | 7.000 | 1424 | 0.736 | 0.502 |
| total | regularized | 8.000 | 207 | 0.833 | 0.507 |
| total | regularized | 9.000 | 27.000 | 0.938 | 0.556 |
| total | sched_adj | 1.000 | 21.000 | 0.170 | 0.381 |
| total | sched_adj | 2.000 | 270 | 0.274 | 0.515 |
| total | sched_adj | 3.000 | 2733 | 0.365 | 0.503 |
| total | sched_adj | 4.000 | 9649 | 0.456 | 0.509 |
| total | sched_adj | 5.000 | 11204 | 0.547 | 0.495 |
| total | sched_adj | 6.000 | 5039 | 0.641 | 0.496 |
| total | sched_adj | 7.000 | 1389 | 0.736 | 0.490 |
| total | sched_adj | 8.000 | 212 | 0.833 | 0.505 |
| total | sched_adj | 9.000 | 27.000 | 0.939 | 0.556 |
| total | native_hca_repaired | 0.000 | 1.000 | 0.092 | 0.000 |
| total | native_hca_repaired | 1.000 | 20.000 | 0.172 | 0.450 |
| total | native_hca_repaired | 2.000 | 321 | 0.270 | 0.498 |
| total | native_hca_repaired | 3.000 | 2946 | 0.364 | 0.510 |
| total | native_hca_repaired | 4.000 | 9320 | 0.456 | 0.507 |
| total | native_hca_repaired | 5.000 | 10832 | 0.548 | 0.493 |
| total | native_hca_repaired | 6.000 | 5330 | 0.641 | 0.502 |
| total | native_hca_repaired | 7.000 | 1502 | 0.737 | 0.493 |
| total | native_hca_repaired | 8.000 | 244 | 0.835 | 0.492 |
| total | native_hca_repaired | 9.000 | 28.000 | 0.939 | 0.536 |
| total | FG1 | 0.000 | 1.000 | 0.093 | 1.000 |
| total | FG1 | 1.000 | 3.000 | 0.179 | 0.333 |
| total | FG1 | 2.000 | 42.000 | 0.272 | 0.381 |
| total | FG1 | 3.000 | 1073 | 0.373 | 0.512 |
| total | FG1 | 4.000 | 9533 | 0.462 | 0.505 |
| total | FG1 | 5.000 | 15027 | 0.546 | 0.499 |
| total | FG1 | 6.000 | 4476 | 0.634 | 0.496 |
| total | FG1 | 7.000 | 367 | 0.729 | 0.482 |
| total | FG1 | 8.000 | 20.000 | 0.821 | 0.550 |
| total | FG1 | 9.000 | 2.000 | 1.000 | 1.000 |
| total | MARKET_NOVIG_CLOSE | 3.000 | 22.000 | 0.389 | 0.455 |
| total | MARKET_NOVIG_CLOSE | 4.000 | 11384 | 0.493 | 0.494 |
| total | MARKET_NOVIG_CLOSE | 5.000 | 19102 | 0.505 | 0.504 |
| total | MARKET_NOVIG_CLOSE | 6.000 | 30.000 | 0.610 | 0.533 |

