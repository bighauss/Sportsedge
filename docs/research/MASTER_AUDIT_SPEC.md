# SportsEdge Master Audit Spec, implemented (v1.0, 2026-11-21)

Sources: Theo (@AllTheo) 50 prompts, Rusty_Bill's 8 build prompts, his 8 audit prompts and 5 standalone prompts, and PlusEVAnalytics' largest-edge loop. Overlaps are removed and each item maps to code in `research/audit/master/`.

The code uses only the Python standard library. It is a **read-only audit layer**. It never imports or edits `engine/sportsedge_v5.py`.

## Four hard rules: how the code enforces them
| Rule | Enforced by |
|---|---|
| 1. No invented advantages | `projections.AdjustmentRegistry`. Any adjustment applies 0 points unless it is registered with n ≥ 200, \|effect\| ≥ 1.96·SE and an out-of-sample confirmation. Motivation, revenge, narrative, sharp money, trap lines, momentum, public fade, rivalry, look-ahead and must-win are `BLOCKED: NARRATIVE_UNQUANTIFIED` by default. `props_corr.over_under`/`prop_projection` raise an error rather than invent a missing SD or game log. |
| 2. No data leakage | `audits.leakage_audit` / `assert_no_leakage` check pred_ts < kickoff, odds_ts ≤ pred_ts, every input ts ≤ pred_ts, and that no postgame fields are used as inputs. `audits.point_in_time` filters training rows. `pipeline.ledger_append` refuses rows logged after kickoff. |
| 3. No unverified +EV | `pipeline.run_gates` sets the status: an EV is shown as PASSED only after leakage, freshness, data-quality, large-edge and calibration-bucket checks. All odds-module EVs are only candidates. |
| 4. No silent model changes | Nothing here writes to the engine. `stats.platt_fit` only *recommends* a recalibration, fit on holdout data. `audits.append_only_check` flags any historical row that was removed or rewritten. `pipeline.row_hash` and `grade()` detect edited ledger rows. |

## Module → code map
| Spec | Function(s) | Prompt sources |
|---|---|---|
| P1.1 Largest-Edge Stress Test | `audits.largest_edge_stress` (top N edges; flags leakage, stale odds, missing/unmapped inputs, edge > 10%, prob ratio, drivers, expected vs actual wins, cross-pick patterns, `converged`) | PlusEV; Rusty Largest Edges / Back-test Edges / Model Review |
| P1.2 Leakage Detective | `audits.leakage_audit`, `assert_no_leakage`, `point_in_time` | Rusty T2#1, T1#1 |
| Data quality inspector | `audits.data_quality` (missing values, duplicates, inconsistent IDs, bad dates/odds/probs; logs every correction, deletes nothing) | Rusty T1#2 |
| P1.3 Calibration | `stats.calibration_table` (5% buckets, Wilson CI, OVER/UNDER/SMALL_SAMPLE), `brier`, `log_loss`, `ece`, `reliability_svg`, `platt_fit` (recommendation only) | Rusty T2#3, Theo 26–31 |
| P1.5 Performance / backtest / versions | `stats.performance` (flat 1u, losses kept, ROI, drawdown, streaks, Sharpe), `stats.bootstrap_roi` (resamples whole games so correlated bets aren't treated as independent; gives P(ROI ≤ 0)), `audits.backtest_audit` (prospective vs retrospective by rule activation time), `audits.append_only_check`, `stats.edge_decay` | Rusty T1#5, T1#7, T2#2, T2#7, T2#8; Theo 28, 31, 41–45 |
| P1.6 Bias hunter | `audits.bias_breakdown` (by player/team/opponent/market/side/edge/projection range/month, with 95% CI and a repeatable flag), `audits.market_disagreement` (pregame only, ROI at original odds, Wilson CI, overconfidence slope, MODEL_WEAKNESS / SMALL_SAMPLE flags) | Rusty T1#6, T2#5, Market Disagreement; Theo 27 |
| P2 Independent projections | `projections.power_rating`, `fair_spread`, `pace_total` (shows its math), `cover_prob`, `total_prob_over`, `Elo`, `fip`, `red_zone_margin`, `blend`, `drop_contradictions` | Theo 1–3, 7, 26, 29, 47, 48 |
| P3 Props, usage, correlation | `props_corr.over_under` (normal/Poisson/negative binomial, with pushes), `prop_projection` (opponent factor shrunk by sample size), `usage_redistribution` (historical vs prior labelled), `joint_hit_rates` (phi, lift, Brier against an independence baseline), `effective_n`, `portfolio_exposure` (Gaussian copula), `sgp_check` | Rusty T1#3, T2#6, Joint Probability; Theo 22, 36–39 |
| P4 Fair odds / EV | `odds.*`: conversions, overround, `no_vig` (multiplicative/additive/power/Shin), `ev_per_unit` (push and commission), `breakeven_prob`, `kelly_fraction`, `line_shopping`, `alt_line_value` (empirical margin distribution), `parlay`, `odds_report`; `audits.ev_inspector` (best book vs benchmark book, stale or unavailable lines) | Theo 8–13, 46; Rusty T1#4, T2#4 |
| P5 Situational | `projections.schedule_factors`, `weather_factors`, `injury_impact` → points come only from `AdjustmentRegistry` evidence | Theo 4, 14–19 |
| P6 Bankroll / exposure | `odds.kelly_fraction` (full/½/¼, recommendation only), `stats.bankroll_sim` (includes a "true edge is half" test), `stats.streak_probability`, `props_corr.portfolio_exposure` | Theo 20–25, 43 |
| P7 Live / prediction markets | Research lane only. Uses the same `odds`/`stats` helpers; there is no live pipeline (as the spec requires). | Theo 32–35, 49 |
| Uncertainty: sim count + spread | `uncertainty.sim_noise_check` (flags picks where sim noise > 10% of edge, gives sims needed), `sim_convergence` (seed × count test), `dispersion_audit` (z-score SD → share of real spread used, interval coverage, extreme-probability share, SD multiplier fit on earlier half / validated on later half, recommendation only) | Owner posts 2026-11-21 |
| Feature-group ablation | `ablation.ablation` (walk-forward, refit without each variable group, paired-bootstrap CI on holdout Brier change → KEEP_HELPS / SIMPLIFY_CANDIDATE; recommendation only; any model via `fit_fn`) | Owner post 2026-11-21 |
| P8 Daily RUN IT gates | `pipeline.freshness`, `run_gates` → candidates (ranked by EV) + blocked list with reason codes, `card_view` (price, win %, EV, stars, flames; no status labels), `ledger_append` (append-only, hashed), `grade`, `postgame_report` (grades blocked picks too) | Rusty T1#8; Theo 50 |

Every candidate carries the fields in `pipeline.REQUIRED_OUTPUT`: model_prob, fair_odds, edge, EV, best price/book, uncertainty, price_ts, audit_status, reason_codes, correlation_flags, input_timestamps.

Some prompts are reasoning prompts rather than math: Theo 5, 6, 11, 16, 18, 23, 25, 33–35, 41. Their quantifiable parts are covered: public bias ↔ blocked narratives, tilt/streaks ↔ `streak_probability`, autopsy ↔ `postgame_report`. Any narrative claim stays blocked until it is registered with evidence.

## How to run (phone-friendly)
- **GitHub Actions → master-audit → Run workflow** (once the workflow file is installed: the GitHub app couldn't write to `.github/workflows/`, so copy `docs/research/master-audit.workflow.yml` to `.github/workflows/master-audit.yml` in the GitHub web editor). Point `file` at any prediction JSON/CSV in the repo. The full report downloads as the `master-audit-report` artifact.
- CLI: `python -m research.audit.master <leakage|quality|largest|calibration|bias|disagreement|backtest|bootstrap|correlation|gates|postgame|simnoise|dispersion|challenge|full> FILE [--rules rules.json] [--history graded.json]`
- Tests: `python research/audit/master/test_master_audit.py` (27 synthetic tests).
- **Universal Model Challenge** (Rusty's every-model prompt): `python -m research.audit.master challenge FILE [--rules rules.json]` runs every check and returns issues ranked by severity, each with how to test the fix on unseen data. It changes nothing.

**Engine wiring (NBA / CBB / CFB, game lines + props):** `python -m research.audit.master.engine_adapter <nba|cbb|cfb> <sport>_card.csv --run-ts <ISO> [--games games.csv] [--results results.csv] --out rows.json` turns the RUN IT card each engine already writes into audit rows (props parsed into player + OVER/UNDER, decimal price → American, kickoff from games.csv, optional grading) and prints coverage by sport and market family so it's visible that props are included. Then run `challenge`, `gates` or `full` on `rows.json`. Default judges `model_p`; `--prob blend` audits the blended probability instead. Engines are read, never edited.

**CLV removed (owner ruling 2026-11-21):** this layer does no closing-line value tracking or reporting (Theo 30 dropped).

## Gap matrix (next step)
| Module | Status in this PR | Evidence still required |
|---|---|---|
| P1.1–P1.6 | Implemented as an audit layer | Run it on real Drive ledgers with true pred/odds timestamps |
| P2 | Reference/challenger calculators | Measured HFA/K-factor/SD per sport, fit walk-forward |
| P3 | Distributions + correlation engine | Historical prop SDs; joint hit-rate data per pair |
| P4 | Done | Authenticated historical quotes for `ev_inspector` |
| P5 | Registry built; it starts **empty**, so every adjustment is blocked | Register each effect with n/SE/out-of-sample results |
| P6 | Done (recommendations only) | none |
| P7 | Research only | Live data pipeline + latency |
| P8 | Gates/ledger/grading done | Wire the engine's output rows into `run_gates` |

The sample data in `examples/` is synthetic. Passing these checks does not show a real betting edge.
