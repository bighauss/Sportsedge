# Migration log (Nov 15 2026)

## Sources
1. **Old repo `isaacrome21-sys/SportsEdge`.** That old repository returned 404 through the available connection. Neither its state nor its history could be independently verified; the following description is a historical handoff summary.
2. **Shared Google Drive folder `SportsEdge` (+ NOTES).** Current rules, models, handoffs, boards and run logs. The 38-file baseline came from `SportsEdge_FULL_repo_20261115.zip` (SHA-256 `6bfbba25a35f6312d0e8b856f6527b7cd506020d87386e29a14c714600a0ad22`); the manifest was not included in the repo.
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

## Test-recovery follow-up (Nov 15)
- PR #1 merged the 38-file baseline. The CFB generator and synthetic fixtures, NBA and MLB sample CSVs, and original NHL/CBB tests actually existed on Drive in separate uploads; the baseline handoff had described some of them as missing. They are recovered in a follow-up branch.
- After recovering the original synthetic inputs, local tests passed: CFB, NBA, CBB; MLB 6/6; NHL 31/31 checks. Those are software tests and **not** calibrated betting-edge evidence.
- The recovery PR removes tracked compiled `.pyc` files, adds `.gitignore`, and installs CI; remote CI results must be checked separately.

## Remaining blockers
- Adopted frozen v5 engine and guarded runner are not integrated here; the wrapper imports board-guard and slate-reconciler helpers missing from the baseline. Do not invent dummy replacements.
- No live authenticated DraftKings captures, source-as-of fixtures, validated starter/goalie availability, closing-line comparisons or calibrated model evidence were included.
- v2.1 risk and audit rules are binding, but standalone model scripts do not yet demonstrate complete end-to-end compliance; keep outputs PAPER / 0u.
- See `docs/audits/2026-11-15_migration_audit.md` for evidence and next steps.
