# SportsEdge ESPN college availability and QB evidence intake

**Status:** Research/PAPER 0u. Does not create official model injury inputs, starter designations, model probabilities, bets or stakes. No model, frozen v5, or historical file modified.

This standard-library tool attempts a **free public** ESPN injury and roster capture for both men's CBB and CFB. It records the **actual HTTP JSON response bytes**, SHA-256, URL and capture time. It does not rewrite those bytes into a purported original receipt. Its output is a private, create-only local directory, not a public GitHub data commit.

## Public ESPN sources

- CFB league-wide injuries: `https://site.api.espn.com/apis/site/v2/sports/football/college-football/injuries`
- CBB league-wide injuries: `https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/injuries`
- Team rosters: `https://site.api.espn.com/apis/site/v2/sports/{football/college-football|basketball/mens-college-basketball}/teams/{ESPN_TEAM_ID}/roster`
- MBB team injuries: same basketball team route, ending `/injuries`
- CFB team depthcharts: football team route, ending `/depthcharts`. **Depthchart/roster does not confirm the starter**.
- The CFB team-specific `/injuries` endpoint is documented by SportsDataverse as returning empty objects, so this code does not rely on it.

References: [cfb ESPN site API docs](https://py.sportsdataverse.org/docs/cfb/reference/site/other), [cfb team docs](https://py.sportsdataverse.org/docs/cfb/reference/site/team), [hoopR injury helpers](https://rdrr.io/cran/hoopR/src/R/espn_basketball_injuries_helpers.R).

These endpoints are publicly accessible without a paid subscription, but availability and data coverage are **not guaranteed**. ESPN may rate-limit or return empty/partial schemas. Unknown/missing data is always **UNKNOWN**, never `healthy`, `active`, or `cleared`. Historical playback is not guaranteed: these endpoints serve current data, not an authenticated point-in-time archive. Capture BEFORE each game.

## Required input: exact event/team-ID slate

Create a *private* CSV with header:

```csv
sport,event_id,kickoff_utc,home,away,home_espn_id,away_espn_id
CFB,example-game-1,2026-11-21T18:00:00Z,Exact Model Team Name A,Exact Model Team Name B,123,456
CBB,example-game-2,2026-11-21T19:00:00Z,Exact Model Team Name C,Exact Model Team Name D,789,101
```

These are **illustrative fake IDs**, not real teams or scheduled games. For a real run, assemble the exact 51-game CBB and 58-game CFB event inventories, kickoff timestamps and ESPN IDs. Verify the ID-to-team mapping via ESPN scoreboards/official source; this script does **not** fuzzy-match team names or infer IDs.

Use the exact team names expected by `models/cbb/sportsedge_cbb_model.py` and `models/cfb/sportsedge_cfb_model.py`. Duplicate event keys, reused ESPNs IDs for different named teams, same-team games and non-offset kickoff timestamps are rejected.

## Live capture

```bash
python research/audit/espn_college_availability_intake.py \
    --slate /private/slate_exact_ids.csv \
    --out-dir /private/espn_availability_2026-11-21_0815CT
```

**Do not put private betting data, an API key, or unreviewed medical information in the public repository.** The capture directory must not already exist. HTTP body size max 4 MB per endpoint; all requests are to the fixed `site.api.espn.com` host. Network errors and HTTP error pages remain explicit fetch failures in the manifest, not healthy teams. If one team fails, all teams are still recorded with coverage warnings; the code never drops the missing rows.

### Output

- `capture_manifest.json` — source URLs, raw SHA-256 hashes, capture times and failures; source claims are not independent authenticity proof
- `raw_espn/*.json` — exact response bytes for every successful ESPN HTTP response
- `coverage.json` — one record for **each team on each game** with `REVIEW_REQUIRED`, source limitations, and `official_eligibility:false`
- `injury_candidates_FOR_REVIEW.csv` — only reported injuries, roster ID/name comparison, conflict/staleness flags; `model_role` and `impact` always blank, `approved_for_model:false`
- `qb_roster_NOT_STARTERS.csv` — roster-identified QB candidates for manual starter investigation. Every one has `starter_confirmed:false`, even if a depthchart response exists.

**Never rename** the injury-candidate file directly into `injuries.csv`. The current CFB model assigns a `QB` impact of about −5.5 points to a QB with `status=OUT`, and the CBB model assigns role-based injury deductions; applying those weights to backups or unverified injury rows is a serious leak/accuracy risk. Verify the actual starter, athlete ID, status, source publication time, and role with game-day team/official reporting before preparing any approved input.

CBB's MBB injury feed is often empty; CFB team injury endpoints may be empty, too. No entry does **not** mean zero injuries. If the source never reported an athlete, there is no clearance evidence. `NO_CONFIRMED_NEGATIVE_INJURY_COVERAGE` is always retained for each team.

## Offline replay (never claims live or source authenticity)

```bash
python research/audit/espn_college_availability_intake.py \
  --slate /private/slate_exact_ids.csv \
  --fixtures /private/espn_json_fixtures \
  --out-dir /private/espn_availability_offline_replay
```

Fixture filenames use keys such as `CFB__league_injuries__league.json`, `CFB__roster__123.json`, `CFB__depthcharts__123.json`, `CBB__injuries__789.json`, `CBB__roster__789.json`. A missing fixture is recorded as a source failure. No replay of current snapshots can establish what was publicly available before an earlier kickoff.

## Tests

```bash
python -m unittest discover -s research/audit -p test_espn_college_availability_intake.py -v
```

The tests cover sourced CBB and CFB injuries, QB non-confirmation, empty vs failed feeds, duplicate roster names, conflicting statuses, unknown status, clock cutoff, team-ID conflicts, create-only raw hashes and slate validation. Tests use fake teams and mock JSON only, never live ESPN data. The main `tests.yml` CBB job invokes these via the existing test script; no GitHub workflow-file edit or engine change.

## Missing evidence before official use

1. Exact 51/58-game event and team-ID censuses from independent, timestamped sources
2. Run the live HTTP capture **before** kickoff; inspect `coverage.json` for unknown source coverage
3. Resolve and independently confirm starting QB and injury role/impact (team official report or equivalent); handle contradictory reports explicitly
4. Add independent player availability and lineup sources where ESPN reports no data; do not infer an absence from no rows
5. Version model inputs, preserve an immutable point-in-time receipt, and walk-forward test adjustment effects on unseen outcomes
6. Once accepted, use a **separate operator-reviewed export** to the existing input schemas; do not bypass SportsEdge's closed/blocked gates

**No automatic model-eligibility promotion.**
