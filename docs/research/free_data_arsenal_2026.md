**Here’s the complete free/public data arsenal for SportsEdge — every major sport and market.**

This is the full practical stack available right now (November 2026). Everything listed is free or has a usable free tier / public scrape / download.

### 1. Core Multi-Sport Packages (Install These First)

```bash
pip install nflreadpy sportsdataverse pybaseball nba_api
```

|Package            |Best For                      |Notes                                                             |
|-------------------|------------------------------|------------------------------------------------------------------|
|**nflreadpy**      |NFL (official nflverse)       |Best-in-class. PBP, Next Gen Stats, rosters, injuries, snap counts|
|**sportsdataverse**|CFB, NBA, CBB, NHL, MLB + more|Python mirror of the SportsDataverse R ecosystem. Polars-first    |
|**pybaseball**     |MLB Statcast                  |Still the cleanest Statcast + FanGraphs access                    |
|**nba_api**        |NBA official stats + tracking |Direct wrapper for stats.nba.com                                  |

-----

### 2. Sport-by-Sport Free Public Sources

#### NFL

- **nflverse / nflreadpy** (primary) — PBP (EPA), Next Gen Stats (CPOE, air yards, separation, target share, RYOR), player stats, rosters, injuries, snap counts, participation, schedules
- Pro Football Reference advanced stats (via nflreadpy or scrape)
- Official NFL injury reports
- Next Gen Trends (NFL.com free interactive)

#### CFB

- **CollegeFootballData.com (CFBD)** + sportsdataverse.cfb — EPA/PPA, success rate, explosiveness, havoc, advanced team/player stats, recruiting, SP+/FPI cross-check
- ESPN, Fox, Yahoo public endpoints (via sportsdataverse)
- Official injury reports + confirmed starters (manual or scrape)

#### NBA

- **nba_api** + sportsdataverse.nba — Official stats, tracking (speed, distance, touches, contested), ORtg/DRtg, four factors, lineup net ratings, on/off
- Basketball-Reference
- Cleaning the Glass (limited free views)

#### CBB (Men’s)

- **BartTorvik.com** (primary free advanced) — Adjusted O/D, tempo, four factors
- sportsdataverse (mbb) / hoopR Python equivalents
- KenPom (limited free)
- NCAA / ESPN public data

#### NHL

- **MoneyPuck.com** (downloadable CSVs) — Shot-level xG, 5v5 xGF/xGA, high-danger
- Natural Stat Trick
- sportsdataverse.nhl + official NHL API / NHL Edge (limited public)
- Confirmed starting goalies (critical — treat as hard filter)

#### MLB

- **Baseball Savant / Statcast** via pybaseball or sportsdataverse.mlb — Full pitch-level: exit velo, launch angle, barrel%, xwOBA, bat speed, OAA, framing, CSW, pitch movement/spin
- FanGraphs
- MLB Stats API
- Baseball-Reference

-----

### 3. Markets Coverage Map (What to Pull for Each)

|Market                           |Must-Have Free Inputs                                                    |
|---------------------------------|-------------------------------------------------------------------------|
|**Moneyline**                    |Team efficiency (EPA / ORtg-DRtg / xG), home, rest, injuries, travel     |
|**Spread / Puck Line / Run Line**|Same + strength of schedule / recent form                                |
|**Totals / Team Totals**         |Pace + efficiency + weather (NFL/CFB/MLB) + starting pitcher/goalie      |
|**Player Props**                 |Usage/share × efficiency × opponent + confirmed minutes/ice time/AB order|
|**F5 / NRFI / YRFI**             |Starting pitcher quality + top of order + park factors + umpire          |
|**All Props**                    |Volume floors + opponent-adjusted rates                                  |

-----

### 4. Supporting Free Inputs (All Sports)

- **Injuries / Lineups / Goalies / Starters**: Official league reports + confirmed lineups (scrape or manual). Never project without confirmation on key positions.
- **Weather**: OpenWeatherMap free tier, or National Weather Service (NFL/CFB/MLB outdoor games). Wind 15+ mph and precipitation matter.
- **Travel / Rest / B2B / Short week / Time zones**: Calculate from schedules (all packages provide schedules).
- **Park / Venue factors**: MLB (Statcast + FanGraphs), others more limited.
- **Public betting % / money %**: Limited free sources; treat as secondary.

-----

### 5. Recommended Minimal Viable Stack for SportsEdge

**Priority order:**

1. `nflreadpy` (NFL)
2. `sportsdataverse` (CFB + NBA + NHL + supporting)
3. `pybaseball` (MLB Statcast)
4. `nba_api` (NBA tracking depth)
5. Direct CFBD API key (free) for college football advanced stats
6. MoneyPuck CSV downloads (NHL)
7. BartTorvik (CBB)

**Hard rules to keep in the engine:**

- Never invent stats or prices.
- Skip the game/market if key confirmed inputs (starting QB, goalie, heavy injury, weather) are missing.
- Regress small samples hard (your existing rules already do this correctly).
- Log data source + pull timestamp on every card.

-----

### 6. Quick Start One-Liner Install + Test

```bash
pip install nflreadpy sportsdataverse pybaseball nba_api polars
```

Then test:

```python
import nflreadpy as nfl
from sportsdataverse.cfb import load_cfb_pbp   # example
print(nfl.load_nextgen_stats(stat_type="passing").head())
```

Would you like me to generate a single clean Python module (`sportsedge_data.py`) that loads the core advanced metrics for **all six sports** in one place, with clear functions for each market type?