# Forward acceptance evidence assessor — Issue #10

This tool reports the **reported structural progress** against Issue #10's hard gates. It is not a provider-attestation verifier or a model-promotion engine.

Run: `python -m sportsedge.validation.forward_acceptance private_manifest.json --report new_sanitized_report.json`.

Schema version `sportsedge-issue10-structural-v1`, with exact keys `schema`, `cards`, `clv_triples`, `calibration_cycles`. Each card must contain ID, UTC generation timestamp, quoted row count, missing/stale/unauthenticated counts, guard-bypass count and PIT complete/total counts. Each CLV item must include a unique bet ID, open/taken/close observed times, event start and settlement times, exact-match flags and settlement outcome. Each calibration cycle must have a registration time, evaluation window, leakage-finding count and SHA-256 research-report digest. See synthetic `test_forward_acceptance.py` for a complete input fixture.

**What it measures:**
- A: most recent consecutive cards with **zero reported** missing/stale/unauthenticated quotes, threshold 100.
- B: reported PIT package completion among latest 100 cards, threshold 95%, **and no price-bearing card in that recent window may report zero PIT packages**. The report includes `reported_zero_pit_cards_last_100` so a single big, complete card cannot hide 99 cards with no claimed input package.
- C: at least three **reported** preregistered nonleaking chronological cycles.
- D: 200 distinct, settled, structurally same-market/book pregame close triples.
- E: 100 most recent cards with **zero reported** risk guard bypass.
- Whole program: at least five consecutive reported Central-Time calendar dates. **Five dates do not prove five complete real-slate days.**

**What it absolutely does not prove:** Self-supplied timestamps, hashes, labels, price counts, claimed book identity, roster observations, calibration files or settlement timestamps are **NOT trusted evidence**. This tool does not verify provider transport, cryptographic signatures, PIT publication by an independent source, real slate completeness, CLV fair-price accuracy or independent human approval. Even when every structural threshold is satisfied, `release_certified=false`, `approved_stake_u=0`, `official_counted=0`, and every gate `externally_certified=false`. A separately approved independent credentialed evaluation process is mandatory for any real promotion.

Reports are create-only, include input SHA-256 and aggregate counts/reasons but not player, sportsbook, event or raw quote fields. Raw provider captures, actual bets/results and credentials remain in restricted Drive.

## Private receipt boundary and deterministic report creation

The tool refuses both source manifests and report destinations inside the
public SportsEdge GitHub checkout, including symlinked paths and nested
working-directory invocations. Put them in an access-restricted private
workspace. Invalid `NaN`/`Infinity` JSON literals fail closed. The tool
serializes its entire paper-only report before creating the destination with
exclusive-create and owner-only file permissions on POSIX platforms. It
refuses to overwrite any existing result.

These are **local data-integrity controls**, not provider attestation,
independent immutable storage, or a secure replacement for access controls.
No report can certify an OFFICIAL bet or lift Issue #10 without external
source verification and distinct owner-signed approval.

An additional defensive check examines both the **lexical** path inside the
public checkout and its resolved symlink destination; either entering the
checkout is refused. If report creation succeeds but an actual write or sync
fails, the partially created result from that invocation is deleted (without
touching the private source). This remains a local integrity precaution rather
than independent attestation or full transaction-safe storage.
