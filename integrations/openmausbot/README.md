# OpenMausBot ↔ SportsEdge (optional integration)

Status: **template committed for review; NOT installed, connected, activated, scheduled or live-tested**. This is an agent coordination layer, NOT a sportsbook API, model release, accepted edge, or wagering executor.

## Purpose and boundaries

Use OpenMausBot's Markdown team importer to create an independent engineering crew, not a runtime dependency of SportsEdge. Source: [OpenMausBot](https://github.com/milind-soni/OpenMausBot) and [BotMRR Markdown v1 format](https://github.com/milind-soni/openmausbot-teams/blob/main/FORMAT.md). SportsEdge remains the canonical source of forecasts and acceptance state. The optional team is kept in [SPORTSEDGE_TEAM.md](SPORTSEDGE_TEAM.md).

- Seven isolated sport engineers: NFL, CFB, CBB, NBA, MLB, NHL, PGA.
- Four shared roles: engineering lead, authorized-source/odds engineer, independent auditor, QA/risk guardian.
- Every sport and offered market family remains visibly `PAPER / 0u` unless A-E evidence and owner-controlled promotion are confirmed in SportsEdge's own release path.
- No embedded credentials, autonomous wagers, shell execution, bankroll actions, or model changes.
- Importing the file creates suggested agent profiles/rooms/playbooks; **it does not** authenticate accounts, run agents, configure a server, create scheduled routines, or turn on Github write access.

## Install / import (requires a computer or server; phone can pair afterward)

1. Obtain an official, verified OpenMausBot release from [upstream releases](https://github.com/milind-soni/OpenMausBot/releases). Choose a supported Windows, macOS or Ubuntu installer, or follow [upstream self-hosting documentation](https://github.com/milind-soni/OpenMausBot/blob/main/docs/self-hosting.md) on a machine you control. Review releases, dependencies and security notes before executing third-party code. This PR does **not** install software on any device.
2. Set up a supported model/agent CLI only through OpenMausBot's own onboarding. Costs/entitlements may apply; the SportsEdge repository includes no provider accounts.
3. In OpenMausBot use **Teams → Import** and choose the local `integrations/openmausbot/SPORTSEDGE_TEAM.md` file, or paste the public raw URL after this PR is merged:

   `https://raw.githubusercontent.com/bighauss/Sportsedge/main/integrations/openmausbot/SPORTSEDGE_TEAM.md`

   Before merge, use the PR branch raw link instead. Review the imported bot definitions and permissions before accepting the template.
4. Leave bot permission mode at **Ask**, leave all routines paused, and do **not** enable host-control/Full access. Connect GitHub with **read-only** permission for `bighauss/Sportsedge` first. If subsequently approving PR writes, grant only required repository scope and avoid secret-management/admin scopes.
5. Keep the private evidence vault outside public GitHub. Do not share DK/BestBook/DataGolf account data, bankroll records, provider receipts, private projections or credentials in public prompts, bot chat logs, issues, CI logs or branch commits.
6. If remote/mobile control is wanted, pair using upstream's supported private pairing method (e.g. Tailscale or HTTPS tunnel). **Never** expose the server loopback port directly on the public internet. Review [upstream security notes](https://github.com/milind-soni/OpenMausBot/blob/main/SECURITY.md) and the documented Slack worker/full-access gap before making any connector active.

## First acceptance exercise — intentionally read-only

In SportsEdge Command, ask:

> Inspect `bighauss/Sportsedge` main and all open PRs. Compare their stated work to `docs/SPORTSEDGE_OPERATING_STANDARD.md` and `docs/operations/SEVEN_SPORT_PARALLEL_EXECUTION_20261115.md`. Produce a seven-sport and all-market-family inventory, plus evidence gaps and a proposal for one small, non-overlapping engineering PR. Do not write, merge, execute a wager, alter risk policy, access private credentials, or claim an authenticated odds feed.

Inspect the bot's responses for:
- Real GitHub references (commit SHA, issue and PR numbers) rather than invented or stale claims.
- Correct unresolved original CBB 496-side pregame file status; no synthetic data presented as the original receipt.
- Explicit missing-source/unsupported market-family reasons; no claims that a game-line projection prices all props.
- A-E gate separation and `PAPER / 0u` defaults.
- No hidden provider authorization, no credentials, no unapproved external side effects.

If any check fails, turn off that bot/connection, preserve its output as an audit finding, and fix the template or permissions before enabling more agents.

## Safe escalation after smoke test

After explicit GitHub PR-write authorization, limit each task to a separate scoped branch/PR. Require an independent review by `auditor` and `guardian`, exact test logs, data scope, input SHA and rollback. Never merge concurrent PRs without checking the latest base. PR creation/merge is distinct from publishing a market as accepted. This template does not authorize financial actions or live-betting promotion.

Suggested lane order is derived from [the existing execution board](../../docs/operations/SEVEN_SPORT_PARALLEL_EXECUTION_20261115.md). Keep the main model engine untouched. An hourly engineering automation already exists outside OpenMausBot; do not duplicate or start a second hourly routine on import.

## Verification and rollback

Run from repository root:

```sh
python -m unittest discover -s integrations/openmausbot -p 'test_*.py' -v
```

This validates local contract invariants, **not** upstream installer safety, live import compatibility, GitHub OAuth, actual agent operation, odds availability or market admission. Verify actual OpenMausBot import interactively before calling this integration deployed.

Rollback: revoke the GitHub OAuth grant if given; disable/delete imported bots and any explicitly activated routines in OpenMausBot; remove the optional integration files from SportsEdge via a separate PR. No engine database migration or betting model rollback is needed, because this package does not modify those systems.
