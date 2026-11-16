# SportsEdge: from real data to projections to candidate disagreement

**Engineering implementation:** `sportsedge/markets/edge_discovery.py` plus
`sportsedge/markets/run_it_research.py`, consumed by the existing
`sportsedge.markets.cli` and full-slate orchestrator. This is a research
screen, **not authenticated +EV or official wagering**. Frozen `engine/sportsedge_v5.py`
and original historical picks are unchanged.

## Where every ingredient belongs

| Stage | Input | Existing code | Output / gate |
|---|---|---|---|
| 0. Schedule and market inventory | Real eligible events and available DK outcome/alternate rows from permitted source | `sportsedge/odds/event_discovery.py`, `sportsedge/odds/completeness_gate.py`, `sportsedge/markets/slate_orchestrator.py` | Exact sport/event/market/period/side/line/player/settlement; missing opportunities remain explicit `NOT_CAPTURED` |
| 1. Point-in-time independent inputs | Ratings, efficiencies, possessions/pace, injuries/roster, weather, active players, golf field/tee times | `sportsedge/markets/pit_source_manifest.py`, `sportsedge/validation/seven_sport_pit_freeze.py`, sport-specific adapters | Actual source bytes, SHA, observed/published/captured UTC, identity and a forecast freeze that precedes the quote/event |
| 2. Independent projection | **No sportsbook price as a predictive feature**. Sport-specific scores or player stat means with fit time and model hash | `sportsedge/markets/projection_bridge.py`, `player_forecast_intake.py`, native sport models | `TeamProjection`, eligible `PlayerMoment`; unsupported injuries/lineups/IDs → BLOCK |
| 3. Calibrated uncertainty | Widths, prop distributions, period splits and **joint** dependence from registered historical folds | Currently `sportsedge/markets/projection_distribution.py` is an explicitly **uncalibrated** scenario generator | Full scenario outcomes and probabilities; first TD/2+ TD/first basket/SGP only if genuine event-level/count models exist; no invented tail |
| 4. Price fair probabilities | One frozen outcome batch per event/market | `sportsedge/markets/allmarkets_research.py::price_market` | Simulated W/P/L count, `P(win)`, `P(push)`, `P(loss)` and nonpush-conditional model P |
| 5. Market comparison | Authenticated original DK **two-sided exact-line quotes** and separately documented independent source | Existing `validate_pair` validates local quote/market/freshness *shape* but **does not authenticate source** | Same-line DK no-vig conditional P, quoted price break-even P, modeled-vs-market disagreement; full offered denominator |
| 6. Edge screening | Matched rows from stage 4–5 | **New** `edge_discovery.evaluate_signal` and `shortlist_signals` | Per-market full probability evidence, MC-only Wilson interval and non-actionable `PAPER_ONLY_NOT_AN_ACTIONABLE_EDGE` shortlist |
| 7. Risk / card / grade | Certified source+model proof, stringent risk policy, original selection/quote | `sportsedge/odds/card_gate.py`, `run_it_research.py`, private evidence bridge | Currently **BLOCK / 0u**. Genuine gates A–E, calibration and original-pick ledger must be accepted separately before any official card |

## What changed in RUN IT

Each submitted straight-leg candidate **still** passes through
`price_market` and the mandatory strict v2.1/v2.2 research risk gate, including
candidates rejected for missing prices. In a legitimately shaped **PAPER**
price-comparison row, a new `edge_signal` object preserves:

- Matched original market identity, sport, period, side, precise line, stat/player,
  source model/feature hashes and original quote receipt identifiers.
- Total scenario draw count; wins, losses and pushes.
- **P(win | not push)** = W/(W+L). **P(push)** = P/N. Raw per-$1 EV
  uses `P(win)×(decimal_odds−1)−P(loss)`, not the no-push approximation.
- The same-book, same-line no-vig market baseline obtained from the existing
  paired-price validator. This is a **DK-only no-vig baseline**; not independent
  sportsbook agreement.
- Book quote's conditional break-even P = `1/decimal_odds`.
- `model_minus_market_pp` and `model_minus_quote_pp`, both in
  **percentage points**, not percentage EV. No conversion of an unvalidated
  probability into a verified edge.
- A 95% Wilson interval on the **simulation's nonpush W/L draws only**.
  This does not measure model accuracy, calibration, data leakage, roster
  uncertainty, correlation misspecification or authenticity.

A `research_shortlist` is also produced for matched-price rows whose
**MC-only Wilson lower bound** exceeds BOTH the DK no-vig baseline and
book quote break-even threshold. That is a *conservative simulation noise
screen*, NOT a statistically proven market mispricing. The screen keeps at
most one mirrored opposite side for the same market/line. Different alternate
rungs, players, periods and settlement definitions remain separate.

Any missing, stale, mismatched, unsigned, poststart, unauthorized or otherwise
invalid pair remains `BLOCK` and `edge_signal: null`. No shortlisting,
filling from bestbook, back-solving from the line, or treating a line
movement as an independent projection. Positive screen signals are **not**
automatically added to betting cards, grading or staking.

The public RUN IT report retains all market rows, including blocked ones.
A full-slate `run_slate` report carries each event's `research_rows[*].edge_signal`
without changing or connecting the main seven-sport inventory/odds feeds.
NHL/PGA remain schedule-only in this five-sport pricing engine until their
own market/pricing integration is independently validated.

## How to run (private data, no iPhone coding required)

Existing private CLI:

```sh
python -m sportsedge.markets.cli \
  /private/frozen_event_model_and_quotes.json \
  /private/frozen_event_research_report.json

python -m sportsedge.markets.slate_orchestrator \
  /private/complete_declared_slate.json \
  /private/complete_slate_research_report.json
```

Use `projection_ref` and the **required point-in-time feature source manifest**
for actual recovered CFB/CBB/NBA/MLB/NFL projection functions. The alternate
literal `projection` object is for unverified input and **must not** be
treated as authenticated historical projection.

Keep source/export data, book quote receipts, player IDs and credentials in
restricted private storage outside public GitHub. `--out` paths should
always be new, not overwritten. The phone-facing research console is
separate: it is a safe status display, not yet connected to an authenticated
book or genuine +EV distribution.

## How model improvements SHOULD enter the probabilities

Sport-specific candidate feature families (Hoop-Explorer RAPM/on-off, Torvik
AdjO/AdjD/tempo, NFLverse/NGS EPA/usage, Open-Meteo weather, verified injury
updates, MLB StatsAPI/Statcast, MoneyPuck xG, golf SG/field/tee time) must
first be examined as original point-in-time sources with documented rights.
They **do not** automatically get additive point adjustments or made-up
weights. Bind the exact player/team/event IDs, derive train-only models and
freeze the fit BEFORE untouched future games.

For each sport/market/period, compare:
1. Prior-only/simple baseline.
2. Authenticated pregame no-vig market baseline.
3. Independent SportsEdge-only projection and calibrated distribution.
4. Preregistered model+market blend where the weight is learned on
   **earlier historical folds**, with market-only weight zero as baseline.
5. Forward shadow outcomes: score Brier/log loss, reliability curves,
   MAE for point/stat estimates, real same-line CLV, W/L/P with correct
   settlement and event-cluster confidence intervals. Report all
   candidates, failures, losses and missing prices.

Do NOT adopt the existing 30% model / 70% market mix as a validated optimal
weight. It's a legacy **untested research heuristic**. Neither the positive
`blended_ev_unverified` field nor a Wilson simulation interval is an
acceptance certificate. If genuine data, legal access, PIT evidence, calibrated
sample support, correlations, or secondary book quotes are absent, the
feature/market stays `NO_MODEL`, `NO_DATA`, `NO_PRICE` or `PAPER / 0u`.

Tests:

```sh
python -m unittest -v \
  sportsedge.markets.test_edge_discovery \
  sportsedge.markets.test_run_it_research \
  sportsedge.markets.test_allmarkets_research \
  sportsedge.markets.test_cli \
  sportsedge.markets.test_slate_orchestrator
```

The latest hard gate is tracked in issue #10. No financial advice or
automatic wagering service is provided by this integration.
