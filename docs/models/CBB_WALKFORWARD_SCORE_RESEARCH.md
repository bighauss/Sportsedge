# CBB frozen score walk-forward research evaluator

Status: RESEARCH ONLY — PAPER / 0u. No production v5, model weights, historical bets, or official admission changed. This is independent of PR #122 and consumes its original frozen prediction output, not historical projections reconstructed from modern ratings.

## Private input: JSON array, one object per attempted original game

Each element contains:
- prediction: ORIGINAL output from models/cbb/torvik_point_in_time_baseline.py project() with game_id, season (ending year, 2026–27=2027), exact team IDs, freeze_utc, tipoff_utc, home_points, away_points, margin_home, total, model_sha256, status=PAPER_NON_COUNTED_UNCALIBRATED, official=false, stake_u=0 and source_clock_consistent_not_authenticated manifest (home, away, league, optional hca) with sha256 and captured_utc.
- final: null if not finished; otherwise original score receipt with matching game_id, season, home_team_id, away_team_id, status=FINAL, period=FG_INCL_OT, home_score and away_score integer, published_utc after tipoff, captured_utc at/after publication, sha256. This requires the true full-game final (including OT).
- quote: null when unavailable; otherwise exact game_id and season, period=FG, book, sha256, captured_utc (before frozen model timestamp), and complete observed pairs for whichever markets were captured: spread uses home_spread, home_price and away_price; total uses total_line, over_price and under_price; moneyline uses home_ml and away_ml. All American prices integer with absolute value >=100. Quote and score sources remain separate.

Keep all blocked, pending, losing, and no-quote game rows. This module quarantines every duplicate season+game_id, even the first copy. Complete pairs are required within a supplied market. A malformed quote is withheld from market benchmarks but does NOT invalidate an otherwise frozen score forecast.

Never put provider originals, captures, credentials or private evaluation reports into the PUBLIC GitHub repository. CLI path safety resolves symlinks and rejects source/output paths inside the public repo, even from nested working directories. The report is create-only and never overwrites earlier reports. Duplicate JSON object keys and NaN/Infinity inputs fail closed.

## Run in a private workspace

From models/cbb run:

    python -m unittest -v test_point_in_time_score_walkforward.py
    python point_in_time_score_walkforward.py /private/cbb/frozen_games.json --report /private/cbb/new_score_report.json --min-prior 30 --max-quote-age-hours 24

The rolling evaluator only uses earlier score outcomes whose FINAL publication timestamp is strictly before the current prediction freeze, within the same season. A minimum of 30 earlier released outcomes is mandatory. Scores and predictive dispersions are not fitted using later game results.

## Report

- model_margin_mae and model_total_mae are descriptive forecast error on games that passed the rolling release gate, independent of market coverage.
- paired_spread compares model home-margin absolute error against the pre-freeze market home-spread-implied margin (minus the home handicap).
- paired_total compares model total-score absolute error against captured full-game total line.
- paired_ml_brier compares a research-only Normal-residual home-win probability (residual mean/SD estimated from previously released results only) with the no-vig market home-win probability from a full two-sided pre-freeze ML quote.
- improvement_market_minus_model above zero is a sample-level score improvement, NOT a betting edge, profit, or validated fair price.
- Event-level normal-approximation 95% intervals are returned only when paired n>=30. Independence assumptions must be checked separately; small clustered samples can mislead.
- One retained output row per input row, with exact input_index and BLOCKED/PENDING_FINAL/VALID_SCORE_RECEIPTS_UNAUTHENTICATED and its quotation/evaluation status. No selection rules are optimized against test outcomes.

## Important limitations and remaining gates

The input's claimed UTC publication timestamps, capture timestamps and SHA strings are NOT independent provider authentication. Before even considering performance claims, reconcile original provider response bytes/digests, allowed use, exact game/team IDs, true time-of-publication and immutable original model SHA with external source records. Fit distributional calibration only on historical training folds, reserve untouched future games, compare every eligible nonselected game, verify both book sides and market ID, separate overtimes/settlement correctly. No authentic 2015–2025 CBB history has been checked by this PR. No CLV, expected value, stakes, or auto-promotion may be emitted.

The 2027 model season corresponds to the November 2026 games; never use final-season adjusted statistics to make a November 2026 pregame forecast.