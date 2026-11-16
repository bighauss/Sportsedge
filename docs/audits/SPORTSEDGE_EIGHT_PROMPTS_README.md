# SportsEdge | Eight-prompt quantitative foundation (2026-11-15)

**Status: RESEARCH / PAPER / 0u.** This is a standalone, read-only companion to `engine/sportsedge_v5.py`, not a change to the frozen engine, market admission, or bankroll policy. Python standard library only. No credentials, real sportsbook receipts, outcomes, or patient/private data are bundled. There is no claim of profitable or calibrated live predictions.

## 1. Architect: same controls, six sport-specific models

**Ten candidate variable families to test, *not* an asserted measured importance ranking** (rank each by held-out incremental log-loss / CRPS / Brier, separately for every market):

1. **Adjusted team strength:** NFL/CFB EPA/PPA; CBB/NBA possession-adjusted O/D; NHL 5v5 xG differential; MLB run-production and pitching quality.
2. **Pace / opportunity:** NFL plays and dropbacks; CFB possessions; basketball tempo; NHL shots/60; MLB projected plate appearances.
3. **Participant availability:** official active/inactive, starters, rotation, goalie, pitcher, lineup; *versioned as-of*.
4. **Expected playing time:** snap rate, minutes, ice time, pitching innings, batting-order PA.
5. **Usage / share:** targets, carries, shots, touches, usage rate, team share.
6. **Per-opportunity efficiency:** yards/attempt, pts/possession, rebounds/chance, saves/shot, K/batter.
7. **Opponent unit matchup:** scheme/defense/pace/park/possession-adjusted strengths frozen before game.
8. **Home / venue / weather:** home effect, altitude/park, wind/temp (publication timestamp required).
9. **Rest / travel / schedule:** days between games, back-to-back, travel distance, rotation carryover.
10. **Market benchmark:** comparable **pregame** no-vig line and price, paired by same book/line/period. Use as an explicitly separate market-augmented model, **never** leak closing lines to earlier forecasts.

**Historical free-source starting points:** NFL [nflreadpy](https://nflreadpy.nflverse.com/) / nflverse; CFB [CFBD](https://api.collegefootballdata.com/getting-started) (free access/API key subject to published limits) and sportsdataverse; CBB Bart Torvik free T-Rank and official NCAA results; NBA `nba_api` / NBA public stats and Basketball-Reference; MLB Statcast through `pybaseball`, MLB Stats API; NHL [MoneyPuck](https://www.moneypuck.com/data.htm) and public NHL stats. Check license before commercial use; MoneyPuck specifies free *non-commercial* use with attribution and restricted scraping. Free sources frequently contain **revised** past seasons and are **not** proof that a value was published before a particular prediction.

Baseline: team rolling average + opponent adjustment for game markets; lagged player game logs with playing-time × opportunity-rate × efficiency for props; paired as-of prices for market baseline. No market should inherit an unrelated score or prop distribution as a substitute. For each variable, freeze a training cut, establish `baseline_without_feature`, add exactly one feature using the same cut and hyperparameter policy, score on later events (Brier/log loss for binary, MAE/CRPS for continuous), bootstrap by event/week, and test another untouched forward window. Include failed and missing-feature rows, coverage delta, and sources-as-of. Use nested chronology, not shuffled CV. Treat 10 listed variables as hypotheses until measured.

**Leakage warnings:** postgame player stats, box scores, hindsight injury statuses, end-of-season adjusted ratings, retrospectively recompiled opponent strength, closing odds, sportsbook settlement state, retrospective player ID mappings, and source releases published after kickoff. A past game row by itself does not establish that its *revision* existed on forecast date.

## 2. Data quality inspector — use without altering evidence

Required CSV fields are the existing `research/audit/pregame_edge_audit.py` contract: `sport,event_id,period,market,side,price_american,p_model,model_asof_utc,captured_utc,game_start_utc,quote_sha256,model_sha256`. Additional strongly recommended fields: `line,book,source,player_id,player,feature_available_utc,source_published_utc`. Exactly one provider quote per row, original byte receipt stored privately and separately, immutable event date identity. Run:

```bash
python quant_foundation.py audit /private/locked_picks.csv \
  --report /private/locked_picks_audit.json \
  --cleaned /private/locked_picks_normalized.csv
```

Both destinations are **create-only**; the input is read-only. All rows are retained; whitespace/unicode-sign edits appear in `corrections`, and missing IDs, timestamp problems, duplicate quote identity, future sources, suspicious feature names, invalid odds/probabilities, player-name/ID conflicts, missing/invalid hash formats, and unverified publication timing appear in `issues`. `PIT_PROVENANCE_NOT_SUPPLIED` is a finding, not proof of leakage. A correctly formatted hash is *not* proof of provider authenticity or historical existence. This is a first-pass validator. It also flags conflicting event start times/team mappings and robust median-absolute-deviation statistical outliers in supported numeric fields when at least 20 comparable observations exist. Outliers are flagged for review, not deleted or automatically corrected; this is not exhaustive sport-stat-specific anomaly classification or a fix for mismatched IDs.

**Historical incident requiring clean-room replay:** Drive's `EDGE_AUDIT.md` reports that Nov 9 CBB team totals were graded by *game totals* (180 rows, 70 labels flipped on correction). `run4_F_grading.md` shows 496 price rows with mirrored opposite sides (190 W / 190 L / 116 ungraded at that snapshot); those are not 496 independent wagers. The incident is evidence of grading and denominator risk, not proof of a positive betting ROI. The report is existing audit evidence, not a reproduction performed by this module.

## 3. Player prop builder — no fabricated inputs

`player_prop_baseline(logs, player_id=..., asof_utc=..., projected_minutes=..., line=..., side=...)` accepts supplied historical actual stats, minutes, opportunities and two independent *actual publication* timestamps. It calculates lag-only observed opportunities/minute, observed efficiency/opportunity, the projected mean and a paired historical-rate empirical distribution, median, win/push/loss probabilities. It requires at least three pre-freeze logs. Neutral opponent multipliers of 1 are explicitly documented; optional non-neutral adjustments **must** be sourced outside this module. No claims of fitted Poisson/negative binomial dispersion, SGP correlation, validated tails, confirmed active players, injury effects, or independent sample size. An extreme output is **not** an actionable edge.

Market-specific distributions for future candidate modules:

| Markets | Candidate distribution and needed validation |
| --- | --- |
| ML, spread, total, team total, alt line, halves and periods | Calibrated joint **score** scenarios; separate regulation/OT and period tests, settlement-specific pushes |
| NFL/CFB passing/rushing/receiving and NBA/CBB points/rebounds/assists | Count: negative-binomial or discrete empirical; yards: positive/heavy-tailed empirical; minutes/volume modeled first |
| TD, first TD, 2+ TD, first basket | Event-level opportunity/rate process with player participation, team scoring, censoring, share and dependency checks |
| MLB hits/K/TB/HR/F5/NRFI | PA/IP exposure; batter/pitcher count or event sequence; park and starting-lineup evidence |
| NHL SOG/goals/points/saves | Time on ice, shots/60, conversion and goalie shot environment |
| SGP/parlay | **Joint simulation** with audited dependence and posted bet-specific price; product of marginal probabilities is not enough |

When distribution fit, official roster, paired quote, or provenance is missing: status `NO_MODEL`, `NO_PROVENANCE`, `NO_LINE` or `PAPER_HOLD`, not synthetic confident EV.

## 4. EV calculator — correct payout and pushes

`american(-110)` returns decimal 1.90909 and **raw** implied probability 0.52381. `devig_two_way(-110, -110)` returns overround ~0.047619 and proportional no-vig 0.5/0.5, only for a correctly matched binary two-way market. More complex books need market-specific methods and acceptance checks. No-vig is an estimated reference probability, not a different payout.

`ev_per_dollar(p_win, p_push, odds)` uses `p_win * net_profit_for_$1 - (1 - p_win - p_push)`. Example: **+150** with p(win)=0.45, p(push)=0.05, p(loss)=0.50 gives **+$0.175 per $1 risked**. Example: **-110** with p(win)=0.55, no pushes gives **+$0.05**. Those are hypothetical illustrations, not SportsEdge edges. `probabilities_from_samples` counts values exactly equal to an integer line as pushes. Quarter-lines, half-wins, voids, dead heats, fees and exchange commissions beyond the optional profit fee require explicit settlement adapters. The updated `odds_in_format` calculator explicitly accepts American, decimal or fractional formats; the default `ev_per_dollar` behavior is still American. `settlement_ev` supports W/L/P/HW/HL and `quarter_line_probabilities` can split empirical quarter-line draws into half-stakes. Do not auto-detect or silently mix formats. Dead-heat or sport/book-specific void rules remain unsupported.

## 5. Walk-forward backtesting

Establish **as-of** input freezes, preregistered eligibility rules and exact model hash. Proposed protocol: train on seasons through T, calibrate on an immediately later validation block, select hyperparameters **once**, freeze, evaluate next untouched month/week; roll forward by date while never reusing future releases. Refit only from prior published evidence. Benchmark against rolling mean/market no-vig. For every in-scope sport/market, record evaluated rows, priced rows, selections, qualified rows, unpriced rows, blocked reasons, missing finals, and official results. Never duplicate mirrored markets as bets or promote synthetic row counts into sample size. Report ROI, net units, calibration, Brier/log loss, Wilson/clustered uncertainty, CLV coverage, market, month and *event-clustered* drawdown. Do not tune on held-out results. Existing merged PR #71 addresses disagreement/calibration. `quant_walkforward_baseline.py` provides a fixed Beta(1,1) smoothed prior-outcome baseline trained strictly on results whose final publication precedes each forecast, segmented by exact sport/market/period/line/player. It does **not** refit v5, which still needs a separate preregistered prospective experiment. Keep other NFL chronological research separate rather than claiming its results validate these modules.

## 6. Error and model-improvement analysis

Track signed residual `actual - predicted_mean` for each valid graded observation. Report by sport, market, player ID, team/opponent, direction, projected bin, price bin, time and source. Identify small-sample volatility with group/event-clustered intervals and minimum sample flags (e.g., fewer than 30 unique events). Mark **hypotheses** (minutes overprojection, QB volume, pace, home edge, goalie availability, starter fatigue, alt-line tails) and hold each proposed fix behind an unseen-date shadow test and preregistered acceptance criterion. Never rewrite historical predictions or grades.

## 7. Performance ledger — qualified selections only, never retrospective choices

Supplementary CSV columns: `qualified` (explicit 1/0), `selection_id`, `qualification_rule_sha256`, `outcome` (`W/L/P`), `result_source`, `feature_available_utc`, `source_published_utc`, `book`. Run:

```bash
python quant_foundation.py ledger /private/locked_picks_and_finals.csv \
  --report /private/qualified_paper_performance.json
```

One **risked** unit per qualified, independently graded selection. The report returns net units, decided win rate, ROI on all graded 1u bets including pushes, drawdown, market breakdown, and a reason for every qualified row not certifiable. Unqualified rows never enter the wager denominator; unverified qualified rows are **not** counted as a loss or quietly discarded: they remain exposed in `unverifiable`, so ROI is explicitly provisional, not audited final. Preserve raw snapshots in an append-only, separately hash-anchored archive; receipt hashes and Git commit histories alone cannot prove historic source authorship. This diagnostic does not use closing prices to settle original-price ROI.

## 8. Automation architecture (no scheduler activated)

**Admin only**, at scheduled intervals: (1) fetch source assets using a per-provider daily quota/cached ETag; (2) store raw bytes with SHA, observed time and provider publish time in private storage; (3) validate event/roster/player maps and pregame timestamps; (4) compute immutable versioned forecasts with unchanged formula SHA; (5) record each independently captured price and original quote; (6) gate eligibility while displaying failed families; (7) write a create-only card/decision ledger **before kickoff**; (8) verify final scores/settlement separately; (9) publish sanitized, read-only public dashboard (no refresh/capture API on dashboard path).

Bound cost with per-provider max calls/hour, 429 exponential backoff with jitter and `Retry-After`, batched history once/day and slate deltas near lock, cache TTL per source, a circuit breaker for stale timestamps, zero wagers on failures, and alerts for missing market categories, late roster updates, lost feed, unsupported settlement, missing as-of release. Never let the dashboard trigger an unmetered public API refresh. Do not automate formula or promotion-policy changes without owner approval.

### Initial acceptance milestones

- [x] A *read-only* reusable CSV quality inspector, explicit odds formats, quarter-line/half-win settlement arithmetic, empirical player baseline, release-aware naive walk-forward baseline, and paper 1u ledger with synthetic tests.
- [ ] Private historical raw snapshots materialized with exact files, date range and proven release timestamps.
- [ ] Data reconciliation of Nov 9 G-18 and all past correlated rows to original immutable card.
- [ ] Real out-of-sample walk-forward baselines and reliability reports **per market**, confidence intervals, source receipts and execution constraints.
- [ ] Source-side authenticated capture proof and accepted per-market live status.

**No historical ROI or live pick is certified by this document.**
