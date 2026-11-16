# Prospective NFL public PBP + weekly + NGS raw source archive

**Research only — PAPER/0u.** Beginning with the changes in this PR, the scheduled and manually triggered `.github/workflows/prospective-public-nfl-source.yml` archives **five** allowlisted public NFL assets (when the publisher actually makes them available) rather than just four:

- `NFL_PBP_2026` → public nflverse PBP release `pbp/play_by_play_2026.csv.gz`, essential for future opponent-adjusted EPA inputs;
- `NFL_WEEKLY_2026` → public weekly player stats;
- `NFL_NGS_PASS`, `NFL_NGS_RUSH`, `NFL_NGS_RECEIVE` → public Next Gen Stats release files.

The PBP release can be substantially larger than a weekly/NGS CSV. SportsEdge validates its **original compressed bytes** against the GitHub release asset SHA-256 and size, then scans its gzip CSV in a bounded stream rather than materializing the full-season PBP into a Python list. The streaming scanner caps decompressed bytes, physical line length, and record count; checks the gzip trailer, duplicate/blank headers, ragged rows, game/week identifiers, and EPA feature columns `game_id,week,posteam,defteam,epa,wp,pass,rush`. It **does not** impute missing EPA on individual plays, compute a team rating, or assume a PBP release was published before a historical game.

## Operator command (private working directory)

Run from a checkout only for the code; the destination **must be outside the public Git repository**.

```sh
python -m sportsedge.validation.forward_public_nfl_archive \
    /private/sportsedge-nfl-forward \
    --assets NFL_PBP_2026 NFL_WEEKLY_2026 NFL_NGS_PASS NFL_NGS_RUSH NFL_NGS_RECEIVE

# For a REAL, separately verified future NFL event only, provide both:
python -m sportsedge.validation.forward_public_nfl_archive \
    /private/sportsedge-nfl-forward \
    --event-id ACTUAL_PROVIDER_CANONICAL_EVENT_ID \
    --event-start-utc 2026-12-01T21:00:00Z
```

The example kickoff is only a timestamp format illustration, **not** a real schedule claim. Do not pass fabricated event IDs or dates to make historical source material appear pregame. `--assets` defaults to all five only when available from upstream. If any asset fails validation, the archive run fails and retains a `BLOCK_INCOMPLETE_PUBLIC_CAPTURE` manifest, never a successful five-source claim.

Original compressed source archives are written to a unique, private create-only run directory; original raw files have mode 0600. The completed manifest records hashes, row counts, original filename, local capture UTC, GitHub release updated-at **claim**, and `source_schema_scan_mode`. It explicitly reports:
`independent_original_source_authentication=false`,
`event_identity_source_authenticated=false`,
`point_in_time_feature_admissible_for_betting=false`,
`official_counted=0`, and `approved_stake_u=0`.

The GitHub Actions workflow's artifact retention is **14 days**. Download and independently archive useful captures to access-controlled long-lived/WORM storage; GitHub artifacts and Drive copies alone do not prove a provider's original publication time or immutable historical pregame availability. The default scheduled run is **not event-bound** and does not meet NFL pregame Gate B or bookmaker Gate A without independently verified schedule, starting QB, inactive, lineup, weather, model and quote freezes.

## What this unlocks—and what it does not

PBP plus weekly and NGS gives the EPA/ridge research stage prospective original source bytes for future as-of ratings builds. A downstream data-preparation job still must select historical games completed and truly released before each forecast, bind stable team/game IDs, verify observation/freeze times and archive the exact derived features. A current 2026 PBP release filtered to Week 9 does **not** prove it existed at the original Week 9 forecast cutoff.

The original sources are nflverse public releases: <https://github.com/nflverse/nflverse-data/releases>. Confirm actual asset licenses and provide nflverse attribution when reusing data. Do not put private odds exports, API keys, wager records, or user-level files in public GitHub, CI logs or published artifacts. The odds and source-to-card Issue #10 hard gates remain fully open.

## Regression tests

```sh
python -m unittest sportsedge.markets.test_nfl_pbp_streaming -v
python -m unittest sportsedge.validation.test_forward_public_nfl_archive -v
```

The tests use synthetic in-memory gzips and injected mock captures, verify no network credentials are needed, reject bad checksums, bad CSV/gzip and decompression-limit overrun, and preserve all original bytes. They prove software behavior only.
