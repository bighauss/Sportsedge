# CBB point-in-time efficiency baseline (research-only, 2026-11-15)

Module: `models/cbb/torvik_point_in_time_baseline.py`
Tests: `python -m unittest -v models/cbb/test_torvik_point_in_time_baseline.py` (run from repository root only if module resolution is configured), or run from `models/cbb` with `python -m unittest -v test_torvik_point_in_time_baseline.py`.

## Purpose
An **independent candidate** alongside the existing SportsEdge CBB model, not a replacement for frozen v5 and not a bet-admission path. The baseline takes already-captured, team-ID-keyed, pregame adjusted efficiencies and tempo and computes expected scores. It does not fetch data, adjust any old picks, estimate win/cover/over probabilities, manufacture +EV, or publish stakes.

### Projected score contract
- Input `game`: `game_id`, integer ending-year `season` (2026–27 = 2027), stable `home_team_id` and `away_team_id`, Boolean `neutral`, `freeze_utc`, `tipoff_utc`, `model_sha256`.
- Input `home` and `away`: matching `team_id`, `season`, `adj_o`, `adj_d` (points/100 possessions), `adj_tempo` (possessions/40 min), plus the evidence envelope.
- Input `league`: `team_id=LEAGUE`, matching `season`, `league_adj_o`, `league_tempo`, and evidence envelope. Do not substitute an unknown season-ending league mean.
- Input `hca` for non-neutral games: home `team_id`, matching `season`, measured `home_court_points`, and evidence envelope. Neutral games require `hca=None`. No invented default HCA.
- Each evidence envelope requires `data_through_utc`, `published_utc`, `captured_utc`, and `source_sha256`; times are UTC with trailing `Z`, monotonically ordered, captured no later than the game's frozen model time, itself before tipoff.

Equations, defined for this unfitted baseline only:

```text
pace = (home_adj_tempo + away_adj_tempo) / 2
home_expected = pace * (home_adj_o * away_adj_d / league_adj_o) / 100 + HCA/2
away_expected = pace * (away_adj_o * home_adj_d / league_adj_o) / 100 - HCA/2
margin_home = home_expected - away_expected
total = home_expected + away_expected
```

The additive HCA convention is a testable modeling hypothesis, not a calibration result. The baseline deliberately omits lineup changes, four factors, travel, rest, injuries, player props, overtime, predictive uncertainty, and sportsbook comparisons. Never reuse its scores as verified betting fair lines.

## Prospective data procedure
1. Before the game, capture raw provider response bytes in a **private** directory and record original published/captured timestamps, source endpoint, provider event/team identity, digest of original bytes, and model code SHA. A SHA *string* in the manifest is not evidence that bytes were checked.
2. Take ratings from a genuine as-of historical archive or a prospectively frozen current snapshot. Do not read today's ratings and relabel them as a past day's ratings. An archived calendar date by itself does not prove the publication hour.
3. Convert only observed, nonmissing values into the contract. Preserve game IDs and team-ID mapping; separate aliases explicitly and quarantine uncertain joins. Use the actual season-ending year.
4. Call `research_board(records, max_age_hours=PRE_REGISTERED_LIMIT)` to retain every input index, including a BLOCKED reason for missing, future, stale, and duplicate input. Do not silently skip losing games.
5. Store this output separately from later actual results. After results are known, use untouched chronological evaluation folds; report score MAE/RMSE, residual bias by venue/tempo/conference, calibration only if distributions are fitted, and market-only comparisons only when original two-sided quotes exist.
6. Register dispersions, game-type HCA, shrinkage, injury and lineup adjustments, market-blend weights, season fold boundaries, evaluation date and sample floors **before** running the final holdout. Promote none automatically.

## Source reality check
- Torvik archived daily ratings are available through the `toRvik` `bart_archive` function and its successor `cbbdata` archive; verify source access rights and actual publication times before treating any historical row as point-in-time authentic.
- CollegeBasketballData provides a free monthly API call allowance; some advanced features require a paid tier. API response structure and quotas must be confirmed against current documentation.
- The user's example `from pybart import Torvik; Torvik().team_ratings(...)` is illustrative, **not** a verified callable interface. Use a documented loader and validate its columns rather than trusting that snippet.
- No claim of 65–72% favorite accuracy or a positive betting ROI is made. Winner accuracy depends heavily on favorite mix, and positive EV requires verified prices, calibrated distributions and correct settlement rules.

## Test and release boundaries
`python -m unittest -v test_torvik_point_in_time_baseline.py` from `models/cbb` performs synthetic-only checks. CI includes the suite. It has no network calls or provider credentials. The existing `sportsedge_cbb_model.py`, its coefficients, original historical input/output artifacts, and engine v5 remain unchanged. Status is always `PAPER_NON_COUNTED_UNCALIBRATED` or `BLOCKED`; `stake_u=0`.