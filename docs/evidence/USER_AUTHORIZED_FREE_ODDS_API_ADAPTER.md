# SportsEdge — authorized $0 odds aggregator intake (research only)

**This is a source-adapter candidate, NOT an approved primary sportsbook receipt.** The Odds API at **https://the-odds-api.com/** advertises a free usage tier (500 credits/month as of Nov 15, 2026) and lists NFL, CFB, CBB, NBA, MLB and NHL, with the read-only v4 endpoint documented at https://the-odds-api.com/liveapi/guides/v4/ . *Different provider:* `theoddsapi.com` has a more restricted free plan; do not confuse domains or undocumented endpoints.

**Owner action required:** Create/authorize a FREE API key on that specific provider site. Do **not** paste any key into ChatGPT or commit it to this public GitHub repo. This runner requires the key in the local environment `SPORTSEDGE_ODDS_API_KEY`. In a private terminal/outside this repository, run:

```sh
export SPORTSEDGE_ODDS_API_KEY='your-own-user-provisioned-key'
python -m sportsedge.odds.free_odds_aggregator_intake NFL /private/sportsedge-original-odds
python -m sportsedge.odds.free_odds_aggregator_intake CBB /private/sportsedge-original-odds
python -m sportsedge.odds.free_odds_aggregator_intake CFB /private/sportsedge-original-odds
python -m sportsedge.odds.free_odds_aggregator_intake NBA /private/sportsedge-original-odds
python -m sportsedge.odds.free_odds_aggregator_intake MLB /private/sportsedge-original-odds
python -m sportsedge.odds.free_odds_aggregator_intake NHL /private/sportsedge-original-odds
# A provider event ID may be taken only from actual provider output, not guessed:
python -m sportsedge.odds.free_odds_aggregator_intake NFL /private/sportsedge-original-odds \
  --event-id REAL_PROVIDER_EVENT_ID --markets h2h spreads totals player_pass_yds player_rush_yds
```

**Security:** This uses only the documented GET API URL via authenticated user-owned key, with a strict allowlist of six game sports (NFL/CFB/CBB/NBA/MLB/NHL), sportsbook names and market syntax. Network HTTP errors deliberately never print URLs or API keys. Original provider response JSON is saved with `0600` permissions in a *private folder outside this public repository*, with SHA-256, local UTC receipt time, optional upstream server Date, claimed market-update time, and credit balance. Only synthetic no-key tests run in public CI; no real odds, credentials, or bet records may be put in GitHub/Actions artifacts.

**Coverage honesty:** Main /odds defaults to h2h/spreads/totals; this is not an all-market claim. To capture player props, TD families, period and alternate ladders, use the documented event-scoped endpoint and explicit actual market keys available from that provider. Unreturned market families are recorded as **missing/unverified** rather than claimed not offered. Live or past-kickoff rows are counted as blocked, not transformed to pregame. Source age >300 seconds or lacking a market-update timestamp is quarantined and counted. The runner is a *raw upstream data archive*, not a price/EV decision engine; downstream R4 and RUN IT v2.1 must still enforce both-side integrity, canonical provider-event/player/outcome IDs, odds freshness, role/lineup confirmation, sport/period settlement and all markets.

**Release limitation:** A key proves authentication to an **aggregator**, not to DraftKings and FanDuel independently. The Odds API can report different upstream book names but cannot alone prove two original authenticated sportsbook source chains as required by Issue #10 Gate A. No line is credited as independent +EV or CLV without separate trusted-book/source original receipts. No player/stat forecasts, real distributions, historical odds, WORM timestamps, future CLV or calibration are supplied by this adapter. It always emits PAPER / 0u, never places wagers or certifies release; protected frozen v5 remains unchanged.

## One-command capture + normalization (private runtime)

On a machine you control, after you have legally provisioned the provider API key in the environment, capture a genuine provider event ID at TAKE time and once again within ten minutes before kickoff at CLOSE time. These commands **do not run on ChatGPT's servers, GitHub Actions, or in the background**: you or an authorized local task scheduler must invoke them at the actual clock times.

\`\`\`sh
# Save SPORTSEDGE_ODDS_API_KEY in your private OS environment.
# Never commit, paste, log or pass it as a command-line argument.
python -m sportsedge.odds.prospective_clv_cycle NFL /private/sportsedge-original-odds \
  --event-id ACTUAL_PROVIDER_EVENT_ID --phase TAKE
# At T−5 minutes, while pregame odds are still actually available:
python -m sportsedge.odds.prospective_clv_cycle NFL /private/sportsedge-original-odds \
  --event-id ACTUAL_PROVIDER_EVENT_ID --phase CLOSE
\`\`\`

The utility makes one authorized event-scoped API call per invocation using the documented HTTPS endpoint. It safely writes the private original response and SHA256 manifest, and in the same command creates the private normalized two-sided quote CSV and companion audit report. Output names contain unique capture identifiers and phases, and each file is create-only. Original provider response bytes are never rewritten. Provider credentials are not stored in source code, filenames or manifests. The provider-claimed market update timestamp, local capture timestamp, event and exact line are retained separately.

Once both captures exist, run the existing \`ledger/historical_clv_bridge.py\` with the actual **TAKE phase CSV path** and **CLOSE phase CSV path**; do not guess generated filenames. A TAKE-labeled board snapshot is **not** proof that anybody wagered that selection. The resulting paper CLV compares observed market probabilities; it is not a performance ledger for actual bets.

No account credentials, local executor, cron job, provider schedule or independent DraftKings receipt was created automatically. A missing key, missing real provider event ID, public checkout destination, stale/one-sided odds or post-start market remains BLOCK/PAPER; unmatched markets are visible with rejection counts. This is a convenience command, not a replacement for the separately verified source provenance, finalized lineup evidence, market-specific model calibration, or Issue #10 release gates.

## Private raw captures → provisional price-history comparison

The built-in six-sport source-archival path can now normalize **only** paired, fresh, point-in-time full-game moneylines, spreads and totals from the user-authorized **The Odds API** raw responses into the strict historical CLV CSV contract. This supplies a concrete free-tier **prospective** closing-price workflow; it does NOT provide the provider's past historical odds on the free plan, convert relayed prices into independent DK receipts, or connect BestBook automatically.

After running the existing capture command, note the exact private `aggregator_<SPORT>_*.manifest.json` filename produced locally (not the real odds data). Immediately convert the archived original file:

```sh
python -m sportsedge.odds.the_odds_api_clv_export \
  /private/sportsedge-original-odds/aggregator_NFL_ACTUAL.manifest.json \
  --output /private/sportsedge-original-odds/nfl_take.csv --phase TAKE
# On the next separate, genuine capture before kickoff (ideally T-5m):
python -m sportsedge.odds.the_odds_api_clv_export \
  /private/sportsedge-original-odds/aggregator_NFL_LATER.manifest.json \
  --output /private/sportsedge-original-odds/nfl_close.csv --phase HISTORY
# Point-in-time source-native quote history comparison; PAPER, never official CLV:
python ledger/historical_clv_bridge.py \
  --taken /private/sportsedge-original-odds/nfl_take.csv \
  --history /private/sportsedge-original-odds/nfl_close.csv \
  --output /private/sportsedge-original-odds/nfl_clv_reference.json
```

Each output CSV and adjacent `.audit.json` are **create-only 0600 files** outside the public repo. Raw SHA256 and a claimed provider `last_update` are checked against the private local manifest. Quotes more than 5 minutes old, after kickoff, with missing source timestamps, without true same-book two-sided prices, or with unsupported markets are quarantined with a complete count of blocked market groups. No market is silently filled in, and source event IDs stay **provider-native**; do not join them to a SportsEdge event without an independently documented mapping. `settlement=POSTED_RULES_UNVERIFIED` deliberately prevents pretending the upstream betting rules are verified. The converter does **not** claim that exporting a full odds board means a particular selection was wagered. Actual TAKE decisions need separate verified pregame pick records.

PGA **Majors outrights** are addressed by a separate provider-specific path, not this two-sided game-lines converter. Full-slate player props, alt lines, 1H/quarters, and all other markets are still raw-capture only until canonical player/side/settlement mapping can be proven; don't claim all-markets CLV readiness. No automatic scheduler or user API credentials are installed by this PR.

The provider's documented free tier has **500 credits/month**, current odds only. Its historical odds endpoint is paid; this source cannot retroactively fill pre-kickoff prices that were never saved. Budget polling frequency to the rate and credit allowance shown by the genuine provider response. Never store API keys in code, chat, CI, GitHub or manifests.

**Tests:** `python -m unittest sportsedge.odds.test_free_odds_aggregator_intake sportsedge.odds.test_the_odds_api_clv_export sportsedge.odds.test_prospective_clv_cycle -v` (synthetic only).
