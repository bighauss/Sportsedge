# Owner ruling: capture-lane, closing-sweep and RUN IT clocks (v2 clarification)

**Decision:** APPROVED as the binding *specification*, 2026-11-16, America/Chicago.
**Canonical repository:** `bighauss/Sportsedge`.
**Coordination:** [issue #57](https://github.com/bighauss/Sportsedge/issues/57).
**Certification:** none implied; all unapproved markets remain **PAPER / 0u** under [Gate A–E #10](https://github.com/bighauss/Sportsedge/issues/10).

This is a **clarification without cadence loosening, source substitution, or operational certification**. The independent standing line lane, closing-price sweep and on-demand RUN IT have different purposes. No workflow, external standing job definition, provider access, live capture, saved quote, frozen model, or original ledger is altered by this document alone.

## Separate clocks and scopes

Let `S` be the registry's governing frozen event start, with revision handling below. All intervals are **half-open**, left-inclusive and right-exclusive. The event's local time zone is `America/Chicago`; persist full ISO-8601 timestamps with numeric UTC offset and distinguish actual read time from platform publication/acknowledgment.

| Path | Allowed source observation / validity | Required coverage | Purpose |
| --- | --- | --- | --- |
| Lane `T-1H` | `[S-90m, S-60m)` | Every market offered on the event page; full board | First comparable board snapshot |
| Lane `FINAL` | `[S-20m, S)` | Full board again, identical enumerated market scope | Second comparable board snapshot |
| Independent closing sweep | `[S-60m, S)` | Priority lines only: full-game spread, moneyline, total, team totals if priced | Grading/CLV feed; **not** the lane FINAL |
| On-demand `RUN IT` | Actual source observation time, with independent pregame/age/identity checks | Full board, every offered market | Point-in-time research/card evaluation; never a synthetic lane close |

The sweep may **pre-dispatch** its work so an actual read lands anywhere in its lawful 60-minute validity interval. Its 60-minute ceiling is **not** the lane FINAL eligibility interval. A 45-minutes-before-start sweep read can be sweep-valid and simultaneously lane-FINAL-invalid. A sweep priority-lines subset cannot be represented as a full FINAL lane board. A RUN IT read cannot be renamed or restamped to repair a missed lane mark.

### Market coverage and honest omissions

T-1H and FINAL each enumerate **all event-page markets and all priced sides**, including full-game spread/ML/totals, team totals, periods/quarters, alternate lines, all offered player-prop statistical families, TD/first-TD/2+ where applicable, and any available SGP or specialty offerings. The exact offered universe is source-dependent: record `NOT_CAPTURED`, `UNKNOWN`, `BLOCKED`, or positively observed `NOT_OFFERED` as distinct evidence states; never infer that absence from a partial read proves non-offering. Preserve event/market/period/side/player/line/price/source identities, failed reads, and the denominator. Compare like-for-like by immutable market identity; do not silently drop a market that disappears between T-1H and FINAL.

The sweep's limited priority scope is expressly allowed **for grading only** and must not claim full-board completeness. RUN IT requests the full board but must show each unavailable or unmodeled market rather than silently filling gaps with vendor projections or invented inputs.

## Official event start and prospective revisions

1. At morning event-ID verification, freeze `S` in the registry from the DK event page **cross-checked against the league slate**. Record event IDs, both source values, their observation times, provenance and a revision/version ID. If the two authoritative readings materially disagree and cannot be reconciled, leave start verification **BLOCKED**, not guessed.
2. A later legitimate start change is entered append-only with observed time, old/new values, original source, and an explicit list of windows **not yet opened**. Only unopened windows adopt the revision.
3. A window already open or closed continues under its prior governing start. An accepted snapshot is **never retroactively disqualified or restamped** merely because DK later changes displayed kickoff. Example: Baylor @ Texas DK changed displayed start to 14:10 CT; the already accepted 13:46 close stands under its then-governing registry start.
4. No start revision can turn a previously late, invalid, or missed read into an accepted one. The same prospective logic applies to sweep validity, and historical records retain their original clock basis.

## Held reads, one-read FINAL, and write budget

- **Held-read gate:** at FINAL window open `S-20m`, a pre-dispatched/held read is usable only if `0 <= S-20m - actual_read_at <= 15m` and all other source/market checks hold. Keep its **real earlier observation time**. A read actually performed within the FINAL window uses **its own actual observation timestamp**; do not impose an additional synthetic 15-minute freshness cutoff against the window-opening time on that in-window read.
- **One FINAL read, no in-window refresh:** select the qualified held read or the single real in-window read. Once that FINAL read is used, do not issue another FINAL source read to improve the result. Failed, late or incomplete reads remain visible; they are not silently re-tried into compliance.
- **Two lane GitHub writes maximum per event pregame:** one T-1H attempt and one FINAL attempt. **Every attempted write counts**, including rejected calls, retries, recovery markers, receipts and completion edits. A failed T-1H write is *not* retried; reserve the remaining slot for FINAL. Do not add a third pregame lane write through a “completion” or “verification” edit. Separate grading/RUN IT outputs have their own provenance and must not bypass this lane constraint or be passed off as a lane publication.
- Record independently: source observation/capture timestamp, clock with offset and source attribution; attempted platform-write timestamp and any acknowledgment; GitHub issue creation/edit/publication timestamp; write attempt number and result; and readback match/hash, if achieved. A local successful attempt or screenshot is **not** independent GitHub readback, and GitHub publication time must never be presented as source read time.
- If platform latency causes an attempted observation/read to land outside its respective source window, mark it `LATE`/`BLOCKED` and preserve it as **record-only**. No after-start backfill, reconstructed original bytes, or retroactive acceptance.

## Deterministic acceptance matrix (contract examples)

1. `S-75m` full-board read: T-1H in-window; not FINAL, not sweep.
2. `S-45m` priority-only sweep read: sweep-valid if source checks pass; **not** lane FINAL, and **not** a full-board capture.
3. `S-25m` unheld read: outside lane FINAL. It cannot be made eligible by changing the write timestamp.
4. Held read at `S-34m` is 14 minutes old at FINAL opening: eligible to use as held evidence only if all other checks pass, preserving `S-34m` as the source time. Held read at `S-36m` is 16 minutes old: reject.
5. Real full-board read at `S-7m`: within FINAL; record that true timestamp; no additional in-window refresh.
6. Read at or after `S`: **not** pregame accepted under any of the three windows.
7. A start revision after a window opens does not invalidate an accepted earlier capture or create a second attempt; it applies prospectively only to unopened windows.
8. After a failed T-1H GitHub write, next allowed lane write is FINAL. A T-1H retry is not permitted under the two-write cap.
9. Missing partial-game/player prop pages remain explicitly uncaptured; a priority-only sweep cannot certify lane full-board completeness.

## Rollout and acceptance boundary

- This decision is approved **as policy**. It is not proof the standing automation, a private sweep runner, or a private RUN IT operator has loaded it.
- Implement any live job/configuration change **prospectively** after inspecting its actual owner, definition and current output. Do not edit unrelated jobs; retain audit trails for old/BLOCKED November 16 records and keep the independent Chargers @ Ravens route independent.
- For the next scheduled lane cycle, require: saved effective job-spec readback; a status receipt posted and independently read back from #57; full slate and market-family denominator with explicit omissions; separated source and publication clocks; two-write accounting; and tagged references to source-bound issue/receipts. Failure is `BLOCKED/NOT_VERIFIED`, not a guessed success.
- Any code implementation must get test-first boundary cases above, exact-head CI and independent review. Do not touch frozen `engine/sportsedge_v5.py`, risk settings, original odds/predictions/grades, or historical acceptance outcomes.

**No official betting release:** no independent original DK+second-book authentication, complete A–E evidence, true validated model probabilities or approved stakes are implied by this specification. All uncertified selections stay **PAPER / 0u**.
