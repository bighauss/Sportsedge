# SportsEdge

Multi-sport betting analytics: NFL, CFB, NBA, CBB, NHL and MLB, across every market (sides, totals, team totals, halves/periods, props).
Owner: Isaac (phone-only; free tools only). Repo: `bighauss/Sportsedge` (public).

## What "run it" means
For research, read these in order. This repo is **not a live betting system**. An actual slate requires independently verified odds, event identities, timing, model evidence and full risk gates:
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
| `engine/` | `sportsedge_v2.py` (legacy research engine, **not** the engine of record), ratings/props v0.2 |
| `sportsedge/data/loaders.py` | Unified free-data loader (nflreadpy, sportsdataverse, pybaseball, nba_api) |
| `docs/data/` | nflverse guide + full data stack |
| `docs/research/` | Outside ruleset review, tracking-data survey, prompt libraries (Rusty_Bill, PlusEVAnalytics, themortalzeus) |
| `docs/handoffs/` | Agent handoffs |
| `docs/MIGRATION.md` | What came from where; what stays on Drive |

## Status and test commands

- The adopted **v5** engine of record (Nov 11; SHA-256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`) remains in Drive and was not included in the Nov 15 baseline migration. `engine/sportsedge_v2.py` is **not** v5; no live v5 runner is integrated here.
- The five standalone sports models have **untested starting weights**. Tests below only validate synthetic examples and code paths, not price accuracy, positive EV, CLV, profitable performance, or model promotion.
- RUN IT v2.1 rules are binding policy specifications, not proven to be enforced by every script. Without independently verified capture and market-specific evidence, all model outputs stay **PAPER / 0u**. Never place wagers automatically.
- Review model changes on chronological holdouts before promoting markets; preserve historical receipts and archived cards.

```sh
python -m compileall -q engine models sportsedge
python models/cfb/test_cfb_model.py
python models/nba/test_sportsedge_nba_model.py
python models/mlb/test_sportsedge_mlb_model.py
python models/nhl/test_sportsedge_nhl.py
python models/cbb/test_cbb.py
```

The same commands are configured in `.github/workflows/synthetic-tests.yml` for CI. CI must be checked on GitHub before claiming a passing remote check.
