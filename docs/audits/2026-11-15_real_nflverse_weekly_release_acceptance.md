# Real 2026 nflverse weekly-player release acceptance — 2026-11-15

**Scope:** Current publicly released 2026 weekly NFL player stats; raw bytes
downloaded in ephemeral, private GitHub Actions runner temp. **Research/PAPER
0u.** This is not a historical pregame point-in-time snapshot, player-scoring
probability, book price, or live card.

## Reproducible release and job receipt

- [Passing live-source workflow run](https://github.com/bighauss/Sportsedge/actions/runs/43749785464)
- Public provider: [nflverse/nflverse-data](https://github.com/nflverse/nflverse-data)
- Release asset: `stats_player/stats_player_week_2026.csv.gz`
- GitHub's recorded release asset SHA-256 and independently recomputed raw
  SHA-256: `90befdf33b7dc9e92a840d86a73149b759b601842ff5e86257dc653d34de7cac`
- Provider's asset-updated timestamp claim: `2026-11-15T16:21:10Z`
- Retrieved by CI at: `2026-11-15T18:59:03.728398+00:00`
- No private player rows, sportsbook odds, credentials or original CSV committed.

## Current source census, reproducible under release digest above

| Metric | Verified count |
| --- | ---: |
| All input CSV rows | 9,534 |
| 2026 regular-season player-week rows through week 9 with bound player/team IDs | 9,455 |
| Rows after week cutoff, excluded | 70 |
| Unbound player-ID rows with **zero** offensive rushing/receiving TDs, excluded | 9 |
| Unbound player-ID rows with offensive TDs | 0 |
| NFL teams represented in the accepted rows | 32 / 32 |
| Nonzero historical offensive player TD-share entries | 271 |

These counts sum: `9455 + 70 + 9 = 9534`. The live release smoke
independently verifies the gzip asset bytes, the source schema, a strict
regular-season week filter, 32-team coverage, stable player identifiers and
all recorded exclusions. Non-scoring unbound rows are **not** silently assigned
to players. Any unbound row with one or more offensive TDs fails ingestion.

### Two actual integration defects repaired by source confrontation

1. The published 2026 nflverse column is `team`, not the originally assumed
   `recent_team`. Source intake accepts exactly the documented alternatives
   and rejects an export with neither; contradictory dual-team fields fail.
2. The public team shorthand `LA` is canonicalized explicitly to SportsEdge
   `LAR`. No fuzzy mapping. The real input includes a small number of
   player-ID-empty, non-scoring rows, now explicitly excluded and counted.

## Strict limitations

- A GitHub release uploaded November 15 **cannot establish what upstream
  stats were observable before the November 9 or prior decision timestamps**.
  A retrospective filtered week-9 CSV is a reconstruction, not an archived
  week-9 PIT record; no promotion-credit claim is made.
- `share = player_rush+receive_TD / team_rush+receive_TD` is only a historical
  descriptive ratio. It excludes defensive/special-teams scores and does not
  imply a calibrated Bernoulli, first TD, 2+ TD, or SGP probability.
- No DraftKings or BestBook prices were fetched or accepted. Gate A, Gate B
  independent timing authentication, model calibration, 200 CLV records and
  v2.1 real-board promotion remain open in Issue #10.
- Today's real smoke is a **public-data ingest validation**, not 2026 TD
  model calibration, documented profit or stake authorization.

Run from repo root with network access:
```bash
python -m sportsedge.markets.nflverse_public_research_smoke /tmp/private-sportsedge-nflverse
python -m unittest sportsedge.markets.test_nflverse_public_research_smoke -v
```
