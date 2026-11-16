# G2/G3 exact market decision identity — retrospective intake safeguard

This is an **audit-only / PAPER / 0u** fix. It does not modify SportsEdge v5,
model weights, original historical grades, old prices, authentic bookmaker
receipts or forecasts.

## Defect

Previously, duplicate detection used only
\`(event_id, market, selection, snapshot_utc)\`.

That key was **both too broad and too narrow**:
- Two different alternate total thresholds or two players in the *same*
  event/time were incorrectly labelled duplicated and removed.
- The exact same under/over outcome quoted at two different screenshot
  timestamps was counted twice, creating artificial grading volume.
- Sportsbook, period, original line and player/team identity were not part
  of the market comparison, so G2/G3 could pool incompatible markets.

## Revised evidence tiers

**Legacy input:** the existing eleven mandatory fields still work to
examine older files that lack explicit market/line/source identifiers,
but those reports are **UNATTESTED research**, not an executable or
authenticated bet ledger. Repeated versions of the same
\`(event_id, market, selection)\` are all quarantined, even if their
snapshot clocks differ.

**Extended input:** add \`sport\`, \`book\`, \`period\`, \`settlement\`
and (when the market requires one) numeric signed \`line\`. Sports
prop stats require exact \`player_id\` plus \`stat\`; team-total markets
require \`team_id\`. Unlisted/missing subject identity is BLOCKED, never
fuzzy-matched. Markets are normalized for common synonyms (e.g. ML vs
moneyline, DraftKings vs DK, full game vs FG), and numeric line
\`50.50\` means the same threshold as \`50.5\`. Exact decision identity
includes sport, source book, event, market, period, settlement rules,
selected side, line, player/team and stat. **Snapshot UTC is not part
of the bet decision identity.** All duplicate copies of that decision
are held, irrespective of input order or different observed prices.

A base-selection group containing both legacy and extended identities,
or an incompletely specified extended candidate, is quarantined as
ambiguous. A clean exact selection is not silently admitted just because
another copy is malformed.

Two different alternate lines, different players, or a different
book may survive as distinct **research observations**, but their
\`unique_events\` denominator is still ONE when derived from one game,
and ordinary independent-trial Wilson confidence intervals remain NULL.

Extended analysis strata separately identify sport, market, book,
period, settlement, exact numeric line, player ID, team ID and stat. A
half-game player prop or a different threshold cannot be silently blended
into another market's calibration bucket. Independent event IDs are
namespaced by sport so an unrelated NFL and CBB event with the same
external ID are not miscounted as a single game. Each reported audit
includes an explicit blocked-reason census.

## Caveats

- A complete identifier in a CSV is user-supplied metadata, not
  independently authenticated original provider evidence.
- Two books do not automatically count as independent upstream data
  sources; a shared odds aggregator may serve both.
- Real CLV needs authentic identical selection/line original taken and
  closing quote files with observed UTC, not just two snapshots here.
- A G2 market probability must be independently sourced and correctly
  matched to settlement. CBB 1H ML printed p may condition on no tie,
  whereas settlement includes pushes; do **not** ingest that as a binary
  unconditional win probability without original push draws.
- Multiple accepted markets from one event are still correlated.
  Selection-level ROI is descriptive and is NOT a signed flat-stake
  betting record. Missing original provider bytes and forward tests
  leave Issue #10 A–E OPEN.

## Verification

Run \`python -m unittest test_audit_disagreement_calibration.py\` from the
\`models/\` folder. The same suite runs in the repository
\`tests\` and dedicated G2/G3 workflows. Regression fixtures cover
multiple alt lines, books, periods, players, aliases, nonfinite lines,
mixed evidence levels, and repeated snapshots. No real private
provider price boards are committed to the public repository.
