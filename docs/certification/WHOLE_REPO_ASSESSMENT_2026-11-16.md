# SportsEdge whole-repository certification assessment — 2026-11-16 CT

**Decision: NOT CERTIFIED for production betting. Official count = 0. Approved stake = 0u.**
No market has passed independent A–E acceptance or received a signed promotion.
This is a **read-only pre-certification audit**, not a legal, security, financial,
accuracy, profitability, source-provider or software quality certificate.

## Exact assessment baseline and reproducible scope

- Canonical public repository: `bighauss/Sportsedge`.
- Inspected `main`: `1c2398b943c04891753a4d6406ed9fac9ee38be3`
  (2026-11-16 07:16 CT / 13:16 UTC).
- Git tree: **622 tracked blob/file entries**, **76 GitHub workflow definitions**
  in the inspected tree. Counting files/workflows is NOT auditing each file,
  nor evidence that all 76 workflows were executed on this commit.
- GitHub Actions first-page check: **18/18 observed completed `push` runs
  succeeded at exactly the inspected head**, including `tests`, frozen-code
  risk/market inventory, seven-sport PIT freeze synthetic validation,
  research price kernel and pregame evidence audits. Remaining workflows
  (including manual/conditional/PR-only jobs) have NOT been proven run on this
  exact head by this check. A pass is CI *software regression evidence only*.
- `research/freezes/market_release_matrix_20261115.json`: exactly
  **49 declared broad sport/family combinations** = 7 sports × 7 families,
  all `PAPER_0U`, all 245 declared A–E flags false, zero approved stakes,
  zero counted official selections. This is NOT the entire offered market
  universe including every player/period/alternate line.
- `research/freezes/frozen_baselines_20261115.json` and
  `research/freezes/verify_code_freezes.py`: pinned code digest checks
  cover selected original v5/risk and seven-sport baselines, not every
  file or model behavior. The verify step cannot authenticate old source
  observation timestamps, coefficients or original game lines.
- `RISK_POLICY.md`: selected strict version
  **`SPORTSEDGE_STRICT_V21_V22_20261115_R1`**, official 0u,
  5u/Chicago day, 2u/game, 3u/theme, push-aware quarter-Kelly research
  diagnostics, T−90 and source gates. The program is not authorized
  to emit wagers.

## Verified certification-blocking findings

| Severity | Evidence | Release impact / remedy |
|---|---|---|
| **P0 — NO external original book source** | Issue #10, source adapters, auth smoke and observation logs | Working credentials for read-only CFBD/The Odds API/API-Sports JSON do **not** prove direct original DraftKings + genuinely independent second bookmaker offers. Obtain properly permitted original provider receipts, source identity, clocks, raw-byte custody and complete offered/missing quote denominator for each market. |
| **P0 — True point-in-time feature provenance absent at acceptance scale** | Issue #10; sport model/source and freeze contracts | Synthetic freezes and retrospectively released NFL/NGS/other season files are not contemporaneously witnessed as-of evidence for earlier events. Preserve actual prior-to-game roster, lineup, QB/goalie, weather, usage and model fit snapshots from authorized sources. |
| **P0 — Forward calibration not externally accepted** | Issue #10 and open per-sport trackers #190–#196 and #239 | At least 3 preregistered leak-free future cycles, unchanged original denominator, model vs market/simple baselines, real Brier/logloss, calibration and uncertainty. Code for train-only score variance, period shares, covariance and 0u research signals is NOT this evidence. |
| **P0 — Authentic CLV missing** | Issue #10; ledger and source receipt contract | Require 200 individually settled identical-market open/TAKE/closing original receipts with documented player, side, exact line, book, period, time, outcome and no-vig CLV. Existing synthetic/local market snapshots do NOT suffice. |
| **P0 — Operational admission not accepted** | `RISK_POLICY.md`, Issue #10 and market matrix | Need 100 consecutive genuinely clean real-slate candidate→guard→card/settlement records, 5 full qualifying calendar days, independent review and signed per-market promotion. No auto-betting or bypass until then. |
| **P1 — Historical default policy identifier drift** | Root `RISK_POLICY.md` vs `research/freezes/market_release_matrix_20261115.json` | The matrix claims `SPORTSEDGE_RISK_2026_11_15_LOCK_V1`, different from the current selected strict ID. `daily_safety_sweep.inspect_matrix` checks PAPER/0u but does **not** reject this drift. Treat this snapshot as **historical**, DO NOT rewrite it as original. Create a new current-dated/strict-policy snapshot after explicit review. The new whole-repo audit reports `MATRIX_POLICY_MISMATCH`. |
| **P1 — Matrix freshness** | Matrix `asof_date_ct=2026-11-15` | The inspected snapshot is not a complete current-date real-slate measurement. Its research-only status remains valid; it cannot certify Nov 16 live inventory. New audit reports `MATRIX_ASOF_NOT_CURRENT`. |
| **P1 — Provider observation metadata ≠ original quote** | PR #255 merged after the inspected 13:16 UTC baseline (`db2c2900d9f9aface3f7917264f75e891168fe17`) | The workflow now validates sanitized observation metadata before normal archival, but does not retain authenticated bookmaker-original bytes or prove independent pricing upstream. Keep Gate A OPEN and track failed/unavailable observations separately. |
| **P1 — Source-gate wiring incomplete for live certification** | PR #257 merged after the inspected baseline (`5837d76170900c5616cfa61c36f789c41c032ae2`), Issue #10 | Research card gate now checks declared independent-chain evidence; this is not externally verified upstream authenticity or evidence of 100 real-slate candidate/guard executions. Gate A/E remain OPEN. |
| **P1 — Unresolved historical 496-side and real grade artifacts** | Issue #49 and #80 / G18 forensic notes | The recreated or derived 496-priced-side census is not proof of the missing contemporaneous original 496 priced sides or original finals. Isolate retrospective research; never claim validated original graded ROI from missing files. |
| **P1 — Five-sport pricing kernel vs seven-sport release scope** | README and Issue #10 / #195–#196 | NHL/PGA have standalone research models but are not independently integrated and forward accepted in the same main five-sport price/risk runner. Do not silently mark family coverage complete. |


### Subsequent engineering merges (outside the inspected baseline)

At 2026-11-16 13:18 UTC, the live main branch had advanced past the
specifically inspected `1c2398b9...` tree to `5837d761...` through
#255 and #257. These newer merges improve metadata validation and source-chain
research checks; they do **not** retroactively enlarge the 622-file/76-workflow
13:16 UTC scope, prove new provider evidence, or change the gate outcome.
The pre-certification workflow operates against the actual checked-out source
and verifies frozen code and release matrix at every execution. A newly
reviewed whole-repo baseline is needed for certification of any subsequent
commit; never silently treat older CI counts as today's full suite.

## Gate-specific signed-release conditions

| Gate | Current reviewed state | Independent acceptance requirement |
|---|---|---|
| **A: Source** | OPEN | Authenticated original DK and distinct second bookmaker; two-sided exact-line quotes; source-native event/market IDs; original UTC provider/capture times; all attempted markets/blocked statuses, real 100-card source streak |
| **B: Features** | OPEN | Independently witnessed pregame team/player/injury/QB/lineup/stats/model-fit sources; ≥95% actual complete PIT packages, all others blocked |
| **C: Calibration** | OPEN | Three *latest* preregistered clean nonoverlapping cycles and independent whole-population walk-forward metrics; no future input use |
| **D: CLV/Settlement** | OPEN | ≥200 independently auditable settled and comparable original open/taken/close receipts, correct pushes/voids and sport settlements |
| **E: Safety/release** | OPEN | No risk bypass, correct strict policy ID, 100 consecutive real-slate guards, 5 full qualifying days, independently signed **per-market** promotion |

**No current source supports a numerical estimate of real betting profitability,
true sportsbook value, full model calibration or a verified official wager.**
Synthetic positive test cases, displayed no-vig comparisons and sample hashes
must not enter ROI or gate acceptance tallies.

## New executable whole-repository pre-certification diagnostic

Run from the repo root, offline, without any API credentials:

```sh
python -m unittest tools.test_whole_repo_release_audit -v
python -m tools.whole_repo_release_audit --asof-date-ct 2026-11-16
```

The JSON result distinguishes:
- Frozen-code identity checked vs source reality not authenticated.
- 49 declared market/family rows vs actual complete offered market universe.
- All 245 gate flags and self-asserted `PASS` values vs **zero**
  independently verified external requirements.
- Root strict-risk version vs historic default release-matrix version.
- Complete source and final outcome evidence missing, code and risks locked.
- `release_verdict=NOT_CERTIFIED`, `production_certified=false`,
  `official_market_count=0`, `approved_stake_u=0`.

An explicit strict invocation:

```sh
python -m tools.whole_repo_release_audit --require-production-certification
```

returns exit code **3** rather than falsely succeeding while outside evidence
is unavailable. The ordinary audit command returns 0 on a successful
assessment even though it reports `NOT_CERTIFIED`. No input to this program
can sign an external release; it has **no independent provider attestation**
backend, and must not silently add one.

The GitHub Actions audit workflow tests those fraud/omission cases against
synthetic content. Green CI certifies neither all 622 files nor any profitable
real-market edge. Before any future actual release, independent reviewers
must audit the complete implementation and original evidence scope, verify
secret custody/least-privilege and provider retention rights, run on real
unseen slates, and sign off each exact market.

## Owners and follow-up

Source of truth: [Issue #10](https://github.com/bighauss/Sportsedge/issues/10)
(A–E release gate), [Issue #57](https://github.com/bighauss/Sportsedge/issues/57)
(shared engineering), [Issue #239](https://github.com/bighauss/Sportsedge/issues/239)
(model-to-edge activation). No duplicate automation is required. The existing
hourly task may continue closing specific engineering defects while preserving
`PAPER / 0u` and leaving all externally unverified gates open.
