# Hoop-Explorer → SportsEdge CBB research companion

**Status:** Optional, local, read-only research integration. **PAPER / 0u**.
Does not modify sportsedge_v5.py, the CBB score projection, forecasts, odds,
line grading, betting eligibility, model weights or the RUN IT card.

## What is implemented

1. Permission-based CSV/JSON ingest from an operator-supplied Hoop-Explorer export.
2. Exact source-byte SHA-256 + optional immutable archive; explicit source column
   mappings and canonical player/team/lineup IDs (no name matching).
3. Season, tipoff, pregame freeze and source through/published/captured timestamp
   ordering (local manifest claims, **not externally authenticated timestamps**).
4. Descriptive nearest-player comparisons using shared RAPM, usage, turnover,
   three-point rate/accuracy, OR%, assist%, rim rate and on/off; fields that
   are missing are not imputed. The feature scales are **untested heuristics**.
5. An explicitly supplied desired-roster-role feature profile, ranked by
   descriptive distance, **not** a transfer forecast or lineup simulation.
6. WOWY-style on/off from a *disjoint partition of five-player lineups*,
   possession-weighted and optionally shrunk toward a **user-supplied**
   team prior with weight n/(n+k). This is a simple SportsEdge heuristic;
   it is **not** Hoop-Explorer's proprietary lineup-padding algorithm,
   nor an estimate of a causal impact.
7. AI-ready JSON evidence report with warnings, scope and provenance. No
   provider AI account, external LLM calls or secret access are required.

Hoop-Explorer's author publicly demonstrates native AI analysis, natural-
language filtering, CSV/JSON exports and lineup padding. The site's
bring-your-own-key AI settings are separate from this local adapter:
https://hoop-explorer.com/AiFreeAccounts . No documented public unattended
MCP/API endpoint or automated source authentication has been verified.
Do not scrape undocumented endpoints or put API keys in repo or manifests.

## Requirements before using real data

- Export the **player leaderboard** and, optionally, the **five-person lineup**
  table yourself, where permitted. Save the raw files; do not edit the bytes.
- Obtain or supply **stable, exact** canonical IDs for every player, team and
  lineup. Do not map ambiguous names or silently reuse IDs across seasons.
- Identify source scope and filters: same season, gender, division, opponent/date
  filters, possessions definition; lineup rows must represent a nonoverlapping
  partition of lineup stints/possessions to compute WOWY. **Overlapping
  combination tables are disallowed.**
- Record truthful `data_through_utc`, `published_utc`, `captured_utc`.
  If publication / as-of times are unknown, the export is **not** an eligible
  pregame point-in-time research input. Do not invent timestamps.
- Use end-year season coding: November 2026 → season 2027.
- Build a sidecar manifest per export containing exactly the source fields.
  `columns` maps *canonical field → exact observed column name*, not an
  assumed provider schema. Required player keys: `player_id`, `team_id`,
  `season`, `minutes`. Optional: `name`, `rapm`, `usage_pct`,
  `turnover_pct`, `three_rate_pct`, `three_pct`, `orb_pct`,
  `assist_pct`, `rim_rate_pct`, `on_off`.
  Required lineup keys: `lineup_id`, `team_id`, `season`,
  `possessions`, `net_rating`, `player_ids`. `player_ids` must be
  five **distinct canonical IDs separated by semicolons**.
- Player and lineup manifests must share `scope_id` and end-year season.
  For WOWY, `disjoint_partition:true` is a user assertion requiring
  outside evidence. The code cannot independently prove disjointness.
- An export can be loaded for exploratory analysis only; a *real*
  prospective source-provenance acceptance review is still outstanding.

## Manifest example (illustrative timestamps, NOT a live receipt)

```json
{
  "provider": "hoop_explorer",
  "kind": "player",
  "format": "csv",
  "source_url": "https://hoop-explorer.com/PlayerLeaderboard",
  "access_basis": "manual_user_export",
  "scope_id": "men-d1-2027-snapshot-001",
  "season": 2027,
  "sha256": "REPLACE_WITH_ACTUAL_SHA256_OF_RAW_EXPORT",
  "data_through_utc": "2026-11-15T17:00:00Z",
  "published_utc": "2026-11-15T17:10:00Z",
  "captured_utc": "2026-11-15T17:30:00Z",
  "columns": {
    "player_id": "EXACT_EXPORTED_ID_HEADING",
    "team_id": "EXACT_EXPORTED_TEAM_ID_HEADING",
    "season": "EXACT_SEASON_HEADING",
    "minutes": "EXACT_MINUTES_HEADING",
    "rapm": "EXACT_RAPM_HEADING",
    "usage_pct": "EXACT_USAGE_HEADING",
    "turnover_pct": "EXACT_TO_HEADING",
    "three_rate_pct": "EXACT_3PR_HEADING"
  }
}
```

The example's timestamps and field headings **are not facts about a real
Hoop-Explorer export**. Inspect the real export and replace every placeholder.
Generate the hash from the *raw bytes*, e.g.
`sha256sum players.csv` (or `shasum -a 256 players.csv`).

For JSON exports, supply `format: "json"` and an array of objects, or an object
with a `rows` array. This generic importer deliberately does **not** claim
to accept every JSON shape the creator may export; adapt the schema only
after inspecting an authorized sample.

## Run companion report

```sh
python models/cbb/hoop_explorer_research.py \
  --players-export /private/players.csv \
  --players-manifest /private/players.manifest.json \
  --target-player-id VERIFIED_CANONICAL_PLAYER_ID \
  --freeze-utc 2026-11-15T18:00:00Z \
  --tipoff-utc 2026-11-15T19:00:00Z \
  --archive-dir /private/hoop_receipts \
  --out /private/cbb_hoop_context.json
```

For five-person lineup comparison, additionally pass
`--lineups-export`, `--lineups-manifest`, `--team-id`,
`--prior-net` (documented team net-rating prior, same metric basis)
and `--pad-k` (explicit **unvalidated** prior-equivalent possessions).
An illustrative `--pad-k 200` is **not** a recommended or fitted value.
It must be chosen and frozen before examining results.

Optional `--role-profile /private/role.json`:

```json
{
  "name": "example only - perimeter rotation wing",
  "targets": {"usage_pct": 20, "turnover_pct": 12, "three_pct": 36}
}
```

Target values and feature scales are descriptive, not fitted to outcomes.

## Safeguards, limits, next validation

- All reports explicitly say `official:false`, `stake_u:0`,
  `pricing_enabled:false`, `model_weights_modified:false`.
- Export SHA-256 detects accidental byte changes; it does not prove a trusted
  provider capture, a genuine timestamp, licensing or historical availability.
- Low-minute players and low-possession WOWY arms are flagged. RAPM is
  contextual and noisy, especially early-season.
- When multiple overlapping lineup groups are present, the on/off partition
  assumption fails; supply raw disjoint full-lineup stints instead.
- Changing season or filtering may alter metric semantics. Do not compare
  mismatched denominator or sample populations.
- Outputs must be reviewed on genuinely frozen, forward, untouched fixtures
  before they enter any predictive model. Test calibration and changes in
  Brier/log loss/CLV (where authenticated) vs the existing frozen baseline.
  Do not retrofit results into historical cards.
- No provider credentials or automated live synchronization. That step needs
  creator-approved access or supported export workflow and real samples.
- Run: `cd models/cbb && python -m unittest -v test_hoop_explorer_research.py`

Tracks acceptance and provider authorization: issue #197.
