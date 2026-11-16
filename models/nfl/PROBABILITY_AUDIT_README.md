# NFL 3-way score probability audit (PIT research R1)

**Every output is PAPER_HOLD_0U, never a verified +EV bet or automatically approved calibration.** This is a read-only prequential evaluator of a frozen final-score distribution, not a new sportsbook odds feed or source-authentication service.

## Research question

Does the **paired-residual empirical score distribution** in `models/nfl/discrete_score_pit.py` better predict unseen NFL final outcomes than a simple prior-result frequency baseline? This evaluator intentionally does **not** re-fit EPA weights, tune thresholds, optimize on game results or assume public data were available before kickoff.

For every originally frozen pregame forecast:

1. Require an exact canonical event ID, separate exact home/away team IDs, model-version SHA256, source-observed UTC, forecast-freeze UTC, kickoff UTC, final UTC, first original final-result availability UTC, original projected home/away scores and independently obtained actual full-game home/away finals.
2. Select **only other same-model-version games** with a kickoff **and reported result availability** strictly before the target forecast freeze. Preserve the target's actual final as grading-only; never feed it into its own distribution.
3. With at least 50 prior pairs (default, unvalidated threshold), create the full-game integer joint-score distribution from `discrete_score_pit.py` and obtain explicit win/tie/loss, home cover/push/away cover, game over/push/under and individual team total results. No fake price, EV or stake.
4. Benchmark the estimated 3-way probabilities against the simple training-only frequency of **actual historical game scores**, assessed at the *target's* pregame line for spread/total/team total. This baseline is deliberately NOT a sportsbook or no-vig baseline, and does not adjust for future opponents, weather or roster.
5. Grade all pre-existing events, including losses and withheld/no-model selections. Report 3-way Brier, log loss and paired improvement per market; show a deterministic game-bootstrap 95% interval **only once 30 separate eligible games exist**.
6. Retain every missing market line as `NOT_CAPTURED` and every insufficient-history market as `NO_MODEL`; preserve a census and the event-by-event diagnostic ledger.

**No historical data are authenticated by schema checks.** Source observed/freeze/available times and model SHAs are self-asserted until independently verified against original archived raw files, provider clocks, event/lineup confirmations and immutable before-kickoff receipts. `win_probability` values from the uncalibrated empirical model must not be sold as a market-beating edge. A positive Brier gain does not imply positive ROI.

## Exact inputs

The `--history` file is a private JSON array with one original row per NFL game. Each row must have *exactly* these fields:

```text
game_id,home_id,away_id,kickoff_utc,forecast_asof_utc,source_observed_utc,
model_sha256,projected_home,projected_away,
final_utc,result_available_utc,final_home,final_away
```

The original frozen forecast must exist before kickoff, and the final/first observed result must be later; all data are in timezone-aware UTC. The `--lines` file is an optional private JSON array (one record per game) containing:

```text
game_id,observed_at_utc,home_spread,game_total,home_team_total,away_team_total
```

A line observed after the **target forecast freeze** is refused. Missing line keys use JSON `null`, and missing games have no row; no line is invented, and the file does **not** represent a verified sportsbook receipt. A home -3 spread means home margin + (-3); a three-point home win is a push. Tie settlement for a 2-way moneyline is never inferred. All markets are **full game only**.

## Run

```sh
python models/nfl/score_probability_audit_pit.py \
  --history /private/original_frozen_game_scores_and_final_results.json \
  --lines /private/original_same_event_pregame_game_lines.json \
  --out /private/nfl_3way_brier_paper.json \
  --min-history 50

python -m unittest discover -s models/nfl -p 'test_score_probability_audit_pit.py' -v
```

Omit `--lines` to evaluate moneyline only; every remaining market will still be listed as `NOT_CAPTURED` or `NO_MODEL`. The CLI uses the current real UTC clock to refuse results claimed available only in the future; it has **no operator-backdated as-of override**. The pure research function accepts an explicit UTC audit cutoff for deterministic tests.

All source and output paths must be **outside the public Git checkout**, including symlink aliases. Original JSON is loaded strictly (duplicate keys, NaN/Infinity, extreme exponent overflow and overlarge inputs blocked). The original bytes are SHA-256 hashed; report is create-only, private mode 0600, fsynced with partial-output rollback. Never commit original provider data, account keys, private quotes, betting records or full source manifests to public GitHub.

## What would be needed to promote a market

- Independent, authentic prospective source/QB/weather/lineup/archive timing before every event, and original authorized two-sided sportsbook quote chains.
- True train-only preregistered hyperparameter selection and untouched future folds, per-market reliability plots, uncertainty by week/game, and robustness across seasons. Test for overconfidence, home/away or dog/under skew, and model-version drift.
- Compare against the **no-vig market-only baseline** from same event/line/period/time, and track actual original-odds ROI/CLV separately via `market_benchmark_pit.py` and the authorized odds-archive pipeline.
- Remain blocked until original source proof, 100 real compliant cards, 200 authentic open/take/close settlements and independent review/owner promotion satisfy Issue #10.

The code is a reproducible validation harness, **not** a verified prediction or gambling recommendation.
