# No-key SportsDataverse CFB weekly ratings — research adapter (2026-11-21)

**Status: STAGING ONLY, PAPER / 0u.** No odds, probabilities, stakes, or v5 edits.

## Source
The public [cfbfastR](https://cfbfastr.sportsdataverse.org/) release-backed `load_cfb_ratings_weekly()` loader needs **no CFBD API key**. The similarly named `load_cfb_teams()` API loader **does** need a key, so do not use it as a substitute. Reference documentation: https://rdrr.io/cran/cfbfastR/man/load_cfb_ratings_weekly.html

Its `adj_off_epa` and `adj_def_epa` are **EPA/play**, and `off_pace` is scrimmage plays/game. These are not the point-valued `offense.rating` and `defense.rating` columns required by `models/cfb/sportsedge_cfb_model.py`. Do **not** rename the columns and price totals. The model still requires valid as-of advanced team stats, a tested EPA-to-point mapping, independent venues, identity and calibrations.

Example public CSV export after installing `cfbfastR` in R (no key needed for this loader):

```r
library(cfbfastR)
data <- load_cfb_ratings_weekly(seasons = 2026)
write.csv(data, "cfb_ratings_weekly_2026.csv", row.names = FALSE)
```

An R dataframe export **is not** proof of the provider's original publication time or that the release never backfilled historical rows. Capture immutable original release asset bytes and its provider release metadata separately; bind the manifest to the actual raw CSV export SHA-256. Never put private DK screenshots, sportsbook prices, keys, or personal account data in this public repository.

## CLI

```bash
python research/audit/cfb_no_key_ratings_adapter.py \
  --ratings /private/cfb_ratings_weekly_2026.csv \
  --crosswalk /private/cfb_team_id_map.csv \
  --games /private/cfb_games_today.csv \
  --manifest /private/cfb_source_manifest.json \
  --out /private/new_cfb_research_report.json

python -m unittest discover -s research/audit \
  -p 'test_cfb_no_key_ratings_adapter.py' -v
```

The output is **create-only** and never overwrites old results. No network request is made. A failing source or ambiguous identity throws a nonzero error; unsupported games retain explicit BLOCKED rows. Every staged row remains `wager_eligible: false` and `stake_u: 0`.

### Required CSV fields

- Weekly ratings: `season,through_week,team_id,games,adj_off_epa,adj_def_epa,off_pace`. Use the complete frozen season CSV with every relevant team-week; duplicate team-week rows fail.
- Team ID map: `team_id,team`. Exact event identity required, no name fuzzy matching.
- Game slate: `game_id,season,week,kickoff_utc,home_team_id,away_team_id,home,away`. Keep full offsets in kickoff timestamps.

### Required manifest JSON example (illustrative, **not an authentic receipt**)

```json
{
  "source_kind": "sportsdataverse_cfb_ratings_weekly",
  "source_url": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_ratings_weekly/ACTUAL_ASSET.csv",
  "source_sha256": "ACTUAL_64_CHARACTER_SHA256_OF_EXPORTED_CSV",
  "published_utc": "2026-11-20T11:00:00Z",
  "captured_utc": "2026-11-21T12:00:00Z",
  "data_through_utc": "2026-11-19T23:00:00Z",
  "model_asof_utc": "2026-11-21T13:00:00Z"
}
```

Do not copy example timestamps: collect real provider publication evidence, then capture, hash, and check chronology. Manifest clock consistency is **self-asserted**, not external custody proof. The adapter rejects same-/future-week snapshots to prevent unintentional in-week leakage.

## Adoption gates

1. Source release raw asset and weekly vintage independently verified; complete team-ID crosswalk and event census.
2. Published/captured/as-of/game kickoff clocks verified against original receipts, not synthetic timestamps.
3. EPA-to-points/pace mapping fitted **only** on historical pregame snapshots; out-of-sample acceptance vs true scores and no-vig DK baseline.
4. Required advanced stats, venue, injuries and measured uncertainty admitted point-in-time.
5. Exact-head CI runs this adapter's tests; risk and pricing state remain closed until separate owner-authorized promotion.

This is a foundation for replacing missing-key excuses. It is intentionally **not a 55-game total card**.

## ESPN SP+ full-census point-unit preflight (research-only)

ESPN's November 15, 2026 SP+ article covers 138 FBS teams, with offense, defense and special teams columns:
https://www.espn.com/college-football/story/_/id/49868647/2026-college-football-sp+-rankings-all-138-fbs-teams

**CRITICAL UNIT RULE:** SP+ offense means approximate points scored against an average defense; SP+ defense means points allowed against an average offense, so lower defense is better. The existing `models/cfb/sportsedge_cfb_model.py` function `ratings_points()` takes **centered offsets** and adds `LG_PPG`. Feeding raw SP+ offense/defense into those fields silently double-counts the baseline. Use separate, explicit unit conversion with source/provenance and an out-of-sample tested scoring baseline. A safe candidate diagnostic is `SPoff_home + SPdef_away - league_scoring_baseline`, which is **not** a validated betting projection.

Run (offline, no ESPN scraping or sportsbook-data upload):

```sh
python research/audit/cfb_spplus_research_preflight.py \
  --ratings /private/espn_spplus_2026_full_138.csv \
  --games /private/todays_full_cfb_games.csv \
  --manifest /private/espn_spplus_manifest.json \
  --out /private/new_spplus_research_report.json

python -m unittest discover -s research/audit -p test_cfb_spplus_research_preflight.py -v
```

**Ratings CSV** headers: `team,offense,defense,special_teams`; exactly 138 unique full-FBS names, all numeric and finite. All team names must match the event census exactly—do not fuzzy guess. This is a *structural count*, not an independently authenticated FBS-member registry.

**Games CSV** headers: `game_id,home,away,kickoff_utc,neutral`, with explicit `0/1` neutral flag and timezone-aware kickoff. This gives a complete row for every user-supplied game; FCS opponents are reported **BLOCKED**, not dropped. The supplied `expected_games` must match the CSV row count.

**Manifest JSON** schema (values illustrative, **not a legitimate source receipt**):

```json
{
  "source_kind": "ESPN_SPPLUS_2026",
  "source_url": "https://www.espn.com/college-football/story/_/id/49868647/2026-college-football-sp+-rankings-all-138-fbs-teams",
  "ratings_sha256": "actual SHA256 of frozen ratings CSV",
  "games_sha256": "actual SHA256 of frozen games CSV",
  "published_utc": "actual dated original publication, offset-aware",
  "captured_utc": "actual time the analyst acquired the source",
  "data_through_utc": "actual last included game",
  "model_asof_utc": "actual time prediction was calculated",
  "expected_games": 58
}
```

The preflight checks ordering `data_through <= published <= captured <= model_asof < kickoff`. It does not independently authenticate claimed publication times. All results are `RESEARCH_PAPER` or `BLOCKED`, with **zero official win probabilities, EV or wagers**. Its diagnostic totals deliberately omit home-field, special teams and game-specific pace. Do not use its output as an official card or substitute it for the audited CFB engine.

Regression tests enforce the point-unit guard, exact 138-team count, event-count preservation, FCS refusal, original-byte hashes and source chronology. The CFB `tests.yml` job invokes both no-key adapter and SP+ preflight tests through `models/cfb/test_cfb_model.py`; the frozen v5 engine is unchanged.
