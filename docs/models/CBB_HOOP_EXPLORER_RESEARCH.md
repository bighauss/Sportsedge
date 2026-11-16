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

## Optional Hoop-Explorer AI (BYOK) setup

The user screenshot from 2026-10-15 shows a **separate on-site** free-provider
guide at https://hoop-explorer.com/AiFreeAccounts .

1. Open the Hoop-Explorer AI settings and a supported AI analysis page.
2. Create your own account with a provider shown on the live guide (e.g.
   OpenRouter's free-model option, subject to provider availability/quotas).
3. Enable AI in the site, choose BYOK, select the provider/model, and paste
   the key **in the provider input on Hoop-Explorer**. Never send a key through
   a ChatGPT message, Github issue, export, or commit.
4. Review the provider's current free credits, request caps and billing
   conditions. "Free account" does not guarantee unlimited free inference.
5. Export filtered/split analysis as CSV/JSON only where supported and
   permitted. The exported data is what this SportsEdge companion consumes.

SportsEdge does **not** use or store that on-site key, proxy private requests
to Hoop-Explorer, or claim the creator's MCP server has been published.

## Fastest phone-only data intake (no keys or computer)

1. In mobile Safari, open Hoop-Explorer's Player Leaderboard or Lineup
   Analyzer. Use the site's **own** permitted CSV/JSON export action.
   If export is unavailable on mobile, do not attempt undocumented endpoints.
2. In the iPhone Share sheet select **Save to Files**, then attach the
   original file in the SportsEdge ChatGPT conversation; avoid screenshots,
   which discard the column schema and source provenance.
3. The assistant can inspect its headers and advise on explicit mappings.
   **Do not paste an API key or place raw exports in the public GitHub repo.**
4. If you run Python in a private environment (Codespace, Colab, etc.), the
   header-only manifest draft creator is:

```sh
python models/cbb/hoop_explorer_intake.py \
  --input /private/players.csv \
  --kind player \
  --out /private/players.inspect.json
```

The inspector outputs the exact raw-file SHA-256, observed headers, source
row count and a manifest draft with **null** as-of fields and **unmapped**
columns. It intentionally does **not** print player names or raw stat rows.
Do not manufacture timestamps, assume that names imply canonical IDs, or
represent a generated manifest as independent provider verification.

### When Hoop-Explorer has no verifiable historical release timestamp

For **descriptive scouting only**, an operator may complete a manifest with
verified export headers and exact canonical IDs while keeping timestamp
fields null. The explicit exploratory mode does not require a game to
be selected and cannot qualify any row for the historical/PIT backtests:

```sh
python models/cbb/hoop_explorer_research.py \
  --players-export /private/players.csv \
  --players-manifest /private/players.manifest.json \
  --target-player-id VERIFIED_ID \
  --exploratory \
  --out /private/scouting_only.json
```

Results must retain `provenance_status=UNVERIFIED_EXPLORATORY_NO_PIT`,
`point_in_time_admissible=false`, `official=false`, `stake_u=0` and
`pricing_enabled=false`. Strict pregame mode remains unchanged: source
data-through, published and capture clocks **must** be provided, ordered
and externally validated separately. Neither mode automatically downloads
data from Hoop-Explorer.

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
- Use end-year season coding: November 2026 → game season 2027.
  Earlier, *fully observed* season-2026 player exports can be analyzed
  against a 2027 pregame freeze if their source clocks precede it; future
  source seasons are rejected. Do not mix different seasons in a WOWY join.
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
