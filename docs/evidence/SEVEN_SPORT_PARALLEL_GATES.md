# Seven-sport parallel acceptance matrix — November 15, 2026 CT

**Status: PAPER / 0u.** This is a structural evidence partition and coordination aid, not provider authentication, verified model skill, a real-price archive, an official bet card, or a promotion mechanism. See Issue #10 (hard A–E exit) and Issue #57 (shared agent coordination).

## Scope and rule lock

- Enumerate NFL, CFB, CBB, NBA, MLB, NHL and PGA concurrently.
- **The root `RISK_POLICY.md` strictest-of-v2.1/v2.2 lock** is the current binding research-policy contract (`SPORTSEDGE_STRICT_V21_V22_20261115_R1`, merged PR #189): quarter-Kelly diagnostic, 5u/day, **2u/game**, 3u/theme, missing-half shrink/LOW, >12pp gap hold, +200 ML 0.25u diagnostic cap, T−90 and lineage safeguards. Pure v2.2's no-game-cap override conflicts with the stricter lock and is **not adopted**. Historical v2.1 records retain original frozen labels; a new prospective matrix requires the current exact locked ID. Any future risk change needs explicit owner signoff and unseen testing, not a silent manifest label.
- Existing frozen v5 model and historical prices, forecasts and grades are unchanged. 0u until every per-market A–E gate and signed owner promotion clears.
- Market inventory is not inferred from the files in the repository. Missing/unsupported markets and zero-evidence families must be explicitly declared; a report may only say **declared**, never **complete**.
- A shared capture service does not close Gate A across all sports. Every independently admitted sport/market/period must show contemporaneous, authenticated, same-identity DK and independent original book evidence, as required by Issue #10. A BestBook display of DK is not a second upstream source.
- For every requested market family and period, use its own distinct evidence manifest. Reusing a card, bet or calibration-cycle ID across different matrix partitions is conservatively rejected.

## Runnable structural assessment

Run from repository root with a private JSON file and output path outside this public checkout:

    python -m sportsedge.validation.market_gate_matrix \
      /private/market_matrix.json --report /private/new_market_report.json

Top-level input must have exactly these fields:

    {
      "schema": "sportsedge-seven-sport-market-gates-v1",
      "rules_version": "SPORTSEDGE_STRICT_V21_V22_20261115_R1",
      "markets": [
        {
          "sport": "NFL",
          "market_family": "SPREAD",
          "period": "FG",
          "market_key": "mainline",
          "evidence_manifest": null
        }
      ]
    }

The example is **incomplete**: the CLI requires at least one declared entry for **all seven sports**. An entry can have a null evidence manifest when no authentic receipts are available. A non-null manifest must be a full independent input conforming exactly to the existing sportsedge.validation.forward_acceptance.analyze schema: cards, CLV triples and preregistered calibration cycles. All such values are still **self-reported structural counts**; a generated report **always** contains release_certified=false, official_market_count=0, approved_stake_u=0 and coverage_is_authenticated_inventory=false.

Use distinct market_key for lines, player stats, periods or settlement variants that should never share an admission decision. Supported family labels: ML, SPREAD, TOTAL, TEAM_TOTAL, PLAYER_PROP, PERIOD, ALTERNATE, SPECIAL, SGP, DFS, OUTRIGHT, MATCHUP, OTHER. The auditor does not claim these labels exhaust any actual provider board.

**Security limits:** duplicate JSON keys / NaN are refused; private input/output lexical and resolved paths outside the checkout; output exclusive-create mode 0600, fsynced; archived original immutable receipt bytes must remain elsewhere in access-controlled storage. This does not independently attest to provider truth, market coverage or WORM durability.

## Parallel engineering handoffs — distinct file/PR boundaries

| Lane | First separate change (not a claim that it is completed) | Acceptance blocker |
|---|---|---|
| Shared source / Gate A | Authorized DK + independent-original-book quote/event map; raw signed/provider-observed timestamps, exact normalized market identity, rejected population | Real permitted account/feed, independent chains, 100 real clean cards per admitted market |
| NFL | Lock frozen EPA/score and source-as-of artifact; separate player/TD/period reliability, genuine forward results | PIT QB/roster, calibrated prop/TD distributions, 3 preregistered cycles |
| CFB | Lock season/team-rating + QB + pace/weather as-of contract; compare historical-only vs market baseline | Lineups/season mappings/authorized quotes, forward test |
| CBB | Retain merged PR #175 original CBBD final verification; lock Torvik-to-score bridge and exact 496-side historical-file provenance | Authentic pregame ratings, original selection denominator and contaminated G18 isolation |
| NBA | Freeze exact player-ID minute/usage + lineup scenarios, grade component props and covariance | Roster certainty, source-observed availability, real per-family calibration |
| MLB | Statcast/MLBAM starter/lineup/bullpen + inning/run-distribution freeze | Starter/lineup PIT capture, confirmed result settlement and variance |
| NHL | Integrate xG/goalie/TOI model as a separately gated scoring kernel; distinguish regulation vs overtime settlement | Confirmed goalie status, independent Poisson/overdispersion checks |
| PGA | Freeze DataGolf adapter only after permitted authorization (or use an approved public alternative); tournament/round joint-simulation and WD/dead-heat rules | Player/field/tee-time source rights, real time-stamped field, tournament-forward calibration |
| CLV / Gate D | Reuse merged #181/#184 capture-plan/receipt reconciliation and build authentic exact-line TAKE/CLOSE links | 200 settled comparable triples, no backfilled close assumptions |
| Safety / Gate E | Test the exact stricter-of-v2.1/v2.2 policy-version drift, source/lineup locks, across-sports exposure and card release veto | 100 real guard-clean cards and separately signed owner approval |

Each independent PR should contain its own fixtures, tests, source hashes, rollback/failure description, unchanged v5 digest and PAPER/0u assertion. Claim lanes first on Issue #57; one branch per disjoint code area, never simultaneously edit one shared file without handoff.

## Release precedence

1. Bind and lock a rules version (strictest-of-v2.1/v2.2 R1 is current); do not allow a user-supplied policy string to create a new executable sizing policy.
2. Independently collect original pregame quote and model/roster receipts **before** the event; archive rejections as well as successes.
3. Freeze each sport kernel; then register market-family/period-specific chronological calibration folds before their outcomes.
4. Join genuine same-identity TAKE/CLOSE and final settlements; do not substitute historical regenerated prices.
5. Require all Issue #10 A–E gates, a multi-day clean forward streak, independent verification and explicit owner signed promotion for each exact admitted market. Other sports remain PAPER.

The matrix only prevents pooled self-reported research tallies from being mistaken for per-market evidence. It is not a substitute for the external acceptance process.
