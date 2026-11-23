# NFL canonical runner — PROPOSAL (needs Isaac approval)

## Today: three paths
| Path | Margin | Total | Pricing |
|---|---|---|---|
| Drive `sportsedge_nfl_wk11_run_v3.py` | ratings-only | regressed season stats | plain normal |
| `engine/sportsedge_v5.py` | from board home/away_proj | sim | v5 sim + power devig |
| `engine/run_nfl.py` (PR #472, unmerged) | wraps v5 | wraps v5 | 30/70 model/market blend, 6-pt per-quote hold, prob guard 1.5x / 0.67x / 12pp, MODEL_ONLY split |

Same lines can give different plays depending on which script an agent picks. That is the bug.

## Proposal: one path
1. **Projections builder** -> `projections.csv` (home,away,home_proj,away_proj). Must use season stats, pace, injuries/inactives, travel, weather (RUN IT STANDARD). The v3 ratings-only margin is retired.
2. **`engine/nfl_build_board.py projections.csv lines.csv board.csv`** -> v5 board, `team` filled on every prop, rejects yardage lines < 1.5 and implausible two-sided pairs (de-vig outside 3-97%), prints every reject.
3. **`engine/run_nfl.py board.csv`** -> card (v5 underneath, PR #472 guards on top).

Nothing else prices NFL. The Drive v3 script is kept read-only for reference.

## Props
Today prop mean = market mean x (model total / market total)^elasticity, i.e. a shaded copy of the market. Challenger in `research/nfl_props_usage/` (usage x share x efficiency) is a research lane only until it shows value against real prop lines.

## Not changed
`sportsedge_v5.py` and `run_nfl.py` are untouched. PR #472 must merge first for step 3.
