# Private prop evidence readiness — no historical backfilling

**Status: RESEARCH / PAPER 0u / NOT A VALIDATED +EV OR JOINT MODEL.**

This read-only command audits the *structure* of original private odds/screenshot
capture CSVs. It prints aggregate counts, never player names, original odds rows
or private source bytes. It never edits an input file, a production model, the
frozen SportsEdge v5 engine or a prior grade.

```bash
python -m research.audit.prop_evidence_readiness /private/captured_nfl_props.csv
python -m unittest discover -s research/audit -p 'test_quant_prop_evidence_readiness.py' -v
```

The original Nov 15 screenshot-based NFL ledger
`2026-11-15_1510CT_CLAUDE_NFL_grading_ledger_596rows.csv` was **read directly
from the owner's private Drive by the owner audit on Nov 21** and was NOT added to
GitHub. Its 596 rows break down into 60 game markets, 200 statistical
`player_prop_xplus` threshold offers, 112 anytime touchdown, 112 first
touchdown and 112 two-plus touchdowns. **536 are player-related**. All 536
`player_id` values are empty; all 596 `grade` and `actual` values are
empty. No `p_model` / frozen model probability or stable provider event ID is
present. Screenshot SHA-256 fields are not independently authenticated original
DraftKings upstream receipts.

Consequently this particular file provides **zero verified joint-stat samples**.
An earlier description of "about 200 props" counted only statistical threshold
markets and overlooked the other 336 touchdown-market rows.

## Future genuine pregame + postgame evidence requirements

Keep the original offer **and its associated authenticated provider receipt**
privately archived and tamper-evident. A real player-prop joint row needs:

1. Stable sport, event ID, kickoff UTC, team ID, *player ID*, market, period,
   side, exact rung/line, book, original price and provider time.
2. Provider receipt ID, original response bytes hash, observation and capture
   UTC, independently authenticated source identity. A screenshot filename or
   its hash is only user-declared evidence.
3. Independent frozen pregame model probability at the **same exact rung**,
   model SHA-256, feature-source SHA-256, feature publication UTC, model
   calculation/decision UTC. `ANCHOR` or bookmaker-implied model outputs are
   explicitly not independent forecasts.
4. Immutable before-kickoff population ledger including unoffered,
   rejected, missing and one-sided rows; don't filter after knowing results.
5. After each official final: event/player/team/stat key, original official
   stat source/receipt, actual stat and W/L/P settlement, postgame settlement
   observation UTC. Missing actual is **ungraded**, never a zero or loss.

Do not create a historical model probability, source clock, verified player ID,
original quote, or grade retroactively. In this verifier, even a record whose
self-declared fields are all complete stays **structurally complete but
UNVERIFIED**; `prop_rows_provider_authenticated=0` and
`prop_rows_eligible_for_verified_joint_metrics=0` by design. This script
cannot authenticate providers itself.

Only after independent source verification and preregistered held-out validation
should the separate `research/audit/prop_joint_correlation.py` candidate
be considered for joint-hit frequencies, observed covariance vs independence,
paired Brier and event-cluster uncertainty. That separate PR is itself still
under review. No official picks or stakes are authorized by this census.
