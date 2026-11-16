# NFL point-in-time QB, rest, travel and weather input gate

**RESEARCH ONLY — PAPER / 0u.** This validates *claims about* independent situational inputs. The module **does not download data, authenticate a provider, infer a starter, fit a weather coefficient, alter projected points or price a bet.** Use it with saved original provider exports outside the public repository. A syntactically valid GSIS player ID and SHA256 digest **do not** prove actual QB identity or transport/authorship.

## Sources to connect separately

- Roster and starting QB: actual source snapshot from official team/NFL injury and inactive reporting or another authorized, verified API/export. The GSIS ID must be checked against the original event roster. `EXPECTED` and `UNKNOWN` **remain incomplete**; even `CONFIRMED` is only a caller claim here until independent verification.
- Rest/travel: historical NFL schedule and stadium location/time-zone mapping available **as of freeze**; don't compute rest using future schedule revisions.
- Outdoor/roof weather: documented NWS or Open-Meteo *forecast issued before freeze*, with an interval spanning actual kickoff. Historical weather observations taken after a game **do not count** as its pregame forecast.
- Closed roof suppresses wind/temp/precip adjustments. Unknown roof blocks adjustment; absent outdoor forecast remains absent (not wind=0 or precip=0).

All JSON documents must be stored and independently observed before kickoff. This guard checks the timestamp order `source_observed_utc <= captured_at_utc <= freeze_utc < kickoff_utc` and the provided SHA's syntax, not independent source identity or whether the asserted timestamp is true. CLI records local SHA256 of each supplied input file for later verification.

## Exact payload contracts

The `--event` JSON object contains:

```json
{"event_id":"EVENT_ID","home_id":"HOME","away_id":"AWAY",
 "kickoff_utc":"2026-12-01T21:00:00Z","freeze_utc":"2026-12-01T18:00:00Z"}
```

The `--roster` JSON contains `event_id`, `home_qb_gsis_id`, `away_qb_gsis_id`, `home_qb_status`, `away_qb_status`, `official_inactives_received` (boolean), `receipt`. QB status is exactly `CONFIRMED`, `EXPECTED` or `UNKNOWN`, with actual exact GSIS IDs or `null`.

The `--rest` JSON contains `event_id`, `home_rest_days`, `away_rest_days`, `away_travel_km`, `away_time_zones_crossed`, `receipt`. Missing data is `null`, not a fabricated zero.

The `--weather` JSON contains `event_id`, `roof_state`, `forecast_valid_from_utc`, `forecast_valid_until_utc`, `wind_mph`, `temperature_f`, `precip_probability`, `receipt`. Roof is one of `OPEN_AIR`, `RETRACTABLE_OPEN`, `RETRACTABLE_CLOSED`, `DOME_CLOSED`, `ROOF_UNKNOWN`. Wind is in mph, probability is in [0,1]. If a roof is closed, weather values are suppressed, not converted to zeros.

**Every** roster/rest/weather input includes a `receipt` object:

```json
{"source_id":"AUTHORIZED_SOURCE_ID",
 "source_observed_utc":"2026-12-01T16:30:00Z",
 "captured_at_utc":"2026-12-01T17:00:00Z",
 "original_bytes_sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

All examples are illustrative and NOT verified real-event details. The raw payload digest must correspond to the original provider export, not a retrospectively edited copy.

## Run

```sh
python models/nfl/situational_asof_pit.py \
  --event /private/event.json \
  --roster /private/roster.json \
  --rest /private/rest_and_travel.json \
  --weather /private/weather_forecast.json \
  --out /private/situation_paper.json

python -m unittest discover -s models/nfl -p 'test_situational_asof_pit.py' -v
```

CLI output is create-only, reports claimed completeness, exact input values/identity and source records, but always **PAPER_HOLD_0U** with null score adjustment and null coefficients. A complete-looking file is **not** a verified pregame QB/inactive confirmation.

## Required follow-on work

Authenticate the providers and archive unmodified raw exports with trustworthy source/observation timestamps; bind schedule/roster and weather forecast to the same canonical NFL game ID. Then collect prospective pregame inputs, preregister training folds and fit effects **on earlier games** alongside EPA; compare weather, QB, travel and rest as separate ablations against score and market-only baselines. No universal `wind points per mph`, `+2.5 home`, `0.25 rest`, or generic QB replacement adjustment is treated as a calibrated truth. Before admitting any NFL market, pass the full Issue #10 source/line/inactive/CLV requirements.
