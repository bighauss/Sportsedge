# Public GitHub model gap audit — 2026-11-16
Status: RESEARCH ONLY. README claims are not independently reproduced. No model coefficients, odds or stakes changed. Complements `docs/research/PUBLIC_REPO_SCOUT_2026-11-15.md`.

## Evidence reviewed (public README, not code execution)
| Repository | Sport/markets | What to test or borrow conceptually | Limit |
|---|---|---|---|
| https://github.com/stevopotpie/gridline | NFL sides, totals, props, first TD | Market-anchored ridge, factor ablations, weekly grading, opening/closing snapshots; weather/usage candidates | Authors report 2018–25 walk-forward and acknowledge selecting factors on the same years; 2026 prospective test needed |
| https://github.com/kshreyan/nfl-predict | NFL ML/spread/total | Compare no-vig closing ML against Elo, logistic and blend; log loss/Brier/ECE and leak tests | Reported 4,162 games; market baseline Brier .2110, ensemble .2109: tiny gain, not verified here |
| https://github.com/TimVanC/nfl-usage-dashboard | NFL player usage | Target share, first-read, backfield, red-zone usage; nflverse/FTN/Sleeper ETL; versioned IDs | Forecast accuracy not established by README |
| https://github.com/johnshun001/nba-props | NBA points/rebounds/assists | Shift(1) rolling features, minutes model, fail-closed event mapping, settlement and drift tests | Reports test MAE points 7.16, rebounds 2.02, assists 2.02; explicitly NO ROI/CLV/probability calibration |
| https://github.com/SRock44/sports-prediction-model | NBA/WNBA/MLB/NFL/NHL/soccer/NASCAR | Per-target quantile models; walk-forward pinball/coverage/Brier; isotonic with later holdouts | Missing data ingest and training-table assembly; not turnkey |
| https://github.com/sports-data-hq/nfl-props-backtest | NFL props | Preserve open/close and original prices, settle pushes; keep raw vendor odds private | EndzoneAPI credits required; no free full-board assumption |
| https://github.com/emm5317/betbot | NFL/NBA/MLB/NHL ML | Append-only odds_history, event normalization, exposure circuit breakers | Implementation/ROI unverified |
| https://github.com/sportsdataverse/sportsdataverse-py | NFL/CFB/CBB/NBA/MLB/NHL + more | Shared typed ingestion adapters with provider-specific IDs, source clocks and immutable hashes | Beta 0.2.0b1; licensing, rate limits and API availability vary |

## Priority additions (all sports, all markets)
1. **Evidence plane before model complexity**: append-only authorized TAKE and CLOSE records with provider, independent book, event/player GSIS or league ID, market/period/line/side, odds, provider observed UTC, local captured UTC, kickoff UTC, raw payload hash and permission. Never publish raw private receipts. Independent-book claims require independent upstream chains, not two logos from one aggregator.
2. **Market-specific benchmark registry**: for every sport x market x period, preregister baseline, feature cutoff, model/version hash, training cutoff, evaluation horizon, decision threshold and failure rule. Always compare market-only, simple historical baseline, candidate, and market+candidate on later games. Report n, MAE for stat projections, NLL/Brier/ECE for event probabilities, pinball/coverage for quantiles, hypothetical original-odds ROI and authentic matched CLV when available.
3. **Usage before efficiency**: NFL GSIS-bound snap/route/target/carry/red-zone share; NBA exact-ID minutes + usage redistribution; CFB EPA and returning roster/starting QB; CBB AdjEM/tempo/roster turnover; MLB PA/lineup/pitcher/park/Statcast; NHL goalie confirmation/TOI/shots/xG. All features as-of decision time, never final box scores from the same game.
4. **Joint outcome simulation**: one event draw for ML/spread/total/team totals/periods/props/SGP and DFS; NFL first TD and 2+ TD need shared touchdown event draws, not independent marginals; NBA PRA and NFL rush+receiving must sum components from the SAME draw. Correlated exposure should be evaluated at portfolio level.
5. **Failure publication**: all games/markets including NO_DATA, NO_MODEL, NOT_CAPTURED, stale, identity mismatch, blocked; release candidate only after registered later-period improvement with uncertainty and minimum sample. Do not turn README-reported gains into SportsEdge weights.

## Numeric findings (third-party claims, NOT SportsEdge settings)
- Gridline reports NFL market-anchored spread 550-490 (52.9%) at a 1+ point disagreement, total 328-275 (54.4%) at 1.5+; notes post-hoc factor selection and Vegas lower margin MAE (9.81 vs 10.04 stats-only). These thresholds are research hypotheses, not adopted filters.
- kshreyan NFL ML claims market Brier 0.2110 vs blended 0.2109 on 4,162 games; gain of 0.0001 requires prospective significance testing.
- johnshun001 NBA props claims held-out MAE 7.16 pts, 2.02 rebounds, 2.02 assists; says probabilities uncalibrated and no ROI/CLV.
- Do NOT adopt universal model weights (30/70, 40/60, etc.) or usage half-lives from third parties without registered walk-forward ablations. Per-market shrinkage and weights must be fitted on earlier training windows only.

## Candidate data sources, by sport (check rights, access, timestamps)
| Sport | Free/public candidates | Core identities/features |
|---|---|---|
| NFL | nflverse/nflreadpy, FTN charting where permitted, official team inactives | GSIS, snaps, routes, targets, carries, EPA, weather, lineup |
| CFB | CFBD API (key/quotas), NCAA/ESPN official scorebooks | team season ID, opponent-adjusted EPA, QB, roster |
| CBB | Bart Torvik free accessible feeds, NCAA/ESPN, hoopR/cbbdata | team season ID, AdjEM, pace, four factors, rotation |
| NBA | nba_api/NBA Stats, ESPN, pbpstats | NBA player ID, minutes, per-minute rates, lineup/usage, injuries |
| MLB | MLB Stats API, Statcast/pybaseball, Baseball Savant | MLBAM player ID, lineup, PA outcomes, starter, park, weather |
| NHL | NHL api-web, MoneyPuck where terms permit, fastRhockey | NHL player ID, confirmed goalie, TOI, shots/xG, power-play |
| Odds | Authorized DK screenshots/exports; The Odds API under quota; independent licensed book feeds | Same event-market-line-side, original odds, timestamped open/take/close |

## Remove or quarantine
- Unvalidated NFL pace adjustment; do NOT delete history. Test as an isolated preregistered candidate before restoring.
- Independently multiplied combo prop or SGP probabilities, hand-set roles presented as measured, unsourced injury strings, fabricated market odds, screenshot-only implied independence, and published Kelly stakes on PAPER rows.
- Marketing claims of 60–90% hit rates or enormous ROI without point-in-time complete records.
- Auto-promoting models based solely on GitHub green CI, in-sample calibration or wins on retrospectively selected plays.

## Implementation backlog / acceptance
- P0: exact-head tests and guard/identity/provenance fixes; issue #10 Gates A–E still block OFFICIAL.
- P1: pregame source receipts and CLV matched triples; NFL usage-share GSIS build; market-by-market walk-forward with negative results retained.
- P2: NBA minutes and lineup model, MLB PA and NHL xG/TOI candidates, CBB/CFB historical calibration, shared correlated simulator.
- P3: deterministic card renderer reading prices and injury strings from verified source file, showing PAPER/0u and blocked reasons.

**Reproduction rule:** pin repository commit and dependency versions; run their tests and reconstruct reported tables before borrowing any numerical coefficient. Do not copy GPL-licensed code into SportsEdge without license review.
