# Totals bias: disclosure and the plan for fresh data (PAPER/0u, NON_COUNTED)

The v1 halves totals systematically under-project scoring. This file records the
fact, forbids a post-test intercept fix, and states the only repair that will be
treated as validated.

## What was observed (already known before any joint/refit work)
- On rolling-origin **dev folds** (so this is not a 2026-only surprise): H1 total
  bias under the normal-shape model was +0.30 (2021), +0.24 (2022), +0.54 (2023),
  **+0.82 (2024)**, **+0.89 (2025)**. Second-half totals show the same late-sample
  drift (+0.89 and +0.95 in 2024 and 2025).
- On the **untouched 2026 test window** (scored once, n=6,259): H1 total bias
  **+1.10**, H2 pregame **+1.38**, HT_H2 **+1.12**. Overs at the H1 model line
  hit 53.4% against 50.0% predicted. MAE is still a little better than the
  legacy 0.47-share rule, but calibration is not.
- The fitted intercept is lagging a rise in scoring. The point-in-time full-game
  projector itself was almost unbiased on 2026 totals (bias +0.006), so the
  half-share mapping, not the full-game mean, is the main leak.

## What will not be done
- No intercept, slope, or residual-mean adjustment will be estimated from, or
  tuned against, the 2026 test window. Doing that would convert the one
  untouched evaluation into a fitted residual.
- The shipped `coefficients_halves_v1.json` is left as scored. Joint copulas
  and a production-projector refit are additive files; they do not rewrite v1
  totals coefficients.

## The repair, when fresh data exist
1. **Preregister** a totals intercept (or a recency-weighted share) that may be
   fit only on seasons whose last tip is strictly before the start of the
   evaluation window.
2. The first evaluation window that qualifies is **season 2027** (the in-progress
   2026–27 season as of this writing). Until that season is complete enough to
   score (or a preregistered mid-season cutoff is declared and frozen), the
   bias stands as a known defect.
3. A second, independent path: refit the half *means* on chronological
   projections from the production or FG1C challenger model (`refit` stage in
   `fit_halves.py`, inputs from `import_fullgame_forecasts.py`). That refit is
   trained only through 2025. If it reduces totals bias on the 2021–2025 dev
   folds, the 2026 number may be reported only as a **secondary re-use**, never
   as a first untouched test, and still does not authorise rewriting v1.
4. After a 2027 evaluation, decide whether to ship a v2 coefficient file.
   Promotion remains PAPER/0u until a later, independent validation.

## Joint and correlation work does not fix this
A copula on (margin, total) changes joint probabilities, not the total mean.
H1–H2 dependence similarly does not shift the expected first-half total.
