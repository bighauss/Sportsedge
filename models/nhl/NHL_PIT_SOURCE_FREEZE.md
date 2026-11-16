# NHL original-source point-in-time freeze — research / PAPER 0u

**Purpose:** a create-only private preflight for NHL xG, goalie stats, skater stats, lineup confirmation and frozen model artifact used by the seven-sport research pipeline. This is **software / byte-integrity evidence only**, not an authenticated MoneyPuck/NHL publication receipt, verified goalie status, data rights, a calibrated forecast or betting promotion.

Existing models/nhl/sportsedge_nhl_model.py, nhl_shared_scenarios.py, their coefficient assumptions and the frozen v5 engine are **not modified** by this change.

## Command

From the repository root:

    python -m models.nhl.nhl_pit_snapshot_contract \
      /private/NHL_snapshot_manifest.json --report /private/NHL_new_report.json

The manifest and original source files must be private **outside this public repository**, except that the MODEL artifact may be an exact file in the source tree. The private output uses exclusive create, mode 0600 and fsync; an existing report is never overwritten.

## Input schema

The exact top-level keys are schema, event, sources. Below is **illustrative only**, not actual odds/goalie data and not a usable release manifest:

    {
      "schema": "sportsedge-nhl-pit-snapshot-v1",
      "event": {
        "event_id": "NHL_EVENT_001",
        "home_team_id": "BOS",
        "away_team_id": "NYR",
        "home_goalie_id": "NHL_GOALIE_ID_A",
        "away_goalie_id": "NHL_GOALIE_ID_B",
        "freeze_utc": "2026-11-15T15:00:00Z",
        "kickoff_utc": "2026-11-15T23:00:00Z"
      },
      "sources": [
        {
          "role": "MODEL",
          "path": "/path/to/existing/nhl_model.py",
          "sha256": "sha256:<64-hex-original-file-digest>",
          "provider": "RESEARCH_MODEL",
          "data_through_utc": "2026-11-14T00:00:00Z",
          "published_utc": "2026-11-14T08:00:00Z",
          "observed_utc": "2026-11-14T08:00:00Z",
          "captured_utc": "2026-11-14T08:00:00Z"
        }
      ]
    }

This example is deliberately **incomplete and cannot pass**. Exactly five distinct roles are mandatory: MODEL, TEAM_XG, GOALIE_STATS, SKATER_STATS, LINEUP. Each needs an independently obtained nonempty original file path, its correct complete SHA-256, declared provider ID, and original UTC data_through, published, observed, captured timestamps. The test checks data_through <= published <= observed <= captured <= freeze < kickoff; no after-start data are allowed. Both lexical and resolved paths outside the checkout are checked; the MODEL role alone can reside in the checkout.

The original LINEUP file must be strict JSON with exactly: event_id, home_team_id, away_team_id, home_goalie_id, away_goalie_id, home_confirmed, away_confirmed, observed_utc. It must name the exact game/teams/goalie IDs of the manifest, both confirmations must be boolean true, and its observed clock must equal the LINEUP source receipt observed UTC. **These are assertions by the supplying source**, not independent proof that either starting goalie was actually confirmed. A real authority plus signed/corroborated goalie/roster crosswalk is still required before practical use.

## Fail-closed and non-promotion conditions

- Missing file, zero bytes, >20MB, duplicate role or reused raw file, checksum mismatch, nonfinite/duplicate-key JSON, unknown IDs, conflicting lineup IDs, unconfirmed goalies, future data-through/publication, late capture, post-kickoff freeze and local file swapping all refuse a report.
- Every successful **structural** report still states: status PAPER_0U_SOURCE_CLAIMS_UNAUTHENTICATED, official_market_count 0, approved_stake_u 0, release_certified false and external_provider_authentication false.
- Provider IDs and historical publisher/clock fields are caller declarations. Hashing original bytes does **not** prove publication time or independent external origin. Actual NHL MoneyPuck/goalie data schemas, stable player crosswalks, past-game timing and permissions are not authenticated here. Neither authentic DraftKings nor a separate independent book has been connected.
- No model pricing is invoked by this preflight. The existing NHL shared-scenarios kernel can only consume subsequent distinct frozen projection inputs after roster/source provenance is externally checked; its incomplete OT and player markets remain BLOCKED.
- Issue #10 per-market Gate A–E release requirements remain OPEN; use the market matrix from PRs #187/#198 and the root strict R1 risk policy to record separate admission statuses.

## Tests

    python -m unittest models.nhl.test_nhl_pit_snapshot_contract -v

The tests create synthetic temp source files outside the public checkout, verify raw bytes/identity/time conditions, and assert all reports stay research-only. They do not collect data, fit calibration parameters or demonstrate an edge.
