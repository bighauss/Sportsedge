# NFL forecast scorecard (research only)

Scores every forecaster on the **same games at the same pregame cutoff**:

- the existing ridge walk-forward model (`score_walkforward_pit.py` output, exported to a predictions CSV)
- a built-in **walk-forward Elo baseline**, FiveThirtyEight style: K=20, HFA 48 Elo, MOV multiplier, 1/3 season reversion. It uses only results available before each game's `forecast_asof_utc`.
- any challenger, for example an EPA model, passed as `--pred NAME=path.csv`

**Reported:** margin MAE, total MAE, Brier score, log loss, a 10-bin calibration table, and the missing/blocked count per model. Comparisons use only the games every model priced, so skipping hard rows can't help. Each challenger gets a paired bootstrap vs Elo that resamples whole weeks, not individual games.

No odds are read. Sportsbook prices stay out of the forecasts.

```sh
python models/nfl/nfl_forecast_scorecard.py \
  --games /private/games.csv --results /private/results.csv \
  --pred ridge=/private/ridge_preds.csv --pred epa=/private/epa_preds.csv \
  --out /private/scorecard.json
python -m unittest discover -s models/nfl -p 'test_nfl_forecast_scorecard.py' -v
```

**Adoption rule:** pick the metric in advance, usually Brier score. A challenger is adopted only if it beats Elo on untouched games with the 95% CI entirely below 0. If the result is inconclusive, the simpler model stays.

**Gaps:** the data inputs must be real pregame snapshots, which this module can't verify. The Elo settings are standard published values that haven't been tuned here. Totals are only scored for models that output a total, so Elo has no total.
