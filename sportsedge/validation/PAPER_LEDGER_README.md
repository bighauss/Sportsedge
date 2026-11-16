# Private PAPER result + close-price grading ledger

Research-only grading infrastructure. Works with the canonical
sportsedge.markets.allmarkets_research.Market and Outcome contracts for NFL,
CFB, CBB, NBA and MLB **when all raw, actual event periods and players are
present**. NHL is not currently admitted by the five-sport market kernel;
do not relabel NHL as graded in this pipeline.

No hidden odds source. No scraped private data. No invented final scores.
No official counted bets or estimated payout/ROI, no signed release
promotion and no automatic wagering. The original quotes, raw final
payloads, private receipts, and SQLite database must remain in restricted
private storage and MUST NOT be uploaded to the public SportsEdge GitHub.

## Bundle

A private bundle.json has pick_id, event_id, kickoff_utc, taken, optional
close, and final. Every source record contains path, sha256 and
captured_at_utc; source bytes must be JSON at that relative file path,
and local SHA256 must match. Quotes must be obtained before kickoff and
be in time order; finals captured after kickoff must self-report FINAL.
Provider-specific authentication and actual observer clocks remain
**independently unverified**: these metadata assertions alone do not
establish real provider authentication or tamperproof storage.

The taken and closing original JSON quote files contain:
- book exactly DraftKings; quote_id; provider_event_id; provider_market_id
- a canonical Market object (sport, event_id, kind, period, selection,
  line when required, player_id or team_id when required, stat when
  required, explicit settlement includes OT/regulation/posted rules)
- an exact opposite Market object, with the same event/period/player/line
  and complementary side
- price_american and opposite_price_american, actual numeric signed
  American odds as 2-sided contemporaneous offers

The closing quote must be a later *distinct* quote from the same book,
provider event/market and exact Market.identity() as the taken offer.
Different alt line, period or player = reject; no rough market-odds delta.
Taken and closing no-vig selection probabilities are computed from
independently supplied quote pairs. CLV_pp means
100 * (no-vig closing implied selection probability minus at-take no-vig
selection probability); positive means the close implied a higher
probability for your original selection. Missing close remains NULL,
not manufactured or imputed.

The original final JSON contains:
- event_id, sport, final_status FINAL, home_id, away_id
- periods e.g. Q1..Q4 and OT as appropriate; for CBB/NBA regulation tie,
  required overtime must be represented, not inferred
- roster_ids, player_stats, optional player_period_stats
- chronologically ordered scoring events and events_complete when
  first TD or first basket is graded

The ledger reuses the same allmarkets_research.settle market contract
so spread signs, push-aware totals, halves, quarters, player stat periods,
TD counts and first-basket/NRFI settlement are handled by the existing
explicit source contract instead of reimplementing a conflicting grader.
Absent model fields or incomplete actual game events BLOCK.

## One-command execution

    python -m sportsedge.validation.paper_ledger \
      /private/bundle.json --database /private/research_ledger.sqlite3

SQLite BEGIN IMMEDIATE transaction and unique pick_id prevent accidental
duplicate grades and conflicting revisions across concurrent agents. A
local SHA256 chain over canonical records can detect accidental local row
alteration, but is **not** WORM or independent signed attestation. Keep
an external immutable raw source archive when moving toward Issue #10 gates.

Fields include grade W/L/P, exact selection identity, source bytes hashes,
sample receipt IDs, actual two-sided no-vig CLV probability-point movement
(or NO_COMPARABLE_CLOSE), and hard-coded approved_stake_u=0,
official_counted=0, source_authentication_independent=false, ROI unavailable.
No automatic contest entry or stake placement.

Test:

    python -m unittest sportsedge.validation.test_paper_ledger

The tests use synthetic quotes/finals; passing CI does not certify
profitable betting, 50+ real graded selections, or trusted closing lines.

## Promotion requirements

1. Freeze *real* pregame offers from DK and an independently authenticated
   second original source, with original provider observation receipts,
   authorized capture method, identity and timestamps.
2. Obtain authentic original final box scores, player events and
   source/publication times after settlement; reconcile corrections.
3. Verify actual opening/taken/closing matched market line and
   same-settlement-rule identity. Missing or disputed close stays missing.
4. Register model/forecast, independent point-in-time team/roster
   evidence, and honest chronological backtest/cross-market calibration.
5. Fulfill issue #10 Gate A–E (100 real clean cards, at least 200 authentic
   matched settled selections/close triples and independent signed
   promotion record) before calling any selection OFFICIAL/real stake.
