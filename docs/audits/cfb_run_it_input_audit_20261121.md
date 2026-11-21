# CFB RUN IT — Step 1 input audit (2026-11-21)

Scope: source → transformation → model-input mappings in `models/cfb/cfb_run_it.py`.
The frozen model `models/cfb/sportsedge_cfb_model.py` is unchanged. Its SHA-256 is pinned in a test: `1f24cf1a…f735be`.
No weights were changed, no live capture was run and nothing was merged. The 2026-11-21 card on #408 stays research-only (PAPER / 0u).

## Source → transformation → model input

| Source field (CFBD) | Transformation in adapter | Model input / expectation | Verdict |
|---|---|---|---|
| `/ratings/sp` `offense.rating`, `defense.rating` (absolute, pts) | Subtract each field's mean across teams; drop `nationalAverages` row | `offense.rating` = pts vs avg (+ better), `defense.rating` = pts allowed vs avg (− better); `points = 28 + own O + opp D` | Sign and centering correct (hand test). **Defect fixed:** the summary row was not excluded before centering. |
| `/stats/season/advanced` `*.ppa` | Passed through | Per-play PPA; `pts = 28 + plays × (ppa − league ppa) + …` | Per-play units confirmed; points scale with plays (hand test). |
| `offense.plays`, `offense.drives`; `games` absent | **Before:** none → model fell back to `drives / 12` games. **Now:** point-in-time count of completed games before run time from `/games` | `games` → plays/game (tempo) and regression weight (k = 6) | **Implementation defect fixed.** At 13 drives/game, the fallback reads 10 games as 10.8 and understates plays/game by about 8% (fixture: 64.6 vs 70.0). Overtime plays are included in CFBD season totals. |
| Advanced fields used by the model (17) | **Now:** required. Any missing field for either team → game withheld | Model's `g(...)` would silently use the league mean | **Defect fixed** (was a silent substitute). |
| Player season stats `CAR/YDS`, `ATT/YDS`, `REC/YDS` | share = player count ÷ team `rushingAttempts` or `passAttempts`; eff = yds ÷ count | `share × volume × eff × opponent factor` | Numerator and denominator are the same team, season and category (hand test). Identity is still name-based; see step 2. |
| Season-stat cutoff | Games that kicked off before the run are withheld | — | Target game is excluded. **Unverified assumption:** CFBD's refresh time for season aggregates is not exposed, so stats could include games finished earlier the same day. |

## Trace (fixture, UCLA @ Michigan, corrected inputs)

plays/team 70.0 · ratings pts H/A 28.0 / 28.0 · matchup pts H/A 22.31 / 31.94 · HFA 2.5 → Michigan 26.41, UCLA 28.72, total 55.12.
Reproduce with `python -m unittest models.cfb.test_cfb_run_it_inputs`.

## What the posted 11/21 card shows (49 games with a full-game total)

- Model total minus market total: **+6.3 points on average** (market average 51.9).
- Ratings component: average total 58.2. SP+ is centred, so this is about `2 × 28 × tempo`. The model's fixed `LG_PPG = 28` baseline puts it above the market before any team information enters.
- Matchup component: average total 58.7, from the same baseline.

**Classification:** most of the over lean traces to the model's fixed scoring baseline. That is an **unvalidated modelling assumption, not an adapter defect**, and it is not changed here. The `drives/12` games fallback was a real adapter defect, but at realistic drive rates it lowered plays/game, so it pushed totals *down*, not up. Its live effect needs a live run to measure.

## Model assumptions flagged (not changed)

- `LG_PPG = 28` is fixed. It isn't tied to the captured season's actual scoring or to garbage-time-excluded stats.
- The sign of `fieldPosition.averageStart` assumes higher = better field position. CFBD's field meaning hasn't been checked against a live response.
- The `passingPlays.rate` share of plays sets volume; sacks and scrambles aren't split out.

## Still open

- Live before/after comparison: needs an approved live capture. The 11/21 private capture is encrypted.
- Steps 2–5: player ID joins, market-mapping re-check, probability construction, and parity with `cfb_paper_card`.
