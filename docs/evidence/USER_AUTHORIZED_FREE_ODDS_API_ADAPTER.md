# SportsEdge — authorized $0 odds aggregator intake (research only)

**This is a source-adapter candidate, NOT an approved primary sportsbook receipt.** The Odds API at **https://the-odds-api.com/** advertises a free usage tier (500 credits/month as of Nov 15, 2026) and lists NFL (`americanfootball_nfl`) and college basketball (`basketball_ncaab`), with the read-only v4 endpoint documented at https://the-odds-api.com/liveapi/guides/v4/ . *Different provider:* `theoddsapi.com` has a more restricted free plan; do not confuse domains or undocumented endpoints.

**Owner action required:** Create/authorize a FREE API key on that specific provider site. Do **not** paste any key into ChatGPT or commit it to this public GitHub repo. This runner requires the key in the local environment `SPORTSEDGE_ODDS_API_KEY`. In a private terminal/outside this repository, run:

```sh
export SPORTSEDGE_ODDS_API_KEY='your-own-user-provisioned-key'
python -m sportsedge.odds.free_odds_aggregator_intake NFL /private/sportsedge-original-odds
python -m sportsedge.odds.free_odds_aggregator_intake CBB /private/sportsedge-original-odds
# A provider event ID may be taken only from actual provider output, not guessed:
python -m sportsedge.odds.free_odds_aggregator_intake NFL /private/sportsedge-original-odds \
  --event-id REAL_PROVIDER_EVENT_ID --markets h2h spreads totals player_pass_yds player_rush_yds
```

**Security:** This uses only the documented GET API URL via authenticated user-owned key, with a strict allowlist of NFL/CBB, sportsbook names and market syntax. Network HTTP errors deliberately never print URLs or API keys. Original provider response JSON is saved with `0600` permissions in a *private folder outside this public repository*, with SHA-256, local UTC receipt time, optional upstream server Date, claimed market-update time, and credit balance. Only synthetic no-key tests run in public CI; no real odds, credentials, or bet records may be put in GitHub/Actions artifacts.

**Coverage honesty:** Main /odds defaults to h2h/spreads/totals; this is not an all-market claim. To capture player props, TD families, period and alternate ladders, use the documented event-scoped endpoint and explicit actual market keys available from that provider. Unreturned market families are recorded as **missing/unverified** rather than claimed not offered. Live or past-kickoff rows are counted as blocked, not transformed to pregame. Source age >300 seconds or lacking a market-update timestamp is quarantined and counted. The runner is a *raw upstream data archive*, not a price/EV decision engine; downstream R4 and RUN IT v2.1 must still enforce both-side integrity, canonical provider-event/player/outcome IDs, odds freshness, role/lineup confirmation, sport/period settlement and all markets.

**Release limitation:** A key proves authentication to an **aggregator**, not to DraftKings and FanDuel independently. The Odds API can report different upstream book names but cannot alone prove two original authenticated sportsbook source chains as required by Issue #10 Gate A. No line is credited as independent +EV or CLV without separate trusted-book/source original receipts. No player/stat forecasts, real distributions, historical odds, WORM timestamps, future CLV or calibration are supplied by this adapter. It always emits PAPER / 0u, never places wagers or certifies release; protected frozen v5 remains unchanged.

**Tests:** `python -m unittest sportsedge.odds.test_free_odds_aggregator_intake -v` (15 synthetic tests on Nov 15).
