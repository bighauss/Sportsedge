# SportsEdge

Multi-sport betting analytics: NFL, CFB, NBA, CBB, NHL and MLB, across every market (sides, totals, team totals, halves/periods, props).
Owner: Isaac (phone-only; free tools only). Repo: `bighauss/Sportsedge` (public).

## What "run it" means
Read these in order, then price the newest board:
1. `docs/rules/RUN_IT_STANDARD_v1_NE-DET.md`: base pipeline (Munich NE@DET run)
2. `docs/rules/RUN_IT_STANDARD_v2_ALL_SPORTS.md`: deep per-sport models (wins where it overlaps v1)
3. `docs/rules/addendum_NFL_NextGenStats.md`, `docs/rules/addendum_CFB_CBB.md`
4. `docs/rules/RUN_IT_V2_1_MANDATORY_RESTORATION.md`: binding. Quarter-Kelly sizing; caps of 5u/day, 2u/game and 3u/theme; confidence tags; 90-minute locks; kill/reprice; CLV stop; prop minimums; audit footer
5. `docs/data/DATA_STACK.md`: free source hierarchy per sport

## Layout
| Path | What |
|---|---|
| `docs/rules/` | RUN IT standard, addenda, v2.1 restoration, corrections handoff |
| `docs/models/` | Per-sport model READMEs (CFB, CBB, NBA, NHL, MLB) |
| `models/<sport>/` | Per-sport model code + tests (Python standard library only) |
| `engine/` | `sportsedge_v2.py` (portable engine of record), ratings/props v0.2 |
| `sportsedge/data/loaders.py` | Unified free-data loader (nflreadpy, sportsdataverse, pybaseball, nba_api) |
| `docs/data/` | nflverse guide + full data stack |
| `docs/research/` | Outside ruleset review, tracking-data survey, prompt libraries (Rusty_Bill, PlusEVAnalytics, themortalzeus) |
| `docs/handoffs/` | Agent handoffs |
| `docs/MIGRATION.md` | What came from where; what stays on Drive |

## Status
All weights are untested starting values. Grade every card (stake units, CLV, Brier/log loss). Refit only after a chronological walk-forward on 100+ graded plays per sport. Never place wagers automatically.
