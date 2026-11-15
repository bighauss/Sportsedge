# Model validation and migration audit — 2026-11-15

## Evidence categories: do not conflate
| Track | Verified work | Cannot claim |
| --- | --- | --- |
| Git recovery | PR #1 / PR #2 / PR #3 merged; PR #5 frozen v5 source and source guards merged | Complete old repository Git history |
| Synthetic model tests | CFB, NBA, MLB, NHL, CBB tests pass in CI | Durable positive EV or accurate fair odds |
| R5 research guards | 87 synthetic regression assertions pass independently of private captures | Real-time DraftKings bookability or authenticated closes |
| Historical CFB forecast | Prior handoff reports MAE improvement on historical fold data | Market-facing spread/totals betting edge or CLV |
| v2.1 policy | Written quarter-Kelly, 5u/day, 2u/game, 3u/theme, T-90 lock, prop minima, win/push/loss sizing, CLV controls | Proof every standalone model enforces the policy |

## Highest-priority unresolved gates
1. **Authentic quote receipts and event identity.** Hashes alone prove byte stability, not a bookmaker observation. Every quote must bind book, market, side, line, event, period, player ID, source and observation timestamp. Prevent duplicates across source formatting variants and event dates.
2. **No-lookahead validation.** Save model code hash, feature publication times, model-as-of time and exact pregame prices. No actual score, closing odds or later injury update may enter earlier projections.
3. **Top-20 extreme edge audit.** Rank using **only** valid pregame frozen predictions; explain each model probability and deviation from no-vig market, source, player identity, data availability and line freshness. Winning results do not validate estimates. For +400-and-higher odds retain devig-method sensitivity review.
4. **Calibration and walk-forward.** Compute Brier, log loss, reliability bins, spread/total residuals and comparisons to unchanged market baselines. Lock training and evaluation windows; record all losses, pushes and excluded rows. Analyze bias by sport, market, team, price, direction and time.
5. **Realistic EV and CLV.** Preserve original prices, vig, pushes and offered limits; compare matched exact closing market/side/line. Include fees/commissions where relevant. Record coverage failures rather than imputing closes.
6. **Correlation and bankroll controls.** Explicitly test all v2.1 caps and quarter-Kelly using modeled win/loss/push outcomes, portfolio theme exposure, game clustering, and SGP joint-price evidence. Without a verified ledger and stake denomination, 0u.
7. **Forward acceptance.** Require preregistered forward logs, independent capture source, rule/version lock, evaluation date and per-market sample count before any upgrade from PAPER.

## Read-only tool
`python research/audit/pregame_edge_audit.py /path/to/locked_snapshot.csv --top 20 --output /path/to/new_report.json`

Required CSV columns are defined in the module docstring. The tool **does not write to source files**, refuses to overwrite reports, flags missing receipt hash formats, stale/late quotes, duplicates and unresolved longshot cases; it only computes unvigged *single-price implied probability* and raw binary EV on eligible rows. It **does not independently authenticate a hash, remove bookmaker margin, handle push EV, or authorize betting**. Do not use its diagnostic ranking as a live betting card.

## Public repository boundary
Preserve prior cards/Drive board-close captures/graded results, API keys, personal data, relay logs and large archives outside this public repository. For a confidential audit use a local, private or access-controlled workspace. Research scripts and README information are safe only after scanning for credentials and license issues.
