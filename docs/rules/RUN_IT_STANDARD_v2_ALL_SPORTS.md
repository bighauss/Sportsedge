# RUN IT STANDARD v2 — ALL SPORTS, DEEP MODELS (Isaac, Nov 15 2026)
Supersedes the sport-specific weights in the CFB/CBB addendum where they overlap. NFL = main standard + Next Gen Stats addendum. All sources FREE only.

## Shared pipeline (every sport, every market)
1. Team projection = 50% SportsEdge ratings model + 50% advanced-stats matchup (below). Season stats regressed toward league mean by sample size (k games: NFL 8, CFB 6, NBA 20, CBB 12, NHL 30, MLB 60).
2. Adjustments: injuries/lineups (confirmed only), travel/rest, pace, weather/park/venue.
3. Pricing: sport SD table (below) -> win p per market; raw EV + blended EV (30% model / 70% no-vig market). Rank by EV. Never block +EV from showing.
4. Props: USAGE x EFFICIENCY x OPPONENT model, blended 70/30 with market-implied mean until calibrated.
5. Filters: drop plays whose line contradicts the projection; flag same-signal stacks; no stale lines (prices must be from this run's capture).
6. Card: Munich format — header/logos, projection strip, Game Card + Prop Card by EV (price, win %, raw EV, blended EV, stars, flames, key stat per play), Key Inputs strip.
7. Grade every card: W/L/P, 1u flat, CLV vs close; feeds background recalibration of weights/SDs/elasticities.

---
## MLB (Statcast / Baseball Savant) — season starts spring 2027; build now, test on 2026 data
Sources: baseballsavant.mlb.com CSV exports (custom leaderboards, Statcast search), FanGraphs (free tables), MLB StatsAPI (lineups, probables, umpires), park factors (Savant), weather (NWS / open-meteo).
Starter: xERA, xwOBA allowed, K%-BB%, CSW%, whiff% by pitch, pitch mix, velo trend (last 3 starts vs season), avg pitch count / leash, times-through-order penalty.
Matchup: batter xwOBA/xSLG vs pitch type x pitcher usage of that pitch; platoon splits (regressed); barrel%, hard-hit%, launch angle sweet-spot%; bat speed / squared-up% (Savant bat tracking).
Bullpen: last-3-days pitch counts (fatigue), bullpen xFIP/K-BB, high-leverage arms available.
Lineup: confirmed lineup only; lineup-weighted xwOBA by batting order PA expectations (1st 4.6 PA -> 9th 3.8).
Environment: park factor by handedness, temp (+1% run env per ~10°F), wind out/in (Wrigley etc.), roof status, altitude; home-plate umpire zone size (run impact).
Defense/catcher: OAA team, catcher framing runs.
Runs model: per-inning simulation or Poisson with team expected runs; NRFI from 1st-inning splits + top-3 lineup vs starter.
Markets: ML, RL, totals, F5 (starter-only), NRFI/YRFI, team totals.
Props: pitcher Ks = expected batters faced x K% vs lineup (lineup K% vs hand, CSW) ; outs recorded = leash; batter hits/TB/HR = PA x xBA/xSLG/barrel% vs pitch mix x park.
SDs: runs per team ~ negative binomial (var ≈ 1.6x mean); total SD ~4.3.

## NBA
Sources: nba.com/stats (browser agent, JS), basketball-reference, pbpstats.com, cleaningtheglass (free parts), official injury report (5pm/1:30pm ET updates).
Matchup: ORtg/DRtg (last 15 games 40% / season 60%), pace (avg of both, adjusted), four factors (eFG, TOV, ORB, FTr) offense vs defense.
Lineups: confirmed starters; on/off net rating for missing players -> point adjustment; minutes redistribution.
Rest/travel: back-to-back -1.5 to -2.5 (road B2B worse), 3-in-4, altitude (DEN/UTA +), time zones.
Home court: ~+2.0 (modern).
Props: minutes projection x usage% x per-minute rates (pts, reb, ast, 3PA x 3P%) vs opponent position defense and pace; minutes cut for blowout risk (spread > 10).
SDs: margin 12.5, total 18, team total 11, 1H ≈ 0.49 x total.

## NHL
Sources: MoneyPuck (free CSV), Natural Stat Trick, NHL API (lineups, goalies), DailyFaceoff (confirmed goalies).
Matchup: 5v5 xGF/60 vs xGA/60 (score & venue adjusted), PP xGF vs PK xGA x expected PP opportunities (penalty rates).
Goalie: confirmed starter only; GSAx/60 (regressed heavily, k = 1500 shots); backup = big adjustment.
Rest: back-to-back -0.15 to -0.25 goals; travel/time zones.
Home ice ~+0.15 goals.
Goals model: Poisson per team (+ empty-net adjustment late for favorites); OT/SO 3-way and 2-way ML conversion.
Markets: ML (2-way and regulation 3-way), puck line, totals, team totals, periods.
Props: shots on goal = TOI x shot rate (iCF/60) x opponent shot suppression; points = TOI x on-ice xGF share x IPP; goalie saves = opponent shots x save% (regressed).
SDs: Poisson; total var ≈ 1.15 x mean.

## CFB
Sources: collegefootballdata.com (free API key: PPA/EPA, success rate, havoc, recruiting/talent, returning production), cfbfastR data, ESPN FPI (free), SP+ / Sasser / Corbie as cross-checks only.
Matchup: EPA/play & success rate offense vs defense (rush/pass split), explosiveness, havoc rate, finishing drives (pts per opp), field position.
Priors: talent composite + returning production early season (fade by week 6).
Adjust: QB out -4 to -7, home +2.5 (stadium-specific 1.5–4), travel 2+ zones -0.5, weather (live: wind 15+ -2, rain/snow -2 to -3), altitude, motivation/lookahead flag (no number).
Pace: plays/game both teams (tempo) -> total.
Props: same usage model as NFL using CFBD player usage share.
SDs: margin 15.5, total 15, team total 11.

## CBB (college basketball)
Sources: barttorvik.com (FREE — adjusted efficiency, tempo, game predictions; KenPom is paid -> not used), sports-reference CBB, team injury news.
Matchup: AdjO vs AdjD per 100 poss x projected possessions (tempo avg, adjusted); four factors; 3PA rate vs opponent 3P defense (regress 3P% heavily).
Home court +3.0 (venue-specific 2–4.5); neutral 0.
Adjust: top-2 usage player out -2 to -4; travel/back-to-back road -0.75; altitude (BYU/Utah/Colorado/Air Force/Wyoming/New Mexico +).
Props: minutes x usage x per-40 rates vs opponent.
SDs: margin 11, total 11 (scale w/ tempo), team total 8.

## NFL (reference)
Main RUN IT STANDARD + Next Gen Stats addendum (nflverse nextgen_stats releases): EPA/play, success rate, pressure rate, PROE, target/air-yards share, separation, RYOE, CPOE.

---
## Build order (sport priority + season)
1. NFL — live now (done today).
2. CFB + CBB — in season; wire CFBD + barttorvik next.
3. NBA + NHL — in season; wire MoneyPuck/NST and nba.com via browser agent.
4. MLB — offseason; build Savant pipeline and backtest on 2026 data before Opening Day.

## Calibration
Every weight above is a starting value, not proven. Grade every card; after 100+ graded plays per sport, refit weights, SDs and prop elasticities. Recalibration runs in the background and never blocks showing picks.
