# NCAA daily odds snapshot (CBB + CFB) — manual-only, encrypted, PAPER / 0u

Research data intake for the CBB paper card (`models/cbb/cbbd_paper_card.py`) and
CFB paper card (`models/cfb/cfb_paper_card.py`). It never emits picks, edges, EV,
CLV results or stakes. Every record carries `official_counted=0`,
`approved_stake_u=0`, `edge_verified=false`.

Code: `sportsedge/odds/ncaa_daily_odds.py`. Workflow:
`.github/workflows/ncaa-daily-odds.yml`. Offline tests:
`sportsedge/odds/test_ncaa_daily_odds.py` (run on PRs by
`.github/workflows/ncaa-odds-intake-tests.yml`, no secrets).
The NFL pilot (`daily_main_odds.py`, `nfl-daily-odds-pilot.yml`) is unchanged.

## Provider contract (verified, not guessed)

| Item | Value | Source |
|---|---|---|
| CBB sport key | `basketball_ncaab` | [Odds API sports list](https://the-odds-api.com/sports-odds-data/sports-apis.html) |
| CFB sport key | `americanfootball_ncaaf` | same |
| Markets | `h2h`, `spreads`, `totals` | [v4 guide](https://the-odds-api.com/liveapi/guides/v4/) |
| Books | `draftkings`, `fanduel`, `betmgm`, `pinnacle` (via `bookmakers`, which takes priority over `regions`) | v4 guide |
| `/odds` cost | `markets x regions`; each group of 10 bookmakers = 1 region; no events returned = not charged | v4 guide |
| `/sports`, `/events` cost | do not count against quota | v4 guide |
| Usage headers | `x-requests-remaining`, `x-requests-used`, `x-requests-last` | v4 guide |

**Budget per run: 3 credits** (`3 markets x ceil(4 books / 10) = 3 x 1`), computed
in code (`credit_budget()`) before any request. Worst case per Central date:
4 runs (2 sports x 2 snapshots) = **12 credits/day**; ~372 per 31 days if every
slot is used. These are documented-billing expectations, not a provider-enforced cap;
`x-requests-last` is checked after the call and any excess triggers a hold.

## Snapshots

- **pregame** — dispatch in the morning (Central). Free `/events` check for
  games starting in the next 36 h; if none, no paid call. Gives the card its
  pre-freeze quote.
- **close** — dispatch **within 90 minutes before** the target games. Free
  `/events` check for games starting in the next 90 min; if none, no paid
  call. Pairs for those games are flagged `in_snapshot_window=true`; only
  those rows are closing quotes for CLV. Other rows are earlier quotes and
  post-start events are excluded from pairs.

One claim per **sport + snapshot + Central date**. A skipped or blocked run
still consumes that day's slot (fail closed). Dispatch close too early and the
day's close slot is gone.

## Per-run sequence

1. Input / secret check (`ODDS_API_KEY`, else `ODDS_API_KEY_BACKUP` only if the
   primary is empty — never both, never a retry with the backup), Fernet
   validation of `SPORTSEDGE_ARCHIVE_FERNET_KEY`, offline tests. Failures spend 0 credits.
2. `daily_pilot_artifact_gate reserve --pilot <sport>-<snapshot>` checks
   `ncaa-daily-odds-quota-hold` and `<sport>-<snapshot>-daily-odds-attempt-YYYY-MM-DD`
   artifacts, writes the claim, uploads it, then `verify` re-reads it for this run ID.
3. Free `GET /v4/sports`: abort with 0 paid credits if `x-requests-remaining`
   is missing/unparseable or below `3 + 50` (reserve floor), or if the sport is not
   `active`. Free `GET /v4/sports/{key}/events` window check.
4. One paid `GET /v4/sports/{key}/odds` through
   `free_odds_aggregator_intake.capture` (unchanged): redirects refused,
   non-200 refused, no retries, key never logged.
5. Private archive (mode 0600, outside the repo), then every file is Fernet
   encrypted; only ciphertext + a SHA-256 index is uploaded (90-day retention).

Log line: state, sport, snapshot, date, budget, credits used, window events,
pair counts, key slot (`primary`/`backup`). No remaining balance, teams, prices or keys.

## Archive files (per run)

| File | Consumer |
|---|---|
| `aggregator_<CBB or CFB>_<ts>_<sha16>.json` — exact provider bytes | both paper cards |
| `aggregator_..._.manifest.json` — schema `sportsedge-oddsapi-aggregator-raw-v1`, `sport` `CBB`/`CFB`, `original_raw_sha256`, `captured_utc` (observed UTC) | both paper cards |
| `ncaa-<sport>-<snapshot>-<date>.pairs.json` — schema `sportsedge-ncaa-odds-pairs-v1`, full two-sided per-book pairs only, event list for crosswalk building | graders / CLV, operator crosswalk |
| `ncaa-<sport>-<snapshot>-<date>.attempt.json` / `.result.json` | audit |
| `ncaa-daily-odds.quota-hold.json` (only on pause/review) | gate |

### Feeding the paper cards (after decrypting privately)

CBB (merged #403):

```sh
python models/cbb/cbbd_paper_card.py ... \
  --odds-api-raw aggregator_CBB_<...>.json \
  --odds-api-manifest aggregator_CBB_<...>.manifest.json \
  --odds-api-crosswalk crosswalk.csv   # odds_event_id,game_id,odds_home_team,odds_away_team
```

CFB (merged #404):

```sh
python -m models.cfb.cfb_paper_card <capture_dir> ... \
  --odds-archive aggregator_CFB_<...>.json aggregator_CFB_<...>.manifest.json crosswalk.json
```

The crosswalk is operator-built from the `events` list in the pairs file; no fuzzy
matching. `test_real_cbb_paper_card_loader_accepts_archive` and
`test_real_cfb_paper_card_loader_accepts_archive` feed a synthetic archive from this
intake to both merged loaders unchanged.

## Quota holds

Unexpected cost, unparseable billing headers, low remaining balance after the call,
a capture failure after the request may have been billed, or a failed pairs sidecar
writes `ncaa-daily-odds-quota-hold`. It blocks **both** sports and snapshots until an
owner reviews billing and deletes the hold artifact. The NFL hold is separate.

## Limitations

- One close snapshot per sport per day can only be "closing" for games within its
  90-minute window; spread-out slates (CBB especially) need per-window snapshots,
  which this design does not provide.
- Provider times and book quotes are aggregator claims, not upstream book attestation.
- An admin can delete claim/hold artifacts and defeat the one-per-day guard.
- No data on days nobody dispatches. No schedule until a separate reviewed opt-in.
- Tests never use a real key; every HTTP call is an in-memory fake.
