# RUN IT runners vs PAPER pipelines: parity audit (2026-11-21)

Research only, PAPER / 0u. Synthetic fixtures (fake teams, fake prices). Passing these
checks is not predictive validation and is not evidence of +EV.

Classifications: **(i)** intentional contract difference · **(ii)** runner defect (fixed here
with a failing test first) · **(iii)** paper-pipeline defect (reported only, not changed) ·
**(iv)** input-format translation artifact.

## CFB

Base: `cfb-run-it-p0` @ `db8ce5d`. Test: `models/cfb/test_cfb_run_it_parity.py`
(`PYTHONPATH=. python -m unittest models.cfb.test_cfb_run_it_parity`).

### Fixture

One frozen fixture: the PAPER suite's synthetic slate (`test_cfb_paper_card.Fixture().standard()`,
games 401 Beta Tech @ Alpha State and 402 Gamma U @ Delta Mines, `STANDARD_QUOTES` on 401 only,
freeze `2026-11-28T15:00:00Z`). `runner_inputs()` translates the same rows into the runner's
capture/intake/weather shape. Numbers are copied, never re-derived. The runner's "now" is the
paper's freeze time.

### Same frozen model

| Check | Runner | Paper | Result |
|---|---|---|---|
| Module imported | `sportsedge_cfb_model` (path insert in models/cfb) | `models.cfb.sportsedge_cfb_model` | same file (realpath equal) |
| File sha256 | recorded in `model_projections.model_file_sha256`; **before this PR it was not gated** | `verify_frozen_model()` refuses on file or constant drift | both `1f24cf1a…35be` = pin |
| Constant drift (in-process) | not checked | refused | (i), see note D1 |

### Field-by-field comparison (game 401, `legacy_inputs=True` unless noted)

| Field | Runner | Paper | Diff | Class |
|---|---|---|---|---|
| Games admitted | lines in intake only (401) | every game in the captured week (401 READY+quoted, 402 READY `NO_QUOTE`) | runner denominator = intake, not slate | (i) |
| Game identity | name pair resolution (+aliases, "…" prefix), optional `cfbd_game_id` pin, kickoff_ct ±20 min | exact CFBD game id, team ids, name/id conflict refused | runner fuzzier, pin optional | (i) |
| Kickoff gate | `ko <= now` withheld | `kickoff <= frozen` PASS | identical (tested) | – |
| kickoff_ct check | compared against the **run** date's CT calendar day | n/a | runner withheld a correct line when run on a prior day | **(ii) D2, fixed** |
| Point-in-time file clocks | none (live capture is "now") | every source `captured_utc <= frozen < kickoff`; games file with a target result refused | paper stricter | (i) |
| Quote timing | intake `captured` is free text, not checked | quote `captured_utc <= frozen` and `< kickoff`, latest per (book, market) | paper stricter | (i) |
| Required advanced fields | all 17 `REQUIRED_ADV` keys present, else withheld | only offense/defense `ppa`, `plays`, `drives` | paper admits missing keys; model then silently substitutes the league mean (`g(r,k,lm[k])`) | **(iii) P1** |
| Games played | default: completed games before run counted from the games file; `legacy_inputs=True`: model fallback | model fallback `offense.drives/12` (10.42 here) | default runner total differs (games=10); with games=drives/12 the runner reproduces the paper number exactly (tested) | (i); paper reliance on a drives estimate noted as (iii) P3 |
| History games for count | needed in default mode | absent from paper fixture | runner withholds "games played unknown" without them | (iv) |
| SP+ centring | mean over rows with both ratings, excluding `nationalAverages` | mean over all captured rows | identical on fixture | – |
| SP+ freshness | none | daily capture, ≤ 8 days old, before freeze | paper stricter | (i) |
| Talent / returning | passed through | passed through; required only before `PRIOR_FADE_WEEK` | identical in week 13 | – |
| Starting QB | no QB gate | missing/unknown QB → HOLD | runner projects, paper holds (tested) | (i) |
| Injuries | intake rows passed straight; review time affects eligibility reasons only | operator file with `games_reviewed` census; QUESTIONABLE → HOLD; borrowed team ids refused | same model rows on fixture; paper stricter | (i) / (iv) row format |
| Weather source | Open-Meteo live: max wind over 4 hourly rows, precip/snow typed | pre-freeze Open-Meteo capture, event-hour wind, precip type `not_in_forecast_fields` (no precip adj) | both 9 mph, 0 adj on fixture; can differ on real data (window max vs event hour; precip applied only by runner) | (i) |
| Roof | venue `dome` flag | owner roof claim; not `OPEN` → closed, weather ignored | can differ | (i) |
| Venue / HFA / teams (travel) | `ctx.venues={}`, `teams` from CFBD `/teams/fbs` | `venues={}`, `teams={}` | runner can apply travel TZ penalty, paper never does | (i) |
| Venue row | `venueId` + lat/lon needed or game withheld | not needed (weather file keyed by event) | translation adds venues | (iv) |
| pts_home / pts_away / margin / total | 37.4228 / 17.9416 / +19.4812 / 55.3645 | same (paper rounds to 4 dp) | equal to 4 dp (tested) | – |
| Notes / HFA | `Beta Tech: Fake WR STAR_SKILL OUT -1.50`, 2.5 | same | equal | – |
| Model p (ML/spread/total) | `pgt` on unrounded margin/total, SD 15.5 / 15.0 | `p_greater` on margin/total **rounded to 4 dp** | ≤ 1e-6 here (e.g. ML EV 0.253835 vs 0.253836) | (iii) P2 (cosmetic) |
| Spread convention | `spread` = home handicap, `pgt(m, -s)` | `line` = home handicap, `p_greater(m, -line)` | identical | – |
| No-vig market p | proportional (`imp/(sum)`) | proportional | equal to 6 dp | – |
| Blended p | `0.30·p_model + 0.70·p_novig` | none | runner only | (i) |
| EV | ranked by `ev_blend = p_blend·dec − 1`; also `ev_raw = p_model·dec − 1` | `ev = p_model·dec − 1` per side | paper EV == runner `ev_raw` (≤1e-5) | (i) |
| Markets priced | ML, spread, total, team totals, 1H, one-sided props | ML, spread, total only (others `NOT_CAPTURED` in census) | runner wider | (i) |
| Rows kept | `finalize`: `ev_blend > 0`, contradicting over/unders dropped, ranked, stars/flames | every eligible quote kept with both sides + PASS rows | runner card = ML Alpha State, Spread Alpha State −7 | (i) |
| Ratings-only comparator | none | `sportsedge-cfb-sp-ratings-only-v1` forecast per game | paper only | (i) |
| Withheld / PASS reasons | free-text tuples (`withheld`) | coded reasons (`KICKOFF_NOT_AFTER_FREEZE`, `QB_STATUS_UNKNOWN:<id>`, …) | different vocab; same gates agree where both exist | (i) |
| Output record | `model_projections` + `card` JSON/MD, `RESEARCH_ONLY`, 0u, receipts; no ledger on this base | O_EXCL card file + sha256 registered in append-only ledger, PAPER 0u | both 0u / official_counted 0 (tested) | (i) |

### Runner defects fixed (failing test first, minimal diff in `cfb_run_it.py`)

* **D1 – model pin not enforced.** The runner recorded the model file hash but would run
  a drifted model. Added `MODEL_SHA256_PIN` (same value as `cfb_baselines.FROZEN_RUNIT`)
  and `run()` raises `Fail("FROZEN_MODEL_FILE_SHA_DRIFT")` on mismatch.
  Test: `test_runner_refuses_model_drift`, `test_both_use_the_pinned_model_file`.
  The paper wrapper also checks in-process constants; the runner does not (file pin only, kept minimal).
* **D2 – kickoff_ct compared on the run date.** `want` used `now_utc`'s CT date, so a correct
  `2:00 PM` line run the evening before was withheld as a "kickoff mismatch" (the paper
  pipeline freezes the day before without issue). Now uses the CFBD kickoff's CT date; a wrong
  time is still withheld. Test: `test_kickoff_check_uses_game_date_not_run_date`.

### Paper-pipeline findings (reported, NOT changed)

* **P1** `parse_advanced` checks only `ppa`, `plays`, `drives`. A team missing e.g.
  `offense.successRate` is READY, and the model silently uses the league mean for that stat
  (`test_paper_admits_missing_advanced_keys_runner_withholds` documents current behaviour).
* **P2** Forecast `margin_home` / `total` are rounded to 4 dp before pricing, so p_model and EV
  differ from the unrounded model by up to ~1e-6. Cosmetic.
* **P3** Games played comes from the model's `offense.drives / 12` fallback (10.42 games here),
  an estimate rather than an observed count.

## CBB

Base: `cbb-run-it` @ `4e59159`. Test: `models/cbb/test_cbb_run_it_parity.py` in a **separate PR
based on `cbb-run-it`** (chosen as simpler than waiting for the branch to merge).

`cbb_run_it.build` calls the unchanged `cbbd_paper_card.build_card`. The test runs the runner
on the existing synthetic fixtures (`test_cbb_run_it.provider()`, `cbbd_paper_synthetic`),
writes the runner's adapter outputs (slate.csv, registry.csv, prior games, board quotes,
ratings body + receipt) to private files and calls `cbbd_paper_card.run` with the clock pinned
to the runner's freeze. Result: cards identical except:

| Field | Why it differs | Class |
|---|---|---|
| `input_sha256` | runner records `{"espn_scoreboard": sha}`; `run()` records sha256 of every input file | (i) |
| `card_sha256` | digest of the whole card, so it follows `input_sha256`; digest recomputed without `input_sha256` is equal | (i) |

`built_utc` is equal (runner builds at its freeze; `run()` is given the same clock). `rows`,
projections, quote census and priced-market counts are identical. No CBB defects found.

## Not run / open

* The CFB parity test is not yet listed in `.github/workflows/cfb-run-it.yml` (left alone to
  avoid colliding with concurrent runner branches); run it with the command above.
* No live provider calls were made; real-data differences (weather window, precip, travel,
  QB) are only shown structurally.
