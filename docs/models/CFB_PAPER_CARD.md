# CFB PAPER card runbook (research only, PAPER / 0u)

This pipeline freezes pregame CFB forecasts and quotes, grades them against official finals and
evaluates them chronologically. **Nothing in it is a betting signal.** Every row is PAPER with
`stake_u=0`, `official_counted=0` and `approved_stake_u=0`. The models are untested; the EV figures
come from unvalidated probabilities and do **not** show a verified edge. **Passing the unit tests is
not predictive validation.** Only a long, untouched, prospectively frozen record can say anything
about accuracy, and even that is not a release decision.

Scope: full-game **ML, spread, total** only. Team totals, halves, props, alternates and SGPs are out
of scope and show up in the PIT contract census as `NOT_CAPTURED`.

## Modules (`models/cfb/`)

| Module | Role |
|---|---|
| `cfb_capture_store.py` | Private, append-only capture directory (`capture.json`, `<source>__<stamp>.bin` + `.receipt.json`). Refuses public-repo paths, non-0700 dirs, and `HISTORICAL_BACKFILL` mode. CLI: `init`, `register`. |
| `cfb_cfbd_capture.py` | Prospective CFBD capture (games for one week, season advanced stats, talent, returning production). Dry-run by default. `--execute` needs `CFBD_API_KEY`; fails closed when the key is missing. |
| `cfb_pregame_assembler.py` | Builds one normalized record per game for `cfb_source_pit_contract.audit`, then returns READY, HOLD or PASS with reasons. |
| `cfb_baselines.py` | `sportsedge-cfb-runit-2026-11-15-untested-v1` wraps `sportsedge_cfb_model.py` unchanged, with the file SHA-256 and every constant pinned; any drift refuses. `sportsedge-cfb-sp-ratings-only-v1` is the simple SP+ comparator. |
| `cfb_paper_card.py` | Quote intake (operator CSV/JSON, or an Odds API v4 CFB archive plus an exact crosswalk), no-vig, pricing, card build, single write, ledger registration. |
| `cfb_ledger.py` | Hash-chained JSONL ledger that can only be appended to (`CARD_FROZEN`, `GAME_GRADED`). |
| `cfb_grading.py` | `grade` (official finals by exact CFBD game ID) and `evaluate` (chronological holdout report). |

## Inputs and endpoints

The CFBD endpoints are documented in [CFB_README.md](CFB_README.md). Base URL
`https://api.collegefootballdata.com`, header `Authorization: Bearer $CFBD_API_KEY`:

* `/games?year=Y&week=W&seasonType=regular&classification=fbs` gives the exact game and team IDs (`id`, `homeId`, `awayId`), `startDate` and `neutralSite`.
* `/stats/season/advanced?year=Y&excludeGarbageTime=true`, `/talent?year=Y` and `/player/returning?year=Y`.
* SP+ (`/ratings/sp?year=Y`) is **not** fetched again here. It comes from the existing daily capture (`sportsedge.validation.daily_ratings_capture`, `cfbd_ratings_sp`) and is admitted through `eligible_bytes`, which requires the correct season and source, observation ≤ freeze < kickoff, and an age of 8 days or less.
* Weather is an **Open-Meteo forecast** captured before the freeze by `sportsedge.data.open_meteo_pit` (request `sport=CFB`, `event_id=cfbd-<season>-<gameId>`). The assembler parses the retained original bytes again and checks that they match the report and the exact kickoff. A retrospective actual is never used. Open-Meteo's free tier is for non-commercial use.
* The starting QB comes from an operator file (`operator_qb`, schema `sportsedge-cfb-operator-qb-v1`) with rows `{cfbd_game_id, team_id, team, qb_id, starter_status}`. A missing file, a missing row, or a status of `QUESTIONABLE`/`OUT`/`UNKNOWN` gives an explicit **HOLD**.
* Injuries come from an operator file (`operator_injuries`, schema `sportsedge-cfb-operator-injuries-v1`) with `games_reviewed` and rows `{cfbd_game_id, team_id, team, player_id, player, role, status[, impact]}`. A game missing from `games_reviewed` gives a PASS. An empty list is recorded as `INJURY_LIST_EMPTY_NOT_PROOF_OF_NO_INJURIES`. `QUESTIONABLE`/`UNKNOWN` gives a HOLD.

Each source keeps its provider, sha256, `observed_utc` and `captured_utc` (`published_utc` is null
unless the provider states one; null means observed is the upper bound). Only the newest capture
with `captured_utc <= frozen_utc` is used. A later capture is ignored, never merged.

## Point-in-time and leakage rules (enforced)

* **Season-wide files downloaded after games are NOT valid pregame evidence.** The capture mode must be `PROSPECTIVE_PREGAME`. A games file that reports a result for a game that had not started at its capture clock is refused (`GAMES_FILE_CLOCK_INCONSISTENT`). A target game already completed in the file gives a PASS. A season file captured at or after a game's kickoff gives a PASS for that game. In evaluation, any card input captured at or after kickoff is excluded.
* The season must match exactly in every file, and the SP+ receipt must be for that season.
* Team identity is the exact CFBD team ID. Name-keyed CFBD files are joined only on that game's exact school string. Operator rows whose `team_id` is not in the game (`*_BORROWED_TEAM_ID`), or whose name disagrees with the ID, give a PASS. A name mapped to two IDs, or the reverse, refuses the file.
* Critical missing input gives an explicit PASS reason: games file, advanced stats, SP+, weather forecast, injury report, plus talent and returning production before week 6.

## Daily operation

```sh
# 1. Before kickoff: capture CFBD sources (or use the manual workflow below and decrypt).
python -m models.cfb.cfb_capture_store init  "$PRIV/cfb-2026-w13" --season 2026 --week 13
CFBD_API_KEY=... python -m models.cfb.cfb_cfbd_capture "$PRIV/cfb-2026-w13" --season 2026 --week 13 --execute
python -m models.cfb.cfb_capture_store register "$PRIV/cfb-2026-w13" --source operator_qb \
    --file qb.json --provider operator:depth-chart-review --observed-utc 2026-11-28T13:00:00Z
python -m models.cfb.cfb_capture_store register "$PRIV/cfb-2026-w13" --source operator_injuries \
    --file inj.json --provider operator:availability-report --observed-utc 2026-11-28T13:00:00Z
# 2. Freeze the card now (freeze time = wall clock). Quotes must be captured at or before the freeze.
python -m models.cfb.cfb_paper_card "$PRIV/cfb-2026-w13" --out-dir "$PRIV/cards" --ledger "$PRIV/ledger/cfb.jsonl" \
    --ratings-dir "$PRIV/ratings-2026-11-28" --weather-dir "$PRIV/weather" --operator-quotes quotes.csv
# 3. After the games: grade with CFBD /games finals (and optional closing quotes for CLV).
python -m models.cfb.cfb_grading grade --ledger "$PRIV/ledger/cfb.jsonl" --cards-dir "$PRIV/cards" \
    --finals finals.json --closing-quotes closing.csv
# 4. Evaluate.
python -m models.cfb.cfb_grading evaluate --ledger "$PRIV/ledger/cfb.jsonl" --cards-dir "$PRIV/cards"
```

Every private path must sit outside the repository checkout and be owner-only (0700). **Never commit
real data.**

### Quotes

Operator CSV columns: `cfbd_game_id, book, market (ML|SPREAD|TOTAL), line, home_price, away_price,
over_price, under_price, captured_utc`. JSON uses `{"schema": "sportsedge-cfb-operator-quotes-v1",
"rows": [...]}`. Both sides are required. A one-sided quote, an out-of-scope market, an ML row with a
line, or an invalid American price refuses the file. The SPREAD `line` is the **home** handicap. The
card keeps the latest quote per (book, market) captured at or before the freeze. A game without one
is `NO_QUOTE` but still gets a projection or a PASS reason.

`sportsedge/odds/daily_main_odds.py` is an NFL-only pilot and does not cover CFB. An Odds API v4
archive written by `sportsedge.odds.free_odds_aggregator_intake` for `CFB` can be used with
`--odds-archive RAW SUMMARY CROSSWALK`. The crosswalk (`sportsedge-cfb-odds-event-crosswalk-v1`)
maps each provider event ID to one CFBD game ID with the exact provider home and away names. No
fuzzy matching is done. Aggregator quotes are not authenticated sportsbook offers.

### Pricing

The no-vig probability uses multiplicative normalization of both sides. The model probability comes
from a Normal distribution with the model's SD (margin 15.5, total 15). Spread and total
probabilities are continuous, so pushes are ignored in EV. EV is `p_model * decimal - 1` at the
actual quoted price. `paper_lean_unvalidated` is the side with positive EV, if there is one. It is a
grading label, not a recommendation.

### Model input notes

* The frozen RUN IT model is run unchanged. SP+ offense and defense ratings are centred on the means of the captured SP+ file before they go in, because the model documents its ratings input as points versus the average team. This changes inputs only, not weights.
* Open-Meteo gives precipitation probability but not precipitation type, so the model's precipitation adjustment never fires. Wind is applied only when the operator marks the roof `OPEN`.
* Travel, rest and per-venue home-field files are not assembled yet, so those adjustments use the model's defaults or do not apply.

## Grading and evaluation

* Finals are matched by **exact CFBD game ID** and both exact team IDs. CFBD `homePoints`/`awayPoints` are final scores including overtime. The finals file must be captured after kickoff. A later final that conflicts with one already graded refuses (`FINAL_CONFLICT_REQUIRES_REVIEW`) and nothing is rewritten. Grading again is idempotent.
* A frozen card is checked against its registered sha256 before every grade or evaluation. An edited card refuses.
* PASS, HOLD, NO_QUOTE, loss and push rows are all kept in the ledger.
* `evaluate` runs in kickoff order. It counts only games that kick off at or after the enforced holdout floor `HOLDOUT_START_UTC` = 2026-11-23T06:00:00Z (Nov 23 00:00 Central), the models' `registered_utc` (or a later `--holdout-start-utc`), uses the first registered card per game, requires the card to be frozen and registered before kickoff, and requires every input to have been captured before kickoff. Each exclusion is counted with its reason.
* The report covers n, margin and total MAE (each model's own coverage, plus a common set of frozen, ratings-only and same-time market), ML Brier and log-loss, spread and total cover Brier excluding pushes, ML calibration bins, paired MAE differences with 95% intervals, and CLV (`p_close_novig * decimal_open - 1`) when a same-line closing quote captured before kickoff exists.
* **Returns are reported separately** as `HYPOTHETICAL_1U_FLAT_PAPER_NOT_COUNTED`, with Wilson and normal intervals. `sample_warning` stays true below 300 games. The report always has `validation_certified=false`.

## Manual workflow

`.github/workflows/cfb-paper-card.yml` runs only on `workflow_dispatch` and only on `main`. It has no
schedule. `offline-tests` runs the synthetic suites. `cfbd-capture` makes at most four CFBD GETs
with `CFBD_API_KEY`. It fails closed when the key or season/week inputs are missing, never prints
keys, and uploads only a Fernet-encrypted archive (`SPORTSEDGE_ARCHIVE_FERNET_KEY`), in the same way
as `daily-ratings-capture.yml`.

## Remaining gaps

* There is no authenticated provider clock. Receipts are local claims, and CFBD publication times are unknown.
* The QB and injury files are entered by hand. Nothing verifies them.
* There are no automated venue coordinates or roof registry for Open-Meteo requests, and no travel or rest inputs.
* No live CFB odds intake is wired to a schedule, and closing quotes come from operator files.
* No prospective record exists yet. Until there is a long untouched sample, all CFB output stays PAPER / 0u.
