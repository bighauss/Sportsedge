# CBB Halves Settlement (PAPER / 0u)

First-half and second-half projections use period-share or joint coefficients
that are currently labelled TRAIN_ONLY / UNVALIDATED.

## Separate settlement rules
- 1H markets settle on the official first-half score only (regulation periods).
- 2H_PREGAME markets are pregame forecasts of the second half; they settle on
  the second-half score (OT excluded from the half itself).
- 2H_HALFTIME_ADJUSTED markets are in-game and are excluded from pregame RUN IT.
- Team totals and alternates for halves follow the same half boundaries.
- Push on whole lines refunds; no half-point key-number special treatment yet.

## Integration status
The shared runner (cbb_run_it_pipeline) will price 1H / 2H_PREGAME families from
the halves adapter when the `halves` flag is set. Until chronological holdout
evidence exists, all half outputs remain PAPER_0U / NON_COUNTED and stars stay
uncalibrated.

No probabilities are invented for missing quotes.
