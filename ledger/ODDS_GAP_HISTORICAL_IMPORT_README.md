# The Odds Gap historical CSV to SportsEdge CLV reference (offline only)

Source: https://theoddsgap.com/data

The vendor documents a no-key, no-signup fixed sample week (October 19–25, 2026) from its published /api/odds-export.csv endpoint. The recent and complete historical records are paid access. This module performs NO website request, payment, credentials, private scraping, or copying of any original source into public GitHub. The site restricts bulk automated reuse and repackaging. Research usage must respect the vendor's terms and attribution requirement.

**This is a price-history adapter, not a historical bet extractor.** A file downloaded later does not establish that SportsEdge actually saved a selection at the earlier vendor quote time. History cannot be retroactively labeled TAKE. The importer always emits HISTORY data, and all outputs remain PAPER / 0u.

## Original source manifest (private)

After obtaining a permitted CSV manually, save it in a private folder outside the public repo. Compute the SHA256 of the original CSV bytes and create this adjacent JSON manifest using actual values (the example placeholders are deliberately NOT valid):

    {
      "schema": "sportsedge-oddsgap-history-import-v1",
      "source_path": "odds_gap_original.csv",
      "source_sha256": "<actual SHA256 of original bytes>",
      "downloaded_at_utc": "<actual UTC save time>",
      "source_url": "https://theoddsgap.com/api/odds-export.csv?sport=americanfootball_nfl",
      "x_data_sample": "1"
    }

Do not invent file hashes or source timestamps. The optional x_data_sample is operator-entered, NOT evidence of an authenticated response header. This parser never connects to the provider; it uses only the locally authorized file and manifest.

Run:

    python -m ledger.oddsgap_historical_import \
      /private/sportsedge/oddsgap_sample.manifest.json \
      --output /private/sportsedge/oddsgap_two_sided_history.csv

The output CSV plus adjacent .csv.audit.json are create-only and private; the original raw file remains unchanged. The archive's exact bytes are SHA-verified. Every malformed, missing-side, duplicate, three-way, exchange, unsupported or post-start row/group is counted as a quarantine reason. The script never invents the opposite price or rewrites missing markets.

## Scope

Only vendor-documented long CSV game lines are admitted: NFL, CFB, CBB, NBA, MLB, NHL; moneyline, spread, total; actual two-sided sportsbook prices at the SAME bookmaker, market, alternate threshold and scan timestamp. Source columns: snapshot_ts, sport, away, home, commence_time, market, side, line, book, american_odds and game_id. The full-game-only market mapping is explicit. The provider's game_id is preserved as source-native, not guessed to be an ESPN or SportsEdge event ID. Player props, touchdown markets, 1H/quarters, correlated parlays, soccer three-way moneylines and prediction-market exchange prices are NOT silently converted.

The importer records the vendor-reported snapshot timestamp and separately records the **real date you downloaded the CSV**. It never backdates the local capture to the vendor's earlier snapshot time. It deliberately uses POSTED_RULES_UNVERIFIED settlement. It cannot certify bookmaker source receipts, completeness, execution, lineup or settlement rules.

## Optional retrospective comparison

If SportsEdge has a genuine pregame TAKE already saved under the exact canonical event mapping, you can use the existing research comparison:

    python ledger/historical_clv_bridge.py \
      --taken /private/sportsedge/original_taken.csv \
      --history /private/sportsedge/oddsgap_two_sided_history.csv \
      --output /private/sportsedge/oddsgap_reference_results.json

A DIRECT_BOOK TAKE and ODDS_GAP reference have different providers, so the output is reference_delta_probability_points, not clv_probability_points. If native event IDs do not match, NO_EXACT_MATCHED_CLOSE is correct until independently verified crosswalk evidence exists. Do not join on team names or replace the original pregame TAKE with a vendor historical scan.

No authenticated CLV, profitable EV, actual user wager, official counted selection, unit or bankroll decision can be created by this import.

## Tests and caveats

    python -m unittest ledger.test_oddsgap_historical_import -v
    python -m unittest discover -s ledger -p 'test_historical_clv_bridge.py' -v

The tests are entirely synthetic, based on the vendor's publicly documented schema. A live free-sample fetch could not be completed in the current runtime, so a real source-file acceptance check is still outstanding. Never describe synthetic passing tests as provider integration proof.

Source data descriptions and permissions: https://theoddsgap.com/data ; https://theoddsgap.com/api-docs
