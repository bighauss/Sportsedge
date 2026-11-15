# SportsEdge — R2 point-in-time quote evidence + v5 research integration

**Prepared on 2026-11-15 (US Central), NON-DEPLOYED.** This is a PR-ready code candidate, not a running production service and not a verified sports-betting edge. GitHub read (README.md) failed with HTTP 403 `Sorry. Your account was suspended`. The assistant cannot restore GitHub account status or bypass its enforcement. GitHub has not accepted a branch, PR, or merge. This package is saved separately; the existing v5 engine remains unchanged.

## Completed, executed

1. Recovered and hash-pinned the actual archived v5 (`72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`) and November 9 census (`17d54f23d1be2caa326fe4aa3b50d0a31fb9ba2619f62e899553501a8bdc576e`). No historical model outputs, predictions, or qualification rules were rewritten.
2. Previously staged R1 rules independently validate timestamps, future features, grade outcomes, player/team identity, projection/source mismatch, and two-sided markets. `repair_r2/receipt_evidence_gate.py` adds a missing requirement: the exact frozen, normalized quote JSON for *every* one-sided snapshot must be available under `<sha256>.json` and its bytes must hash to the supplied `quote_receipt_sha256`. It checks quote ID, provider event ID, event, team, side, market, line, odds, original observation time, ingestion time, capture time, start and staleness. An absent receipt, edited quote, reused receipt, changed odds, or changed timestamp blocks R2 execution.
3. `repair_r2/run_guarded_v5_r2.py` calls the byte-evidence gate first, then the unchanged R1 receipt/identity/projection admission, then the inherited hash-pinned v5 guarded research runner. Both an end-to-end synthetic preflight and an actual synthetic v5 engine subprocess were executed successfully. No real sportsbook quote was invented; the synthetic provider `https://example.org/test-only` in unit tests is clearly only a fixture.
4. `RUN_RELEASE_TESTS_R2.py` is the short release gate for immutable source hashes, 72 R1 tests, 12 R2 tests, and 4 inherited guarded-v5 tests. Results are saved as `RELEASE_R2_TEST_RESULTS.json`; the separate old integrated CFB full suite exceeded runtime in this session and was not counted as newly re-passed.
5. Proposed GitHub Actions workflow is **not installed** until the repository is reachable and its path layout is verified. Its existing in-package folder tree may differ from the repo layout.

## Point-in-time evidence caveat — critical

The R2 gate proves that records **match the bytes stored** and have an internally coherent claimed pregame chronology. It does NOT prove a third-party bookmaker really posted those odds or that the quote was frozen before kickoff; an adversary could generate a plausible JSON and hash retrospectively. **External timestamp/source authentication and provider raw response evidence** are still mandatory for OFFICIAL/COUNTED promotion. Fields such as `provider` or `quote_verification` in self-authored files are NOT third-party authentication. R2 never changes official_counted from 0.

As checked at roughly 06:52 CT on Sunday Nov 15, Drive search returned **no `capture_2026-11-15...` files**. Rocky's Nov 14 end-of-day note says 15 Nov 15 games, including the Sunday NFL slate, were already on the 36-hour slate and T−1H/FINAL captures were scheduled in-window. Prior Nov 14 captures are not relabeled as Nov 15 quotes; later availability cannot be inferred. The Nov 15 forward test must use the **frozen** `FORWARD_TEST_R2_RULES_frozen_2026-11-14.md` and never retroactively change inclusion criteria. The Miami QB-change HOLD remains a separately logged governance decision; it cannot be silently reclassified without versioning.

## Run the self-contained check

```bash
python RUN_RELEASE_TESTS_R2.py
```

A synthetic, receipt-complete research preflight can be reproduced via `python -m unittest discover -s repair_r2/tests -v` from a properly configured PYTHONPATH or inside `repair_r2` as the current directory. The runtime CLI for actual future records is:

```bash
python repair_r2/run_guarded_v5_r2.py \
  --board newly_captured_board_with_legacy_and_receipt_columns.csv \
  --snapshot fresh_one_side_snapshots.csv \
  --receipt-dir receipts_from_this_capture/ \
  --engine integrated/nfl/sportsedge_v5.py \
  --output-dir NEW_UNIQUE_RESEARCH_RUN
```

Add `--execute-research` only for internal paper execution after the full gate passes. The original board, snapshot, and engine hashes are checked before and after execution. No bets are placed. Never fake missing receipts, model timestamps, roster status, or neutral-venue evidence to bypass a HOLD.

## Production promotion requirements (still unmet)

- **GitHub**: restore authorized access using account recovery/support in the GitHub UI; fetch current default branch, verify merge base and existing workflows, create a guarded PR, pass CI, review diff, then merge. Do not force push or bypass 403.
- **Live ingestion**: an authorized, independently witnessed upstream source must provide actual raw offer responses, timestamp attestations, provider event/player IDs, both sides and immutable hashes *before* game time. Compare to the normalized receipts supplied to R2. Drive historical screenshots alone are insufficient.
- **Validation**: maintain forward-test groups `ORIGINAL`, `R2_KEEP`, and `PERIOD_DERIVED` separately; keep all losing bets and withheld rows; grade with two independent final sources and no later rule changes; use precommitted 150 distinct games/Jan 15 2027 R2 verdict as frozen. Do not change model weights or release a real-money lane solely because test fixtures pass.

## Recommended PR title and body (once access restored)

**Title:** `research: add file-backed quote receipt guard before pinned v5 execution`

**Body:** `Add R2 raw normalized quote byte/linkage verification (missing/altered/stale quotes fail closed), wrap existing R1 and hash-pinned v5 runner, and run 88 targeted regression tests. Engine v5, historical census, original predictions and frozen forward-test R2 rules unchanged. Research-only, official_counted=0. External quote provenance, provider authentication, source timing, and point-in-time admission remain separate gates. No betting execution.`
