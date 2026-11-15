# SportsEdge

Multi-sport betting analytics: NFL, CFB, NBA, CBB, NHL and MLB, across every market (sides, totals, team totals, halves/periods, props).
Owner: Isaac (phone-only; free tools only). Repo: `bighauss/Sportsedge` (public).

## What "run it" means
Read these in order when researching a slate; **the repository has not been shown to generate a validated live betting card**:
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
| `engine/` | frozen **v5** `sportsedge_v5.py` (SHA-256 `72ccaad75b...`), legacy portable v2 for comparison, ratings/props v0.2 |
| `sportsedge/data/loaders.py` | Unified free-data loader (nflreadpy, sportsdataverse, pybaseball, nba_api) |
| `docs/data/` | nflverse guide + full data stack |
| `docs/research/` | Outside ruleset review, tracking-data survey, prompt libraries (Rusty_Bill, PlusEVAnalytics, themortalzeus) |
| `docs/handoffs/` | Agent handoffs |
| `docs/MIGRATION.md` | What came from where; what stays on Drive |

## Current status and safety
- **Engine of record:** `engine/sportsedge_v5.py`, adopted 2026-11-11 and restored unchanged in PR #5. Original R5 guards and research-only NFL lane are under `research/r5/`.
- New standalone model weights remain **untested starting values**. Even passing every synthetic CI check does not imply a verified betting edge.
- RUN IT v2.1 is a specification: the documented quarter-Kelly, 5u/day, 2u/game, 3u/theme, T-90 lineup locks, and evidence/CLV requirements are **not established as enforced end-to-end** by this repo. All standalone model outputs are **PAPER / 0u** until per-market promotion evidence exists.
- The read-only `research/audit/pregame_edge_audit.py` diagnoses top pregame projected edges, duplicates, quote ages, receipt hash formatting and longshots; it does not authenticate sources or place bets.
- Historical captures, daily run logs, historical graded results and private data remain in Drive. The old GitHub repository's contents and Git history cannot be reconstructed from a 404.
- Research sources include `docs/research/` and a separated prediction-markets watchlist. Never copy unreviewed external trading bot code into execution lanes or put credentials in GitHub.

## Tests
```sh
python models/cfb/test_cfb_model.py
python models/nba/test_sportsedge_nba_model.py
python models/mlb/test_sportsedge_mlb_model.py
python models/cbb/test_cbb.py
python models/nhl/test_sportsedge_nhl.py
python research/audit/test_pregame_edge_audit.py
```
CI runs the five sport suites, 87 additional R5 synthetic regressions, and 12 pregame evidence-audit tests. Betting calibration, source verification and real-world profitability require separate forward evidence.

