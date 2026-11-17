# CBB availability + forward-quality wiring — PAPER / 0u

Owner request: repair the Nov 16 CBB model's unsupported player/injury layer, one-directional card disagreements, missing sustained market Brier/CLV proof, and selected-card vs full-board denominator. This is a **fail-closed integration**, **not** a claim that the model has been fitted, is profitable, or that Gate A–E is closed.

## Wiring into RUN IT

`sportsedge/markets/run_it_research.py` now accepts an optional `cbb_availability` argument **only for CBB**. The argument is the **raw** object `{"event": {...}, "roster": [...], "observations": [...]}`, **not** a caller-written `{"state": "PASS"}` or pre-certified verdict. The runner invokes `audit_cbb_availability` itself, verifying exact `batch.event_id`, immutable digest shape, UTC-only chronology, roster-bound player/team IDs, and one frozen availability observation per roster player. Each event must provide:

- event: `event_id`, `home_team_id`, `away_team_id`, `freeze_utc`, `tipoff_utc`, `roster_sha256`, `roster_published_utc`, `roster_captured_utc`.
- roster rows: `player_id`, `team_id` (exact canonical IDs, no name matching, no transfers inferred).
- observation rows: `player_id`, `team_id`, `status` (`ACTIVE`, `OUT`, `QUESTIONABLE`, `DOUBTFUL`, `UNKNOWN`), `source_sha256`, `published_utc`, `captured_utc`.
- every timestamp is UTC `YYYY-MM-DDTHH:MM:SSZ`; source publication and local capture must be at/before forecast freeze, which must precede actual tipoff.

No source rights or direct download route is implied; permitted original roster/injury reports must be obtained and privately archived via the source lane. The guard explicitly **does not infer how many points an OUT player changes the team projection**. Without a pre-registered fitted effect/variance model, non-active/uncertain players block the research shortlist. Even an all-active complete roster is **shape-valid but unauthenticated**. Unavailable inputs block the CBB shortlist by default; all raw computed research evidence remains in the attempted-row census (`quarantined_signal`), not deleted.

A second symmetric `screen_cbb_disagreement` quarantines **both directions** of >=15 percentage-point model-vs-no-vig disagreement or >=25% *unverified raw* EV. These are fixed **audit tripwires**, not calibrated thresholds, forecast modifications, or a claim that large edges cannot exist. Every row continues through the original v2.1 risk gate: `official_counted=0`, `approved_stake_u=0`. No alteration to frozen v5, bookmaker prices, original odds receipts, previous cards, or fitted weights. The direction diagnostic reports category counts; it never inserts favorite/over picks to manufacture balance.

## Research forward evaluator

`models/cbb/cbb_forward_quality.py` consumes a **private JSON array of original attempted offered sides**, including blocked / unoffered / missing-price rows. Pass the original attempted count separately; equality checks can detect accidental local omissions but **cannot prove that a whole sportsbook slate was captured**.

Each `capture_state=OFFERED` row requires:

- `market`: exact 10-tuple from `Market.identity()`, with CBB sport, provider event, family, period, side, exact line/subject and settlement. Only no-push (.5) lines are scored; unsupported integer lines are retained but blocked rather than inventing push probabilities.
- `book`, `model_p`, `model_sha256`, `feature_sha256`, `feature_published_utc`, `feature_captured_utc`, `forecast_frozen_utc`, `event_start_utc`.
- `take_american`, `take_opposite_american`, `take_source_sha256`, `take_observed_utc`, `selected` (original pregame boolean).
- `outcome` 0 or 1 **only after** settlement, plus `final_source_sha256`, `final_published_utc` and `final_captured_utc`; pending finals stay null. Push/unmodeled settlement is not silently called a loss.
- Optional complete same-market `close_american`, `close_opposite_american`, `close_source_sha256`, `close_observed_utc`. Close must have been observed within the independent grading sweep's pregame 60-minute ceiling, and not before the take. This does **not** replace the separate standing FINAL full-board window [start−20m, start).

A legal matched pair must contain two reciprocal original side rows (same book, market, period, source, point-in-time forecast, quote clock, prices and consistent inverse probabilities/outcomes). Duplicates and conflicts quarantine **both** copies. The evaluator creates exactly **one Brier datapoint per mirrored market**, while retaining both rows and every attempted/blocked row. It reports market no-vig vs model Brier, the research best-side flat-unit counterfactual, *original preselected* flat-unit result, significant disagreement cases and same-line no-vig close shifts. Both mirrored selections must not count as two recorded bets. These statistics are descriptive and **never independently reproducible without the originals**.

Run from a private location, not checked-in data:

```bash
cd models/cbb
python -m unittest -v test_cbb_forward_quality
python cbb_forward_quality.py /private/cbb/original_full_board.json \
  --expected-attempted-rows <original_row_count> \
  --report /private/cbb/new_forward_diagnostic.json
```

The CLI refuses evidence/report paths in the public repository and creates the report with exclusive permissions (0600); it never overwrites an older report. Do not commit real provider bytes, personal bets, credential material, or unredacted original odds to this public repository.

## Remaining evidence gates / acceptance

This change creates a technical route for model **PIT availability** and **full-board market comparison**, not an already fitted injury adjustment or an authenticated forward streak. A market remains PAPER / 0u and EMIT_BLOCKED until:

1. Authorized original provider data with independently verifiable sportsbook source identity, quotes, capture/published times, team/player bindings, injury availability, and complete slate census is acquired privately.
2. Availability effects on points, minutes, and variance are **trained only on earlier games** and ablated against a roster-blind frozen baseline. Missing, conflicting and unknown statuses fail closed. Any proposed frozen-model replacement is a separate reviewed version and unseen-data study.
3. An untouched, pre-registered forward cohort shows model improvements vs **same-line original** no-vig market probabilities using Brier/log loss, game-cluster uncertainty, historical-vs-holdout calibration and all offered markets. A nominal positive spread/ML Brier average with only a handful of days is not sufficient.
4. Real take/close originals are identity matched with legitimate close windows, regardless of whether a selected card won. Count winning, losing, unselected, model-doubted, missing and blocked rows together; never backfill closes or revise old forecasts.
5. Independent Gate A–E review, existing 100-clean-card / 200-valid-settled-close / five-day requirements, Risk Policy, and explicit owner-signed per-market promotion are satisfied.

**Currently proven by these tests:** synthetic program integrity and fail-closed outputs. **Not proven:** original sportsbook authenticity, 2026 real injury feed, fitted player coefficients, genuine CLV, profitable CBB model, or counted forward Brier superiority.

Related: [CBB baseline](CBB_WALKFORWARD_SCORE_RESEARCH.md), [Independent projection inventory](INDEPENDENT_PROJECTION_COVERAGE.md), [Issue #10](https://github.com/bighauss/Sportsedge/issues/10), [Issue #192](https://github.com/bighauss/Sportsedge/issues/192), [Issue #239](https://github.com/bighauss/Sportsedge/issues/239).
