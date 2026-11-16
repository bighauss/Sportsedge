# SportsEdge Gate A — permissioned DK + second-book completeness runbook

**Production source state as inspected Nov 15:** NOT LIVE / NOT AUTHENTICATED in this session. Existing `sportsedge/odds/adapters.py` accepts a normalized, authorized **offline export** and hashes original bytes; there is no verified live official DraftKings developer feed or separately authenticated second bookmaker account. BestBook public pages are not proof of a developer API. No cookies, unofficial endpoints or HTML scraping should be used.

**No free-tier Odds API or any aggregator as a production/grade source.** The historic free-tier adapter remains research-only; do not enable it in approved selection or scoring workflows.

## Private authorized collection contract

A permitted book adapter must retain privately (mode 0700 directory, 0600 raw file; never public Git or runner artifact):
- Source-provided original bytes + full SHA-256, provider/source book identity and independent transport path.
- Original provider observation/last-update timestamp UTC (never replaced by the time *we* retrieved it).
- Our actual local retrieval/capture UTC and optional independent timestamp attestation.
- Real provider event, market and outcome IDs; sport, event/tee time UTC, market family/period, team/player/stat identity and settlement period.
- Every offered outcome/alternate rung and original side/line/price. Missing or blocked outcomes must have exact event/market/outcome keys, an explicit reason and the time it was discovered.
- Original response/provider evidence, rate limit, licensing permission and upstream market mapping, not simply an aggregator's displayed sportsbook name.

To audit local **completeness only**, run:

```bash
mkdir -m 700 -p /private/sportsedge/odds/reports
chmod 600 /private/sportsedge/odds/YYYY-MM-DD.raw_catalog.json
python -m sportsedge.odds.completeness_gate \
  --archive /private/sportsedge/odds/YYYY-MM-DD.raw_catalog.json \
  --report /private/sportsedge/odds/reports/YYYY-MM-DD.completeness.json
python -m unittest sportsedge.odds.test_completeness_gate -v
```

The archive must be JSON object `schema="sportsedge-odds-completeness-v1"` with `events` array. Each event contains: `event_id`, `sport` (NFL/CFB/CBB/NBA/MLB/NHL/PGA), `kickoff_utc`, `market_inventory`, `quotes`, `exclusions`. Every offered inventory item has `book,provider_market_id,family,period,side,line`; store one item per offered **outcome/rung**, not one line per generic family. **Do not create fake inventory rows:** when a core DK outcome cannot be inventoried, the report refuses completeness. Each matching quote adds `price_american` (integer), `original_observed_utc`, `captured_utc`, and `source_receipt_sha256` if it exists. A matching exclusion instead provides a `reason` from the allowed reason catalog and a genuine `noted_at_utc`. Use exactly `ML`, `SPREAD`, `TOTAL`, `FG` and `HOME/AWAY` or `OVER/UNDER` for core inventory.

Supported reasons: `NOT_OFFERED`, `NOT_CAPTURED`, `NO_AUTHORIZED_ACCESS`, `NO_PRICE`, `UNSUPPORTED`, `STALE`, `AFTER_START`, `IDENTITY_UNMATCHED`, `PROVIDER_ERROR`. Mark `NOT_OFFERED` only after authenticated source inventory actually confirms that fact. Local source-provided timestamps remain claims pending external attestation.

### Hard fail rules

1. Missing any offered outcome without a quote or timed exclusion = fail. Missing either core DK moneyline, spread or total **side** from its market inventory without an explicit catalog/exclusion reason = fail. An exclusion is transparency, not proof a market was offered or independently sourced.
2. Duplicate keys, unsupported sports, malformed American prices, missing source/capture clock, observed after captured or quotes captured after start = fail.
3. Private original archive is read-only, private report create-only, mode-0600 and fsynced with no overwrite; an audit report never edits originals.
4. A locally complete file returns `PAPER_0U_COMPLIANT_INVENTORY`, **not** `GATE_A_CLEARED`; `gate_a_authenticated=false` and official stake/count remain zero.

### Exact outstanding authorization

Owner/operator must establish a **documented, authorized** DK export/API path and a separately collected second-book path with permitted retention. Do not put passwords/tokens in chat, Git, issues or generated reports. Add real provider adapters **only** after capturing permitted sample original responses in private storage and verifying actual schemas and upstream source rights.

No non-synthetic source retrieval, credentials, sportsbook prices, private decision ledger or true 2026 historical snapshot is introduced by this PR.
