# Migration log (Nov 15 2026)

## Sources
1. **Old repo `isaacrome21-sys/SportsEdge`.** That older repository returned 404 through available access. Its code and historical commits could not be inspected or independently verified; later history notes are memory-based handoff claims.
2. **Shared Google Drive folder `SportsEdge` (+ NOTES).** Current rules, models, handoffs, boards and run logs. The 38-file baseline was copied from the SHA-pinned `SportsEdge_FULL_repo_20261115.zip` and merged as PR #1. The ZIP manifest is not tracked as a separate file.
3. **Isaac's Nov 15 notes.** Ruleset review, tracking-data survey, prompt libraries, nflverse/data-stack guide (`docs/research/`, `docs/data/`).

## Left on Drive (archive, not copied)
- Hourly `runNNN_*` sweeps, board/close CSV captures, pick receipts, zips.
- `GRIND_QUEUE.md` (~515 KB) and `RELAY_LOG.md` (~183 KB).

Copy specific ones on request.

## Old repo history (summary)
- **Promotion ladder:** VALIDATED_MATH → PRODUCTION_LOGIC_PASS → CI_ATTESTED → DEPLOYED. Later market state machine: NO_ENGINE → EXPERIMENTAL → VALIDATED_MODEL → READY_FOR_POLICY → OFFICIAL → REVOKED. Every market keeps its own evidence; no market inherits another's status.
- **CFB:** market-blind joint-score Monte Carlo (ridge regression → paired historical residuals, 20k sims, CFB overtime profile). Full-game ML/spread/total were executable.
- **MLB:**
  - 38 markets.
  - Replay policy v1 frozen: 180s TTL and 30s skew; Pinnacle→DK→FD→MGM→Caesars hierarchy for core markets; CR1 cluster-robust SEs by slate date.
  - Hybrid context autopull from MLB StatsAPI + NWS, fail-closed.
- **NFL:** M2 score-distribution engine. The feature search was exhausted Sept 10 2026: 10/10 attempts failed to beat closing lines.
- **Devig:** POWER_V1 is authoritative. Above +400, run method sensitivity; a spread over 1.0pp blocks the market.
- **Portable hybrid engine:** core + MLB adapter (inning-by-inning) + football adapter (drive-based, key numbers 3/7).
- **Other rules:**
  - Per-source candidate ledger.
  - RUN IT Layer A (model) is kept separate from Layer B (market context); market signals never become the model.
- **CI rules:** every workflow-referenced script must exist; broken workflows get quarantined, never stubbed green.

## Included in the bundle (exact Drive bytes)
Rules (v1, v2, NGS + CFB/CBB addenda, v2.1 restoration + corrections), five model READMEs, five sport models, CFB/NBA/MLB tests, engine/sportsedge_v2.py, ratings/props v0.2, Nov 13 handoff.

## Tests (Nov 15 2026)
All five sport models pass an end-to-end test on synthetic data:
- MLB, NBA, CFB: added `make_samples.py` (some original sample folders were omitted from the migration ZIP (separate originals were located in Drive)).
- NHL (`test_sportsedge_nhl.py`) and CBB (`test_cbb.py`): new tests that build their own samples.
- CI runs everything on each push (`.github/workflows/tests.yml`).

Sample data is fake and only exercises code paths; it says nothing about edge.

## Still open
- `sportsedge_guarded_v5_runner_r2.py` is left out. It imports `sportsedge_board_guard_r1` / `sportsedge_slate_reconciler_r1`, which were later recovered from the **Nov 13 R5 integrated engineering ZIP** and merged as PR #5.
- The models don't yet apply the v2.1 restoration (quarter-Kelly sizing, 5u/2u/3u caps, confidence tags, prop minimums, audit footer).

## Verified Nov 15 follow-up
- PR #5 restored frozen `engine/sportsedge_v5.py` byte-for-byte (SHA-256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`) and NFL/CFB/NBA research validation modules. Source archive SHA-256 `5ffad3d9a61b629aee8da2f2687f945ad46ab0b9e44a63b404a92535107eeb77`.
- Original full dated betting captures and receipt datasets stay in the Drive archive because GitHub is public; the recovered R5 suite runs 87 synthetic checks without them.
- The old repo history has not been recovered. The v2.1 rulebook is **not yet fully enforced** by the standalone scripts. See `docs/audits/2026-11-15_model_evidence_gates.md`.
