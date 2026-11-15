# Migration log (Nov 15 2026)

## Sources
1. **Old repo `isaacrome21-sys/SportsEdge`.** That GitHub account is suspended and the repo returns 404, so no files could be copied. Its history is summarized below.
2. **Shared Google Drive folder `SportsEdge` (+ NOTES).** Current rules, models, handoffs, boards and run logs. See `MANIFEST_drive_to_repo.csv` for the files copied.
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

## Known gaps (to fix next)
- Tests: CFB needs `make_samples.py` + `samples/` (not on Drive); NBA needs its `sample/` CSVs (KeyError G1); MLB test reports 1 failure. NHL and CBB test files are not on Drive.
- `sportsedge_guarded_v5_runner_r2.py` left out: it imports `sportsedge_board_guard_r1` / `sportsedge_slate_reconciler_r1`, which aren't in Drive's root folder.
