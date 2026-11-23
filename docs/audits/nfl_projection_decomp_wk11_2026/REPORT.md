# NFL projection decomposition — Week 11 2026 (v3 run) — read-only

Generated 2026-11-23 by Claude. No model, weight or engine change. Script: `decomp_wk11.py` (same folder).

## Evidence inventory
| Item | Source | Status |
|---|---|---|
| Run script with inline inputs (lines, prices, season PF/PA/G) | Drive `sportsedge_nfl_wk11_run_v3.py` (created 2026-11-22 14:52 UTC, before kickoffs) | Complete |
| Engine-consumed projections (home margin M, total T) per game | `note` column of Drive `sportsedge_nfl_wk11_v3_graded.csv` / `_all_candidates.csv` | Complete (1 decimal) |
| Ratings component internals (`sportsedge_ratings_local.R`, games.csv, fit date) | not saved | **Unavailable** |
| Season-stats component | recomputed from inline S, k=8, LG=22.5 | Complete, reproduces saved T to <=0.05 |
| Per-side settlement (W/L/P) | graded CSV | Complete for 11 games, CIN@WAS pending |
| Final scores | not in artifacts | **Unavailable here** (grading used ESPN; not archived) |
| Model version / seed | v3 script, closed-form normal pricing (no sim, no seed) | Complete |

Classification: **11 games partial** (engine input + stats component + settlement; ratings internals missing), CIN@WAS partial/pending. This is a retrospective reconstruction from artifacts saved before kickoff, not a full frozen decomposition.

## What the Week 11 v3 pipeline actually did (from the script)
- **Margin** = ratings component only: `Mr = project(R, home, away)`. The season-stats half was **not** used for the margin.
- **Total** = season-stats component only: `Tf = avg(home PF, away PA) + avg(away PF, home PA)`, each regressed with k=8 toward 22.5. Ratings total not used.
- So the RUN IT STANDARD's "50% ratings + 50% stats" blend was **not** what ran: each output came from one component.
- Pricing: normal, margin SD 13.5, total SD 13, 1H = 0.5 x full game, SD 9.5. Not engine v5.

## Results (12 games, market = DK home margin / total in the same capture)
| Measure | Value |
|---|---|
| Slope, engine margin on market margin | **0.71** |
| Slope, stats-component margin (regressed k=8) on market | 0.37 (not used) |
| Slope, stats margin unregressed on market | 0.69 (not used) |
| Mean abs engine margin vs market | 5.4 vs 7.5 |
| Slope, engine total on market total | **0.19** |
| Mean engine total minus market total | +0.4 |
| Big-spread bucket (abs market margin >= 7, fixed before looking): n=5 | engine keeps 65% of market margin; favorite covered 4 of 5 |

## Findings (descriptive, n=12; not a validated cause)
1. Margin compression in Week 11 came from the **ratings component alone** (slope 0.71). Its internals were not saved, so ridge vs. prior vs. recency cannot be separated yet.
2. **Totals are far more compressed than margins**: engine totals ranged 43.2-48.3 while the market ranged 37.5-54.5 (slope 0.19). The k=8 regression plus averaging offense/defense pulls every game toward about 45. This is what produced the large "edges" on extreme totals (e.g. CIN@WAS Under 54.5 at +40% raw EV, PIT@PHI Over 37.5, LV@DEN Over 40.5).
3. The documented 50/50 blend is not the code path that produced the card. Either the documentation or the script needs to change, by owner decision.
4. n=12 in one week: no conclusion about accuracy; final scores are needed to say whether the market or the model was closer.

## Next (prospective capture, starting with the next run)
Save per game, timestamped before kickoff: ratings output (home/away, off/def/pace, games.csv hash, fit date), stats output, combination weights actually used, engine inputs, market no-vig probabilities, final scores. Then repeat this report with finals and compare margin/total MAE: engine vs market vs each component, same games.
