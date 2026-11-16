# SportsEdge audit gates (all agents)

Source: audit prompts Isaac collected from @Rusty_Bill and @PlusEVAnalytics (Nov 2026), adapted to this repo.
Rule for every gate: audit and RECOMMEND; do not change model weights or past records. Fixes are proposed on issue #57, tested on unseen (later-dated) games, then merged.

## G1. Largest-edge audit (run on every card before display)
Take the 20 largest projected edges (raw and blended). For each: model prob, book price, implied prob, edge; the inputs causing the high confidence; stale-price, wrong-player-ID and arithmetic checks; result vs prediction (a win does not prove the projection right). Look for shared patterns across the 20. Rank by severity.
Seed finding (Nov 15): the biggest "edges" were long-shot moneylines and thin-data props; most lost. Large model-vs-market gaps are treated as input bugs, not edges (guard in run_it_card.py).

## G2. Market-disagreement analyzer (weekly, from ledger/)
Bucket every graded play by |model prob - no-vig market prob|. Per bucket: n, predicted win %, actual win %, ROI at original odds. Flag small samples. Expect worse results as the gap grows; if so tighten the guard.

## G3. Calibration (monthly, out-of-sample only)
Bins 50-55, 55-60, ...; observed win rate per bin; Brier score; log loss; reliability diagram. Recommend calibration, do not apply silently.

## G4. Leakage and timestamps
Every saved card stores the capture time of each price and injury report. Tests fail if any input is dated after the card's lock time.

## G5. Tracker integrity
ledger/ records every qualifying play: timestamp, book, line, odds, model prob, result, net units (flat 1u baseline). Losses never removed; qualification rules never changed retroactively; missing or unverifiable rows flagged.

## G6. Version tracker
Each card carries the rules version and engine commit. Reports are per version; prospective results are kept separate from retro-qualified plays.

## G7. Correlation and stress
Count same-game, same-QB and same-player props as one exposure. Bootstrap ROI and drawdown with correlated bets grouped before saying a record is convincing.

## G8. Execution realism
Compare best-available price to a single benchmark book; drop edges that vanish at the benchmark price or after stale/unavailable lines.

Evidence needed before calling any model durable: hundreds of tracked pregame plays including losses, out-of-sample calibration, positive CLV.
