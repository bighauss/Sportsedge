# Firecrawl / ESPN injury-context intake — research only

**Status:** PAPER / 0u. No market promotion or model-feature admission.

## Live discovery findings (2026-11-15 CT / 2026-11-16 UTC)

Firecrawl was connected in ChatGPT and an Alexandria source contract was
discovered for `espn-com/sports-data/injuries`: an `nfl`/`football`
feed with team filtering, ESPN athlete IDs, status, note date, source-observed
milliseconds and a feed timestamp. An actual `CHI` request returned **25
records**, including rows labeled **Active** whose comments were ordinary
game recaps. Thus `player_count` is **NOT** the count of confirmed injured
players; not every row is a contemporaneous injury designation. The provider
run is an API result, not independently timestamped immutable evidence of
when an earlier injury note became public. It must never be backfilled as a
historical injury record.

A separate Firecrawl discovery for the official `nfl-com/sports-league-data/injury_report`
provider found a versioned contract; actual scoped week 10 and week 11 CHI
requests returned **zero rows**, not validated proof of a healthy roster.
That provider's reported availability can lag or differ by team/date.

The ESPN source uses the upstream contract endpoint
`https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries`.
The provider contract has a five-credit price per execution, subject to the
Firecrawl plan; provider execution and discovery are different operations.

## Offline, private adapter

`sportsedge.validation.firecrawl_espn_injury_intake` consumes a saved,
**original, unmodified** Firecrawl Alexandria JSON tool response. It does
not run Firecrawl, fetch the endpoint, carry OAuth tokens, or authenticate
a sports-feed publisher. The host/authorized runner must first save the raw
JSON itself in owner-private storage.

Example CLI:

```bash
python -m sportsedge.validation.firecrawl_espn_injury_intake \
  --original /secure/archives/firecrawl_espn_chi_original.json \
  --report /secure/archives/firecrawl_espn_chi_receipt.json \
  --team CHI \
  --event-id YOUR_VERIFIED_EVENT_ID \
  --event-start-utc 2026-11-22T18:00:00Z
```

The example event/start fields are **placeholders** and must be replaced by
verified provider event metadata. Do not copy the date into a live job without
checking the actual game schedule. Any stale or post-event original is refused.

Both files must live outside the public GitHub checkout under a mode-0700
private directory; original input must be mode-0600. The report is written
create-only as mode-0600. No file is overwritten. The raw player names,
comments, IDs and details are not copied into the resulting sanitized report.

## Guard conditions

* Requires exactly one successful `espn-com/sports-data/injuries` provider
  execution, upstream HTTP 200, workflow digest, and provider request ID.
* Requires matching NFL, league `nfl`, exact team code, one team, all statuses
  present in source (`status_filter: null`), and consistent player census.
* Every player must have a unique nonblank ESPN athlete ID, matching current
  ESPN team ID, UTC note date no later than observation, and known status.
* The feed timestamp must precede source observation. Local execution must
  happen after observation (within 300 seconds) and before the declared
  game start. Feed timestamps older than seven days relative to observation
  are refused; older individual notes are counted and block use.
* Classifies `Active` / `Healthy` / `Available` as **non-injury**,
  not as active injury signals. Unrecognized statuses never become
  `Questionable`, `Out` or other modeled effects.
* Zero rows, only Active rows, unknown status rows or stale notes yield a
  visible BLOCK rather than inventing health or imputing injuries.
* Duplicate JSON keys, NaN, inconsistent counts, mismatched team or athlete,
  public checkout paths, symlinks and insecure permissions are refused.

A well-formed recent non-active status yields only a research-context
receipt, **not** permission to adjust playing time or projection weights.
Status is not guaranteed to equal final NFL participation designation.

## Remaining work

1. A separately authorized runner must save true original response bytes
   prospectively; ChatGPT's Firecrawl login is not automatically available
   to GitHub Actions and must not be copied into repository secrets without
   an explicit operator-controlled authorization.
2. Independently verify the athlete/team crosswalk, the relevant game,
   original source publication timing and a contemporaneous official
   NFL practice/game-status report, especially when a row is Active or an
   old recap. Maintain conflicting and missing observations as exclusions.
3. Only after actual source chain and true PIT evidence exist, submit as a
   private feature artifact to the seven-sport freeze workflow. **This
   adapter intentionally sets `model_feature_admissible=false`,
   `gate_b_pit_certified=false` and `approved_stake_u=0`.**
4. Gate A source authorization, independent book offers, chronological
   calibration, genuine CLV, official settlement and Gate E safety remain
   separately required. This adapter does not close any gate.

Test without spending data-provider credits:

```bash
python -m unittest sportsedge.validation.test_firecrawl_espn_injury_intake -v
```
