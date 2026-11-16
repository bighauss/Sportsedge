# SportsEdge manual source archive — PAPER / 0u only

This is a **temporary record-preservation workflow**, NOT an authenticated DraftKings / BestBook feed or a way to certify bets. Typed sportsbook prices, screenshots and manually asserted timestamps are not independently verified provider-original quotes. No API credentials, logins, scraped sessions, automatic wagers or official cards are used.

The script sportsedge/odds/manual_paper_archive.py reads one original privately stored CSV without rewriting it, hashes the exact bytes, retains every parseable and malformed logical row in an owner-private report, flags all bad rows, and never emits an official stake. Unlike a sportsbook feed, it cannot demonstrate that *every* offered market was captured, verify provider publication clocks, or prove an independent two-book chain. No part of Gate A–E closes because this script ran.

## Input columns — all must be present exactly once

sport,event_id,game_start_utc,book,source_surface,market_family,provider_market_id,period,selection_id,side,participant_id,stat,line,price_american,observed_at_utc,offer_state,exclusion_reason

- Sports: NFL, CFB, CBB, NBA, MLB, NHL, PGA. Families: ML, SPREAD, TOTAL, TEAM_TOTAL, PLAYER_PROP, PERIOD, ALTERNATE, ATTD, FIRST_TD, TD_2PLUS, FIRST_BASKET, NRFI, YRFI, HR, SOG, SAVES, OUTRIGHT, MATCHUP, FIRST_ROUND_LEADER, ROUND_SCORE, SGP, DFS, OTHER.
- book is the *claimed underlying sportsbook*, e.g. DK; source_surface is where the observer *actually saw* the price, e.g. DK_APP or BESTBOOK_UI. BestBook displaying DK odds is not independent confirmation of a separate original upstream book.
- event_id, selection_id and provider_market_id retain genuine original source values *only when actually known*. Never invent a provider-native ID. A blank provider_market_id is retained but remains unverified.
- game_start_utc and observed_at_utc must end in Z and represent the observer's claimed UTC times, e.g. 2026-11-16T01:20:00Z. The system separately records the local archive creation time. Neither is cryptographic proof of upstream time of publication.
- offer_state is OBSERVED_PRICE, NOT_CAPTURED or REJECTED. A not-captured row needs an exclusion_reason: NO_PRICE, NO_MODEL, NO_PROVENANCE, UNSUPPORTED, STALE, IDENTITY_MISMATCH, OUT_OF_WINDOW, INJURY_UNCONFIRMED or OTHER.
- **NOT_OFFERED is prohibited** in manual records. Only an externally authenticated, complete sportsbook market inventory can establish that. Use NOT_CAPTURED / NO_PRICE when no quote was observed.
- A price record needs its actual American quote (e.g. -110 or +200), the corresponding side and a line for line-based markets. List both sides as separate rows *if each was actually observed*. Do not manufacture the opposing price or infer it from -110 defaults.
- The reporter preserves blocked records, duplicate snapshots, bad quotes, invalid lines, future and postgame observations, and observations more than 300 seconds stale. A header with duplicate or missing fields, or malformed quoted CSV, stops the entire import before any output; the original input remains unchanged.

## Synthetic example, not real odds

    sport,event_id,game_start_utc,book,source_surface,market_family,provider_market_id,period,selection_id,side,participant_id,stat,line,price_american,observed_at_utc,offer_state,exclusion_reason
    NFL,EXAMPLE-001,2026-11-16T01:20:00Z,DK,DK_APP,TOTAL,,FG,TOTAL45OVER,OVER,,,45.5,-110,2026-11-15T22:01:00Z,OBSERVED_PRICE,
    NFL,EXAMPLE-001,2026-11-16T01:20:00Z,DK,DK_APP,TOTAL,,FG,TOTAL45UNDER,UNDER,,,45.5,-110,2026-11-15T22:01:00Z,OBSERVED_PRICE,
    NFL,EXAMPLE-001,2026-11-16T01:20:00Z,DK,DK_APP,PLAYER_PROP,,FG,MISSING_REC_PROP,OVER,EXAMPLE_PLAYER,RECEIVING_YARDS,54.5,,2026-11-15T22:01:00Z,NOT_CAPTURED,NO_PRICE

## Run in a private environment (outside public SportsEdge checkout)

    mkdir -p /private/sportsedge-manual
    chmod 700 /private/sportsedge-manual
    chmod 600 /private/sportsedge-manual/observed_original.csv
    python sportsedge/odds/manual_paper_archive.py /private/sportsedge-manual/observed_original.csv --report /private/sportsedge-manual/manual_capture_001.json
    python sportsedge/odds/test_manual_paper_archive.py -v

A new report must get a **new file name**; output uses O_EXCL, mode 0600, fsync and no symlinks. The source must itself be mode 0600 and remain unchanged in restricted storage alongside the report. The source path or report path inside public Git is refused. The original CSV is **not copied** by this script; the operator must preserve it. Source images, exports and screenshots must be separately retained with their original source/clock metadata. The tool does NOT process image pixels or independently confirm them.

## Interpretation

- PAPER_UNVERIFIED means the row passed local type/time checks, **not** Gate A source authentication or positive-EV validation. All rows have approved_stake_u=0.
- BLOCKED retains the row and the reason; duplicate manual rows are quarantined together. No quote ever becomes an official bet.
- The SHA-256 only binds the local CSV bytes to the receipt. It does not prove a sportsbook offered the price or that a user-entered timestamp was truthful.
- This tool is intentionally not connected to the live card/odds path. It does not calculate ROI, EV or CLV.

**Next required step:** obtain explicitly authorized and documented original DraftKings offer capture and a distinct, independently verified original-book source. Preserve untouched provider response bytes, IDs, times and complete market inventory. Then finish the separate A–E calibration, CLV and safety requirements, market by market. Free-tier Odds API cannot provide full all-sport, all-market production capture.

Reference: [Gate A–E blocking issue](https://github.com/bighauss/Sportsedge/issues/10).