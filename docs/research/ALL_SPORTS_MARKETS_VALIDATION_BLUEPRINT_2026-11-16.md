# All-sports / all-markets validation blueprint — 2026-11-16
Status: engineering research, not verified production model performance. Sports: NFL, CFB, CBB, NBA, MLB, PGA, NHL. Applies to every available market, including alternate lines, periods, props, combos, DFS and outrights.

## Newly inspected public GitHub repositories (readme evidence, NOT independently reproduced)
- https://github.com/Volodymyr4K/market-efficiency-lab — MLB/tour tennis: season-block walk-forward, nested holdouts, market benchmark, minimum detectable effect (MDE), negative results. Reports MLB +9.3% pooled ROI on 1,215 bets, but claims are third-party and must NOT become SportsEdge expectations or weights. Reports a previous +15% estimate fell after correcting selection bias.
- https://github.com/itzel-oca/sportcal — NFL: market-aware neural net reported 66.27% accuracy vs market 66.13%, but worse Brier 0.2149 vs 0.2122 and worse ECE 0.0217 vs 0.0128. A warning against selecting on raw accuracy.
- https://github.com/MirageGiri/SportsProps — NFL possession-level simulation, player usage, same-game correlation, injury redistribution; claims game-level ECE .023, log loss .601 vs market .598, negative -6% to -9.5% closing-line ROI. No authentic CLV and injury updates are not automatic.
- https://github.com/kshreyan/nfl-predict — immutable weekly prediction snapshots, separate results ledger, as-of test suite, explicit no-market-beating conclusion.
- https://github.com/stevopotpie/gridline — market-anchored regression, usage and weather; odds snapshots and weekly grading. Beware retrospective factor selection.
- https://github.com/SRock44/sports-prediction-model — multi-sport LightGBM quantiles, calibration, pinball loss, coverage; lacks its own database ingest and training table assembly.
- https://github.com/JacobiusMakes/awesome-sports-betting-data — curated vendor/dataset/tool index; not a model or evidence of profitable strategies.
- https://github.com/sportsdataverse/sportsdataverse-py — multi-league adapters; large API surface does not imply verified, permitted, point-in-time feeds.

## The non-negotiable experimental design
1. Register each experiment *before* evaluation: sport, market, period, feature set, target, target definition (including push/void), data snapshot cutoff, embargo, model code hash, training folds, holdout, selection threshold, and benchmark.
2. Save immutable decision-time rows: provider-verified observed/captured time, quote time, kickoff/tee time, full event/market/line/side, original American odds, normalized participant IDs, source and feature hashes. No reconstruction using later data. Hashes alone do not prove authenticity.
3. Evaluate **every** candidate including blocked and losing rows. Never fit a feature weight, edge threshold, staking rule or calibrator on the final test period. One-time untouched holdout and then prospective shadow ledger.
4. Use market-only no-vig benchmark, simple domain baseline, candidate, market+candidate. Report paired improvement and confidence intervals clustered by event and by week/season; MDE and effective sample size. Multiple testing requires correction/holdout discipline.
5. For probabilities: Brier, log loss, ECE and reliability, calibration slope/intercept. For count/continuous props: MAE, RMSE, quantile pinball and empirical coverage. For wagering research: ROI at actual *original* price, net units, drawdown, CLV only when matched TAKE and CLOSE are independently timestamped.
6. Simulate correlated legs from the same latent game/round/possession/plate-appearance draw; never multiply marginal probabilities without validated independence. Keep market-specific unsupported states visible.
7. No unit recommendations while PAPER/0u or issue #10 gates incomplete.

## Feature catalogue by sport (candidate only, all must be available as-of)
| Sport | Baseline | Candidate additions | Important join/validation |
|---|---|---|---|
| NFL | No-vig market + Elo | EPA/play, success rate, pace, QB, snap/route/target/carry shares, red-zone roles, weather, rest, injury availability | GSIS IDs, active status, pregame nflverse snapshot; separate side/total/TD/prop calibrations |
| CFB | No-vig market + season ratings | opponent-adjusted efficiency, returning QB, roster turnover, pressure, pace, injuries, travel | season/team/player ID, transfer mapping, scorebook cutoff |
| CBB | No-vig market + AdjEM/tempo | four factors, shot quality, 3PA variance, lineup minutes, rest, home-court, conference/tempo interactions | season/team IDs, pregame Torvik/Haslametrics snapshot, no current-game stats |
| NBA | No-vig market + minutes/rate | lineup on/off, exact-ID minutes, usage redistribution, possessions, rest, back-to-back, opponent matchup | NBA player IDs, official status as-of, minutes uncertainty and covariance |
| MLB | No-vig market + pitcher/lineup | starter quality, platoon xwOBA, projected PA, bullpen workload, park, weather, umpire if known pregame | MLBAM IDs, confirmed lineup/starting pitcher, pregame Statcast rolling features |
| PGA | Market outright baseline + player strokes-gained rolling history | SG OTT/APP/ARG/PUTT, course fit, field strength, tee-time/weather, round variance, cut/WD risk | official PGA/DP World golfer IDs, tournament/round/tee-time clocks, mutually exclusive placement/outcome consistency |
| NHL | No-vig market + team xG | goalie confirmation, 5v5 shot quality, special teams, TOI, rest, travel, line combos | NHL player IDs, as-of goalie status, overtime/60-minute vs incl-OT settlement |

## Numeric weight and threshold policy
- There are **no universal validated SportsEdge weights** for all sports and markets. Never copy another author's coefficients or hardcode a 30/70 or 70/30 market blend as established truth.
- Candidate shrinkage `p_final = w * p_model + (1-w) * p_market_novig` where `w` is learned separately for sport/market/period using earlier chronological folds only, constrained to [0,1], and compared with `w=0` (market only). If insufficient authentic samples, report `NO_VALIDATED_WEIGHT`.
- Continuous targets: model mean, quantiles, over/under probability from calibrated predictive distribution; period and alt-line outputs must be internally coherent. Fit dispersion and dependence on training folds, not the target game.
- Use numerical claims from third-party READMEs only as *hypotheses*. SportsEdge release thresholds must be preregistered with sample size, power/MDE, clustered uncertainty and forward evidence; do not optimize them on held-out wins.

## PGA-specific research plan (beyond merged #87)
- Source options: DataGolf (commercial, check permission), PGA Tour official leaderboard/shotlink access terms, OWGR historical rankings, weather forecast snapshots, official tournament field and tee times, authorized sportsbook quotes. Historical event outcomes alone are not enough for pregame feature snapshots.
- Build player round-level SG components, robust rolling estimates with sample-size shrinkage, course/weather conditional variance, hierarchical field simulation. One joint tournament simulation must price outright, top5/10/20, cut, matchup, 3-ball, round leader and score props consistently. Withdrawals and dead heats need explicit settlement policies.
- Validate by tournament-forward splits; cluster at tournament, not individual golfer-row; preserve all non-selected golfers. Reject retrospective field/tee-time/weather and any unavailable round-level price.
- No model probabilities or stakes until validated data and preregistered forward tests.

## Prioritized engineering work
P0: point-in-time receipts, player/event identity joins, duplicate quarantine, shared gate #10 and executable CI tests for every research suite.
P1: market-specific immutable prediction ledger + paired baseline and MDE/clustered uncertainty, genuine matched TAKE/CLOSE.
P2: NFL/CFB/CBB/NBA/MLB/PGA/NHL sport adapters and candidate models, with chronological feature ablations and a common settlement schema.
P3: same-draw joint simulations, all-market internal consistency, DFS lineup/inactives checks, risk/exposure engine only after promotion.
P4: nightly/weekly automation of authorized capture, grading, monitoring and deterministic phone card, with explicit NOT_CAPTURED/NO_MODEL/PAPER states.

This file is the handoff for ChatGPT and any future collaborator. Never claim that writing a blueprint has completed implementation or validated profitability.
