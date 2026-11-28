# Integer-line bounds from market-implied count ladders

Research only. This extends the existing two-sided half-line consensus, not the runner or grader. It answers a narrow question: what do the quoted thresholds imply about the probability that an integer line pushes, without assuming a distribution between them?

## Integration

Call `integer_count_bounds(external_book_quotes, k, as_of=..., max_age_seconds=...)` in `research.market_implied.ladder`. Pass the source-native contract mapped to an explicitly supported count market, with common player, period, rules, independent book identities and consistent weights. No DraftKings offer is needed or accepted as evidence. Output is conditional on non-void settlement; the function cannot authenticate source independence, rules, availability or an execution quote. Do not use bounds as stakes, calibrated predictions, or a synthetic full distribution.

If X is a nonnegative count, S(j + 0.5) = P(X > j). Hence P(X = k) = S(k - 0.5) - S(k + 0.5) for adjacent observed rungs (at zero use S(-0.5) = 1). Otherwise, an interval of integers has known mass but unknown allocation. For each outcome, the sharp lower bound sums masses of intervals entirely inside that outcome; the upper bound sums masses of intervals intersecting it. Extremes are attainable by placing each interval's mass on a feasible count. The three marginal bounds cannot be combined independently. An open upper tail stays open.

## Historical source qualification

SmartStake (2026), [MLB Player Prop Odds and Results](https://huggingface.co/datasets/SmartStake/mlb-player-props/raw/main/README.md), publishes historical selection-minute decimal odds under CC BY 4.0. The [pinned March partition](https://huggingface.co/api/datasets/SmartStake/mlb-player-props/tree/7cedfd3fe29f2de4f675039410a48160739323fc/mon%3D2026-03) is 40,343,480 bytes. No raw data is committed. The code aborts if its SHA-256 differs. The publisher describes March to early July odds with grades through June; never infer a result-availability clock from a final grade. In particular, the provider table has names rather than canonical player IDs, and no independent capture receipt, contract-specific void rules, limits, or original book-chain evidence.

Reproduce from repository root (Python 3.11+, DuckDB 2.0.1 for the optional offline audit):

```sh
curl -fL 'https://huggingface.co/datasets/SmartStake/mlb-player-props/resolve/7cedfd3fe29f2de4f675039410a48160739323fc/mon%3D2026-03/part-000.parquet' -o /tmp/smartstake-march.parquet
python -m research.market_implied.smartstake_march_audit /tmp/smartstake-march.parquet
python -m research.market_implied.smartstake_march_audit /tmp/smartstake-march.parquet --example
SPORTSEDGE_SMARTSTAKE_MARCH=/tmp/smartstake-march.parquet python -m pytest -q tests/test_market_implied*.py tests/test_smartstake_march_audit.py
```

**Coverage audit:** At bet365, the six March prop markets yielded 12,889 distinct pregame source game/start/player/market/half-line contracts observed at any time. Exactly 60 minutes before scheduled first pitch, 696 had one valid over and one valid under; 9,536 had no tick and 2,657 were one-sided or ambiguous. Of 3,209 player-game-markets, zero had two qualified rungs at this cutoff. This is observed-archive coverage, not the attempted MLB slate, proof a book did not offer a market, or evidence against carefully validated carry-forward. We did not search for a better-performing cutoff.

**Worked archive example:** At the separate Fanatics timestamp 00:02 UTC on March 26, three minutes before scheduled start, Rafael Devers total bases had two complete adjacent rungs. Under the shared-settlement assumption, the implied mass at exactly one base was 21.34% (multiplicative), 22.60% (additive), 23.28% (power), and 22.60% (Shin). These are transformed historical offers, not four independent predictions or a confidence interval. The example was chosen for geometry, not to estimate accuracy. Neither query projects the result or won fields; no DK EV, pooling, grade, CLV, or profit claim follows. Integer-line pricing for other sports remains unvalidated even where count geometry is supported.
