# SportsEdge coding-agent contract

Applies to Claude Code and contributors using coding agents in this repository.
For Codex/other agents, `AGENTS.md` points here. Inspired by the community
[`andrej-karpathy-skills`](https://github.com/multica-ai/andrej-karpathy-skills)
guidelines derived from Karpathy's observations; **not written by Karpathy**.

## 1. Surface assumptions
- First inspect current `main`, the specific files, related PRs and tests.
- State the requested outcome, relevant evidence, unresolved assumptions, and
  one concrete pass/fail condition. Distinguish observed facts from guesses.
- If authority, data licensing, safety, or source identity is materially unclear,
  ask or fail closed. Otherwise make the smallest reversible local choice.
- Never interpret a clean synthetic test as proof of genuine odds or profitability.

## 2. Cut scope
- Do the least work that satisfies the assigned acceptance check.
- No speculative features, generalized frameworks, redundant wrappers, or
  abstractions for a single use. Follow existing interfaces and style.
- Avoid expanding one source/model/market fix into unrelated sports or files.
- Keep owner requests for all markets visible as a coverage *inventory*;
  unsupported families must say `NO_DATA`/`NO_PRICE`/`NO_MODEL`, not disappear.

## 3. Keep the diff surgical
- Each changed line must connect to the issue and its test or documentation.
- Do not reformat, rename, or repair unrelated code opportunistically.
- Remove only unused imports, variables and helpers **your diff introduced**.
- Flag pre-existing dead code separately instead of deleting it.
- Do not overwrite another agent's branch, original evidence, or open PR.

## 4. Turn work into tests
- For a bug, write or identify a reproducing failing check first when feasible;
  then implement the smallest repair and prove the check passes.
- Include boundary/adversarial cases: time ordering, duplicate identities,
  missing and tampered evidence, original denominators, source independence.
- Never fake live provider responses in a way presented as authenticated data.
- For documentation-only changes, verify links, file paths, required safeguards,
  and that the patch contains no unrelated model/runtime modifications.

## 5. Verify before shipping
- Write a brief sequence: `change -> verification -> expected result`.
- Run the narrow test suite, then relevant repository CI on the **exact PR head**.
- On failures, inspect logs, fix the cause, and repeat checks on the *new* head.
- Do not call a PR merged because checks passed; verify the merge result on main.
- Report actual tests, head/merge SHA, remaining blockers, and any unrun tests.
- If work requires user authorization or unavailable credentials, stop at the
  tested, inactive boundary; never claim it runs live or will finish later.

## 6. SportsEdge non-negotiable evidence rules
- `RISK_POLICY.md` and [Issue #10](https://github.com/bighauss/Sportsedge/issues/10)
  are release constraints. **PAPER / 0u** until every applicable gate A–E
  has authentic, independently reviewable evidence and signed promotion.
- Protect frozen v5, original bets/boards, historical predictions and grades.
  No silent risk-cap, probability-weight or training-boundary changes.
- Preserve original source bytes/hash, UTC observation vs local capture times,
  provider-native and canonical IDs, exact book/market/period/side/line,
  both-sided prices, rejected rows, and the full attempted slate denominator.
- Guard point-in-time features: source publication must precede prediction;
  no closing lines, later injuries, game stats or hindsight in historical fits.
- An aggregator showing two book logos does **not** establish independent
  original sportsbook source chains or verified +EV/CLV.
- No secret/API key, private original quote file or personal wager data in a
  public PR, Actions log, issue, or fixture. Use authorized documented routes;
  do not scrape hidden endpoints or bypass subscription/licensing rules.

## 7. Parallel-agent handoff
- Work on a named isolated branch and scoped files; check for concurrent PRs
  before edits. If overlapping, coordinate instead of racing to overwrite.
- Record the change, exact test/CI outcome, PR URL, merge SHA and open gates
  in [engineering issue #57](https://github.com/bighauss/Sportsedge/issues/57).
- "Done" means the change is merged and verified; source authentication,
  real prospective acceptance and betting certification remain separate goals.
