# SportsEdge

Multi-sport betting analytics: NFL, CFB, NBA, CBB, NHL and MLB, across every market (sides, totals, team totals, halves/periods, props).
Owner: Isaac (phone-only; free tools only). Repo: `bighauss/Sportsedge` (public).

## Permanent owner directive: RUN IT = ALL MARKETS, every time

**No game-lines-only interpretation is permitted.** Unqualified `run it` requests the full scheduled slate across NFL, CFB, CBB, NBA, MLB and NHL; `run it NFL` requests all NFL markets, not just full-game sides/totals. A named sport narrows **sport scope only**, never market scope. A named game narrows **event scope only**, never market scope unless the owner explicitly requests a particular market.

For **every** scheduled/in-scope game, enumerate and attempt capture of **all offered market families**: full-game ML/spreads/totals, team totals, halves, quarters, alternate lines and totals, period and team markets, every available player-stat prop (passing/rushing/receiving/completions/attempts, etc.), TD/first TD/2+ TD, game specials, singles, SGP and other sport-specific categories (NBA/CBB player props and first basket, MLB pitching/hitting/innings, NHL goals/shots/saves and goalie/skater props). Do not equate a player-prop X+ ladder with a two-sided main line.

A market that is not offered, not captured, not independently modeled, identity-unbound, stale, live/closed, not supported by current software or otherwise fails proof must **stay visible in the market-by-market inventory** with an explicit reason: `NOT_OFFERED`, `NOT_CAPTURED`, `NO_MODEL`, `NO_PROVENANCE`, `UNSUPPORTED`, `LIVE_OR_CLOSED` or a more specific reason. Never silently replace missing prop, TD or SGP model evidence with a full-game score projection or imply that absence from a card means absence of markets. Never invent probability, EV, stars, joint probabilities or stakes.

Separate **market coverage** from **wager eligibility**. Display research-only diagnostics and all failures, but retain `PAPER / 0u` without market-specific forward acceptance, authenticated quotes, complete identities, source lineage and calibration. A run is not "full coverage" merely because full-game spreads, totals and ML are priced. The runner must disclose its observed sport/event/market-family coverage and incomplete-source limitations, including unsupported NHL support in any five-sport research CLI.

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

