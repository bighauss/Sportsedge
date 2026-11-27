# Chronological league scoring baselines (#431)

PAPER / 0u / NON_COUNTED. Research only; no model, weight or runner is changed.

## Question
How well do simple league-level total-score baselines predict later games, and how large is the drift of the fixed `LG_PPG = 28` (total 56) assumption in the frozen CFB model? Every prediction for a game uses only games on strictly earlier dates.

## Source provenance (PRIVATE Drive extracts, not committed)
| Sport | Upstream | Rows | Upstream full-source SHA-256 (as stated in extract) |
|---|---|---|---|
| CFB 2015-2024 | github.com/dalluram2011/cfb-scores-2002-2024 `data/processed/games_for_tableau_clean.csv` | 8570 | 4021e0c0ddc238c878bfd7c74bda7d25951675f947373717ce03dd82a096daf3 |
| NFL 2015-2025 | github.com/nflverse/nfldata `data/games.csv` | 3028 | 437aa0f8ba9bfd1ef5e2086e170800529fb0d3d39f3c7f3a96df0eb8d2c97d41 |

Both were retrieved 2026-11-22 CT through a GitHub connector and pasted into a PDF text representation; they are NOT byte-identical originals. Row counts match the extract headers. This package's own parsed-row hashes are in `results/run_metadata.csv` (they hash the parsed rows, so they are not comparable to the upstream SHA-256 values above).

## Run
```
pip install pdfplumber numpy pandas
python research/scoring_baselines/scoring_baselines.py CFB_EXTRACT.pdf NFL_EXTRACT.pdf research/scoring_baselines/results
```
The bootstrap is seeded (20261127). The PDF parse takes about two minutes.

## Evaluation design
- CFB evaluated on 2016-2024 (7,700 games), NFL on 2016-2025 (2,761 games); 2015 only seeds the baselines.
- Baselines: frozen total 56 (CFB), constant 45 (NFL, descriptive only), prior-season mean, expanding mean, rolling 1,000 games, rolling 365 days, season-to-date shrunk to the prior season (k = 300 games, CFB).
- Metrics: MAE, RMSE, signed residual (actual minus predicted), per-season signed residual, and a season-block bootstrap 95% interval for the mean signed residual (seasons are the resampling clusters, so there are only 9-10 clusters and the intervals are wide).
- No model was selected on this evaluation. Choosing a baseline from these numbers would be retrospective selection; a challenger needs untouched data.

## Headline results
- CFB: MAE differs by less than 0.08 across all baselines (14.10-14.18); RMSE about 17.9. The frozen 56 has signed residual -0.24 (95% season-block CI -1.16 to +0.78) over 2016-2024, so it is not statistically biased in aggregate, but it drifts: -1.21 (2022), -2.31 (2023), -2.04 (2024).
- CFB mean totals fell from about 57-58 (2015-2018) to 53.7-54.0 (2023-2024).
- NFL: MAE 10.98-11.07 for every baseline; prior-season, expanding and rolling baselines are unbiased within wide intervals. Non-neutral home margin 1.92 points (season-block 95% CI 1.34 to 2.42).

## Limitations
- Final scores only: no pregame features, no team-level model output, no sportsbook price. These results say nothing about betting performance or about the model's own projections.
- The CFB set includes FCS opponents and has no FBS flag, so it is not the market's FBS slate. No overtime/regulation split, no quarter or half scores, no play counts.
- Neutral-site labels are third-party and unauthenticated. NFL price columns exist in the upstream CSV but were NOT read or used; they are not authenticated point-in-time quotes.
- League-level baselines cannot isolate tempo, rating normalization, opponent adjustment or home-field effects inside the model; that needs the component decomposition and ablations still to be built.
- Upstream history may be revised; rerun after re-hashing the source.
