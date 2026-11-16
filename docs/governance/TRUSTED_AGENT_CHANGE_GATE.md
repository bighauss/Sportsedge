# Agent change governance — trusted PR guard, November 2026

## Purpose and scope

This adds a narrow, deterministic enforcement step to the existing agent
contract in [CLAUDE.md](../../CLAUDE.md). It is **not** a replacement for
human authorization, signed model release, real sports-data validation, or
branch protection. It is a fail-closed *change-intake* check.

**Protected file families:** `RISK_POLICY.md`, `CLAUDE.md`,
`AGENTS.md`, `sportsedge_v5.py`, all `models/`, `research/risk/`,
`research/freezes/`, `sportsedge/odds/`, `.github/workflows/`,
the governance tools, and the versioned synthetic golden fixture.

A PR touching any protected file must carry
`docs/governance/changes/pr-<PR_NUMBER>.json` with:
- Exact **protected path census** from `git diff --no-renames`, including
  file deletions/renames (treated as delete + add); the exact base commit
  SHA and PR number; a reference to an existing SportsEdge GitHub issue.
- Small change specification, explicit assumptions and identified agent.
- Least-privilege declarations: coding-agent **branch-only** permissions,
  no secrets access, no production deployment or model/market promotion;
  merge authority remains subject to actual repository rules.
- Baseline metric and its status; `UNKNOWN` requires null value and may not
  be silently represented as zero. `SELF_REPORTED` is not an authenticated
  external measurement.
- The exact pinned SHA-256 of the **nine synthetic agent-policy cases**,
  a reproducible deterministic unit test, an external review state of
  **NOT_VERIFIED**, and `unseen_data_verified=false`.
- Rollback target equal to the PR's base commit, a reviewed revert PR plan,
  and a command to re-verify after rollback.
- AI/project task cost in USD with `UNKNOWN` / null by default, or a
  nonnegative self-reported amount and receipt digest. The guard never
  invents zero cost or outcome-per-dollar performance.
- **No betting promotion**: known v2.1/v2.2 policy, certification false,
  independent approval false, 0u, 0 official-counted.

For PR #268 the recorded protected path census and explicit unknown
baseline/cost live in
[`changes/pr-268.json`](changes/pr-268.json).
This manifest is a **claim by the PR author**, not proof of actual account
permissions, an external signature, or a real model evaluation.

## Trusted execution

[Agent high-risk governance workflow](../../.github/workflows/agent-high-risk-governance.yml)
has two roles:

1. `contract-tests` on ordinary PR/push: Python unittest adversarial
   checks and a pinned frozen JSON fixture. These are *synthetic policy
   tests*; they do not cover genuine NFL/CBB betting models or provider
   captures. A green check is not evidence that an agent's answer accuracy
   improved.
2. `trusted-high-risk-manifest` on `pull_request_target`: runs the
   **trusted BASE SHA's** tool and golden fixture. Uses read-only
   `contents` permission, disables persisted credentials, and never
   executes code from the pull-request head. It fetches only git commit
   objects, verifies the exact expected PR-head SHA, and consumes the
   untrusted manifest as bounded, strict JSON. It refuses malformed
   JSON, duplicate keys, NaN, path traversal, changed-file omission,
   self-granted privileges, fake owner sign-off, false source auth,
   claims of official stakes, wrong golden digest, missing rollback,
   or silently zeroed costs.

For an ordinary PR with **no protected changes**, the trusted job returns
`PASS_NO_PROTECTED_DIFF`; with a complete manifest it returns
`PASS_DECLARED_REVIEW_ONLY`; neither status authorizes production use.
Without a required manifest or with a bad one, CI fails. This is a
necessary-but-not-sufficient merge quality check.

**Critical operational dependency:** A repository administrator must
explicitly configure `trusted-high-risk-manifest` as a required
status check in GitHub **Settings → Branches / Rulesets**. GitHub
connection in this chat does not provide branch protection administration
access. Until the status check is required, GitHub may allow a merge
that bypasses this workflow. Human review requirements and merge rights
must be configured in the same repository ruleset, independently of what
a JSON manifest declares.

Never add `secrets.GITHUB_TOKEN`, provider API keys or live original
sports data to this workflow. `pull_request_target` is safe *here only
because* it never executes the untrusted head, nor grants write/secrets.

## Golden dataset versus independent model evaluation

The nine checked-in synthetic cases cover only output safety:
PAPER/0u research acceptance, fabricated certification, positive stake,
bogus authenticated source, missing or extra fields, boolean stake, and
prompt injection as untrusted text. SHA-256 binding detects changes to
those nine source bytes and the gate refuses silent dataset mutation.

This is **not** a real prediction/odds golden set, point-in-time backtest,
or independent challenge evaluation. For any market-model PR a separate
prospective, preregistered unseen-period model evaluation and authenticated
original captures remain required. Independent reviewer attestation is
not inferable from the manifest.

## Rollback, ownership, budget and operations

A protected PR must name a base SHA to restore and a reviewed revert-PR
plan, but CI **does not actually execute a rollback** or guarantee that
a later branch can be reverted without conflicts. For a failed change,
freeze admissions, open an issue and submit a reviewed revert PR;
run the recorded validation command and recheck all affected A–E gates.
Never rewrite original odds, predictions, pick ledgers or frozen artifacts.

The model/AI budget report records source references and actual amounts
only when supplied; `UNKNOWN` is a valid visible state, not a zero-dollar
assumption. "Outcome per dollar" requires independent outcome evidence and
is always withheld by this safety gate. Existing request quota ledger in
`research/audit/quant_provider_budget.py` addresses provider-rate
reservations separately and must not be confused with actual AI spend.

Governance scope is shared across NFL, CFB, CBB, NBA, MLB, NHL and PGA.
It does not issue market prices, rewrite model parameters, collect provider
credentials, claim real ROI/CLV, or remove another agent's controls.

## Reproduction

```sh
python -m unittest tools.test_agent_change_governance -v
python -m tools.agent_change_governance \
  --repo . \
  --base-sha <actual-pr-base-commit-sha> \
  --head-sha <actual-pr-head-commit-sha> \
  --pr-number <actual-pr-number>
```

The standalone checker expects both SHA commits present locally.
For future protected PRs, create the PR first to get its number,
then add its per-PR manifest to that PR branch. Since the base can
change as other agent PRs merge, refresh the manifest's base SHA if
GitHub updates the base before reviewing. Never fabricate validation
outcomes or assume a manifest makes a PR safe to merge.

**Market release:** all current sports/market Gates A–E remain OPEN.
Only an independent signed market-specific evidence package could
change that. **PAPER / 0u.**
