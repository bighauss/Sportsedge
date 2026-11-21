# CBB CBBD-native paper card runbook (PAPER / 0u)

This pipeline builds a daily College Basketball paper card from a CBBD-native
score model, freezes it before tipoff, attaches official finals by exact CBBD
game ID in an append-only ledger, and evaluates the model against the same-time
market in chronological order.

All output is **PAPER / 0u**: `official_counted=0` and `approved_stake_u=0`.
A positive paper EV is **not** verified +EV. The tests are synthetic and offline.
They show that the code enforces its contract. They do **not** show that the
model predicts well. `RISK_POLICY.md` and
[Issue #10](https://github.com/bighauss/Sportsedge/issues/10) still apply.

## Components

| File | Role |
| --- | --- |
| `models/cbb/cbbd_native_score_model.py` | CBBD-native score model. It is separate from frozen v5 (`sportsedge_cbb_model.py`) and the `torvik_*` baselines, and does not import or replace them. |
| `models/cbb/cbbd_paper_card.py` | Builds the daily card and accepts quotes from operator files or the Odds API |
| `models/cbb/cbbd_paper_ledger.py` | Append-only ledger: card freeze, final attachment, closing quotes, and the evaluator |
| `models/cbb/cbbd_paper_synthetic.py` | Synthetic test fixtures only. Never use them as a data source. |
| `.github/workflows/cbb-cbbd-paper-card.yml` | Manual-only offline test workflow: `workflow_dispatch`, runs on `main` only, no schedule, no secrets |

Reused components (unchanged):

- `sportsedge/validation/daily_ratings_capture.py`: `eligible_bytes` checks the ratings cutoff
- `sportsedge/validation/cbb_venue_registry.py`: `verify_cbb_venue` checks neutral or home status
- `models/cbb/cbbd_prospective_capture.py`: `/games` capture and `finals_from_capture`
- `models/cbb/cbbd_frozen_final_join.py`: `verify_provider_originals` and `_final_verified`
- `models/cbb/point_in_time_score_walkforward.py`: `_parse_final`, `_paired_ci`, and `audit` (the chronological walk-forward)

## Model (`cbbd-native-additive-v0.1-research`)

Every input must be available at the time `freeze_utc` is set.

- **Ratings.** The bytes and receipt come from CBBD `/ratings/adjusted`, as captured by `daily_ratings_capture.py`. They must have `state=CAPTURED`, match their hash, have been observed at or before the freeze, and be no older than 36 h. Fields: `teamId`, `team`, `season`, `offensiveRating`, `defensiveRating`, `netRating`. Season 2027 means 2026-27. Teams are matched by exact positive integer `teamId` only. A duplicate ID, the wrong season, or a `netRating` that disagrees with `off - def` fails the whole payload.
- **Efficiency.** `eff_home = ORtg_home + DRtg_away - mean(ORtg)`. The away side is computed the same way.
- **Pace.** Expected possessions are `pace_home * pace_away / league_pace`. Pace comes only from prior games whose final was captured **strictly before** the freeze. Each team needs at least 3 prior games, and the league needs at least 30.
- **Home-court advantage (HCA).** There is no default constant. HCA is the mean residual of at least 50 prior non-neutral finals that have an explicit `neutral=false` flag. It is recorded as `hca.n`, `hca.se`, and `hca.basis`. Neutral games get no HCA.
- **Predictive SDs.** These come from prior released results only:
  - The preferred source is prospective card residuals (`margin_residual`, `total_residual`) exported by the ledger evaluator, using only residuals captured before the freeze. At least 30 are required.
  - If there are fewer, the fallback is retro residuals from prior finals. These are labelled `RETRO_PRIOR_FINALS_IN_SAMPLE_LIKELY_UNDERSTATED`.
- **Probabilities.** Margin and total are modelled as normal distributions. On integer lines, push probability uses a ±0.5 continuity band.

### Prior-games input

The prior-games file is a JSON list:

```json
{"game_id": "123", "season": 2027, "tipoff_utc": "...Z", "final_captured_utc": "...Z",
 "home_team_id": "1", "away_team_id": "2", "neutral": false,
 "home_points": 71, "away_points": 65, "possessions": 67.5}
```

These rules apply:

- Rows captured at or after the freeze are counted as `rejected:FUTURE_FINAL_AFTER_FREEZE` and are never used.
- Duplicate IDs quarantine every copy.
- `possessions` must come from captured CBBD game team stats.

**Gap:** no automated capture of possessions exists yet. The operator must supply this file from original captures.

## Daily card

Run from `models/cbb` with `PYTHONPATH=<repo>:<repo>/models/cbb`. Keep every path outside the public checkout; the code refuses paths inside it.

    python cbbd_paper_card.py --freeze-utc 2026-11-21T15:00:00Z --season 2027 \
      --slate /private/cbb/slate.csv --registry /private/cbb/venue_registry.csv \
      --ratings /private/cbb/ratings/cbbd_ratings_adjusted.json \
      --ratings-receipt /private/cbb/ratings/receipt.json \
      --prior-games /private/cbb/prior_games.json \
      [--prior-residuals /private/cbb/residuals.json] \
      [--quotes /private/cbb/lines.csv ...] \
      [--odds-api-raw R --odds-api-manifest M --odds-api-crosswalk X] \
      --output /private/cbb/cards/card-2026-11-21.json

### Input formats

- **Slate CSV.** Columns: `game_id,season,tipoff_utc,home_team_id,away_team_id,neutral`. `neutral` must be `0` or `1`.
- **Venue registry CSV.** This uses the existing `cbb_venue_registry` schema. The neutral flag must agree with the slate. The source clocks must precede the freeze. The registry tipoff must equal the slate tipoff.
- **Operator quotes.** Supply CSV or JSON with exact columns `game_id,market,book,line,price_a,price_b,captured_utc`:
  - `market` is `moneyline`, `spread`, or `total`.
  - For spread, `line` is the **home** line.
  - `price_a` is the home or over price; `price_b` is the away or under price.
  - Both sides are required.

### Odds API intake

`sportsedge/odds/free_odds_aggregator_intake.py` captures CBB (`basketball_ncaab`). The card reads its raw archive and manifest only when you also supply an operator crosswalk CSV with columns `odds_event_id,game_id,odds_home_team,odds_away_team`.

- Each provider event maps exactly 1:1 to one CBBD game ID.
- The provider's home and away names must match the crosswalk exactly, which checks orientation.
- Nothing is fuzzy-matched. Unmapped events are counted and dropped.

`sportsedge/odds/daily_main_odds.py` is NFL-only and does not cover CBB.

### Quote selection

For each game and market, the card uses the latest quote captured at or before the freeze, within a 24 h age limit. If two quotes tie on time, the alphabetical book name wins. Selection never looks at the model or EV. Conflicting copies of the same book and timestamp quarantine every copy.

### Card contents

The card is written create-only, mode `0600`. It includes:

- `model_version`, `model_code_sha256`, `card_builder_sha256`
- `input_sha256` for every input file
- the ratings receipt
- the fitted context: HCA and SD with their n and basis, plus the prior-game census
- the quote census
- a self-hash, `card_sha256`

Each row is `PROJECTED` or `PASS` with a reason. Each row always has three market entries. A priced market reports:

- the full quote: book, line, both prices, and `captured_utc`
- the model probabilities, including push
- the no-vig market probabilities and the overround
- `paper_ev_per_1u_at_price` for both sides

### PASS reasons

These game-level PASS reasons are listed exhaustively in the code:

- `GAME_ID_NONCANONICAL`
- `DUPLICATE_GAME_ID_ALL_COPIES`
- `WRONG_SEASON`
- `TIP_DATE_SEASON_MISMATCH`
- `TIPOFF_NOT_AFTER_FREEZE`
- `CARD_BUILT_AT_OR_AFTER_TIPOFF`
- `UNMAPPED_CBBD_TEAM_ID`
- `NEUTRAL_SITE_UNVERIFIED:<venue code>`
- `VENUE_REGISTRY_TIPOFF_MISMATCH`
- `RATINGS_OR_CONTEXT_NOT_ELIGIBLE_AT_FREEZE:<code>`
- `NEUTRAL_SITE_UNKNOWN`
- `MISSING_LEAGUE_PACE_HISTORY`
- `MISSING_PACE_HISTORY`
- `HCA_UNMEASURED_INSUFFICIENT_PRIOR_GAMES`
- `PREDICTIVE_SD_UNMEASURED`

At market level, the reason is `MISSING_QUOTE` or `GAME_PASS`.

## Ledger and grading

    python cbbd_paper_ledger.py append-card   /private/cbb/ledger.jsonl /private/cbb/cards/card-2026-11-21.json
    python cbbd_paper_ledger.py append-close  /private/cbb/ledger.jsonl /private/cbb/close_quotes.json
    python cbbd_prospective_capture.py finals --raw R --manifest M --output /private/cbb/finals.json
    python cbbd_paper_ledger.py attach-finals /private/cbb/ledger.jsonl /private/cbb/finals.json \
      --provider-raw R --provider-manifest M
    python cbbd_paper_ledger.py evaluate /private/cbb/ledger.jsonl \
      --report /private/cbb/eval.json --residuals-out /private/cbb/residuals.json

### Ledger file

- The ledger is a JSONL hash chain (`prev_entry_sha256`, `entry_sha256`). Every read and append re-verifies the whole chain, so editing, reordering, or deleting a line fails closed.
- The file is mode `0600` and is locked during each append.
- A card is appended whole, PASS rows included, and is never rewritten.
- A card whose self-hash fails is refused, as is a card whose game IDs already appear on an earlier card. The second rule stops a game from being re-frozen to get a better line.

### Finals

- The original CBBD `/games` bytes and manifest must reproduce the derived finals (`verify_provider_originals`).
- A final attaches by exact game ID, season, and home and away team IDs.
- The final must be observed after tipoff.
- Duplicate finals quarantine every copy.
- A game is graded once. Later attempts are counted as `already_graded`.

### Grades

Every row is graded, including passes and rows without a quote. Each market result is one of `W`, `L`, `P`, `NO_QUOTE`, `PASS`, or `NO_POSITIVE_PAPER_EV_SELECTION`.

The hypothetical paper selection is the side with the higher positive paper EV at the frozen price. It is not a wager.

### Closing quotes

A closing quote is accepted only if it was captured after the card freeze and strictly before tipoff. Only one is kept per game and market. CLV is computed only when the closing line equals the frozen line, as the no-vig probability at close minus at open.

### Evaluator

The evaluator reports these sections separately:

- **`forecast_accuracy`:**
  - margin and total MAE versus the same-time spread and total lines
  - Brier and log-loss versus the no-vig market for moneyline, spread, and total
  - calibration bins with Wilson intervals
  - paired normal 95% intervals, shown only when n ≥ 30
- **`paper_returns_separate_from_accuracy`:** W/L/P counts, hypothetical flat-1u return, and CLV
- **`walkforward_reuse_point_in_time_score_walkforward`:** the existing `audit()` output for each market. Only finals released before each freeze enter its training set, with min_prior 30.

## Wiring and secrets

- The workflow is manual-only and offline. It reads no secrets and calls no providers.
- Live captures stay in the existing workflows. Ratings come from `daily-ratings-capture.yml`, which is encrypted with `SPORTSEDGE_ARCHIVE_FERNET_KEY`.
- Never commit real slates, quotes, ratings, cards, or ledgers. Every CLI refuses paths inside the repo.

## Known gaps (honest)

- The model is unvalidated. CBBD rating semantics come from the documentation, not from a verified live response. The additive formula and the normal error model are untested on real data.
- Possessions history has no automated capture, and the slate and venue registry are built by the operator.
- Retro SDs are in-sample and likely understated until 30 or more prospective residuals exist.
- HCA uses ratings from the freeze-time snapshot, which may already include the prior games it is measured on. That is in-sample, though it uses no information from after the freeze.
- Quote and final timestamps are local capture claims, not provider attestations. Aggregator quotes do not authenticate the original book offer.
- The offline workflow is manual-only, so these tests do not run automatically on pull requests. `tests.yml` was intentionally left unchanged, though its `compileall` step does compile the new modules.
