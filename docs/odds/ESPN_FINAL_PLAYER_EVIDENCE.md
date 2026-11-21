# SportsEdge ESPN final-score and player-stat evidence (dependent on #397)

**Research-only staging / PAPER 0u**. This does not mutate SportsEdge's odds, frozen v5, event-market scoring logic, existing SQLite ledger, projections or live wagers. It stages a canonical *candidate* final plus an **unaltered original ESPN response**. The parent PR #397 grades saved paper picks offline and explicitly separates result grades from unauthenticated price/CLV evidence; this adapter supplies one possible final-data candidate for subsequent **manual review**.

## Source and supported scope

One event at a time from the public ESPN Site v2 summary route:

`https://site.api.espn.com/apis/site/v2/sports/<sport>/<league>/summary?event=<ESPN_ID>`

Supported event families: NFL, CFB, CBB men's, NBA and MLB. **PGA is not supported**; tournament/round settlement is a different problem and must not be invented from this game structure. The ESPN Site API is unofficial and does not guarantee uninterrupted service, point-in-time historical snapshots, complete box scores, or independently authenticated publication timestamps.

Final-result staging requires: the **exact ESPN event ID**, both official ESPN team IDs and home/away mapping, a timezone-aware scheduled kickoff, `STATUS_FINAL` with `completed=true`, a single event competition, complete per-period home/away scores, and the score sums matching official totals. Missing periods, altered team IDs, unplayed/postponed games and other ambiguities **BLOCK** creation of a canonical candidate. MLB needs at least nine actual innings (rain-shortened games are blocked until a dedicated settlement policy exists); extras are kept distinct. For CBB, two halves use `H1/H2` and optional `OT`; basketball and football quarters use `Q1` through `Q4` and `OT`. Overtime does not silently inherit unobserved scores.

Player box-score ingestion is **partial**. Stat cells are parsed only from exact ESPN category+label matches with unambiguous athlete IDs, and only supported non-negative integer outcomes. Recognized football fields include passing/rushing/receiving yards, attempts/completions, receptions and touchdowns; CBB/NBA includes points, rebounds, assists, 3PM, blocks, steals and turnovers. Stat cells that are missing, negative, ambiguous, contradictory, or unsupported **remain missing**, never zero. A player ID used under both teams is quarantined. MLB player props are **not automatically mapped** pending verified batting/pitching schemas. **No player-period stats, full play-by-play, complete scoring-event stream, FIRST_TD, TD_2PLUS or first-basket proof is inferred**; these remain ungradable until an independent source provides that complete evidence. Even for supported stats, downstream roster binding and settlement terms remain subject to review.

## Run a one-event source capture (after the game ends)

```bash
python -m sportsedge.validation.espn_final_evidence \
  --sport CBB --event-id ESPNEVENTID \
  --home-espn-id ESPNHOMEID --away-espn-id ESPNAWAYID \
  --kickoff-utc 2026-11-21T18:00:00Z \
  --out-dir /private/new_espn_final_event_directory --execute
```

The example IDs are placeholders. Do not use them for actual events. No paid API key is required; one HTTP GET is attempted, no redirects are followed, and the response is capped at 5 MB. This command has **no scheduler**, no automatic retries, and is blocked if the result cannot be verified structurally.

## Import an already downloaded original (no HTTP)

```bash
python -m sportsedge.validation.espn_final_evidence \
  --sport NFL --event-id ESPNEVENTID \
  --home-espn-id ESPNHOMEID --away-espn-id ESPNAWAYID \
  --kickoff-utc 2026-11-21T18:00:00Z \
  --out-dir /private/new_espn_import_directory \
  --raw-file /private/saved_actual_espn_summary.json
```

Original bytes are preserved. The intake stamps its **current local acquisition time after reading**; importing a file today does not prove the provider made it available before today, or before some older grading decision.

The **new private output folder's parent** must already exist with owner-only permissions (0700); saving into a public GitHub checkout, group-readable parent or symlinked parent is refused.

Output files:

- `original_espn_summary.json` — exact original source bytes
- `result_evidence_receipt.json` — SHA256 of original, local read-completion UTC, source URL/kind, known validation limitations, PAPER 0u
- `canonical_final_FOR_REVIEW.json` — explicit event/team IDs, period scores, known player-stat cells, player IDs, source-derived `FINAL` status and recorded observation time; **NOT an automatically admitted grade**

All files are owner-private. **Do not commit any private result/price records to public GitHub.**

## Linking to #397 without fabricating sportsbook evidence

1. Independently verify the ESPN ID/team map, kickoff and final scores, including crosswalking operator event/player IDs to the canonical pick's IDs. ESPN and sportsbook IDs are **not interchangeable**.
2. Confirm the original source's collection time and SHA; review player-stat coverage and any warnings.
3. Copy/reference the reviewed candidate as the `final` original evidence file in #397's *private* manifest, with SHA and true capture-clock receipt (not a backdated claim).
4. Run #397's **dry-run** batch grader first; verify how many picks are `PAPER_RESULT_GRADED`, `PENDING_FINAL`, `FINAL_OR_SETTLEMENT_BLOCKED`, and `PRICE_EVIDENCE_BLOCKED` separately.
5. Append **result-only** rows to the separate research SQLite ledger only after review. A result grade is *not* proof of offered price, CLV, ROI, profitable edge, or an actual wager.

If the exact ESPN schema or score-split naming differs from these source contracts, keep the event **BLOCKED** and add a regression test after inspecting an original response; do not silently loosen parsing.

## Test

```bash
python -m unittest sportsedge.validation.test_espn_final_evidence -v
```

The 24 synthetic tests cover five sports, quarters/halves/innings, original bytes, exact event/home/away IDs, missing or contradictory athlete stats, insufficient final-score splits, incomplete events and private archive permissions. This PR has **not** authenticated any particular live ESPN response or graded actual picks; no provider call is made in CI.
