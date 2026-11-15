# nflverse in Python (2026)

`nflreadpy` is the official Python port of nflreadr. `nfl_data_py` is deprecated.

```
pip install nflreadpy        # or: uv add nflreadpy
```

```python
import nflreadpy as nfl
pbp = nfl.load_pbp()                       # current season
pbp = nfl.load_pbp([2024, 2025, 2026])     # list of seasons; True = all (1999+)
pbp_pd = pbp.to_pandas()                   # returns Polars by default

ngs_pass = nfl.load_nextgen_stats(stat_type="passing")    # CPOE, air yards (2016+)
ngs_rec  = nfl.load_nextgen_stats(stat_type="receiving")  # separation, target share
ngs_rush = nfl.load_nextgen_stats(stat_type="rushing")    # RYOE

nfl.get_current_season(); nfl.get_current_week(); nfl.clear_cache()
```

| Function | Loads |
|---|---|
| load_pbp | Play-by-play (EPA, success) |
| load_nextgen_stats(stat_type=) | NGS passing/receiving/rushing |
| load_player_stats / load_team_stats | Weekly/season summaries |
| load_schedules | Schedules + results |
| load_rosters / load_rosters_weekly | Rosters |
| load_injuries | Injury reports |
| load_snap_counts / load_participation | Snaps, personnel |
| load_pfr_advstats | PFR advanced |
| load_depth_charts | Depth charts |
| load_ftn_charting | FTN charting |

The data comes from nflverse-data GitHub releases, with memory and filesystem caching.
