# Claude <-> ChatGPT sync (2026-11-15)

## Ground rules (both agents)
- One repo, one pipeline: bighauss/Sportsedge `main`. No private parallel versions; every change is a PR with tests.
- Engine of record: frozen v5 (`engine/sportsedge_v5.py`). DFS engine: `models/nfl_dfs/showdown_mc.py` (see `DFS_SAME_PAGE.md`).
- Inputs live in committed files, not chat. Same inputs + same seed = same numbers.
- RUN IT = all markets incl. props (README). Missing markets listed with a reason, never silently dropped.
- No invented probabilities, ownership, or quotes. Unvalidated output = PAPER / 0u.
- Before starting work, post a claim in NOTES (or an issue) naming the area so two agents don't build the same thing.

## Done today
- Claude: NFL DFS Showdown Monte Carlo (play-level, correlated, exact DK scoring, full legal-lineup enumeration, opt-rate) + PIT@CIN inputs/projections/tests; DK salary fetcher (untested; Actions workflow blocked until Claude app gets Workflows permission).
- ChatGPT: PRs #43-#48 (pairing validation, all-markets rule, NFL bridge, R4 tests, player-evidence integrity), nflverse/NGS forward capture, PR #52 odds intake (needs private key).

## Build queue (claim one at a time)
1. ChatGPT: merge its GitHub salary loader + tests into `models/nfl_dfs/` against `showdown_mc.py` (one pipeline).
2. Claude: generalize DFS to Classic (multi-game) + CFB/NBA; wire dk_auto salaries into game configs.
3. Claude: Monte Carlo game sim per sport feeding ALL markets (sides, totals, team totals, halves, player props) from one shared sim, so DFS and props use identical numbers.
4. ChatGPT: point-in-time data loaders (nflverse/NGS done) -> auto-build game JSON inputs (roles, targets, YPC) instead of hand entry.
5. Either: grading + CLV ledger for every market and DFS lineup, daily.
6. Either: phone card renderer (NE@DET Munich format) committed to repo, run by Actions.
7. Blocked on owner: Odds API key as a GitHub secret; Workflows permission for Claude app.
