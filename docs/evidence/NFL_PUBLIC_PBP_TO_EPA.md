# NFL archived public play-by-play → point-in-time EPA ratings (research)

**Status: PAPER_HOLD_0U. No model promotion, official bets or validated EV.** This read-only bridge consumes original **PBP-bearing nflverse public source ZIP** from the GitHub Actions prospective capture. It binds the full ZIP SHA-256, original provider PBP source compressed-byte SHA-256, the exact capture manifest and its claimed provider update/capture timestamps, and a separately archived **complete per-game availability manifest** before using the existing `epa_ridge_pit.build_ratings` routine.

It never changes or guesses missing game finals, injuries, starting QBs, quotes or period/prop probabilities. It is NOT an automated schedule provider and is NOT proof that any historical PBP was available before its original week.

## Input contract

1. **Original archived ZIP**, not an extracted or recompressed substitute. The ZIP must have exactly one `forward_nfl_.../capture_manifest.json`, its PBP asset and corresponding PBP sidecar. It must be the *completed PAPER public capture* with `NFL_PBP_2026` and internally consistent hashes, bytes, rows, retrieval time, source type and stream scan mode. Other originally requested assets remain in the ZIP untouched. Original ZIP bytes are not rewritten.
2. **Expected ZIP SHA-256** from a previously separately recorded original artifact digest. Compare to the raw input ZIP. A caller could invent a hash after downloading, so the bridge cannot establish independent prior publication.
3. **Game availability JSON**: dict keyed by *every source PBP game_id*, each with `kickoff_utc`, `final_utc`, `data_available_utc`. These must be legitimate, independently maintained UTC timestamps; `kickoff < final <= data_available`. Do not invent or replace `data_available_utc` with a game-date string or `final_utc`. Missing game IDs fail rather than shrinking the denominator. All game's PBP is excluded if final or data availability is after the target as-of.
4. **Expected game manifest SHA-256** separately computed from the exact saved JSON bytes. The bridge rejects duplicate nested JSON keys, invalid/nonfinite fields, mismatched hashes and later provider captures.
5. **As-of UTC** must be after the original source capture time. If you need a forecast for a historical date predating the captured file, **STOP**: a current/revised release cannot be reclassified as genuine past pregame evidence.

Input ZIP, game manifest and resulting ratings JSON must all be **outside the public Git checkout** (lexical and resolved path guards). Output uses create-only mode `0600` with fsync/rollback; original source files remain unmodified. ZIP entries are never extracted to disk; source CSV is scanned and then consumed as a gzip stream with bounded memory and verified content.

## CLI

```sh
python models/nfl/epa_from_public_archive.py \
  --source-archive /private/nflverse_forward_raw_capture_20261115_run43799858180.zip \
  --expected-archive-sha256 sha256:41f8854aec8ebeadbc074f96ce45798796902332422dd2520aa4def5dae537ce \
  --game-manifest /private/independently_verified_2026_game_availability.json \
  --expected-game-manifest-sha256 sha256:YOUR_REAL_SAVED_GAME_MANIFEST_HASH \
  --asof-utc FUTURE_ACTUAL_FORECAST_FREEZE_UTC \
  --out /private/nfl_epa_research_ratings.json
```

The ZIP SHA above refers to the real public five-source capture from GitHub Actions run 43799858180. **The other placeholder values are not real captured inputs and the example is NOT executable until those actual source records exist.** As-of must be a real time chosen for a future actual research forecast; do not substitute a historical date. Set `--ridge` or `--half-life-days` only as preregistered research settings, not as post-hoc optimized bets. Optional `--wp-filter` ablation is not validated to improve forward performance.

## Research output and strict limits

The output is the unmodified EPA ridge feature stage plus `archive_provenance` with the original ZIP and source/manifest SHA256, actual captured source rows, claimed source observation UTC and booleans declaring **not independently authenticated**. Ratings are per-team pass/rush offensive and defensive-allowed EPA effects; no score, calibrated winner/cover/total probabilities, player props, touchdown distributions or validated edge.

Current source capture and target-game availability can be separately archived, but a basic SHA and provider `updated_at` do not authenticate original sportsbook/bookmaker or historical source publication clocks. Do not infer the source existed before earlier games. No source data in the public repository, no private odds or user records in GitHub, no wager placement. Issue #10 Gates A–E still block release.

## Synthetic tests

```sh
python -m unittest discover -s models/nfl -p 'test_epa_from_public_archive.py' -v
```

These tests use tiny in-memory mock ZIPs and gzip PBP rows. They check exact source SHA, manifest/sidecar, duplicate/traversal ZIP entries, late capture, missing game availability, nonfinite EPA, source row census, output path privacy and mode `0600`. CI passing confirms only **software behavior**. Live real archive is useful only with a genuinely supplied game-availability manifest.
