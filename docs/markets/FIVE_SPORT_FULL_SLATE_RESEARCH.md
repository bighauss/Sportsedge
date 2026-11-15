# SportsEdge five-sport full-slate RUN IT research — v1

**Purpose:** Reconcile every scheduled NFL, CFB, CBB, NBA and MLB game
against the events actually submitted to the existing five-sport research
engine. Never silently omit a game or claim a market has no value because its
price or independent projection was not captured.

**This is NOT a real-money release, live DraftKings integration, independently
authenticated schedule, verified profitable model, or official betting card.**
Every execution returns `approved_stake_u=0`, `official_counted=0`,
`card=null`, and `BLOCK_OFFICIAL_RELEASE_RESEARCH_ONLY`.

## Command

Run from repository root with a PRIVATE input and PRIVATE output path:

```bash
python -m sportsedge.markets.slate_orchestrator \
  /private/sportsedge_2026-11-16.json \
  /private/REPORT_sportsedge_2026-11-16.json
python -m unittest sportsedge.markets.test_slate_orchestrator -v
```

Output is exclusive-create; an existing report is never replaced. Source
files, bookmaker exports and local player records belong in private storage,
not GitHub. The runner does not scrape, log in or send orders to an operator.

### Input schema

```json
{
  "schema": "sportsedge-five-sport-slate-research-v1",
  "slate_id": "SLATE-EXAMPLE-20261116",
  "slate_date_ct": "2026-11-16",
  "sports": ["NFL", "CFB", "CBB", "NBA", "MLB"],
  "expected_events": [
    {"sport": "NFL", "event_id": "EXAMPLE-NFL-1", "start_utc": "2026-11-16T20:00:00Z"}
  ],
  "event_inputs": [
    {
      "sport": "NFL", "event_id": "EXAMPLE-NFL-1",
      "manifest": {
        "projection": {
          "sport": "NFL", "event_id": "EXAMPLE-NFL-1",
          "home_id": "SAMPLE_HOME", "away_id": "SAMPLE_AWAY",
          "expected_home": 24, "expected_away": 21,
          "model_sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "feature_sha256": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "asof_utc": "2026-11-15T19:00:00Z"
        },
        "distribution": {
          "sport": "NFL", "sd_margin": 12, "sd_total": 17,
          "period_shares": [0.24, 0.26, 0.24, 0.26],
          "model_sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "training_end_utc": "2026-11-14T00:00:00Z",
          "status": "UNCALIBRATED_RESEARCH"
        },
        "markets": [],
        "simulation_count": 1100, "simulation_seed": 20261116
      }
    }
  ]
}
```

**The sample above is entirely fictional.** All source dates/teams/models and
volatility parameters are placeholder demonstrations and MUST NEVER count as
live captures, independent source evidence or forward calibration. For a
real model function invocation, use the existing `projection_ref` plus its
required frozen source-file PIT manifest, rather than a manually entered
uncalibrated mean. Real odds need original raw bytes and exact DK quote
identities, not guessed lines. Missing such inputs → BLOCK / 0u.

## Behavior and market inventory

- Uses an externally supplied **expected schedule registry**, including
  exact sport/event ID and UTC kickoff. Verifies every kickoff's Central date.
  The registry itself still requires independent source authentication.
- Rejects duplicate schedule IDs, unknown extra games, mismatched projection/
  market/quote identities, wrong source event-start times and reused provider
  quote IDs across any events in the input. Refuses model features dated after
  kickoff. All submitted candidates run through the existing per-event v2.1
  research risk gate.
- A scheduled event absent from inputs receives
  `SCHEDULE_EVENT_CAPTURE_MISSING` rather than disappearing. Events that
  have started are blocked as `SCHEDULE_EVENT_STARTED`.
- For every game, shows the research submission counts for **ML, spread,
  totals, team totals, player props**, plus football TD types, basketball
  first basket, baseball NRFI/YRFI and SGP. Missing families are labeled
  `NOT_SUBMITTED_OR_NOT_OFFERED_UNVERIFIED` — this is NOT a claim the
  bookmaker offered that market or no true +EV opportunity exists. SGP
  research has a separate joint-scenario pricer, but SGP output is NOT
  silently manufactured by the single-leg CLI.
- An event with **zero** submitted markets is `BLOCK:
  NO_MARKETS_SUBMITTED_OR_OFFERED_UNVERIFIED`, counted in
  `counts.no_market_rows`, and is **not** called a successfully processed
  research game. It is never counted as no value or no available offers.
- The straight-leg CLI does not price SGPs. A separate explicit **SGP
  inventory-only placeholder** can be submitted as
  `{"market":{"sport":"NFL","event_id":"EXAMPLE","kind":"SGP","period":"FG"}}`.
  This emits an individual visible BLOCK with reason
  `SGP_REQUIRES_POSTED_JOINT_QUOTE_AND_CALIBRATED_EVENTS`, retains its
  position in the input and keeps unrelated straight legs evaluable. Any
  fake single-leg SGP quote or caller assertion that its v2.1 gate passed
  is refused for the entire intake. An SGP-only game is BLOCK, not
  processed/priceable, and the SGP row is counted as blocked.
- Only the correctly typed straight-leg candidates actually run the
  existing `v2.1` research guard. An unpriced SGP placeholder is **not
  promoted** into that gate; its row says explicitly that v2.1 was not
  run, because no valid joint-market wager candidate exists. No parlay
  EV, made-up correlation or stake is generated.

- Entire sports with no registered scheduled games say
  `NO_AUTHENTICATED_SCHEDULE_EVIDENCE`, not "0 valid bets."
- Event failures retain a sanitized BLOCK code; the five-sport report never
  issues an official card or counted outcome.
- The runnable research scenario engine supports score and player outcome
  types but many physical source adapters, roster/PIT confirmations and
  stat-distribution calibration contracts are still not populated.

## Independent release gates

Issue #10 remains binding: real original-book DK + genuinely independent
secondary provider offers; independent source/clock and starting-lineup
confirmation; three genuine preregistered chronological calibration cycles;
100 consecutive authenticated clean cards with v2.1 no-bypass controls;
at least five full days and 200 comparable settled opening/taken/closing
receipts; separate signed release review. No paid data may be silently
assumed, and BestBook displaying DraftKings is not a second original book.
No claims of profit or +EV from unvalidated blended synthetic research.

[Issue #10](https://github.com/bighauss/Sportsedge/issues/10)
