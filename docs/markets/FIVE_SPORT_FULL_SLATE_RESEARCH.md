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

## Seven-sport schedule visibility (five-sport pricing engine unchanged)

The request's `sports` list may now include **NHL** and **PGA** in addition to
the five pricing-kernel sports NFL, CFB, CBB, NBA and MLB. Their scheduled
events MUST appear as `BLOCK` with
`NO_SUPPORTED_NHL_OR_PGA_PRICING_KERNEL`, and every listed research market
family carries `NO_SUPPORTED_PRICING_ADAPTER`. This is an explicit
**schedule/inventory-only** lane. It neither consumes unregistered NHL/PGA
price/model manifests nor assumes a bookmaker actually offers those markets.
Supplying a purported NHL/PGA priced event through the five-sport manifest
raises `SCHEDULE_ONLY_SPORT_HAS_NO_VALIDATED_PRICER`.

The report retains its legacy `five_sports` key for existing consumers and
adds `sport_coverage`, `schedule_only_sports`, and
`research_pricing_sports`. The `schedule_only_unpriced_events` counter
shows the unsupported scheduled event count without treating it as a
priced/processed slate. A future authenticated NHL/PGA pricing adapter must
be reviewed separately before any research pricing is accepted.

For a future card, all seven sports require an **independent, complete
upstream schedule capture**. A supplied expected-events list alone is not
proof that all contests or markets were actually offered; a missing event
cannot be discovered from an incomplete caller-supplied schedule.

The CLI rejects input *and* output paths inside the public repository by
checking the resolved repository root, not whichever nested working
directory launched it. Private sportsbook offers must never be committed.

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
  At most **one** such marker is permitted per sport/event: without a
  distinct posted parlay ID and leg fingerprint, repeated placeholders are
  duplicates, not separately verified offered SGPs. A repeated marker
  blocks intake with `DUPLICATE_UNPRICED_SGP_INVENTORY`.
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


## Independent projection receipt overlay (new, all seven sport labels)

The optional private top-level `projection_evidence` array attaches an **exact
10-field market identity** to an independently asserted SportsEdge forecast.
It is evaluated **only after** the existing scenario pricing, research risk,
BestBook, and weather paths, so it cannot turn sportsbook odds into model
features or alter historical/unchanged research prices.

Every processed straight research row now carries
`independent_projection.status`, `independent_projection.reasons`, and
`verified_model_ev=false`. Without an evidence receipt, that row explicitly
says `BLOCK: NO_INDEPENDENT_PROJECTION_RECEIPT`. Accepted metadata shape
is **`PAPER_0U_MODEL_PROJECTION_UNVERIFIED`**, never certified. The report
adds `independent_projection_coverage` event/slate counts across *all*
submitted research rows including blocked SGP inventory placeholders.

Example **fictional** private input addition (use real model/feature SHA values
from the actual already-generated event before submitting; this example cannot
pass the binding by itself):

```json
{
  "projection_evidence": [
    {
      "market_identity": ["CBB", "GAME-1", "TOTAL", "FG", "OVER",
                          "142.5", "", "", "", "REGULATION"],
      "forecast": {
        "origin": "SPORTSEDGE_INDEPENDENT",
        "model_sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "feature_sha256": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "distribution_sha256": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "feature_frozen_utc": "2026-11-15T19:00:00Z",
        "generated_utc": "2026-11-15T19:01:00Z",
        "event_start_utc": "2026-11-16T20:00:00Z",
        "feature_sources": [
          {
            "kind": "PLAY_BY_PLAY",
            "sha256": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
            "published_utc": "2026-11-15T18:59:00Z"
          }
        ],
        "p_win": 0.55,
        "p_push": 0.02
      }
    }
  ]
}
```

For player markets, the receipt additionally requires a
`frozen_roster` player-ID-to-team-ID map that is independently established
as of the prediction time; a bookmaker's unlabeled prop name is insufficient.
The evidence adapter does **not** resolve missing players, create a
probability, backfill a quote, or validate original source authenticity.
Non-FG, first-event, 2+, SGP and PGA specials require corresponding
period/ordered/count/joint model evidence and identities. An exact-market
receipt for a row not submitted to RUN IT, or a duplicate receipt, rejects
the input rather than silently joining to another team or line.

Important: this is the existing repository's five-sport **research** slate
runner plus seven-sport schedule visibility. It is **not** automatically
integrated with the separate Nov 16 `operative_run_20261116_runit` saved
elsewhere; that system requires its own import from this contract. No real
new CBB/NFL/NBA/NHL/PGA outcomes or original sportsbook receipts are
generated by the overlay. Frozen v5, historical selection records, original
quote bytes, risk policy and PAPER / 0u status remain unchanged.
