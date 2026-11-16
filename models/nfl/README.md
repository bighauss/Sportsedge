# NFL EPA Ridge R1 — research-only feature builder

**Status: PAPER / 0u.** This is an opponent-adjusted team-efficiency *feature stage*, not a calibrated game-score model, player-prop engine, price, or verified +EV betting system. It neither imports nor modifies frozen engine v5.

## What is actually implemented

- Play-level nflverse fields: `game_id,posteam,defteam,pass,rush,epa,wp` (remove the space in `posteam` when constructing the CSV). nflreadpy returns **Polars**, not pandas; use `.write_csv()` from a selected Polars frame.
- For each eligible pass/rush play, estimate EPA = intercept + offense-team effect + defense-allowed-team effect, with L2 ridge on team effects. Higher defensive effect means that team **allows more EPA**. Features use exponential recency weighting; 21-day half-life and ridge=30 are **unvalidated research defaults**, not SportsEdge approved weights.
- No default garbage-time filter. Run a 10–90% WP **ablation** with `--wp-filter`, and retain only if a preregistered chronological comparison improves out-of-sample metrics. Filtering WP is not universally best.
- Explicit manifest of each source game's kickoff, final and postgame data availability timestamps; pre-forecast-only selection, and audit of future rows excluded. The entire data snapshot's observed timestamp must be on/before forecast time.
- A missing game manifest, contradictory timestamps, bad team identity, unparseable unit, or too little history raises a clear error. Exclusions for future games, missing EPA, unavailable offense, non-scrimmage plays, and optional WP filter are counted.
- Output: two opponent-adjusted EPA-per-play features, audit census and hashes of the **local** input bytes; **no projection, odds, EV, approval or staking**.

## Free-data preparation

```python
import nflreadpy as nfl

pbp = nfl.load_pbp([2026])  # Polars dataframe
pbp.select(["game_id", "posteam", "defteam", "pass", "rush", "epa", "wp"]).write_csv(
    "/private/nfl_pbp_2026.csv"
)
```

Maintain `/private/game_availability.json` from trustworthy game status, UTC kickoff/final and source update events, e.g.:

```json
{
  "2026_09_SEA_LV": {
    "kickoff_utc": "2026-11-08T21:05:00Z",
    "final_utc": "2026-11-09T00:30:00Z",
    "data_available_utc": "2026-11-09T01:00:00Z"
  }
}
```

**These timestamps are illustrative schema values, not assertions about a real 2026 game.** Every game_id in the PBP export (including future ones) must have a corresponding complete record. A separate capture process must archive and independently authenticate original source bytes, exact provider update event and observed time. Do not create retrospective provider availability records from today's downloaded play-by-play.

```sh
python models/nfl/epa_ridge_pit.py \
  --plays /private/nfl_pbp_2026.csv \
  --game-manifest /private/game_availability.json \
  --asof-utc 2026-11-15T17:30:00Z \
  --source-observed-utc 2026-11-15T17:00:00Z \
  --out /private/nfl_epa_ratings_paper.json

python -m unittest discover -s models/nfl -p 'test_epa_ridge_pit.py' -v
```

The example `asof_utc` and `source_observed_utc` are illustrative; enter timestamps of your actual archived capture. The CLI uses create-only output mode, never overwrites a previous prediction.

## What still blocks a genuine NFL predictor

1. Authenticate and archive point-in-time source records; provider revision timestamp is distinct from local retrieval, and local SHA256 does not establish when data was available.
2. Preserve actual pregame features and prospective forecast freezes. A 2026 snapshot downloaded after the fact cannot be used to claim a genuine 2018–2025 time-forward replay.
3. Fit QB starter effects, home/rest/travel, pace and scoring conversion from **earlier** game outcomes only. Don't copy fixed weather coefficients or another repo's weights.
4. Fit score distributions and push probabilities at 3/7, then calibrate by training fold. Compare to a market-only no-vig baseline, simple non-EPA baseline, and model+market blend. Disclose uncertainty and all failed ablations.
5. Only then add separate validated ML, spread, total, team-total, period and prop probability layers. Exact IDs and authenticated book quotes are required for each market.
6. Grade every original quote at original odds with consistent push/void settlement; cluster confidence intervals by game/week, track genuine CLV and untouched forward metrics. Keep all unsupported families visible as `NO_MODEL`/`NO_PRICE`/`PAPER_HOLD`.

Do not call this production-ready from synthetic tests or claim any hit rate or profitable EV from it.
