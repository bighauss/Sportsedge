# Full-game improvement ablations (PAPER / 0u, NON_COUNTED)

Tune 2020-22 (frozen). Validation 2023-25. 2026-27 is a CONFIRMATORY REUSE of an already-used window, not a fresh holdout.

ESPN historical odds are an auxiliary comparator only, not execution prices or CLV.

## Gaps

- **player_availability:** No legitimate point-in-time public injury/availability source is shipped with this challenger. The production gate already blocks a missing injuries role. Documented as a gap; not filled with a leaky proxy.
- **returning_minutes:** Player box scores exist on the box for some seasons, but there is no dated preseason roster or transfer snapshot that would let returning minutes be computed without using current-season appearances (leakage). Early-season ratings continue to use the previous-season carry prior only.
- **travel_proxy:** Travel miles use city/state labels from sportsdataverse schedules and region centroids (same-city 0, same-state 120, else haversine of centroids). Not surveyed road distance.

## Tune-window coefficients (2020-22)

### rest
- margin (n=14393): intercept=-0.1371, rest_diff=-0.1261, home_b2b=-3.5927, away_b2b=2.9550
- total (n=14393): intercept=-0.2186, rest_diff=0.0630, home_b2b=0.1949, away_b2b=-1.9314
### travel
- margin (n=14393): intercept=-0.4931, away_miles100=0.0452, home_miles100=-0.0301, away_moved=0.3963, home_moved=-0.3750
- total (n=14393): intercept=-1.9068, away_miles100=0.0824, home_miles100=-0.0583, away_moved=1.7360, home_moved=-0.6454
### neutral
- margin (n=14393): intercept=-0.1202, is_neutral=-0.3184
- total (n=14393): intercept=-0.1629, is_neutral=-1.8847
### early
- margin (n=14393): intercept=-0.3231, early=0.8893
- total (n=14393): intercept=-0.1848, early=-0.9908
### ctx
- margin (n=14393): intercept=-0.4443, rest_diff=-0.1266, home_b2b=-3.8815, away_b2b=3.3828, is_neutral=-0.6823, away_miles100=0.0425, home_miles100=-0.0078, early=0.9504
- total (n=14393): intercept=-0.2984, rest_diff=0.0623, home_b2b=-0.2004, away_b2b=-0.9609, is_neutral=-2.0820, away_miles100=0.0847, home_miles100=0.0609, early=-0.9488

- favourite bump delta=-0.0074 (n=9157)
- over-shift at model's own total delta=-0.0159 (n=9044)
- longshot primary=0.05 edges={"0.05": {"n": 26, "model": 0.02967820096668979, "rate": 0.07692307692307693}, "0.08": {"n": 55, "model": 0.048428432576667, "rate": 0.09090909090909091}, "0.12": {"n": 157, "model": 0.08479312018618745, "rate": 0.10191082802547771}}

## Point metrics on identical FG1 rows (actual − forecast)

| season | split | engine | n | margin MAE | margin RMSE | margin bias | total MAE | total RMSE | total bias |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2020 | TUNE | FG1 | 5236 | 8.985 | 11.443 | 0.048 | 13.310 | 16.832 | -0.040 |
| 2020 | TUNE | FG2_rest | 5236 | 8.990 | 11.446 | 0.205 | 13.300 | 16.830 | 0.245 |
| 2020 | TUNE | FG2_travel | 5236 | 8.985 | 11.442 | 0.170 | 13.303 | 16.826 | 0.214 |
| 2020 | TUNE | FG2_neutral | 5236 | 8.984 | 11.443 | 0.195 | 13.294 | 16.820 | 0.285 |
| 2020 | TUNE | FG2_early | 5236 | 8.984 | 11.441 | 0.220 | 13.297 | 16.828 | 0.312 |
| 2020 | TUNE | FG2_ctx | 5236 | 8.984 | 11.435 | 0.198 | 13.280 | 16.805 | 0.171 |
| 2020 | TUNE | FG2 | 5236 | 8.984 | 11.435 | 0.198 | 13.280 | 16.805 | 0.171 |
| 2021 | TUNE | FG1 | 3788 | 9.335 | 11.829 | -0.483 | 13.414 | 16.888 | -0.889 |
| 2021 | TUNE | FG2_rest | 3788 | 9.315 | 11.796 | -0.298 | 13.398 | 16.863 | -0.327 |
| 2021 | TUNE | FG2_travel | 3788 | 9.327 | 11.823 | -0.274 | 13.394 | 16.873 | -0.290 |
| 2021 | TUNE | FG2_neutral | 3788 | 9.330 | 11.825 | -0.325 | 13.399 | 16.874 | -0.498 |
| 2021 | TUNE | FG2_early | 3788 | 9.331 | 11.825 | -0.382 | 13.396 | 16.869 | -0.457 |
| 2021 | TUNE | FG2_ctx | 3788 | 9.323 | 11.799 | -0.339 | 13.393 | 16.858 | -0.249 |
| 2021 | TUNE | FG2 | 3788 | 9.323 | 11.799 | -0.339 | 13.393 | 16.858 | -0.249 |
| 2022 | TUNE | FG1 | 5369 | 8.887 | 11.295 | -0.122 | 13.161 | 16.757 | -0.330 |
| 2022 | TUNE | FG2_rest | 5369 | 8.876 | 11.281 | 0.010 | 13.148 | 16.743 | -0.008 |
| 2022 | TUNE | FG2_travel | 5369 | 8.881 | 11.289 | 0.028 | 13.136 | 16.726 | -0.004 |
| 2022 | TUNE | FG2_neutral | 5369 | 8.886 | 11.295 | 0.039 | 13.143 | 16.739 | 0.074 |
| 2022 | TUNE | FG2_early | 5369 | 8.875 | 11.283 | 0.055 | 13.147 | 16.751 | 0.017 |
| 2022 | TUNE | FG2_ctx | 5369 | 8.864 | 11.265 | 0.046 | 13.142 | 16.732 | 0.009 |
| 2022 | TUNE | FG2 | 5369 | 8.864 | 11.265 | 0.046 | 13.142 | 16.732 | 0.009 |
| 2022 | TUNE | FG2C | 5369 | 8.868 | 11.274 | 0.070 | 13.115 | 16.698 | -0.109 |
| 2022 | TUNE | FG1C | 5369 | 8.879 | 11.291 | 0.085 | 13.124 | 16.717 | -0.096 |
| 2023 | VALIDATION | FG1 | 5588 | 9.007 | 11.363 | 0.249 | 13.182 | 16.639 | 0.294 |
| 2023 | VALIDATION | FG2_rest | 5588 | 9.008 | 11.364 | 0.377 | 13.168 | 16.644 | 0.619 |
| 2023 | VALIDATION | FG2_travel | 5588 | 9.013 | 11.364 | 0.398 | 13.175 | 16.654 | 0.622 |
| 2023 | VALIDATION | FG2_neutral | 5588 | 9.013 | 11.370 | 0.412 | 13.157 | 16.630 | 0.714 |
| 2023 | VALIDATION | FG2_early | 5588 | 9.006 | 11.363 | 0.434 | 13.173 | 16.641 | 0.632 |
| 2023 | VALIDATION | FG2_ctx | 5588 | 9.008 | 11.359 | 0.417 | 13.154 | 16.631 | 0.607 |
| 2023 | VALIDATION | FG2 | 5588 | 9.008 | 11.359 | 0.417 | 13.154 | 16.631 | 0.607 |
| 2023 | VALIDATION | FG2C | 5588 | 9.005 | 11.357 | 0.429 | 13.115 | 16.603 | 0.641 |
| 2023 | VALIDATION | FG1C | 5588 | 9.006 | 11.364 | 0.448 | 13.134 | 16.613 | 0.665 |
| 2024 | VALIDATION | FG1 | 5610 | 9.081 | 11.477 | -0.145 | 13.225 | 16.829 | -0.198 |
| 2024 | VALIDATION | FG2_rest | 5610 | 9.073 | 11.473 | -0.015 | 13.214 | 16.823 | 0.119 |
| 2024 | VALIDATION | FG2_travel | 5610 | 9.075 | 11.469 | -0.001 | 13.204 | 16.817 | 0.119 |
| 2024 | VALIDATION | FG2_neutral | 5610 | 9.086 | 11.479 | 0.017 | 13.196 | 16.815 | 0.212 |
| 2024 | VALIDATION | FG2_early | 5610 | 9.079 | 11.470 | 0.040 | 13.213 | 16.828 | 0.140 |
| 2024 | VALIDATION | FG2_ctx | 5610 | 9.066 | 11.461 | 0.019 | 13.208 | 16.819 | 0.102 |
| 2024 | VALIDATION | FG2 | 5610 | 9.066 | 11.461 | 0.019 | 13.208 | 16.819 | 0.102 |
| 2024 | VALIDATION | FG2C | 5610 | 9.066 | 11.467 | -0.083 | 13.184 | 16.786 | 0.480 |
| 2024 | VALIDATION | FG1C | 5610 | 9.079 | 11.477 | -0.069 | 13.191 | 16.797 | 0.520 |
| 2025 | VALIDATION | FG1 | 5645 | 9.043 | 11.548 | 0.197 | 13.019 | 16.661 | -0.575 |
| 2025 | VALIDATION | FG2_rest | 5645 | 9.039 | 11.550 | 0.315 | 12.999 | 16.641 | -0.249 |
| 2025 | VALIDATION | FG2_travel | 5645 | 9.041 | 11.546 | 0.329 | 13.016 | 16.652 | -0.281 |
| 2025 | VALIDATION | FG2_neutral | 5645 | 9.049 | 11.557 | 0.359 | 12.999 | 16.643 | -0.168 |
| 2025 | VALIDATION | FG2_early | 5645 | 9.043 | 11.548 | 0.381 | 13.001 | 16.647 | -0.236 |
| 2025 | VALIDATION | FG2_ctx | 5645 | 9.034 | 11.542 | 0.335 | 13.000 | 16.628 | -0.294 |
| 2025 | VALIDATION | FG2 | 5645 | 9.034 | 11.542 | 0.335 | 13.000 | 16.628 | -0.294 |
| 2025 | VALIDATION | FG2C | 5645 | 9.036 | 11.543 | 0.242 | 12.951 | 16.595 | 0.084 |
| 2025 | VALIDATION | FG1C | 5645 | 9.044 | 11.549 | 0.276 | 12.957 | 16.615 | 0.125 |
| 2026 | CONFIRMATORY_REUSE | FG1 | 5644 | 9.202 | 11.689 | -0.183 | 13.826 | 17.368 | -0.955 |
| 2026 | CONFIRMATORY_REUSE | FG2_rest | 5644 | 9.204 | 11.696 | -0.071 | 13.795 | 17.344 | -0.641 |
| 2026 | CONFIRMATORY_REUSE | FG2_travel | 5644 | 9.199 | 11.682 | -0.052 | 13.785 | 17.344 | -0.670 |
| 2026 | CONFIRMATORY_REUSE | FG2_neutral | 5644 | 9.200 | 11.689 | -0.024 | 13.779 | 17.335 | -0.562 |
| 2026 | CONFIRMATORY_REUSE | FG2_early | 5644 | 9.198 | 11.683 | 0.001 | 13.803 | 17.357 | -0.615 |
| 2026 | CONFIRMATORY_REUSE | FG2_ctx | 5644 | 9.200 | 11.689 | -0.053 | 13.782 | 17.335 | -0.677 |
| 2026 | CONFIRMATORY_REUSE | FG2 | 5644 | 9.200 | 11.689 | -0.053 | 13.782 | 17.335 | -0.677 |
| 2026 | CONFIRMATORY_REUSE | FG2C | 5644 | 9.199 | 11.691 | -0.187 | 13.739 | 17.302 | 0.159 |
| 2026 | CONFIRMATORY_REUSE | FG1C | 5644 | 9.197 | 11.684 | -0.154 | 13.762 | 17.325 | 0.201 |
| 2027 | CONFIRMATORY_REUSE | FG1 | 1050 | 10.623 | 13.357 | 1.242 | 13.812 | 17.654 | 0.483 |
| 2027 | CONFIRMATORY_REUSE | FG2_rest | 1050 | 10.600 | 13.344 | 1.397 | 13.801 | 17.667 | 0.776 |
| 2027 | CONFIRMATORY_REUSE | FG2_travel | 1050 | 10.614 | 13.351 | 1.340 | 13.859 | 17.721 | 0.837 |
| 2027 | CONFIRMATORY_REUSE | FG2_neutral | 1050 | 10.626 | 13.367 | 1.414 | 13.835 | 17.699 | 0.949 |
| 2027 | CONFIRMATORY_REUSE | FG2_early | 1050 | 10.616 | 13.335 | 0.763 | 13.832 | 17.728 | 1.562 |
| 2027 | CONFIRMATORY_REUSE | FG2_ctx | 1050 | 10.578 | 13.295 | 0.701 | 13.847 | 17.725 | 1.405 |
| 2027 | CONFIRMATORY_REUSE | FG2 | 1050 | 10.578 | 13.295 | 0.701 | 13.847 | 17.725 | 1.405 |
| 2027 | CONFIRMATORY_REUSE | FG2C | 1050 | 10.571 | 13.281 | 0.533 | 13.800 | 17.654 | 2.231 |
| 2027 | CONFIRMATORY_REUSE | FG1C | 1050 | 10.601 | 13.308 | 0.556 | 13.787 | 17.663 | 2.311 |

## Market Brier (auxiliary ESPN close quotes) vs market Brier

| season | split | engine | market | n | model Brier | market Brier | delta (model−market) |
|---|---|---|---|---:|---:|---:|---:|
| 2023 | VALIDATION | FG1 | spread | 2 | 0.3997 | 0.2707 | +0.1289 |
| 2023 | VALIDATION | FG1 | total | 23 | 0.1410 | 0.2714 | -0.1304 |
| 2023 | VALIDATION | FG1 | moneyline | 5371 | 0.1843 | 0.1805 | +0.0039 |
| 2023 | VALIDATION | FG2 | spread | 2 | 0.3522 | 0.2707 | +0.0814 |
| 2023 | VALIDATION | FG2 | total | 23 | 0.1430 | 0.2714 | -0.1283 |
| 2023 | VALIDATION | FG2 | moneyline | 5371 | 0.1844 | 0.1805 | +0.0040 |
| 2023 | VALIDATION | FG2C | spread | 2 | 0.3375 | 0.2707 | +0.0668 |
| 2023 | VALIDATION | FG2C | total | 23 | 0.1446 | 0.2714 | -0.1268 |
| 2023 | VALIDATION | FG2C | moneyline | 5371 | 0.1845 | 0.1805 | +0.0040 |
| 2023 | VALIDATION | FG2_rest | spread | 2 | 0.3848 | 0.2707 | +0.1141 |
| 2023 | VALIDATION | FG2_rest | total | 23 | 0.1408 | 0.2714 | -0.1305 |
| 2023 | VALIDATION | FG2_rest | moneyline | 5371 | 0.1844 | 0.1805 | +0.0039 |
| 2023 | VALIDATION | FG2_travel | spread | 2 | 0.3716 | 0.2707 | +0.1009 |
| 2023 | VALIDATION | FG2_travel | total | 23 | 0.1433 | 0.2714 | -0.1280 |
| 2023 | VALIDATION | FG2_travel | moneyline | 5371 | 0.1843 | 0.1805 | +0.0038 |
| 2023 | VALIDATION | FG2_neutral | spread | 2 | 0.3923 | 0.2707 | +0.1216 |
| 2023 | VALIDATION | FG2_neutral | total | 23 | 0.1445 | 0.2714 | -0.1269 |
| 2023 | VALIDATION | FG2_neutral | moneyline | 5371 | 0.1844 | 0.1805 | +0.0040 |
| 2023 | VALIDATION | FG2_early | spread | 2 | 0.3997 | 0.2707 | +0.1289 |
| 2023 | VALIDATION | FG2_early | total | 23 | 0.1410 | 0.2714 | -0.1304 |
| 2023 | VALIDATION | FG2_early | moneyline | 5371 | 0.1843 | 0.1805 | +0.0039 |
| 2023 | VALIDATION | FG2_ctx | spread | 2 | 0.3522 | 0.2707 | +0.0814 |
| 2023 | VALIDATION | FG2_ctx | total | 23 | 0.1430 | 0.2714 | -0.1283 |
| 2023 | VALIDATION | FG2_ctx | moneyline | 5371 | 0.1844 | 0.1805 | +0.0040 |
| 2023 | VALIDATION | FG2C_longshot | spread | 2 | 0.3375 | 0.2707 | +0.0668 |
| 2023 | VALIDATION | FG2C_longshot | total | 23 | 0.1446 | 0.2714 | -0.1268 |
| 2023 | VALIDATION | FG2C_longshot | moneyline | 5371 | 0.1846 | 0.1805 | +0.0041 |
| 2023 | VALIDATION | FG2C_favbump | spread | 2 | 0.3375 | 0.2707 | +0.0668 |
| 2023 | VALIDATION | FG2C_favbump | total | 23 | 0.1446 | 0.2714 | -0.1268 |
| 2023 | VALIDATION | FG2C_favbump | moneyline | 5371 | 0.1846 | 0.1805 | +0.0041 |
| 2023 | VALIDATION | FG2C_longshot_favbump | spread | 2 | 0.3375 | 0.2707 | +0.0668 |
| 2023 | VALIDATION | FG2C_longshot_favbump | total | 23 | 0.1446 | 0.2714 | -0.1268 |
| 2023 | VALIDATION | FG2C_longshot_favbump | moneyline | 5371 | 0.1847 | 0.1805 | +0.0042 |
| 2023 | VALIDATION | FG1C | spread | 2 | 0.3867 | 0.2707 | +0.1160 |
| 2023 | VALIDATION | FG1C | total | 23 | 0.1426 | 0.2714 | -0.1288 |
| 2023 | VALIDATION | FG1C | moneyline | 5371 | 0.1845 | 0.1805 | +0.0040 |
| 2024 | VALIDATION | FG1 | spread | 4955 | 0.2588 | 0.2500 | +0.0088 |
| 2024 | VALIDATION | FG1 | total | 4956 | 0.2579 | 0.2501 | +0.0078 |
| 2024 | VALIDATION | FG1 | moneyline | 4941 | 0.1854 | 0.1801 | +0.0053 |
| 2024 | VALIDATION | FG2 | spread | 4955 | 0.2582 | 0.2500 | +0.0083 |
| 2024 | VALIDATION | FG2 | total | 4956 | 0.2578 | 0.2501 | +0.0077 |
| 2024 | VALIDATION | FG2 | moneyline | 4941 | 0.1851 | 0.1801 | +0.0051 |
| 2024 | VALIDATION | FG2C | spread | 4955 | 0.2582 | 0.2500 | +0.0082 |
| 2024 | VALIDATION | FG2C | total | 4956 | 0.2573 | 0.2501 | +0.0072 |
| 2024 | VALIDATION | FG2C | moneyline | 4941 | 0.1852 | 0.1801 | +0.0051 |
| 2024 | VALIDATION | FG2_rest | spread | 4955 | 0.2585 | 0.2500 | +0.0085 |
| 2024 | VALIDATION | FG2_rest | total | 4956 | 0.2578 | 0.2501 | +0.0077 |
| 2024 | VALIDATION | FG2_rest | moneyline | 4941 | 0.1854 | 0.1801 | +0.0053 |
| 2024 | VALIDATION | FG2_travel | spread | 4955 | 0.2586 | 0.2500 | +0.0087 |
| 2024 | VALIDATION | FG2_travel | total | 4956 | 0.2577 | 0.2501 | +0.0077 |
| 2024 | VALIDATION | FG2_travel | moneyline | 4941 | 0.1853 | 0.1801 | +0.0053 |
| 2024 | VALIDATION | FG2_neutral | spread | 4955 | 0.2589 | 0.2500 | +0.0089 |
| 2024 | VALIDATION | FG2_neutral | total | 4956 | 0.2575 | 0.2501 | +0.0074 |
| 2024 | VALIDATION | FG2_neutral | moneyline | 4941 | 0.1854 | 0.1801 | +0.0053 |
| 2024 | VALIDATION | FG2_early | spread | 4955 | 0.2588 | 0.2500 | +0.0088 |
| 2024 | VALIDATION | FG2_early | total | 4956 | 0.2579 | 0.2501 | +0.0078 |
| 2024 | VALIDATION | FG2_early | moneyline | 4941 | 0.1854 | 0.1801 | +0.0053 |
| 2024 | VALIDATION | FG2_ctx | spread | 4955 | 0.2582 | 0.2500 | +0.0083 |
| 2024 | VALIDATION | FG2_ctx | total | 4956 | 0.2578 | 0.2501 | +0.0077 |
| 2024 | VALIDATION | FG2_ctx | moneyline | 4941 | 0.1851 | 0.1801 | +0.0051 |
| 2024 | VALIDATION | FG2C_longshot | spread | 4955 | 0.2582 | 0.2500 | +0.0082 |
| 2024 | VALIDATION | FG2C_longshot | total | 4956 | 0.2573 | 0.2501 | +0.0072 |
| 2024 | VALIDATION | FG2C_longshot | moneyline | 4941 | 0.1852 | 0.1801 | +0.0052 |
| 2024 | VALIDATION | FG2C_favbump | spread | 4955 | 0.2582 | 0.2500 | +0.0082 |
| 2024 | VALIDATION | FG2C_favbump | total | 4956 | 0.2573 | 0.2501 | +0.0072 |
| 2024 | VALIDATION | FG2C_favbump | moneyline | 4941 | 0.1852 | 0.1801 | +0.0051 |
| 2024 | VALIDATION | FG2C_longshot_favbump | spread | 4955 | 0.2582 | 0.2500 | +0.0082 |
| 2024 | VALIDATION | FG2C_longshot_favbump | total | 4956 | 0.2573 | 0.2501 | +0.0072 |
| 2024 | VALIDATION | FG2C_longshot_favbump | moneyline | 4941 | 0.1853 | 0.1801 | +0.0052 |
| 2024 | VALIDATION | FG1C | spread | 4955 | 0.2588 | 0.2500 | +0.0088 |
| 2024 | VALIDATION | FG1C | total | 4956 | 0.2574 | 0.2501 | +0.0073 |
| 2024 | VALIDATION | FG1C | moneyline | 4941 | 0.1855 | 0.1801 | +0.0054 |
| 2025 | VALIDATION | FG1 | spread | 5643 | 0.2596 | 0.2499 | +0.0098 |
| 2025 | VALIDATION | FG1 | total | 5644 | 0.2584 | 0.2499 | +0.0085 |
| 2025 | VALIDATION | FG1 | moneyline | 5534 | 0.1835 | 0.1784 | +0.0051 |
| 2025 | VALIDATION | FG2 | spread | 5643 | 0.2593 | 0.2499 | +0.0095 |
| 2025 | VALIDATION | FG2 | total | 5644 | 0.2580 | 0.2499 | +0.0081 |
| 2025 | VALIDATION | FG2 | moneyline | 5534 | 0.1831 | 0.1784 | +0.0047 |
| 2025 | VALIDATION | FG2C | spread | 5643 | 0.2593 | 0.2499 | +0.0094 |
| 2025 | VALIDATION | FG2C | total | 5644 | 0.2572 | 0.2499 | +0.0073 |
| 2025 | VALIDATION | FG2C | moneyline | 5534 | 0.1831 | 0.1784 | +0.0047 |
| 2025 | VALIDATION | FG2_rest | spread | 5643 | 0.2594 | 0.2499 | +0.0095 |
| 2025 | VALIDATION | FG2_rest | total | 5644 | 0.2582 | 0.2499 | +0.0083 |
| 2025 | VALIDATION | FG2_rest | moneyline | 5534 | 0.1831 | 0.1784 | +0.0047 |
| 2025 | VALIDATION | FG2_travel | spread | 5643 | 0.2596 | 0.2499 | +0.0097 |
| 2025 | VALIDATION | FG2_travel | total | 5644 | 0.2584 | 0.2499 | +0.0085 |
| 2025 | VALIDATION | FG2_travel | moneyline | 5534 | 0.1834 | 0.1784 | +0.0050 |
| 2025 | VALIDATION | FG2_neutral | spread | 5643 | 0.2598 | 0.2499 | +0.0099 |
| 2025 | VALIDATION | FG2_neutral | total | 5644 | 0.2581 | 0.2499 | +0.0082 |
| 2025 | VALIDATION | FG2_neutral | moneyline | 5534 | 0.1836 | 0.1784 | +0.0052 |
| 2025 | VALIDATION | FG2_early | spread | 5643 | 0.2596 | 0.2499 | +0.0098 |
| 2025 | VALIDATION | FG2_early | total | 5644 | 0.2584 | 0.2499 | +0.0085 |
| 2025 | VALIDATION | FG2_early | moneyline | 5534 | 0.1835 | 0.1784 | +0.0051 |
| 2025 | VALIDATION | FG2_ctx | spread | 5643 | 0.2593 | 0.2499 | +0.0095 |
| 2025 | VALIDATION | FG2_ctx | total | 5644 | 0.2580 | 0.2499 | +0.0081 |
| 2025 | VALIDATION | FG2_ctx | moneyline | 5534 | 0.1831 | 0.1784 | +0.0047 |
| 2025 | VALIDATION | FG2C_longshot | spread | 5643 | 0.2593 | 0.2499 | +0.0094 |
| 2025 | VALIDATION | FG2C_longshot | total | 5644 | 0.2572 | 0.2499 | +0.0073 |
| 2025 | VALIDATION | FG2C_longshot | moneyline | 5534 | 0.1833 | 0.1784 | +0.0049 |
| 2025 | VALIDATION | FG2C_favbump | spread | 5643 | 0.2593 | 0.2499 | +0.0094 |
| 2025 | VALIDATION | FG2C_favbump | total | 5644 | 0.2572 | 0.2499 | +0.0073 |
| 2025 | VALIDATION | FG2C_favbump | moneyline | 5534 | 0.1832 | 0.1784 | +0.0048 |
| 2025 | VALIDATION | FG2C_longshot_favbump | spread | 5643 | 0.2593 | 0.2499 | +0.0094 |
| 2025 | VALIDATION | FG2C_longshot_favbump | total | 5644 | 0.2572 | 0.2499 | +0.0073 |
| 2025 | VALIDATION | FG2C_longshot_favbump | moneyline | 5534 | 0.1834 | 0.1784 | +0.0050 |
| 2025 | VALIDATION | FG1C | spread | 5643 | 0.2596 | 0.2499 | +0.0098 |
| 2025 | VALIDATION | FG1C | total | 5644 | 0.2576 | 0.2499 | +0.0078 |
| 2025 | VALIDATION | FG1C | moneyline | 5534 | 0.1835 | 0.1784 | +0.0051 |
| 2026 | CONFIRMATORY_REUSE | FG1 | spread | 5574 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG1 | total | 5591 | 0.2611 | 0.2500 | +0.0111 |
| 2026 | CONFIRMATORY_REUSE | FG1 | moneyline | 5399 | 0.1870 | 0.1802 | +0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2 | spread | 5574 | 0.2598 | 0.2500 | +0.0098 |
| 2026 | CONFIRMATORY_REUSE | FG2 | total | 5591 | 0.2606 | 0.2500 | +0.0106 |
| 2026 | CONFIRMATORY_REUSE | FG2 | moneyline | 5399 | 0.1872 | 0.1802 | +0.0070 |
| 2026 | CONFIRMATORY_REUSE | FG2C | spread | 5574 | 0.2597 | 0.2500 | +0.0097 |
| 2026 | CONFIRMATORY_REUSE | FG2C | total | 5591 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG2C | moneyline | 5399 | 0.1873 | 0.1802 | +0.0071 |
| 2026 | CONFIRMATORY_REUSE | FG2_rest | spread | 5574 | 0.2598 | 0.2500 | +0.0098 |
| 2026 | CONFIRMATORY_REUSE | FG2_rest | total | 5591 | 0.2609 | 0.2500 | +0.0109 |
| 2026 | CONFIRMATORY_REUSE | FG2_rest | moneyline | 5399 | 0.1872 | 0.1802 | +0.0070 |
| 2026 | CONFIRMATORY_REUSE | FG2_travel | spread | 5574 | 0.2595 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG2_travel | total | 5591 | 0.2608 | 0.2500 | +0.0108 |
| 2026 | CONFIRMATORY_REUSE | FG2_travel | moneyline | 5399 | 0.1870 | 0.1802 | +0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_neutral | spread | 5574 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG2_neutral | total | 5591 | 0.2607 | 0.2500 | +0.0107 |
| 2026 | CONFIRMATORY_REUSE | FG2_neutral | moneyline | 5399 | 0.1870 | 0.1802 | +0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_early | spread | 5574 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG2_early | total | 5591 | 0.2611 | 0.2500 | +0.0111 |
| 2026 | CONFIRMATORY_REUSE | FG2_early | moneyline | 5399 | 0.1870 | 0.1802 | +0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_ctx | spread | 5574 | 0.2598 | 0.2500 | +0.0098 |
| 2026 | CONFIRMATORY_REUSE | FG2_ctx | total | 5591 | 0.2606 | 0.2500 | +0.0106 |
| 2026 | CONFIRMATORY_REUSE | FG2_ctx | moneyline | 5399 | 0.1872 | 0.1802 | +0.0070 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot | spread | 5574 | 0.2597 | 0.2500 | +0.0097 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot | total | 5591 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot | moneyline | 5399 | 0.1875 | 0.1802 | +0.0073 |
| 2026 | CONFIRMATORY_REUSE | FG2C_favbump | spread | 5574 | 0.2597 | 0.2500 | +0.0097 |
| 2026 | CONFIRMATORY_REUSE | FG2C_favbump | total | 5591 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG2C_favbump | moneyline | 5399 | 0.1871 | 0.1802 | +0.0069 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | spread | 5574 | 0.2597 | 0.2500 | +0.0097 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | total | 5591 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | moneyline | 5399 | 0.1874 | 0.1802 | +0.0072 |
| 2026 | CONFIRMATORY_REUSE | FG1C | spread | 5574 | 0.2596 | 0.2500 | +0.0096 |
| 2026 | CONFIRMATORY_REUSE | FG1C | total | 5591 | 0.2602 | 0.2500 | +0.0102 |
| 2026 | CONFIRMATORY_REUSE | FG1C | moneyline | 5399 | 0.1871 | 0.1802 | +0.0069 |
| 2027 | CONFIRMATORY_REUSE | FG1 | spread | 1049 | 0.2812 | 0.2497 | +0.0315 |
| 2027 | CONFIRMATORY_REUSE | FG1 | total | 1049 | 0.2624 | 0.2498 | +0.0125 |
| 2027 | CONFIRMATORY_REUSE | FG1 | moneyline | 967 | 0.1678 | 0.1544 | +0.0134 |
| 2027 | CONFIRMATORY_REUSE | FG2 | spread | 1049 | 0.2801 | 0.2497 | +0.0304 |
| 2027 | CONFIRMATORY_REUSE | FG2 | total | 1049 | 0.2633 | 0.2498 | +0.0134 |
| 2027 | CONFIRMATORY_REUSE | FG2 | moneyline | 967 | 0.1671 | 0.1544 | +0.0127 |
| 2027 | CONFIRMATORY_REUSE | FG2C | spread | 1049 | 0.2795 | 0.2497 | +0.0298 |
| 2027 | CONFIRMATORY_REUSE | FG2C | total | 1049 | 0.2605 | 0.2498 | +0.0107 |
| 2027 | CONFIRMATORY_REUSE | FG2C | moneyline | 967 | 0.1674 | 0.1544 | +0.0130 |
| 2027 | CONFIRMATORY_REUSE | FG2_rest | spread | 1049 | 0.2803 | 0.2497 | +0.0306 |
| 2027 | CONFIRMATORY_REUSE | FG2_rest | total | 1049 | 0.2626 | 0.2498 | +0.0127 |
| 2027 | CONFIRMATORY_REUSE | FG2_rest | moneyline | 967 | 0.1673 | 0.1544 | +0.0129 |
| 2027 | CONFIRMATORY_REUSE | FG2_travel | spread | 1049 | 0.2808 | 0.2497 | +0.0311 |
| 2027 | CONFIRMATORY_REUSE | FG2_travel | total | 1049 | 0.2636 | 0.2498 | +0.0137 |
| 2027 | CONFIRMATORY_REUSE | FG2_travel | moneyline | 967 | 0.1675 | 0.1544 | +0.0131 |
| 2027 | CONFIRMATORY_REUSE | FG2_neutral | spread | 1049 | 0.2811 | 0.2497 | +0.0314 |
| 2027 | CONFIRMATORY_REUSE | FG2_neutral | total | 1049 | 0.2634 | 0.2498 | +0.0136 |
| 2027 | CONFIRMATORY_REUSE | FG2_neutral | moneyline | 967 | 0.1678 | 0.1544 | +0.0134 |
| 2027 | CONFIRMATORY_REUSE | FG2_early | spread | 1049 | 0.2812 | 0.2497 | +0.0315 |
| 2027 | CONFIRMATORY_REUSE | FG2_early | total | 1049 | 0.2624 | 0.2498 | +0.0125 |
| 2027 | CONFIRMATORY_REUSE | FG2_early | moneyline | 967 | 0.1678 | 0.1544 | +0.0134 |
| 2027 | CONFIRMATORY_REUSE | FG2_ctx | spread | 1049 | 0.2801 | 0.2497 | +0.0304 |
| 2027 | CONFIRMATORY_REUSE | FG2_ctx | total | 1049 | 0.2633 | 0.2498 | +0.0134 |
| 2027 | CONFIRMATORY_REUSE | FG2_ctx | moneyline | 967 | 0.1671 | 0.1544 | +0.0127 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot | spread | 1049 | 0.2795 | 0.2497 | +0.0298 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot | total | 1049 | 0.2605 | 0.2498 | +0.0107 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot | moneyline | 967 | 0.1678 | 0.1544 | +0.0134 |
| 2027 | CONFIRMATORY_REUSE | FG2C_favbump | spread | 1049 | 0.2795 | 0.2497 | +0.0298 |
| 2027 | CONFIRMATORY_REUSE | FG2C_favbump | total | 1049 | 0.2605 | 0.2498 | +0.0107 |
| 2027 | CONFIRMATORY_REUSE | FG2C_favbump | moneyline | 967 | 0.1670 | 0.1544 | +0.0126 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | spread | 1049 | 0.2795 | 0.2497 | +0.0298 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | total | 1049 | 0.2605 | 0.2498 | +0.0107 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | moneyline | 967 | 0.1675 | 0.1544 | +0.0131 |
| 2027 | CONFIRMATORY_REUSE | FG1C | spread | 1049 | 0.2804 | 0.2497 | +0.0307 |
| 2027 | CONFIRMATORY_REUSE | FG1C | total | 1049 | 0.2599 | 0.2498 | +0.0101 |
| 2027 | CONFIRMATORY_REUSE | FG1C | moneyline | 967 | 0.1682 | 0.1544 | +0.0138 |

## Side bias (model p − realised rate) at market lines (auxiliary)

| season | split | engine | side | n | model p | rate | bias | SE |
|---|---|---|---|---:|---:|---:|---:|---:|
| 2023 | VALIDATION | FG1 | ML favourite | 5371 | 0.7088 | 0.7300 | -0.0212 | 0.0059 |
| 2023 | VALIDATION | FG1 | over | 23 | 0.7650 | 0.7391 | +0.0258 | 0.0799 |
| 2023 | VALIDATION | FG1 | spread favourite | 2 | 0.6295 | 0.0000 | +0.6295 | 0.0578 |
| 2023 | VALIDATION | FG2 | ML favourite | 5371 | 0.7097 | 0.7300 | -0.0203 | 0.0059 |
| 2023 | VALIDATION | FG2 | over | 23 | 0.7660 | 0.7391 | +0.0269 | 0.0804 |
| 2023 | VALIDATION | FG2 | spread favourite | 2 | 0.5918 | 0.0000 | +0.5918 | 0.0440 |
| 2023 | VALIDATION | FG2C | ML favourite | 5371 | 0.7081 | 0.7300 | -0.0220 | 0.0059 |
| 2023 | VALIDATION | FG2C | over | 23 | 0.7672 | 0.7391 | +0.0281 | 0.0808 |
| 2023 | VALIDATION | FG2C | spread favourite | 2 | 0.5789 | 0.0000 | +0.5789 | 0.0496 |
| 2023 | VALIDATION | FG2_rest | ML favourite | 5371 | 0.7096 | 0.7300 | -0.0204 | 0.0059 |
| 2023 | VALIDATION | FG2_rest | over | 23 | 0.7667 | 0.7391 | +0.0276 | 0.0798 |
| 2023 | VALIDATION | FG2_rest | spread favourite | 2 | 0.6190 | 0.0000 | +0.6190 | 0.0409 |
| 2023 | VALIDATION | FG2_travel | ML favourite | 5371 | 0.7089 | 0.7300 | -0.0212 | 0.0059 |
| 2023 | VALIDATION | FG2_travel | over | 23 | 0.7659 | 0.7391 | +0.0268 | 0.0805 |
| 2023 | VALIDATION | FG2_travel | spread favourite | 2 | 0.6068 | 0.0000 | +0.6068 | 0.0587 |
| 2023 | VALIDATION | FG2_neutral | ML favourite | 5371 | 0.7087 | 0.7300 | -0.0213 | 0.0059 |
| 2023 | VALIDATION | FG2_neutral | over | 23 | 0.7641 | 0.7391 | +0.0250 | 0.0809 |
| 2023 | VALIDATION | FG2_neutral | spread favourite | 2 | 0.6240 | 0.0000 | +0.6240 | 0.0545 |
| 2023 | VALIDATION | FG2_early | ML favourite | 5371 | 0.7088 | 0.7300 | -0.0212 | 0.0059 |
| 2023 | VALIDATION | FG2_early | over | 23 | 0.7650 | 0.7391 | +0.0258 | 0.0799 |
| 2023 | VALIDATION | FG2_early | spread favourite | 2 | 0.6295 | 0.0000 | +0.6295 | 0.0578 |
| 2023 | VALIDATION | FG2_ctx | ML favourite | 5371 | 0.7097 | 0.7300 | -0.0203 | 0.0059 |
| 2023 | VALIDATION | FG2_ctx | over | 23 | 0.7660 | 0.7391 | +0.0269 | 0.0804 |
| 2023 | VALIDATION | FG2_ctx | spread favourite | 2 | 0.5918 | 0.0000 | +0.5918 | 0.0440 |
| 2023 | VALIDATION | FG2C_longshot | ML favourite | 5371 | 0.7062 | 0.7300 | -0.0238 | 0.0059 |
| 2023 | VALIDATION | FG2C_longshot | over | 23 | 0.7672 | 0.7391 | +0.0281 | 0.0808 |
| 2023 | VALIDATION | FG2C_longshot | spread favourite | 2 | 0.5789 | 0.0000 | +0.5789 | 0.0496 |
| 2023 | VALIDATION | FG2C_favbump | ML favourite | 5371 | 0.7018 | 0.7300 | -0.0282 | 0.0059 |
| 2023 | VALIDATION | FG2C_favbump | over | 23 | 0.7672 | 0.7391 | +0.0281 | 0.0808 |
| 2023 | VALIDATION | FG2C_favbump | spread favourite | 2 | 0.5789 | 0.0000 | +0.5789 | 0.0496 |
| 2023 | VALIDATION | FG2C_longshot_favbump | ML favourite | 5371 | 0.6999 | 0.7300 | -0.0301 | 0.0059 |
| 2023 | VALIDATION | FG2C_longshot_favbump | over | 23 | 0.7672 | 0.7391 | +0.0281 | 0.0808 |
| 2023 | VALIDATION | FG2C_longshot_favbump | spread favourite | 2 | 0.5789 | 0.0000 | +0.5789 | 0.0496 |
| 2023 | VALIDATION | FG1C | ML favourite | 5371 | 0.7075 | 0.7300 | -0.0226 | 0.0059 |
| 2023 | VALIDATION | FG1C | over | 23 | 0.7662 | 0.7391 | +0.0270 | 0.0803 |
| 2023 | VALIDATION | FG1C | spread favourite | 2 | 0.6190 | 0.0000 | +0.6190 | 0.0601 |
| 2024 | VALIDATION | FG1 | ML favourite | 4941 | 0.7110 | 0.7262 | -0.0152 | 0.0061 |
| 2024 | VALIDATION | FG1 | over | 4956 | 0.5209 | 0.5077 | +0.0132 | 0.0072 |
| 2024 | VALIDATION | FG1 | spread favourite | 4955 | 0.5078 | 0.4991 | +0.0087 | 0.0072 |
| 2024 | VALIDATION | FG2 | ML favourite | 4941 | 0.7118 | 0.7262 | -0.0143 | 0.0061 |
| 2024 | VALIDATION | FG2 | over | 4956 | 0.5222 | 0.5077 | +0.0145 | 0.0072 |
| 2024 | VALIDATION | FG2 | spread favourite | 4955 | 0.5082 | 0.4991 | +0.0091 | 0.0072 |
| 2024 | VALIDATION | FG2C | ML favourite | 4941 | 0.7113 | 0.7262 | -0.0149 | 0.0061 |
| 2024 | VALIDATION | FG2C | over | 4956 | 0.5145 | 0.5077 | +0.0068 | 0.0072 |
| 2024 | VALIDATION | FG2C | spread favourite | 4955 | 0.5107 | 0.4991 | +0.0117 | 0.0072 |
| 2024 | VALIDATION | FG2_rest | ML favourite | 4941 | 0.7116 | 0.7262 | -0.0145 | 0.0061 |
| 2024 | VALIDATION | FG2_rest | over | 4956 | 0.5219 | 0.5077 | +0.0142 | 0.0072 |
| 2024 | VALIDATION | FG2_rest | spread favourite | 4955 | 0.5079 | 0.4991 | +0.0088 | 0.0072 |
| 2024 | VALIDATION | FG2_travel | ML favourite | 4941 | 0.7111 | 0.7262 | -0.0151 | 0.0061 |
| 2024 | VALIDATION | FG2_travel | over | 4956 | 0.5220 | 0.5077 | +0.0144 | 0.0072 |
| 2024 | VALIDATION | FG2_travel | spread favourite | 4955 | 0.5081 | 0.4991 | +0.0090 | 0.0072 |
| 2024 | VALIDATION | FG2_neutral | ML favourite | 4941 | 0.7109 | 0.7262 | -0.0152 | 0.0061 |
| 2024 | VALIDATION | FG2_neutral | over | 4956 | 0.5205 | 0.5077 | +0.0129 | 0.0072 |
| 2024 | VALIDATION | FG2_neutral | spread favourite | 4955 | 0.5078 | 0.4991 | +0.0087 | 0.0072 |
| 2024 | VALIDATION | FG2_early | ML favourite | 4941 | 0.7110 | 0.7262 | -0.0152 | 0.0061 |
| 2024 | VALIDATION | FG2_early | over | 4956 | 0.5209 | 0.5077 | +0.0132 | 0.0072 |
| 2024 | VALIDATION | FG2_early | spread favourite | 4955 | 0.5078 | 0.4991 | +0.0087 | 0.0072 |
| 2024 | VALIDATION | FG2_ctx | ML favourite | 4941 | 0.7118 | 0.7262 | -0.0143 | 0.0061 |
| 2024 | VALIDATION | FG2_ctx | over | 4956 | 0.5222 | 0.5077 | +0.0145 | 0.0072 |
| 2024 | VALIDATION | FG2_ctx | spread favourite | 4955 | 0.5082 | 0.4991 | +0.0091 | 0.0072 |
| 2024 | VALIDATION | FG2C_longshot | ML favourite | 4941 | 0.7089 | 0.7262 | -0.0172 | 0.0061 |
| 2024 | VALIDATION | FG2C_longshot | over | 4956 | 0.5145 | 0.5077 | +0.0068 | 0.0072 |
| 2024 | VALIDATION | FG2C_longshot | spread favourite | 4955 | 0.5107 | 0.4991 | +0.0117 | 0.0072 |
| 2024 | VALIDATION | FG2C_favbump | ML favourite | 4941 | 0.7051 | 0.7262 | -0.0210 | 0.0061 |
| 2024 | VALIDATION | FG2C_favbump | over | 4956 | 0.5145 | 0.5077 | +0.0068 | 0.0072 |
| 2024 | VALIDATION | FG2C_favbump | spread favourite | 4955 | 0.5107 | 0.4991 | +0.0117 | 0.0072 |
| 2024 | VALIDATION | FG2C_longshot_favbump | ML favourite | 4941 | 0.7028 | 0.7262 | -0.0234 | 0.0061 |
| 2024 | VALIDATION | FG2C_longshot_favbump | over | 4956 | 0.5145 | 0.5077 | +0.0068 | 0.0072 |
| 2024 | VALIDATION | FG2C_longshot_favbump | spread favourite | 4955 | 0.5107 | 0.4991 | +0.0117 | 0.0072 |
| 2024 | VALIDATION | FG1C | ML favourite | 4941 | 0.7112 | 0.7262 | -0.0150 | 0.0061 |
| 2024 | VALIDATION | FG1C | over | 4956 | 0.5136 | 0.5077 | +0.0060 | 0.0072 |
| 2024 | VALIDATION | FG1C | spread favourite | 4955 | 0.5106 | 0.4991 | +0.0115 | 0.0072 |
| 2025 | VALIDATION | FG1 | ML favourite | 5534 | 0.7034 | 0.7250 | -0.0216 | 0.0058 |
| 2025 | VALIDATION | FG1 | over | 5644 | 0.5241 | 0.4986 | +0.0255 | 0.0068 |
| 2025 | VALIDATION | FG1 | spread favourite | 5643 | 0.5047 | 0.5127 | -0.0080 | 0.0068 |
| 2025 | VALIDATION | FG2 | ML favourite | 5534 | 0.7051 | 0.7250 | -0.0199 | 0.0057 |
| 2025 | VALIDATION | FG2 | over | 5644 | 0.5255 | 0.4986 | +0.0269 | 0.0068 |
| 2025 | VALIDATION | FG2 | spread favourite | 5643 | 0.5050 | 0.5127 | -0.0076 | 0.0068 |
| 2025 | VALIDATION | FG2C | ML favourite | 5534 | 0.7038 | 0.7250 | -0.0211 | 0.0057 |
| 2025 | VALIDATION | FG2C | over | 5644 | 0.5208 | 0.4986 | +0.0222 | 0.0067 |
| 2025 | VALIDATION | FG2C | spread favourite | 5643 | 0.5065 | 0.5127 | -0.0062 | 0.0068 |
| 2025 | VALIDATION | FG2_rest | ML favourite | 5534 | 0.7046 | 0.7250 | -0.0204 | 0.0057 |
| 2025 | VALIDATION | FG2_rest | over | 5644 | 0.5246 | 0.4986 | +0.0261 | 0.0068 |
| 2025 | VALIDATION | FG2_rest | spread favourite | 5643 | 0.5050 | 0.5127 | -0.0077 | 0.0068 |
| 2025 | VALIDATION | FG2_travel | ML favourite | 5534 | 0.7038 | 0.7250 | -0.0212 | 0.0058 |
| 2025 | VALIDATION | FG2_travel | over | 5644 | 0.5256 | 0.4986 | +0.0270 | 0.0068 |
| 2025 | VALIDATION | FG2_travel | spread favourite | 5643 | 0.5047 | 0.5127 | -0.0079 | 0.0068 |
| 2025 | VALIDATION | FG2_neutral | ML favourite | 5534 | 0.7034 | 0.7250 | -0.0216 | 0.0058 |
| 2025 | VALIDATION | FG2_neutral | over | 5644 | 0.5239 | 0.4986 | +0.0253 | 0.0068 |
| 2025 | VALIDATION | FG2_neutral | spread favourite | 5643 | 0.5047 | 0.5127 | -0.0080 | 0.0068 |
| 2025 | VALIDATION | FG2_early | ML favourite | 5534 | 0.7034 | 0.7250 | -0.0216 | 0.0058 |
| 2025 | VALIDATION | FG2_early | over | 5644 | 0.5241 | 0.4986 | +0.0255 | 0.0068 |
| 2025 | VALIDATION | FG2_early | spread favourite | 5643 | 0.5047 | 0.5127 | -0.0080 | 0.0068 |
| 2025 | VALIDATION | FG2_ctx | ML favourite | 5534 | 0.7051 | 0.7250 | -0.0199 | 0.0057 |
| 2025 | VALIDATION | FG2_ctx | over | 5644 | 0.5255 | 0.4986 | +0.0269 | 0.0068 |
| 2025 | VALIDATION | FG2_ctx | spread favourite | 5643 | 0.5050 | 0.5127 | -0.0076 | 0.0068 |
| 2025 | VALIDATION | FG2C_longshot | ML favourite | 5534 | 0.7015 | 0.7250 | -0.0235 | 0.0057 |
| 2025 | VALIDATION | FG2C_longshot | over | 5644 | 0.5208 | 0.4986 | +0.0222 | 0.0067 |
| 2025 | VALIDATION | FG2C_longshot | spread favourite | 5643 | 0.5065 | 0.5127 | -0.0062 | 0.0068 |
| 2025 | VALIDATION | FG2C_favbump | ML favourite | 5534 | 0.6978 | 0.7250 | -0.0272 | 0.0057 |
| 2025 | VALIDATION | FG2C_favbump | over | 5644 | 0.5208 | 0.4986 | +0.0222 | 0.0067 |
| 2025 | VALIDATION | FG2C_favbump | spread favourite | 5643 | 0.5065 | 0.5127 | -0.0062 | 0.0068 |
| 2025 | VALIDATION | FG2C_longshot_favbump | ML favourite | 5534 | 0.6955 | 0.7250 | -0.0295 | 0.0057 |
| 2025 | VALIDATION | FG2C_longshot_favbump | over | 5644 | 0.5208 | 0.4986 | +0.0222 | 0.0067 |
| 2025 | VALIDATION | FG2C_longshot_favbump | spread favourite | 5643 | 0.5065 | 0.5127 | -0.0062 | 0.0068 |
| 2025 | VALIDATION | FG1C | ML favourite | 5534 | 0.7027 | 0.7250 | -0.0223 | 0.0058 |
| 2025 | VALIDATION | FG1C | over | 5644 | 0.5203 | 0.4986 | +0.0217 | 0.0068 |
| 2025 | VALIDATION | FG1C | spread favourite | 5643 | 0.5064 | 0.5127 | -0.0063 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG1 | ML favourite | 5399 | 0.7088 | 0.7187 | -0.0099 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG1 | over | 5591 | 0.5305 | 0.4899 | +0.0406 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG1 | spread favourite | 5574 | 0.5074 | 0.4980 | +0.0094 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2 | ML favourite | 5399 | 0.7097 | 0.7187 | -0.0090 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2 | over | 5591 | 0.5317 | 0.4899 | +0.0418 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2 | spread favourite | 5574 | 0.5077 | 0.4980 | +0.0097 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C | ML favourite | 5399 | 0.7091 | 0.7187 | -0.0095 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2C | over | 5591 | 0.5166 | 0.4899 | +0.0267 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C | spread favourite | 5574 | 0.5089 | 0.4980 | +0.0108 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_rest | ML favourite | 5399 | 0.7095 | 0.7187 | -0.0091 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2_rest | over | 5591 | 0.5313 | 0.4899 | +0.0414 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_rest | spread favourite | 5574 | 0.5077 | 0.4980 | +0.0096 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_travel | ML favourite | 5399 | 0.7089 | 0.7187 | -0.0098 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2_travel | over | 5591 | 0.5320 | 0.4899 | +0.0421 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_travel | spread favourite | 5574 | 0.5076 | 0.4980 | +0.0096 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_neutral | ML favourite | 5399 | 0.7087 | 0.7187 | -0.0100 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2_neutral | over | 5591 | 0.5308 | 0.4899 | +0.0409 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_neutral | spread favourite | 5574 | 0.5075 | 0.4980 | +0.0094 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_early | ML favourite | 5399 | 0.7088 | 0.7187 | -0.0099 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2_early | over | 5591 | 0.5305 | 0.4899 | +0.0406 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_early | spread favourite | 5574 | 0.5074 | 0.4980 | +0.0094 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_ctx | ML favourite | 5399 | 0.7097 | 0.7187 | -0.0090 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2_ctx | over | 5591 | 0.5317 | 0.4899 | +0.0418 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2_ctx | spread favourite | 5574 | 0.5077 | 0.4980 | +0.0097 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot | ML favourite | 5399 | 0.7066 | 0.7187 | -0.0121 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot | over | 5591 | 0.5166 | 0.4899 | +0.0267 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot | spread favourite | 5574 | 0.5089 | 0.4980 | +0.0108 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C_favbump | ML favourite | 5399 | 0.7030 | 0.7187 | -0.0156 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2C_favbump | over | 5591 | 0.5166 | 0.4899 | +0.0267 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C_favbump | spread favourite | 5574 | 0.5089 | 0.4980 | +0.0108 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | ML favourite | 5399 | 0.7004 | 0.7187 | -0.0182 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | over | 5591 | 0.5166 | 0.4899 | +0.0267 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | spread favourite | 5574 | 0.5089 | 0.4980 | +0.0108 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG1C | ML favourite | 5399 | 0.7089 | 0.7187 | -0.0097 | 0.0059 |
| 2026 | CONFIRMATORY_REUSE | FG1C | over | 5591 | 0.5162 | 0.4899 | +0.0263 | 0.0068 |
| 2026 | CONFIRMATORY_REUSE | FG1C | spread favourite | 5574 | 0.5088 | 0.4980 | +0.0107 | 0.0068 |
| 2027 | CONFIRMATORY_REUSE | FG1 | ML favourite | 967 | 0.7508 | 0.7363 | +0.0145 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG1 | over | 1049 | 0.4725 | 0.4938 | -0.0213 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG1 | spread favourite | 1049 | 0.5015 | 0.5148 | -0.0133 | 0.0164 |
| 2027 | CONFIRMATORY_REUSE | FG2 | ML favourite | 967 | 0.7521 | 0.7363 | +0.0158 | 0.0131 |
| 2027 | CONFIRMATORY_REUSE | FG2 | over | 1049 | 0.4747 | 0.4938 | -0.0191 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2 | spread favourite | 1049 | 0.5014 | 0.5148 | -0.0134 | 0.0163 |
| 2027 | CONFIRMATORY_REUSE | FG2C | ML favourite | 967 | 0.7544 | 0.7363 | +0.0181 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG2C | over | 1049 | 0.4708 | 0.4938 | -0.0230 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2C | spread favourite | 1049 | 0.5028 | 0.5148 | -0.0120 | 0.0163 |
| 2027 | CONFIRMATORY_REUSE | FG2_rest | ML favourite | 967 | 0.7514 | 0.7363 | +0.0151 | 0.0131 |
| 2027 | CONFIRMATORY_REUSE | FG2_rest | over | 1049 | 0.4745 | 0.4938 | -0.0193 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2_rest | spread favourite | 1049 | 0.5016 | 0.5148 | -0.0132 | 0.0163 |
| 2027 | CONFIRMATORY_REUSE | FG2_travel | ML favourite | 967 | 0.7513 | 0.7363 | +0.0151 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG2_travel | over | 1049 | 0.4721 | 0.4938 | -0.0217 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2_travel | spread favourite | 1049 | 0.5011 | 0.5148 | -0.0136 | 0.0164 |
| 2027 | CONFIRMATORY_REUSE | FG2_neutral | ML favourite | 967 | 0.7511 | 0.7363 | +0.0148 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG2_neutral | over | 1049 | 0.4736 | 0.4938 | -0.0202 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2_neutral | spread favourite | 1049 | 0.5015 | 0.5148 | -0.0133 | 0.0164 |
| 2027 | CONFIRMATORY_REUSE | FG2_early | ML favourite | 967 | 0.7508 | 0.7363 | +0.0145 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG2_early | over | 1049 | 0.4725 | 0.4938 | -0.0213 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2_early | spread favourite | 1049 | 0.5015 | 0.5148 | -0.0133 | 0.0164 |
| 2027 | CONFIRMATORY_REUSE | FG2_ctx | ML favourite | 967 | 0.7521 | 0.7363 | +0.0158 | 0.0131 |
| 2027 | CONFIRMATORY_REUSE | FG2_ctx | over | 1049 | 0.4747 | 0.4938 | -0.0191 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2_ctx | spread favourite | 1049 | 0.5014 | 0.5148 | -0.0134 | 0.0163 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot | ML favourite | 967 | 0.7475 | 0.7363 | +0.0112 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot | over | 1049 | 0.4708 | 0.4938 | -0.0230 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot | spread favourite | 1049 | 0.5028 | 0.5148 | -0.0120 | 0.0163 |
| 2027 | CONFIRMATORY_REUSE | FG2C_favbump | ML favourite | 967 | 0.7484 | 0.7363 | +0.0121 | 0.0131 |
| 2027 | CONFIRMATORY_REUSE | FG2C_favbump | over | 1049 | 0.4708 | 0.4938 | -0.0230 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2C_favbump | spread favourite | 1049 | 0.5028 | 0.5148 | -0.0120 | 0.0163 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | ML favourite | 967 | 0.7415 | 0.7363 | +0.0052 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | over | 1049 | 0.4708 | 0.4938 | -0.0230 | 0.0158 |
| 2027 | CONFIRMATORY_REUSE | FG2C_longshot_favbump | spread favourite | 1049 | 0.5028 | 0.5148 | -0.0120 | 0.0163 |
| 2027 | CONFIRMATORY_REUSE | FG1C | ML favourite | 967 | 0.7539 | 0.7363 | +0.0176 | 0.0132 |
| 2027 | CONFIRMATORY_REUSE | FG1C | over | 1049 | 0.4697 | 0.4938 | -0.0241 | 0.0157 |
| 2027 | CONFIRMATORY_REUSE | FG1C | spread favourite | 1049 | 0.5028 | 0.5148 | -0.0120 | 0.0164 |

## Notes

- FG1 already contains opponent-adjusted offensive and defensive efficiency and a recency-weighted preseason carry. FG2_* add frozen residual adjustments on top of FG1.
- FG2C is chronological linear de-bias of FG2 (seasons < S), the same protocol as FG1C.
- Longshot and favourite-bump maps are fit on 2020-22 model probability vs outcome only, then frozen.
- Variants that do not improve a metric are kept in the tables; nothing is cherry-picked.
