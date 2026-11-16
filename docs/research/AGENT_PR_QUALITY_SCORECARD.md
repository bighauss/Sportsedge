# SportsEdge agent engineering quality scorecard

**Goal:** measure whether the shared coding-agent instructions in
[`CLAUDE.md`](../../CLAUDE.md) and [`AGENTS.md`](../../AGENTS.md) are
associated with smaller, more verifiable PRs. This is an *observational* report,
not a controlled experiment and **not a claim of 65%→94% coding accuracy**.

## Cohorts and freeze

- Policy intervention: [PR #220](https://github.com/bighauss/Sportsedge/pull/220),
  merged **2026-11-16 04:52:14 UTC** (Nov 15, 10:52:14 PM CT).
- **Baseline:** last 20 PRs whose **creation AND merge** precede that timestamp.
- **Prospective:** first 20 PRs whose **creation AND merge** follow the timestamp.
- Exclude #220 itself, PRs crossing the boundary, open/abandoned PRs and PRs
  without merge evidence. GitHub API source PR numbers are always visible.
- Until 20 post-policy PRs have merged **and 14 full days have passed since
  their latest merge**, report `POST_SAMPLE_INCOMPLETE` or
  `POST_MATURITY_WINDOW_PENDING`, never a success declaration.
- Compare descriptive scope and CI measures; GitHub does not label which PR
  was produced by which model/agent. Context, authorship, project phase and
  changing CI checks can confound every difference.

## Metrics, with boundaries

- **Scope:** median files changed, median additions + deletions and count of
  unusually large PRs. Small is not always better; important source fixes
  can require larger changes.
- **Commits per PR:** descriptive only. Not an accurate bug-fix/rework count.
- **Observed CI:** number of merged PRs with recorded completed PR-head
  workflows, their all-green share and failed conclusions. Missing CI is
  `unknown`, never green. A successful final attempt is not proof earlier
  attempts were green; counted reruns are shown separately.
- **Review rework proxy:** GitHub `CHANGES_REQUESTED` review submissions.
  Not all bug fixes receive formal reviews, and some requests are editorial.
- No measure can infer actual agent answer accuracy, wagering profitability,
  source authentication, or correctness of proprietary player models.

## Execution

The [coding-agent scorecard workflow](../../.github/workflows/agent-pr-quality-scorecard.yml)
runs **weekly on Mondays 14:17 UTC**, can be invoked manually by maintainers,
and runs once on merge of the scorecard's own files. The PR path runs only
offline contract tests. It uses the built-in ephemeral `GITHUB_TOKEN` with
read-only `contents`, `pull-requests`, and `actions` permissions to fetch
**public GitHub PR metadata only**; no custom API keys or account connection.

The result appears in the workflow **job summary** and as two downloadable
**30-day GitHub Actions artifacts**:
`sportsedge_agent_pr_scorecard.json` and `.md`. Artifacts are snapshots,
not a permanent outcome ledger or an immutable WORM archive. If long-term
tracking is needed, explicitly archive the original weekly artifact, not
retrospectively recomputed changed source data.

Reproduce in any authorized read-only environment:

```sh
python -m unittest -v research.observability.test_agent_pr_scorecard
GITHUB_TOKEN='<private read-only GitHub token>' \
  python research/observability/agent_pr_scorecard.py \
    --output-prefix /tmp/sportsedge_agent_pr_scorecard
```

Do **not** paste tokens into chat, commit them, or upload a token-bearing
terminal log. The scheduled workflow injects its own ephemeral token.

**Protected state:** `RISK_POLICY.md` and issue #10 remain unchanged.
All SportsEdge betting outputs without certified A–E acceptance stay
**PAPER / 0u**. A coding-agent quality scorecard never promotes markets.
