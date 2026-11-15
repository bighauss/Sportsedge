# SportsEdge NFL public-source prospective capture (PAPER / 0u)

**What is new:** A scheduled/manual GitHub Actions job captures four **public nflverse** release assets (2026 player weekly stats, NGS passing/rushing/receiving). The previously implemented source downloader checks each GitHub release asset's SHA-256 digest against the original bytes. This new archive wrapper checks the original file again, records the actual runtime UTC, and keeps both payload and sanitized metadata as a short-lived GitHub Actions artifact.

The job executes at 09:37 and 20:37 UTC each day and on changes to the script/workflow; a delayed/skipped GitHub schedule is an *unobserved missing capture*, not evidence. A `workflow_dispatch` can add a declared event ID and UTC kickoff to explicitly distinguish pre-event versus late capture. Raw data are publicly licensed nflverse assets; no private odds, bets, cards, secrets or customer data are transmitted. The download remains free/read-only and does not touch the frozen v5 model.

## What it establishes and does not

* Github's separate run timestamp plus retained original public bytes is contemporaneous evidence that the *CI runner* fetched and preserved those bytes at that run, if the Actions run and attached artifact can still be verified. Original SHA256 is matched to GitHub's asset digest; file readback is checked again.
* This is **not** a publisher-signed publication timestamp, a verified roster/confirmed starter receipt, an independently authenticated DraftKings quote, a paired second-book quote, real player variance calibration, a betting edge, complete real-slate capture, or WORM/long-term immutable storage. Every report explicitly remains PAPER/0u, and Gate A–E are unchanged.
* `provider_updated_at_claim` can be later than the underlying data's first availability; historical revised files cannot be backdated to an earlier slate. `collected_before_declared_event` is a timing *check against the operator-supplied event time*, not authenticated event identity.
* The workflow captures raw source bytes daily but does not auto-admit them into any card. Admission for a specific event requires independently verified game ID/kickoff/lineup/odds, prior-week feature filtering, and source/forecast version proof. A returned `PAPER_0U_RAW_PUBLIC_SOURCE_CAPTURE` is never a bet.
* Athlete data licensing: nflverse datasets generally CC-BY 4.0; attribution to [nflverse](https://github.com/nflverse/nflverse-data) and any asset-specific notices is required. Artifacts expire after 14 days. Operators must migrate originals to durable restricted storage and record verified timestamps to use for multi-week forward audits.

## One-time local/private command

```bash
python -m unittest sportsedge.validation.test_forward_public_nfl_archive -v
python -m sportsedge.validation.forward_public_nfl_archive /private/nfl-source-captures \
  --event-id LAC_BAL_20261116 --event-start-utc 2026-11-17T01:15:00Z
```

Do not populate these event fields from an inferred team name alone. They must come from a separately recorded contemporaneous fixture with exact ID and cutoff; the example only illustrates input format. For real scheduled captures without event evidence, omit both flags: the result stays `collected_before_declared_event=false`.

Next release work remains obtaining permitted **original** sportsbook feeds from DraftKings and a genuinely independent book and freezing the actual pregame lineup/ratings and forecasts with independent observation timestamps. Aggregators can supply discovery prices, but two book logos on one unverified upstream feed are not independent source chains. Track all missing outcomes explicitly and continue collecting actual comparable closing-line triples rather than reconstructing history.
