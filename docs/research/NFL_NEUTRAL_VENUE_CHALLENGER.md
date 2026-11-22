# NFL frozen v3 neutral-site HFA challenger — 2026-11-22

**Research-only. No model, betting-engine, freeze, wager or account state is changed.**

## Root cause

The private frozen `sportsedge_ratings_local.py` uses `site=0` for neutral games when **fitting** historical team effects, but `project(R, home, away)` unconditionally applies `+hca/2` to home scoring and `-hca/2` to away scoring. With the original `hca=1.6` points, a known neutral venue receives an unearned **+1.6 home margin** in prediction, although projected total is unchanged.

Main's `models/nfl/score_walkforward_pit.py` is a separate PIT EPA score-conversion research lane and was NOT changed. The original v3 runner is a private frozen artifact, not a file in this PR.

## Challenger semantics

`models/nfl/neutral_venue_challenger.py` accepts **already-projected scores**, exact `bool` neutral status and an explicitly supplied home-field margin term. It removes the HFA margin only for `neutral=True`; `neutral=False` is an exact score no-op. `neutral=None`, strings, nonfinite inputs and impossible corrected scores fail closed. A source-receipt / PIT verification of the venue still must occur externally.

### Independently reproduced development replay

Historical input: owner-private reconstructed `results_2026.csv` with sha256 `383508dbbe618098ce8264f21da28c1a21111f14733d298c140764ecd4a8dd3a`, 151 completed rows through the Nov 19 game.

Execution: fit the original ratings model on *prior weeks only*, compare each future game for weeks 2–11, with its recorded neutral flag. The 135-game development evaluation includes 7 reported neutral games, 10 test week clusters and one tie. The change was tested and chosen using this same sample; it is not independent holdout performance.

| Metric | Frozen v3 baseline | Research neutral challenger |
|---|---:|---:|
| All 135 games: margin MAE | 10.1215353 | 10.0622760 |
| 7 neutral games: margin MAE | 11.3341148 | 10.1912576 |
| All games: total MAE | 11.3168624 | 11.3168624 |
| Non-neutral projected scores changed | 0 | 0 |

The exploratory week-cluster bootstrap (20,000 deterministic resamples) for challenger-minus-original margin MAE was `[-0.1024, -0.0107]`. These intervals are **not future predictive validation** because the proposed fix was inspected and selected on this dataset. No historical bookmaker odds, implied odds, confidence calibration, CLV, transaction costs, stake acceptance or realized portfolio exists here. Accordingly, **ROI, Sharpe, Sortino, Calmar, drawdown, +EV and official stakes are unavailable**.

To reproduce privately, use the original frozen ratings runner (its SHA and original archive retained in owner-private Drive), the 151-row file of that exact hash, and sequential prior-week fit / venue-known comparison. Do not commit the original private CSV or a retroactive bookmaker claim. Synthetic CI verifies semantics only.

## Promotion gates

- [ ] Independently source-attest each future game's actual neutral status *before* model freeze.
- [ ] Add explicit venue binding to the main relevant runner's freeze contract without modifying the original v3 records.
- [ ] Confirm any venue transformation uses the same HFA convention in fit and prediction.
- [ ] Freeze a v3.1 challenger before future outcomes and evaluate on untouched games with paired prior-week baselines.
- [ ] Require enough observed games for calibration/interval comparisons and original priced quotes before official EV or unit claims.

Tracking [SportsEdge #445](https://github.com/bighauss/Sportsedge/issues/445) and agent coordination [#57](https://github.com/bighauss/Sportsedge/issues/57).
