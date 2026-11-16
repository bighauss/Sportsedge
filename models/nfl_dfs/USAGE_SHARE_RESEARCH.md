# Point-in-time NFL role inputs (PAPER/0u)

Run: cd models/nfl_dfs && python test_usage_share_features.py

For usage_share_features.py, create a private manifest JSON with:
source_path (relative to manifest), source_sha256, compressed (true for .gz),
captured_at_utc, kickoff_utc, season, target_week, and roster array of
{player_id,team} bound from an independently verified GSIS roster. Optional:
half_life_days=180, shrink_pseudo_team_opportunities=20, min_prior_weeks=3.

Run: python usage_share_features.py /private/asof.json --output /private/usage.json

It never changes accepted game inputs or v5. Only targets/carries are present
in these nflverse weekly rows; snap and route shares remain null. Source hashes
and declared times are not signed sportsbook/source authentication. Do not
fill missing IDs by name or backfill historical as-of files after outcomes.
Require real forward sample, minutes/role mapping and market-by-market scoring
before evaluating production adoption.
