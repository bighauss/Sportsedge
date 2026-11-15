# Prospective NFL player-stat archive: pregame freeze → final grade

**Research only, PAPER / 0u.** The tool gives SportsEdge a create-only,
two-stage pipeline for timestamped per-event, per-player forecasts. It
does not place bets, determine an edge, independently authenticate a feed
or count as Issue #10 promotion evidence without external receipts.

## Before kickoff

Record a **real** event ID, BUF/MIA-style canonical home/away IDs, kickoff
UTC, model-feature freeze UTC, and independent forecast CSV (the existing
`player_forecast_intake.REQUIRED` schema). Each projected player requires
their stable player ID, team ID, stat type, mean, uncalibrated standard
deviation, prior model-training cutoff, source snapshot SHA-256, confirmed
status, and role/target/attempt floors.

**Source evidence must be archived separately from the public repository:**

- Raw original CSV/gz and its full SHA-256, registered NFL source ID.
- Original source `observed_at_utc`, local `captured_at_utc`,
  `data_through_utc` with `data_through <= observed <= captured <= freeze`.
- A separate exact-hash lineup-status CSV with columns
  `event_id,player_id,team_id,status`, where status is
  `ACTIVE`, `INACTIVE`, or `UNCONFIRMED`, and a source name,
  claimed observation/capture timestamps.
- The pregame freeze must be later than both source+lineup captures
  and earlier than actual kickoff. An optional observed sportsbook-quote time
  further limits all source/lineup data to be no later than that quote.
  No date may be invented/backdated to count past slates.

Use a **private directory**, not the public GitHub checkout:

```bash
python -m sportsedge.validation.forward_player_evidence \
    freeze /private/nfl_pregame_request.json \
    /private/nfl_frozen_event_20261116.json
```

The resulting JSON is created once, never overwritten. Model source bytes
are hashed and bound to its output, and each original nflverse/NGS source
file is checked row by row against the specified NFL `season`/`week`. A
current-season `week=0` NGS aggregate, the event's own week, any later week
or a future season causes a hard refusal even if the caller falsely labels
the source's `data_through_utc` as earlier. All source/forecast/model/lineup
file hashes are rechecked before the freeze object is returned. It hashes its
independent input files and includes every candidate as either
`PAPER_0U_FROZEN_UNVERIFIED` or `BLOCK` with exact rejection reasons.
Unknown, inactive, unbound, missing-source or insufficient-volume player
rows are retained as BLOCK, not silently omitted. The source inputs
remain private and the tool writes only redacted process counts to STDOUT.
Do not publish private player/lineup snapshots.

## After the game is officially final

Provide the exact SHA-256 of the **unchanged** original frozen archive;
an actual postgame CSV containing only
`event_id,player_id,team_id,stat,actual`; an independent original-file
hash, and claimed result-source observation/capture timestamps after
the reported final time. A numerical zero is a valid actual. No matching
player+team+stat row means `UNRESOLVED_MISSING_FINAL_STAT` (never zero).

```bash
python -m sportsedge.validation.forward_player_evidence \
    grade /private/nfl_final_grade_request.json \
    /private/nfl_graded_event_20261116.json
```

Final grades are also separate create-only JSON records and include their
original frozen-archive and results-file hashes. They do not modify the
prior file, assert a settled bet, compute bogus CLV, or authorize stakes.

**Schema:** `sportsedge-nfl-player-forward-freeze-v2` accepts the
root keys `schema,event_id,home_id,away_id,season,week,start_utc,
forecast_asof_utc,forecast_file,model_artifact,lineup_file,
source_files,roster_player_ids,odds_observed_at_utc`. `forecast_file` and `model_artifact` both require `path,raw_sha256`.
`lineup_file` adds `source_name,observed_at_utc,captured_at_utc`.
Each `source_files` entry adds `source_id,observed_at_utc,
captured_at_utc,data_through_utc`.
`sportsedge-nfl-player-forward-grade-v2` accepts
`schema,frozen_capture_path,frozen_capture_sha256,event_id,
event_final_at_utc,result_file`, where `result_file` carries
`path,raw_sha256,source_id,observed_at_utc,captured_at_utc`.

## Critical limits

An ordinary filesystem's exclusive-create and SHA-256 hash make local
changes detectable; **they do not prove existence at the claimed historical
time or guarantee WORM immutability**. Claimed lineups, event times and
provider publication timestamps are also not independently authenticated.
To satisfy Issue #10, original source/clock and sportsbook quote receipts
must be externally preserved and independently verified. Actual fit quality
requires genuine forward-measured distribution calibration, not simply a
forecast CSV. A second book's independently issued price, closing-line
evidence, complete real-slate coverage, and signed release review remain
separate. All outputs always set `approved_stake_u=0`,
`official_counted=0`, `card=null`.

## Test

```bash
python -m unittest sportsedge.validation.test_forward_player_evidence -v
python -m unittest sportsedge.validation.test_forward_acceptance -v
```

This code supplements, rather than alters, the frozen `sportsedge_v5.py`
or prior market/quote audit records.
