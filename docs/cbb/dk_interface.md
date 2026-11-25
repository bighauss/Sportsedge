# CBB DraftKings integration: runner interface (`models/cbb/dk/`)

PAPER/0u, NON_COUNTED. This module only reads the original boards in `models/cbb/lines/` and writes derived files.

## Commands
```
python -m models.cbb.dk.cli crosswalk --date 2026-11-25
python -m models.cbb.dk.cli reconcile --date 2026-11-25 --as-of <UTC run time> [--out-dir DIR] [--require-authenticated] [--issue57-hold "Away@Home" ...]
python -m models.cbb.dk.fetch_public events --ids <dk ids...> --out <evidence.jsonl>   # network, public pages only
python -m models.cbb.dk.fetch_public espn --date YYYYMMDD --out <raw.json>
```
`--as-of` is how RUN IT excludes games that have already tipped: any row with `tip_utc <= as_of` gets `STARTED_BEFORE_AS_OF`. Rows captured at or after tip always get `LIVE_AT_CAPTURE`.

## Inputs (per date)
| Input | Path |
|---|---|
| PDF board (original, read-only) | `models/cbb/lines/board_<date>_0636CT_pdf_capture.csv` |
| PDF board, PR #530 H1 re-transcription (read-only) | `..._h1_corrected.csv` (used as the PDF row source; the 20 truncated original rows are logged as `LINE_TRUNCATED_SUPERSEDED_PR530`) |
| Operator transcript CSV + markdown (read-only) | `models/cbb/lines/board_<date>_0900CT_operator_transcript.csv`, `research/cbb/boards/<date>_0900CT_muse_transcript.md` |
| DK event-page evidence | `models/cbb/dk/evidence/<date>/dk_event_pages.jsonl` (one record per fetch: request URL, final URL, HTTP, retrieval UTC, SHA-256 of bytes, parsed leagueId/eventName/participants/venueRole/eventStatus/startEventDate) |
| DK sitemap matches | `models/cbb/dk/evidence/<date>/dk_sitemap_matches.json` |
| ESPN scoreboard extract (venue, neutral flag; current DK-labelled odds are an auxiliary research comparator only, never pricing or quote authentication) | `models/cbb/dk/evidence/<date>/espn_scoreboard_extract.json` |
| Event crosswalk (generated) | `models/cbb/lines/dk_event_crosswalk_<date>.csv` |
| Team crosswalk (generated) | `models/cbb/lines/dk_team_crosswalk_<date>.csv` |

## Outputs (`models/cbb/dk/derived/<date>/`)
* `runner_board.csv` is what RUN IT should ingest. It has the same leading columns as the original boards (`sport,away,home,market,line,price_a,price_b,period,player,tip_utc,captured_utc,dk_event_id`) plus `totals_order,provenance,authenticated,row_key,notes`. It contains only rows that are `ACCEPTED`, or `HELD` solely for `TOTALS_ORDER_UNVERIFIED` (the runner keeps its own totals gate: `totals_order=over_under` admits the row, blank withholds it). `dk_event_id` is filled only when verified.
* `derived_board.csv` has every input row (one `DerivedRow` each, see `schema.py`) with disposition, reason codes, provenance, event-ID evidence, ESPN venue/neutral, tip in CT, implied and no-vig probabilities.
* `rejection_ledger.csv` has every non-ACCEPTED row plus the 20 truncated original rows, each with a reason code and text.
* `report.json` holds input hashes, counts, event-ID stats, identity-check verdicts, the ESPN cross-check and the cross-capture diff.

## Conventions (same as `cbb_run_it.py`)
`line` is the HOME spread. `price_a` is HOME (spread/ML) or OVER (totals). Times are UTC with `Z`, and `tip_ct` is America/Chicago.

## Dispositions
`ACCEPTED`: identity, time, price and market checks all pass. `HELD`: only soft holds (`TOTALS_ORDER_UNVERIFIED`, `ISSUE57_ORIENTATION_HOLD`). `SUPERSEDED`: a later capture of the same game/period/market family/player exists. `REJECTED`: anything else. The full code list with text is in `schema.REASONS`.

## Provenance labels
`OWNER_PDF_SCREENSHOT_UNAUTHENTICATED`, `OWNER_PDF_RETRANSCRIBED_PR530_UNAUTHENTICATED`, `OPERATOR_TRANSCRIPT_UNAUTHENTICATED`, and `DK_AUTHENTICATED_PROVIDER_CAPTURE` (reserved; no row uses it today). `--require-authenticated` rejects every non-authenticated row with `UNAUTHENTICATED_SOURCE`.

## Tests
`python -m unittest -v models.cbb.dk.test_dk_reconcile` (offline, from the repo root). No existing workflow runs this yet: a `tests.yml` step must be added by the workflow owner.

## Event IDs vs quote authentication
A verified DK event ID (`VERIFIED_PUBLIC_DK_EVENT_PAGE` / `BOARD_ID_CONFIRMED_PUBLIC_DK_EVENT_PAGE`) confirms only public event identity: leagueId 92483, Away/Home participants, and start time within 15 minutes of the board tip, from a signed-out public page. **Event-ID verification is not quote authentication.** Prices, market IDs and capture provenance stay unauthenticated unless the row's provenance is `DK_AUTHENTICATED_PROVIDER_CAPTURE`. The Nov 25 board has **zero authenticated quote rows**.

ESPN scoreboard odds are an auxiliary research comparator only. They are not an admitted source and are never used for pricing or to authenticate a quote.

## Owner ruling: Saint Bonaventure @ Belmont, Nov 25 9:00 AM CT
The accepted retrospective reading is Saint Bonaventure −4.5 / −205 and Belmont +4.5 / +170 (`line` and `price_a` are HOME). The original issue #57 orientation hold is retained on every row of this game. The matchup is hard-excluded from `runner_board.csv` and **must never enter a pregame card**.
