# Public GitHub scout (Nov 15 2026) — for Claude, ChatGPT, Muse

Method: web search of public repos and docs per sport, then read README text. I did NOT run any of their code. Every performance claim below is the repo author's own README claim unless marked "walk-forward NLL" (reported with a baseline). Do not copy GPL code (e.g. kenpompy is GPL-3.0); copy ideas and call public APIs.

## 1. Repos worth studying (public)
| Repo | Sport | Why it matters |
|---|---|---|
| Nicowirz/nfl-props | NFL | Most honest README found. Walk-forward NLL vs naive baseline per market, calibration deciles, lists what FAILED. |
| hadantes-lab/ff-model | NFL | nflverse + Odds API, per-player mean+std, Monte Carlo, walk-forward backtest with hit rate, ROI, CLV. Same architecture as ours. |
| Beans0v0/proplab | NFL+NBA | Shared game draws, teammate usage competition, NBA minutes x per-minute rate x pace/script, walk-forward calibration tab; states what NBA lacks. |
| mattleonard16/nflalgorithm | NFL+NBA | Minutes model feeds rate model; opponent defense, EWMA volatility, isotonic calibration, injury redistribution, 5,000-draw Monte Carlo for correlated portfolios; drift and importance checks. |
| bviolino93/NBA-model | NBA | Recipe: start from sharp-market fair line, add only adjustments that beat the closing line walk-forward; recency-weighted ridge ratings refit each game day on earlier games only; logs lines nightly; checks that "opening" lines are real openers. |
| Rmhoward96/Sports_model | MLB-first | Shrinkage + odds-ratio matchup blend, prop distributions from per-PA vectors, DuckDB + Parquet warehouse, no-vig/CLV helpers, tests on model math. |
| FullCountProps (baselinemlb, open source) | MLB | LightGBM on 33 Statcast features -> 8 PA outcomes, PA-level Monte Carlo (about 2,500 sims/game), confirmed lineup from MLB Stats API, shows park/umpire/framing/weather per pick, surfaces props only at 3%+ edge ("below that is noise"). |
| mghnasiri NHL goal predictor | NHL | 8 models side by side incl. market baseline; Monte Carlo assigns team goals to players weighted by scoring rate^1.8; recent-form boost capped +30%; PP bonus; lineup/TOI scaling; xG XGBoost on play-by-play shots. |
| chanzer0/NFL-DFS-Tools | DFS | opto, classic sim, showdown opto and sim sharing one correlation/sampling logic; distribution and correlation files. |
| jamji/draftfast, pydfs-lineup-optimizer | DFS | Rule sets for DK NFL/NBA/MLB Showdown and classic across sports. |
| pradazay1-code/Sports-betting-model | 5 sports | Free GitHub Actions + Pages pipeline; per-(sport,market) trainers; walk-forward harness; ESPN/MLB/NHL/NBA endpoints. |
| JXiong15/sports-parlay-generator | NFL | Free data stack: nflverse weekly stats, snap counts, injury reports since 2009, Kalshi prices, Action Network public betting %. |
| andreweatherman/cbbdata, toRvik | CBB | Free Barttorvik-based API (free key); game/tournament predictors. |
| sportsdataverse-py, hoopR, baseballr, fastRhockey, oddsapiR | all | Unified free wrappers: ESPN, NBA Stats, MLB Stats API/Savant, NHL, KenPom, Odds API, CFBD. |

## 2. Specific weights and numbers found (use as starting priors, validate on our data)
- Nicowirz NFL props: target log(yards+10); weighted ridge; recency weight 0.5^(days/180); ridge reg 5.0; player+opponent shrinkage but not intercept/home; sigma per position group when >=30 residuals; min usage 10 pass att / 5 carries / 2 targets. Walk-forward NLL improvement vs baseline: pass yds ~15%, rush ~9-10%, rec yds ~9-10%, receptions ~6%, pass TD ~2%, rush/rec TD ~5%, game margin ~1.9%, totals ~1.2% (author warns baselines flatter the model). USAGE-SHARE covariate helped (rec yds ~3%, rush yds ~10%). PACE ADJUSTMENT DID NOT HELP (no gain or worse) and was dropped. Independent-sum fantasy distribution is overconfident (not validated). Game margin tails too narrow.
- Lesson: TD markets are weakest (about 95% zeros); game totals and margins have tiny edge over baseline; player volume markets have the most signal.
- NHL Monte Carlo: goal share raised to power 1.8; recent-form multiplier capped at +30%; opponent goals-against factor (3.5 vs 3.07 league avg ~ +14% environment).
- MLB: 2,500 sims/game, 33 features, 3% minimum edge; pitcher-prop writeups say totals/lines are too sharp to beat, and profitable edges were mostly UNDERS on pitcher props; recommend only bet types that stayed profitable.
- CFB: hybrid spread = 70% one model + 30% another; opponent-adjusted EPA (rushing/passing, offense/defense) is the standard feature set; CFBD publishes a training dataset 2016-2024.
- CBB: single feature AdjEM difference logistic is about log-loss 0.545 and hard to beat; add four factors, tempo, SOS, injuries via replacement model; roster churn is the main noise.
- NBA: build minutes first (game script/blowout, foul trouble, injuries), then per-minute rates x pace; teammate-out usage redistribution; PRA combo needs a copula, not independent sums.

## 3. Free data sources by sport (all public)
- NFL: nflverse (pbp, player stats, snap counts, rosters, injuries since 2009, NGS, FTN charting where free), ESPN site API, Kalshi read-only prices, Action Network public betting %.
- NBA: nba_api (stats.nba.com), ESPN box scores and injuries, balldontlie free tier (games/players only; stats/odds paid), pbpstats (derived), hoopR.
- MLB: MLB Stats API (schedule, lineups, boxscores), Baseball Savant/Statcast via pybaseball, FanGraphs/BRef (check terms), baseballr.
- NHL: api-web.nhle.com (schedule, boxscores, play-by-play), MoneyPuck (xG, free downloads), Natural Stat Trick, hockey-scraper, fastRhockey.
- CBB: Barttorvik (free) via cbbdata/toRvik, ESPN, hoopR; KenPom is paid (skip scraping unless terms allow).
- CFB: CFBD API (collegefootballdata.com; free key, tiers), ESPN, SP+ via ESPN, nflverse-style cfbfastR.
- Odds: The Odds API free tier (low quota), DK screenshots from Isaac, Kalshi, public betting %.

## 4. What these repos do that SportsEdge does not (gaps)
1. Walk-forward backtest per market vs a naive baseline (NLL/Brier), published even when it is bad. We have none validated.
2. Closing-line capture: nightly line snapshots (including props) so CLV is measurable. We capture screenshots only.
3. Minutes/snap/usage-share modeling feeding the sim (NBA minutes; NFL snap/target share). Our NFL roles are hand-set; that is the cause of the Brown/Gesicki/Dowdle gaps.
4. Calibration (isotonic or decile checks) and sigma estimated from residuals per position group.
5. Dispersion: Poisson/negative-binomial rates with shrinkage for low-sample players.
6. Correlated-portfolio risk (shared game draws; same-game exposure).
7. Market anchor: use sharp market line as the base and test if any model adjustment beats the close, rather than trusting the model's raw edge. This is what bviolino93 does and it directly addresses our long-shot moneyline losses.
8. A lineup/TOI/confirmed-lineup gate for MLB and NHL props.

## 5. What to DROP or distrust
- Pace adjustment in NFL props (failed in Nicowirz walk-forward) unless our own test shows gain.
- Independent sums for combo props (PRA, rush+rec, fantasy points): use shared draws or copulas.
- Any repo or site claiming 60-90% hit rates or +200% ROI (examples seen: 91.9% spread win rate, +244% four-season ROI, 62% CBB hit rate) without published pregame line captures. Treat as marketing; a 55% hit rate at -110 is already strong.
- Raw model-vs-market gaps as "edge": Nicowirz uses a 30-point plausibility cap and says reported edges are "feed price minus model fair number, not a proven inefficiency." Our guard (models/common/guard.py) is the same idea.
- Scraping paid or terms-restricted sites (KenPom, Sports Reference automated use).

## 6. Action list (priority order)
1. Capture closing lines for every card (Odds API free tier or DK screenshots at 5 min pre-start) into ledger/ so CLV works. (ChatGPT/Muse)
2. NFL: replace hand-set role inputs with nflverse snap/target/carry share (usage-share covariate), recency half-life ~180 days as a starting prior, shrink low-sample players; test vs baseline walk-forward. (ChatGPT builder + Claude sim)
3. Per-market walk-forward NLL vs baseline report for NFL props from nflverse history (no odds needed). (ChatGPT)
4. NBA: minutes model then per-minute rates x pace with teammate-out redistribution on the shared-sim pattern. (Claude)
5. MLB: PA-level matchup simulation using Statcast + confirmed lineups; only unders/stable bet types until proven. (in season)
6. NHL: goalie-adjusted shots/xG with goal-share^1.8 player assignment prior and capped form boost.
7. CBB: AdjEM/tempo base from Barttorvik (cbbdata), four factors, injury replacement; keep ratio guard because roster churn inflates gaps.
8. CFB: opponent-adjusted EPA (CFBD), market-anchored spread; test model adjustments against the close.
9. DFS Classic: reuse chanzer0-style shared sampling and correlation files idea (ideas only), on our shared sims.
10. Every new model ships with: baseline, walk-forward test, calibration deciles, gap guard, ledger entries.

## 7. Limits of this scout
Only README-level reading of ~15 repos and docs. No code run, no stats verified. Search covered NFL, NBA, MLB, NHL, CBB, CFB, DFS. Not covered: soccer, golf, tennis, MMA, NASCAR, WNBA; props markets beyond those listed; paid feeds.
