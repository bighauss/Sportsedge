# Seven-sport authorized offline export census — Gate A preparation

**PAPER / 0u only. Not a DraftKings API, DataGolf API, BestBook API, online scraper, independent book authentication or licensed provider transport.** No network calls occur. The module accepts only already lawfully obtained files supplied by an operator with source permission, and claims about permission remain unverified until independently documented.

`sportsedge/odds/seven_sport_authorized_export.py` supports a structured **offline research intake** for NFL, CFB, CBB, NBA, MLB, NHL, PGA. It preserves hashes of BOTH original provider response bytes and separately converted canonical quote rows. No original payload or converted quote price is printed to console or sent to public GitHub. Both files and the request/report must live outside the public checkout with private `0600` file modes and `0700` directories.

The code **does not** transform an undocumented proprietary provider payload into canonical quotes. That transformation needs a legitimately documented, separately reviewed, version-pinned source-specific adapter. Passing a version string or source name is not authentication.

## Contract
A private **request** JSON has exact fields:

- `schema`: `sportsedge-seven-sport-offline-export-request-v1`
- `sport`: one of the seven listed sports
- `provider`, `upstream_book`, `upstream_provider`, `collection_path_id`, `source_mapping_version`, `permission_reference_claim`: nonempty claimed source labels, not attestation
- `source_observed_utc`, `source_captured_utc`: claimed UTC source time, observed <= captured and captured <= current local UTC
- `original_provider_file` and `converted_quote_file`: each `{"path":"/private/path","sha256":"sha256:<64 lowercase hex>"}`, verified against original bytes
- `events`: one or more `{"event_id":"...", "start_utc":"...", "market_inventory":[...]}` entries, with distinct event IDs and source capture before event start

Every event inventory MUST declare each of **13** generic families exactly once: `ML, SPREAD, TOTAL, TEAM_TOTAL, PLAYER_PROP, PERIOD, SPECIAL, ALTERNATE, SGP, OUTRIGHT, MATCHUP, DFS, OTHER`. Each has `market_family` and `status` from `CAPTURED, NOT_CAPTURED, OFFER_UNKNOWN, UNSUPPORTED`. `NOT_OFFERED` is deliberately unsupported: claiming the actual sportsbook had no market requires externally authenticated complete provider inventory. Family-level coverage cannot replace a complete provider offered-market census for Gate A.

The converted JSON has exact root `{"schema":"sportsedge-seven-sport-converted-quotes-v1","quotes":[...]}`. Every quote has:
`event_id,market_family,period,selection,selection_id,participant_id,stat,line,price_american,provider_quote_id,provider_market_id,observed_utc`.

Only `CAPTURED` families may contain converted quotes; each declared captured family must contain at least one quote. All converted rows must be pregame and no later than the claimed source capture. Missing events, duplicate canonical outcomes, recycled provider quote IDs, invalid American odds, missing prop IDs/stats, nonexistent source files and hash mismatch cause a hard failure. Distinct alternate lines and periods remain distinct market keys. These are only local schema and hash checks — mapping from a quote to its *actual original* provider row remains unverified.

Run:

```sh
python -m sportsedge.odds.seven_sport_authorized_export /private/capture_request.json --out /private/new_capture_report.json
python -m unittest sportsedge.odds.test_seven_sport_authorized_export -v
```

Result is a create-only fsynced `0600` report with hashes, explicit unverified source mapping, per-family status counts and zero approved units. No sportsbook odds are invented or queried. An offline converted row can never satisfy independent original-source authentication just because it has a provider name, a SHA or a timestamp.

**Gate A remains OPEN:** actual authorized primary DK plus independent second-book original transport, trusted clocks, provider-to-market mapping, real all-event inventory and 100 genuine source-clean cards must still be independently verified. This tool permits preservation and auditing of any lawful original export if provided.
