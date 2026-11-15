# NFL Next Gen Stats 2026 current-release acceptance — November 15

**Research-only.** This report certifies that the **current** public
nflverse Next Gen Stats releases could be downloaded, hashed and validated
against their registered weekly schema. It does NOT certify any historical
pregame snapshot, model calibration, betting edge or executable price.

[Passing live workflow receipt](https://github.com/bighauss/Sportsedge/actions/runs/43750391489)

| Current release (Nov 15, 2026) | Source raw SHA-256 prefix | Total CSV rows | Eligible 2026 REG player-week rows through W9 | Excluded week 0 (season aggregate) | Excluded after W9 | Teams |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| nflverse `ngs_passing.csv.gz` | `ff09429b119e` | 6,246 | 274 | 37 | 2 | 32 |
| nflverse `ngs_rushing.csv.gz` | `a14b15fd7aaa` | 6,377 | 271 | 45 | 2 | 32 |
| nflverse `ngs_receiving.csv.gz` | `1895ce4275d` | 15,491 | 637 | 118 | 5 | 32 |

Full SHA256 originals are retained in the actual workflow receipt / private
runner manifest. Counts outside the target 2026 regular season are not in the
eligible denominator. The current release's weekly `week=0` season-to-date
rows are **not** valid single-week observations and are explicitly excluded.

## Verified source identity columns and metrics

All three observed 2026 files carry `season`, `season_type`, `week`,
`player_gsis_id`, `team_abbr`. The registered NFL team list accepts
the provider's explicit Rams `LA` code as canonical SportsEdge `LAR`,
and refuses unknown teams. The source-level tests also require:

- Passing: `attempts`, `completions`, `pass_yards`, `pass_touchdowns`
- Rushing: `rush_attempts`, `rush_yards`, `rush_touchdowns`
- Receiving: `targets`, `receptions`, `yards`, `rec_touchdowns`

For every eligible player-week row, a stable GSIS ID, registered team, valid
finite stats and unique (year, week, team, player) key are required. Completed
passes cannot exceed attempts, receptions cannot exceed targets. No missing
value is filled with a guessed zero. Out-of-cutoff and aggregate records are
logged separately; any identity/stat/coverage failure halts acceptance.

## What this enables, and what it does not

This is now a verified **raw-source + row-shape** input for forward football
player research. A subsequent modeling layer may fit position/role/usage
projections and time-registered residual distributions from appropriately
frozen past rows, but this check supplies **no independent future player
stat mean, standard deviation, expected touchdowns or correlation model**.

The current Nov 15 release is not evidence the same rows were available
before prior slates; the provider's `updated_at` value is an observable
publisher timestamp claim but not an independently signed historical PIT
receipt. All DraftKings/BestBook source and Gate A/E requirements remain
open in [Issue #10](https://github.com/bighauss/Sportsedge/issues/10).

Official picks: **0**. Approved stake: **0u**. Frozen v5: unchanged.
