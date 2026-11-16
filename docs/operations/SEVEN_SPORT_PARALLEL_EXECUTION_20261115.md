# Seven-sport parallel execution board (2026-11-15)

**Canonical project:** `bighauss/Sportsedge`. **Release:** every sport/market PAPER / 0u. This board is engineering scope, not a market certification or evidence that a live feed exists. PRs should stay small and separately tested.

| Lane | Deliverable and repo anchor | Immediate blocking evidence | Acceptance test |
| --- | --- | --- | --- |
| A / all seven | Authorized DK + independent second-book original quotes; `sportsedge/odds/` | No independently attested provider transport, exact upstream timestamp/identity or authorized BestBook export | Raw byte receipts, exact canonical line, independent chain and all offered/blocked family inventory |
| NFL | Frozen EPA/projection P-I-T artifacts, `models/nfl/`, `sportsedge/markets/` | Real weekly pregame inputs, authenticated odds, player prop/TD calibration, prospective grades | Preregistered holdout + matching frozen source/report hashes; no lookahead |
| CFB | Ratings/pace/injury as-of snapshots, `models/cfb/` | Source completeness and tested weights | Documented season cutoffs, chronology and forecast-versus-market grades |
| CBB | Torvik/CBBD PIT bridge, `models/cbb/` | **Original** Nov 9 496-side `picks.csv` and `run7_finals.json` raw bytes still not independently recovered; historical G-18 exact replay unresolved | Keep reconstructed 496-entry census separate; exact SHA/row counts and all win/loss/push rows, no retroactive rewrite |
| NBA | Team efficiency and per-player minutes/usage uncertainty, `models/nba/` | Confirmed lineups, minutes distributions, as-of source and prop calibrations | PIT minutes, opponent-adjusted projections and forward coverage by market |
| MLB | Statcast SP/bullpen/run distribution, `models/mlb/` | Confirmed SP/lineups, complete chronological training/holdout, settlement identity | SP/lineup time cutoff and run/prop distribution calibration |
| NHL | xG/goalie/TOI market kernel, `models/nhl/` | Verified goalies, TOI PIT and authenticated lines; not yet in five-sport research CLI | Explicit 60-min versus includes-OT rules and separate prop grading |
| PGA | DataGolf receipt and simulator path, `models/pga/` | Authorized DataGolf account + independent odds/real calibration | Observed raw provider data, event/round participant maps, frozen distribution/grade |
| C / all seven | Registered calibration, CLV and exact original-price grades; `sportsedge/validation/` | No independently verified forward cards / original matched closes | Three clean preregistered folds and 200 matched settled CLV triples per admitted market |
| E / all seven | Fail-closed risk/settlement/Truth Gate; `research/risk/`, `sportsedge/odds/card_gate.py` | Source and owner promotion signatures, genuine connected settlement | Zero admitted wagers without full A–E evidence, v2.1 + stricter v2.2 rules, market-family exclusions retained |

## Independence and sequencing

Run A, each of the seven model lanes, C, and E in parallel. Final gate promotion is **sequential per sport/market** only after A+B+C+D+E have independent receipts; passing an NFL game line does not open NFL player props or CBB spreads. Do not turn a sample model weight or synthetically passing fixture into a freeze of empirically validated predictions.

### Immediate issues to carry forward

1. Issue #10 stays OPEN until external source proofs are attached; free-tier aggregator quotes cannot substitute for independent DK+secondary chains.
2. [CBB PR #175](https://github.com/bighauss/Sportsedge/pull/175) is already **merged**; do not reopen. Its local CBBD response consistency checks do **not** authenticate upstream source publication. Original 496-side Nov 9 file still missing.
3. Preserve original 248-row board and 209-row printed-card evidence separately from reconstructed 496-entry grading; G-18 revised labels are retrospective only.
4. Freeze NFL/PGA/NHL and others as **research artifacts** with SHA-pinned code/config/input snapshots; when PIT inputs unavailable record BLOCK, not invented weights or grades.
5. No credential, private token, unpublished odds receipt or bankroll ledger in this public repository. Use protected private storage. Report precise denominator of covered, blocked and missing markets for every slate.

### Per-market promotion evidence checklist

A: authorized DK and separately independent primary raw quote chain with provider clock, dual identity and market inventory.  
B: as-of source hashes for every model input, source publication clocks, no future features.  
C: preregistered model/coefficients/fold boundaries, leak-free walk-forward with market baselines and all losses.  
D: authentic exact same-market opening/taken/closing receipts and settlement with realized price CLV.  
E: connected v2.1/v2.2 risk and settlement tests, 100 clean cards, five-day streak and signed owner promotion record.  
**Absent any item: PAPER / 0u, explicit failure reason.**
