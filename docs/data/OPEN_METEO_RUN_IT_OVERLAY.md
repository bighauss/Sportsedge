# RUN IT — read-only Open-Meteo original weather research overlay

This is a real optional integration to the existing canonical seven-sport slate research runner. **It does not enter model weights or bookmaker quote pricing, auto-place bets, close Issue #10 A–E or certify that any weather forecast was issued before a historical event.** Project owner-approved engineering; provider free tier noncommercial-only.

## Source capture first

Use the official one-shot Open-Meteo no-key capture described in OPEN_METEO_RUN_IT_SOURCE.md. Real operator-created outputs are a restricted original request JSON, original provider forecast response JSON, and a normalized local receipt JSON. Each is 0600, in a 0700 directory outside public Git. Preserve raw bytes exactly. The original source file basename is bound to the receipt. No account, cookies or API key for the provider's free noncommercial service. CC BY 4.0 attribution: Weather data by Open-Meteo.com.

Run a forward source capture for an exact sport/event/venue *before start*, with verified venue coordinates and roof status. The source adapter supports NFL/CFB/MLB/PGA and refuses non-genuine commercial use of the free API. Avoid guessing the home stadium; neutral sites, relocation, retractable roofs and weather-related changes can invalidate a map.

## Run RUN IT with the original weather triplet

    python -m sportsedge.markets.slate_orchestrator \
      /private/sportsedge/slate_input.json \
      /private/sportsedge/slate_result.json \
      --weather-triplet \
      /private/sportsedge/forecast_request.json \
      /private/sportsedge/SYNTH_EVENT_TIMESTAMP.openmeteo.original.json \
      /private/sportsedge/SYNTH_EVENT_TIMESTAMP.openmeteo.report.json

The names shown are illustrative; use **exact actual files output by the source capture**. Repeat --weather-triplet for each additional game. The normal two-positional-argument CLI still works without weather. BestBook public-page comparison flags and weather flags can coexist, with no cross-source trust. This does not itself fetch a new weather forecast; use the explicit capture source step first. Do not run stale original files and pretend they are new forecast releases.

### Mechanism and exact invariants

The importer reads all **three original private files** and parses exact UTF-8 JSON with duplicate keys, NaN/Infinity and oversized/non-private/symlinked files blocked. It replays the original provider response against the original request at the **claimed local original capture clock**. The result is compared field-by-field (including numerical types) against the archived receipt. Original request SHA256, original response SHA256 and exact original filename must match, otherwise the entire import is refused.

Then it binds exact **existing SportsEdge sport, event ID and scheduled UTC start**. Unscheduled original source games, duplicate event receipts, requested kickoff mismatch, a capture after the RUN IT decision, and any cross-event replay refuse the batch. No mapping from ambiguous team names or sport player IDs is invented. This original-request replay is a local cryptographic consistency check, **not external upstream source attestation**: an altered/re-created set of three files can be internally self-consistent yet not independently establish a provider publication time.

For each scheduled event, result.events[].open_meteo_weather_reference includes:
- Not captured for eligible NFL/CFB/MLB/PGA games; not requested for other sports, including schedule-only NHL.
- BLOCK weather live/after event and stale when an archived local capture is older than six hours at decision time.
- RESEARCH weather exposure unconfirmed if stadium roof is CLOSED, UNKNOWN or retractable/unconfirmed.
- PAPER outdoor forecast research reference when the local evidence claims a fresh outdoor snapshot with exact schedule identity, without claiming roof/venue are externally authenticated.

The event-hour temperature, wind speed/gusts, precipitation probability and cloud cover, model grid/requested venue coordinates and attribution appear for display only. The source's model issuance clock is **NULL and unverified** because /v1/forecast is a continuously blended forecast. Any measured postgame weather or later-issued model forecast cannot be used to reconstruct a historical prediction. No original sportsbook odds are obtained here.

### Market safety

The weather overlay is attached **after** canonical score simulation, all-markets candidate census, pricing, v2.1/v2.2 risk guard and the previously merged BestBook research overlay. Missing/unmodeled props and specialty markets remain visible under their original statuses; model probabilities and EV are not recomputed. All 7 scheduled sports stay in the original result with 0 approved units and zero official bets.

The provider permits the free/no-key service only under noncommercial terms and 10k/day and lesser hourly/minute limits. If SportsEdge is monetized or an external commercial service, do not use this free endpoint; obtain a commercial provider license first. Operator approval of the work is not permission on behalf of the provider. See https://open-meteo.com/en/terms and https://open-meteo.com/en/docs.

### Synthetic tests

    python -m unittest sportsedge.data.test_open_meteo_pit -v
    python -m unittest sportsedge.markets.test_weather_slate_overlay -v
    python -m unittest sportsedge.markets.test_slate_orchestrator -v
    python -m unittest sportsedge.markets.test_bestbook_slate_overlay -v

These tests use synthetic requests/provider data. A real private operator source capture and genuine pregame venue/roof mapping are still necessary to use the optional RUN IT weather reference for real games. No statistical improvement or official bettor eligibility is claimed by passing CI.
