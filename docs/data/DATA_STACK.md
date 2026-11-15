# SportsEdge free data stack (Nov 2026)

```
pip install nflreadpy sportsdataverse pybaseball nba_api polars pandas requests
```

| Sport | Primary | Fallback | Key metrics | Markets |
|---|---|---|---|---|
| NFL | nflreadpy (nflverse: PBP/EPA, Next Gen Stats) | Pro Football Reference | CPOE, air yards, separation, target share, RYOE, EPA, success rate, pressure rate, snap counts | ML, spread, total, team total, props |
| CFB | CollegeFootballData API / sportsdataverse.cfb | ESPN (SP+/FPI/Sasser/Corbie cross-check only) | EPA/PPA, success rate, explosiveness, havoc | ML, spread, total, team total, props |
| NBA | nba_api (stats.nba.com) / sportsdataverse.nba | Basketball-Reference, pbpstats | ORtg/DRtg, four factors, pace, tracking, on/off, lineup net | ML, spread, total, team total, props (minutes × usage) |
| CBB | BartTorvik | Sports-Reference, sportsdataverse mbb | Adj O/D, tempo, four factors, 3P% (hard regression) | ML, spread, total, team total |
| NHL | MoneyPuck CSVs / sportsdataverse.nhl | Natural Stat Trick | 5v5 xGF/xGA per 60, high-danger chances, goalie GSAx, Corsi/Fenwick | ML, puck line, total, team total, SOG/points/saves |
| MLB | pybaseball (Statcast/Savant, FanGraphs) | FanGraphs exports, MLB StatsAPI | EV, LA, barrel%, xwOBA, bat speed, OAA, framing, CSW, pitch movement | ML, RL, total, team total, F5, NRFI/YRFI, K/hits/TB/HR |

## Market → inputs
| Market | Inputs |
|---|---|
| ML / spread / puck line / run line | Team efficiency (EPA, ORtg/DRtg, xG), home, rest, injuries |
| Totals / team totals | Pace + efficiency + weather (outdoor) + goalie/SP |
| Props | Usage × efficiency × opponent; minutes/ice time/batting order; volume floors |
| F5 / NRFI | SP + top of order + park + umpire |

## Rules
- No tracking-level data exists publicly for CFB or CBB, so don't wait for it or invent it. Use EPA/success (CFB) and BartTorvik (CBB).
- No paid sources (PFF, full Second Spectrum, KenPom).
- If a primary metric is missing or below the regression threshold, fall back to season efficiency, drop confidence one level, or skip.
- Log package versions and pull timestamps on every card.
