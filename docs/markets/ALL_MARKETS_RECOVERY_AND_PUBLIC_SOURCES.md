# SportsEdge five-sport all-market research integration — Nov 15, 2026

**This is new isolated research infrastructure, NOT an adopted real-money engine.**
Frozen `research/r5/nfl/sportsedge_v5.py` is unchanged. No live bets or API
credentials. All outputs are `PAPER_0U` or `BLOCK`, with `card=None`,
`approved_stake_u=0`, `official_counted=0`. No historical pregame
card or forward-test baseline is altered.

## Architecture and recovered model wiring

| Layer | Code | What it does | Still missing |
|---|---|---|---|
| Own team projections | `projection_bridge.py` | Calls Claude CFB/CBB/NBA/MLB **projection functions only**. For NFL, checks the frozen R1 ridge forecast against the source ratings. Hashes model-feature bytes; excludes prices. | Independently frozen publication timestamps, injury/lineup evidence, calibrated forecast quality |
| Public stats capture | `source_ingestion.py`, `public_release_capture.py` | Lists public repositories; parses original CSV/gz, rejects duplicate/invalid fields; optional NFL release digest-verified downloader into **private external archive** | Real feed auth/PIT certification; source-specific CFB/NBA/MLB APIs; no booked odds |
| NFL offensive touchdown share | `nfl_td_shares.py` | Builds player rushing+receiving TD shares by year/week/team, rejects duplicate IDs and future weeks, checks 32-team coverage | Current full-file hash, active lineup, joint team TD/scoring process, ATTD/first/2+ calibration |
| Outcome distribution | `projection_distribution.py` | Explicit external model SDs/period shares and player-stat moments → deterministic provisional score+player scenarios | Validated error distributions and joint correlations. It **never** manufactures touchdown or first-basket event sequences |
| Market pricing | `allmarkets_research.py` | Exact scenario grading for single and period markets, props, TDs and first score; exact quote pair, push-aware raw+30/70 blended EV; parlay **joint** simulation, not leg multiplication | Verified current DK/BestBook lines; independent provider receipt checks; calibrated probabilities; posted SGP odds |
| Independent player prop intake | `player_forecast_intake.py` | Reads original hashed CSV of per-player ID, team, sport/stat, mean+SD, model training/feature freeze, active roster, volume/lineup; rejects all odds/market-implied means as features. | Real independently observed pregame source snapshots, player-level width calibration and joint game/player correlations |
| Chronological test | `chronological_calibration.py` | Walk-forward fitted train-only margin/total widths; holdout MAE, Brier, log loss; leak-preventing timestamps | Authenticated long-run historical forecasts/results, three signed cycles, independent price/CLV evidence |
| Card/risk integration | `run_it_research.py` | Runs each candidate through existing v2.1 guards, stores unverified quote receipts and risk decisions in the same local hash chain, emits **no official card** | Independent quote authenticity, actual v2.1 full production inputs, per-market promotion signoff |

## Markets covered at the scenario-engine level

- **NFL**: FG/1H/2H/quarters, spread, moneyline, totals, team totals;
  passing/rushing/receiving/target/player-yard and count props; ATTD, first TD,
  2+ TD; conditional joint same-game parlays (SGP).
- **CFB**: same football game and player-market settlement families; TD
  projections only where full roster/scoring-event traces exist.
- **CBB**: FG/1H/quarters, sides, totals, team totals, player points/rebounds/
  assists/3PM/PRA/steals/blocks, first basket only with complete ordered events.
- **NBA**: same basketball families, with its own minutes/lineup gate.
- **MLB**: moneyline, run line, total, team totals, F5, first-inning NRFI/YRFI,
  pitcher K/outs, hits/TB/HR/RBI/runs/walks; SGP joint scenarios.
- **NHL** is maintained in Claude's recovered sport-specific module but is
  intentionally not included in this five-sport user-scope kernel.

**Period-specific player stats:** a 1H/1Q player prop requires separately simulated 1H/1Q player outcomes; the model will not reuse full-game player statistics. Both DK sides must carry the same original provider-market ID and settlement definition.

This is **coverage for evaluating externally generated scenario outcomes**,
not proof all markets have reliable independent projections today. Missing
players, play-by-play chronology, model variance, verified two-sided prices or
settlement details yield **BLOCK**, never market-only fake projections.

For all single-market EVs, the script requires both actual DraftKings
complementary captured sides for the **same event, period, market definition,
line and settlement**, with original raw hashes and a sub-300-second pregame
window. It calculates separate win / push / loss probabilities. The stated
`30% model / 70% no-vig market` is reported as an **unverified diagnostic**
and is never used to authorize a stake. Market prices are not inserted into
the independent team-projection model.

For SGPs, the engine uses the frequency of ALL legs winning in the same
scenario. It requires an exact-leg fingerprint and a contemporaneous
DraftKings parlay quote. **A push anywhere blocks pricing** until posted
SGP-specific settlement rules can reprice that combination. No quoted offer,
no SGP model-vs-market EV.

## Public projects and source access audit

The following are **existing open-source project references**, not installed
bookmaker/trading bots or verified production data connectors:

| Sport | Public sources and open-source repos | Intake / limitations |
|---|---|---|
| NFL | [nflverse-data](https://github.com/nflverse/nflverse-data), [nflreadpy](https://github.com/nflverse/nflreadpy), [nflfastR](https://github.com/nflverse/nflfastR) | PBP, stats_player_week, NGS passing/rushing/receiving, depth, snaps; official inactives require separate current dated record |
| CFB | [cfbfastR](https://github.com/sportsdataverse/cfbfastR), [sportsdataverse-py](https://github.com/sportsdataverse/sportsdataverse-py) | EPA/PPA, team season results, QB/roster; CFBD free API key may be required; no paid SP+ |
| CBB | [hoopR](https://github.com/sportsdataverse/hoopR), [Bart Torvik](https://barttorvik.com) | Free adjusted efficiency/tempo, NCAA games and player history; no KenPom subscription |
| NBA | [nba_api](https://github.com/swar/nba_api), [hoopR](https://github.com/sportsdataverse/hoopR) | NBA stats/PBP; provider can throttle; official injury/lineup update must be archived independently |
| MLB | [pybaseball](https://github.com/jldbc/pybaseball), [MLB StatsAPI](https://github.com/MLB-StatsAPI/MLB-StatsAPI) | Savant/Statcast xwOBA/xERA, pitcher and batter splits, verified starting pitcher/lineups and park factors |

**Public data release facts checked Nov 15:** nflverse `stats_player` contains
`stats_player_week_2026.csv.gz`; `pbp` contains
`play_by_play_2026.csv.gz`; `nextgen_stats` contains cumulative
`ngs_passing.csv.gz`, `ngs_rushing.csv.gz`, and
`ngs_receiving.csv.gz`. A recent release timestamp does not automatically
make any row valid at an older historical betting decision.

Authorized optional source pull (NO side effect unless directly invoked):

```bash
python -m sportsedge.markets.public_release_capture NFL_WEEKLY_2026 /private/sportsedge-archive
python -m sportsedge.markets.public_release_capture NFL_NGS_PASS /private/sportsedge-archive
```

This verifies GitHub's recorded SHA256 digest, keeps the original bytes in a
new non-overwriting archive file, and writes a local research-only manifest.
It does **not** independently authenticate a sportsbook or establish PIT
provider publication. The operator must validate the downloaded data's season
and week coverage before use. The official sportsbook quote path remains
Issue #10. No BestBook API or URL is invented; its DK display is not an
independent second sportsbook quote.

## Run synthetic acceptance

```bash
python -m unittest sportsedge.markets.test_allmarkets_research -v
python -m unittest sportsedge.markets.test_projection_bridge -v
python -m unittest sportsedge.markets.test_run_it_research -v
python -m unittest sportsedge.markets.test_player_forecast_intake -v
python -m unittest research.audits.test_multisport_quote_ev_regressions -v
python -m unittest sportsedge.odds.test_issue10_offline -v
```

All tests use fake teams/players, fake quote values, and deterministic scenarios.
Do NOT confuse passing tests with Brier/CLV/ROI on authenticated real slates.

## Remaining hard gates (Issue #10)

1. Valid API/export permissions, source and identity receipts, 2 independent
   original books, fresh prices, no duplicated single-aggregator book.
2. Real player and team point-in-time roster/lineup/injury/pace/weather
   snapshots with independent source hashes and cutoffs before each game.
3. Three signed walk-forward calibration cycles **on actual pregame outputs**
   with no leaks; calibration by market, period, prop stat and scoring count.
4. Genuine matching open / take / close quotes for 200 settled selections,
   with proper comparable win/push/no-vig economics.
5. RUN IT v2.1 connected before every event/market card, with 100 consecutive
   fully logged no-bypass runs, 5u/day, 2u/game, 3u/theme and injury T−90
   reprice locks.

Minimum 5 real-slate days, 100 consecutive compliant cards, 200 independently
gradeable selections, independently reviewed signed promotion. No automatic
promotion after 100 samples; no promises of profit.

> **Audit rule:** Price absent or model feature absent -> visible BLOCK reason.
> Invalid market calibration -> PAPER / 0u. An apparent +EV longshot based only
> on historical scoring shares is never official. No unverified data or paid
> service should be silently substituted.
