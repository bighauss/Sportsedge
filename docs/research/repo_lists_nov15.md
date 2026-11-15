# Outside GitHub repos Isaac flagged (Nov 15 2026)

These are for reference only. None of them is installed or used by SportsEdge. Anything that trades or places orders is out of scope: SportsEdge never places bets automatically.

## Polymarket bots (from an X post)
The post gave truncated links, so the full repo paths are unknown.

| # | What it claims | Link as shared |
|---|---|---|
| 1 | AI trading agent, 118 strategies, research/analysis dashboard for prediction markets | github.com/recogardtech/A… |
| 2 | Backtester: simulates a strategy on historical markets (P&L, win rate, risk) | github.com/evan-kolberg/p… |
| 3 | Copy trading, arbitrage, smart-money/whale alerts, sports trading, spread farming | github.com/tarpboi/Predic… |
| 4 | Weather trading from forecasts + METAR/SPECI airport observations | github.com/yangyuan-zhen/… |
| 5 | Limit-order manager for Polymarket liquidity rewards | github.com/lihanyu81/poly… |

**Possibly useful to SportsEdge:** #2's backtesting approach (walk-forward, full loss inclusion) and #4's METAR/weather pull, as a free weather input for outdoor NFL/CFB/MLB.

**Caution:** treat unknown trading bots as untrusted code. Never give them wallet keys or account credentials.

## "50 useful GitHub repos" graphic
Saved as `50_useful_github_repos.jpg`. Relevant picks:
- `public-apis/public-apis`: catalog of free APIs (look for free sports/weather feeds).
- `TauricResearch/TradingAgents`: multi-agent analysis framework (design ideas only).
- `browser-use/browser-use`, `browserbase/stagehand`, `mendableai/firecrawl`: browser/scrape tooling for JS pages like nba.com/stats and nextgenstats.nfl.com.
- `n8n-io/n8n`: free self-hostable automation. It needs a server, so it doesn't fit a phone-only setup.
