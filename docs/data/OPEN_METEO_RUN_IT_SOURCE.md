# SportsEdge Open-Meteo noncommercial weather forecast capture

## Source and license (verified November 15, 2026)

Official documented public API: https://open-meteo.com/en/docs and https://api.open-meteo.com/v1/forecast . Open-Meteo offers a free no-signup/ no-key API for **noncommercial** use only, fewer than 10,000 calls/day, fewer than 5,000/hour and fewer than 600/minute, subject to provider policies. Requires CC BY 4.0 attribution, e.g., "Weather data by Open-Meteo.com". Terms: https://open-meteo.com/en/terms . **Commercial betting services, subscriptions, advertising or promotional products are not covered by the free license.** Use the free endpoint only for genuinely personal, noncommercial research; otherwise obtain Open-Meteo commercial access first. User permission to work on SportsEdge does not grant a third-party commercial license.

This is a **real supported no-key URL with an isolated source adapter**, not a list of websites. The source's contents have **not yet been validated with a real private SportsEdge capture**. There is no auto-polling or website account login. It supplies external environmental research inputs only: NFL/CFB/MLB/PGA outdoor wind, temperature, precipitation probability and cloud cover. No indoor sport weather adjustment, no new TD/prop projections, no sportsbook price, no official model weight change.

## One-shot capture with original provider response (private only)

Create an operator-private 0700 directory and an owner-only 0600 request JSON, outside the Git checkout. Supply the actual canonical SportsEdge event ID, independently mapped venue identifier and venue coordinates; DO NOT assume names/latitudes or auto-select a stadium from a generic city. Only the following exact request fields are permitted:

    {
      "schema": "sportsedge-open-meteo-pregame-request-v1",
      "sport": "NFL",
      "event_id": "EXAMPLE_EVENT_ID",
      "event_start_utc": "2026-11-16T19:20:00Z",
      "venue_id": "EXAMPLE_STADIUM_ID",
      "latitude": 41.13,
      "longitude": -87.54,
      "coordinate_source": "OPERATOR_SUPPLIED",
      "roof_status": "OPEN",
      "purpose": "PERSONAL_NONCOMMERCIAL_RESEARCH"
    }

The **values above are synthetic illustrative values, not an identified real event or stadium**. Actual kickoff, location and roof must be independently confirmed at capture. The coordinate_source field is the operator's provenance claim only.

    mkdir -p /private/sportsedge-weather
    chmod 700 /private/sportsedge-weather
    chmod 600 /private/sportsedge-weather/weather_request.json
    python -m sportsedge.data.open_meteo_pit \
      /private/sportsedge-weather/weather_request.json \
      --private-destination /private/sportsedge-weather \
      --noncommercial-terms-reviewed

Use the explicit noncommercial-terms-reviewed flag only after an actual policy review and when the application is strictly noncommercial. The one-off CLI makes a single no-redirect HTTPS GET to the official fixed no-key endpoint with strictly allowlisted weather parameters and up to 16-day future weather, GMT timestamps, imperial temperature/wind. It does not send tokens, site logins or cookies. It is not a scheduler. True capture time is read from the authorized executor clock; no user-edited historical capture timestamp flag is exposed in production CLI. Tests inject a simulated clock and HTTP response only.

The source's untouched JSON bytes are privately archived as a create-only 0600 file. A second create-only 0600 report stores original SHA-256, actual capture UTC, exact event ID, manually asserted venue coordinates, source grid coordinates, roof/field status, and event-hour forecast. Invalid JSON or incomplete arrays preserve the original private raw file for review but do not produce a plausible valid normalized report. Duplicate JSON keys, NaN/Infinity constants, UTC timezone misalignment, future horizon issues, mismatched grid, missing/hourly-unit mismatches, negative wind or post-kickoff collection all block report issuance. Original file is never rewritten.

This accepts only real present/future original snapshots, **never a retrospective reconstructed as-of weather forecast**. The latest Open-Meteo /v1/forecast output blends different weather models (and published forecasts) and does **not provide one independently verifiable original model run publication/issue timestamp in this response**. The report therefore explicitly declares provider_model_run_issuance_verified=false and provider_forecast_issue_time_utc=null. Local original capture proves only what the operator's environment stored; it does not certify a model forecast was actually issued at an earlier historical time. Open-Meteo also offers historical single model runs separately, but those are a distinct product with separate access/permissions and require their own prior knowledge check.

The report never feeds a weather value into an actual risk/card/pricing module automatically. It is a READY-TO-CONNECT **source** with a deterministic original-byte archive and synthetic tests. The downstream model feature gate requires documented exact event/venue binding, authoritative lineup/roof/weather as-of clock, forward-calibrated weather effect and independent frozen feature receipts; all lacking those should be listed as WEATHER_RESEARCH_ONLY. Same venue with closed/retractable roof is not an outdoor exposure until verified.

## Verification and review

    python -m unittest sportsedge.data.test_open_meteo_pit -v

Tests are synthetic only and do not hit the live API or consume provider quota. Source integration may not be used to claim A–E issue #10 complete, bookmaker odds authenticity, original CLV, or profitable selections. Every report is PAPER/0u, official_counted=0. Frozen SportsEdge v5, original odds/grades, risk, and all-market RUN IT model outputs are unchanged. Next independent work item is to connect this source receipt to the seven-sport private feature frozen-as-of registry with real event IDs and source agreement, then evaluate prospective improvements before adjusting any model weight.
