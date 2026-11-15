# SportsEdge | Engineering operating standard

**Version:** 2026-11-15 hardening baseline  
**Canonical repository:** `bighauss/Sportsedge`  
**Engine of record:** SHA-256-pinned frozen `engine/sportsedge_v5.py`  
**Default output status:** **PAPER / 0u** until market-specific forward acceptance

## Principles

**Evidence before EV.** A spreadsheet of sportsbook numbers is not an authenticated quote source. Each observation requires a verifiable book, event, side/line, period, capture timestamp, hash and original record. A valid hash only proves byte stability.

**Reproduce before repairing.** Never mutate historical prices, forward logs, accepted model versions or original candidates. Maintain small PRs separating model changes, schema changes, policy changes and formatting changes. Preserve tests that recreate each defect.

**No invented coverage.** Full-game spreads/totals/ML, team totals, first/second half, quarters, player props, TD families, special teams and SGPs must have separate model+quote+settlement status. Unsupported markets stay visible as `NO_MODEL`, `NO_PRICE` or `NO_PROVENANCE`, not omitted or filled from an unrelated curve.

**Honest calibration.** Validate using chronological as-of train/test, reproducible scoring, Brier and log loss, calibration bands, comparisons with market-only baselines, realized line availability, CLV and correlation-aware risk. Do not change an adopted formula based on one winning or losing week. A large EV outlier triggers investigation, not automatic promotion.

**Safe releases.** For every PR, record input/output SHA-256s, exact fixture scope, regression counts, unchanged engine SHA, expected risk state and the specific acceptance criteria tested. Require passing CI. Use private Drive for sensitive odds captures, historical bankroll data, customer data, account tokens and source exports; use GitHub for source, synthetic fixtures, tests and sanitized documentation.

## Code map

- `engine/sportsedge_v5.py` — frozen adopted v5; do not edit under ordinary maintenance.
- `research/r5/` — archived NFL projection and guard experiments, not proof of live market readiness.
- `research/receipt_integration_r2/` — immutable historical raw-byte receipt work; checks integrity, not provider authorship.
- `research/claude_nfl_20261114/se_repair_layer.py` — historical **logarithmic** R2 layer. Preserve for accurate replay; its legacy keep flag is **not** admission.
- `research/claude_nfl_20261114/v21_fail_closed_repair.py` — stand-alone, non-executable, **linear** v2.1 research audit; outputs `PAPER_HOLD_0U` on every row.
- `research/risk/v21_risk_contract.py` — separate diagnostic stake-sizing contract; approved stake is always zero until all evidence gates pass.
- `docs/rules/RUN_IT_V2_1_MANDATORY_RESTORATION.md` — binding policy specification, including nine overrides.
- `docs/audits/` — independent findings and accepted limitation statements.

## Standard RUN IT workflow

1. Capture every requested market from a permitted, independently verifiable feed. Stamp one exact, timezone-aware observation per quote; preserve both sides of every offered line, and retain unavailable markets with explicit reasons.
2. Freeze eligible pregame model/roster assumptions by actual kickoff time, then apply the immutable v5/RUN IT controls. If a material change occurs, reprice using a fresh quote; never silently overwrite an original card.
3. Audit model-vs-market disagreement, push settlement, duplicate event/player IDs, and source-age receipts before computing any candidate stake.
4. Report separate `MODEL_DIAGNOSTIC`, `PAPER_HOLD`, and independently accepted states. Positive arithmetic EV alone is not acceptance.
5. Grade *every* originally selected row after the game, including losses and pushes, at original prices and stake units; preserve the as-of model version and closing price match provenance.

## Read-only v2.1 repair command

```bash
python research/claude_nfl_20261114/v21_fail_closed_repair.py \
  /private/path/picks_r2.csv \
  --out /private/path/new_annotated.csv \
  --report /private/path/new_audit.json
```

It never edits the input, does not overwrite an existing output, explicitly labels illustrative binary EV, refuses to invent missing push probabilities, flags missing evidence and retains **0u** stakes. Do not turn its output into a public betting card.

## Responsibilities and control boundaries

Changes to historical pricing, risk limits, market eligibility or model parameters require an explicit new version, a reproducible unseen-data evaluation and owner-approved release process. Documentation/test-only changes must not silently promote markets. Publishing from private Drive to public GitHub must be source-reviewed for sensitive data. See GitHub Issue #10 for the remaining independent source-to-card and forward-validation requirements.
