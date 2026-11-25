# CBB player props: holdout protocol (written 2026-11-25 11:19 CST before any backtest metric was viewed)

Status: RESEARCH, PAPER_0U, NON_COUNTED, approved_stake_u=0, official_counted=0.

## Data split (chronological, SDV season labels = spring year)
- Training-only warm-up: 2022 (2021-22). Never scored.
- Development / validation: 2023 (2022-23) and 2024 (2023-24). All model selection and any repair decisions use only these seasons.
- Untouched test: 2025 (2024-25). Read once, from the frozen code at the commit that records the validation decision. Never used to tune, select or repair.
- Forward: 2027 (2026-27) live DK captures, PAPER only.

## Fixed before any metric was viewed
- Features (models/cbb/players/features.py): #519 two-day lag and eligibility (>=5 prior same-team appearances in last 8, distinct dates); minutes = 0.6*EWMA(half-life 3 games)+0.4*mean(last 8); per-minute rates over last 15 same-team appearances shrunk to prior-season same-athlete rate (>=150 min) or league per-minute rate with 100 pseudo-minutes; team pace and opponent allowed per-possession rates shrunk with 5 pseudo-games.
- Per-origin fit (fit.py): pace elasticity grid {0,.5,1,1.5}, opponent elasticity grid {0..2 by .25} (grid ranges were widened once after inspecting a single 2024 in-season training fit, before any forecast was scored), multiplicative debias, NB2 alpha by moments, P/R/A residual correlation. Training window: rows dated <= origin-2d within 365 days.
- Origins: every Monday; forecasts for [origin, origin+7d).
- Lines: #519 fixed half-lines; ladders POINTS 8,10,12,15,18,20; REBOUNDS 3,4,5,6,8,10; ASSISTS 2,3,4,5,6; THREES 1,2,3,4; PRA 15,20,25,30; PR 10,15,20,25; PA 10,15,20,25; RA 5,8,10; relative line N=floor(#519 native_5 mean)+1.
- Metrics: MAE/RMSE/bias of means; discrete CRPS; Brier, log loss (p clipped to [1e-6,1-1e-6]), ECE (10 bins), over-bias (mean p - observed rate); week-block bootstrap CI (1000 draws, seed 57) for Brier deltas vs #519 NB.

## Selection rule (validation only)
- Combo method in {moment (preregistered default), independent, copula}: choose the lowest mean CRPS pooled over 2023+2024 on the deterministic 1-in-20 copula subsample, all four combo families pooled. Ties within 0.1% keep "moment".

## Pass criteria on the untouched test season (model-vs-model only)
- Mean CRPS below the #519 NB benchmark in all eight families, and relative-line Brier delta vs #519 NB with a week-block CI95 entirely below 0 in at least six of eight families.
- No historical sportsbook prop odds exist in the repo, so the market leg of the verification definition cannot be evaluated. Passing here does NOT verify the market or permit staking; it stays PAPER_0U / NON_COUNTED.
