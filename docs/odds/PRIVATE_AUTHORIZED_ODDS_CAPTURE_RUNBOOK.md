# SportsEdge authorized Odds API private capture — phone-safe wiring

**2026-11-16** | Research-only | A–E gates OPEN | All stakes 0u

The existing GitHub Secrets–backed workflows `provider-auth-smoke.yml` and
`provider-observation.yml` ran successfully on November 16, 2026. In the
sanitized observer log, CFBD, The Odds API and API-Sports each responded with
parseable JSON. This establishes only working access to the tested **provider
endpoints**. It does NOT authenticate a DraftKings original bookmaker offer,
a second independent original sportsbook chain, all market rights, historic
availability, or point-in-time quote publication.

## Credential name mismatch repaired

The GitHub smoke workflows name the existing secret **`ODDS_API_KEY`**.
Previously the permissioned private capture CLI only accepted
`SPORTSEDGE_ODDS_API_KEY`. It now accepts either name when invoked WITHOUT
an explicit `key` argument. Precedence:

1. Explicit `key` parameter (including empty = error; never silently spend
   another account's credits).
2. `SPORTSEDGE_ODDS_API_KEY` for existing private runners.
3. `ODDS_API_KEY` for environments already wired like the GitHub Actions
   provider smoke test.

**No credential is printed or added to the public repository.** The change
does not run a live API request when code is imported, tested, or deployed;
the operator must explicitly invoke the CLI. All CI requests use a synthetic
in-memory response opener, so tests consume no API credits.

## Private manual execution after provider permission is confirmed

Use an isolated private computer/runner with the appropriate secret available
as an environment variable. Never choose a directory under the public
SportsEdge checkout or a directory linked into it.

```sh
python -m sportsedge.odds.free_odds_aggregator_intake \
  NFL /private/sportsedge-original-odds \
  --markets h2h spreads totals \
  --bookmakers draftkings fanduel
```

This is an **explicit potentially credit-consuming** provider request and
must not be scheduled without a quota and rights check. The default requested
market set is h2h/spreads/totals; it is **not all markets**. For higher cost
event-level player/period/alternate markets, use only documented endpoints and
the user's authorized entitlement, with an independently audited source
mapping and exclusion census. PGA outrights are not processed by this
game-lines adapter.

The authorized capture code:
- Uses documented The Odds API v4 endpoints and current valid TLS;
  rejects redirected credential-bearing requests, stale/missing quoted
  market times and after-start status.
- Saves the original provider response bytes and its SHA-256 manifest to a
  **private 0600 create-only directory**, outside public GitHub.
- Records the original event, bookmaker, market and outcome universe,
  requests-used/remaining headers if supplied, provider/server clock claims,
  capture UTC and the reason any market is unavailable or research-only.
- Preserves DraftKings and FanDuel as **The Odds API aggregator observations**;
  they cannot count as two independently authenticated bookmaker chains
  solely because two labels occur in one API response.

The private capture can be normalized to the existing CLV research bridge,
without treating a historical board as a bet actually taken:

```sh
python -m sportsedge.odds.the_odds_api_clv_export \
  /private/sportsedge-original-odds/<original-manifest>.manifest.json \
  --output /private/sportsedge-processed/research_observations.csv \
  --phase HISTORY
```

This is not an authenticated closing-line triple; the original offered and
excluded market census and external publisher chain still need independent
verification. Do not use `--phase TAKE` to imply a wager from merely
observing a line. Never upload private receipts, provider credentials or
licensed raw data to this public repository or a public GitHub artifact.

## What remains to reach Gate A

- Authenticate the exact upstream DraftKings offer origin and an independently
  originated second bookmaker provider (The Odds API can be a *comparator*).
- Independently preserve and verify the **entire original offered universe**,
  not just returned markets and a caller-supplied count.
- Capture opening, decision-time and true pre-event closing prices for the
  **identical** event, line, side, period, participant, rule and book; preserve
  all failed/withheld rows and provider observation time.
- Verify permitted data retention and quota limits; The Odds API historical
  snapshots are offered on paid usage plans according to official docs, so
  do not presume historical access on the existing account.
- Join exact original evidence to independent frozen feature inputs,
  preregistered forward validation, compliant risk policy and settlement
  only after every A–E gate has external evidence.

References: The Odds API official v4 documentation
https://the-odds-api.com/liveapi/guides/v4/
and its historical access details
https://the-odds-api.com/historical-odds-data/.
