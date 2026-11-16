# Scenario specification lineage — research-only

SportsEdge generates simulated score/player-outcome paths from *two independent
components*: a pregame team projection (means/model/feature hashes) and an
UNVALIDATED scenario distribution (`sd_margin`, `sd_total`, period shares,
dispersion model hash, fit cutoff), plus optional separate player moments,
roster membership, simulation count, seed and the exact generator code.

Before this change, RUN IT only displayed the team projection's model/feature
hashes. Two different variance or seed settings could change win/push/loss
probabilities and unverified EV while appearing to have identical model
lineage. That risks undetected parameter drift in research and backtests.

## New contract

`sportsedge/markets/projection_distribution.py` computes a deterministic
SHA-256 of a canonical JSON specification containing:
- Exact SHA of the scenario-generator source code and a named generator version.
- Sport/event/teams, projected means, model hash, input feature hash, freeze.
- **Separate** dispersion model hash, training cutoff, all widths and period
  splits. The distribution model may be *different* from the score model.
- Every confirmed roster ID, sorted for order invariance.
- Every player-stat moment in the **original draw order**, including raw feature
  hash, active/lineup claims, mean, SD, usage/volume and source freeze.
- Scenario count and pseudorandom seed.

The actual wall-clock *execution time* is excluded from the specification:
same source code and frozen input parameters/seed/count reproduce the same
scenario hash and draws, regardless of when the evaluation is rerun.

The generated `SimulationBatch` carries
`scenario_spec_sha256` and `scenario_generator_version`. Both values are
also included in the RUN IT event report and every submitted market row; when
a paper `edge_signal` exists, the same fingerprint is attached to it. A
caller-created legacy synthetic batch lacking a complete source specification
remains `null` (never a forged generator fingerprint). Partial or malformed
lineage metadata is rejected.

**The fingerprint is NOT proof of actual source bytes, authentic sportsbook
prices, historical publication, probability calibration or a valid betting
edge.** It's merely a reproducibility checksum. The original quote/raw source
and complete model/feature evidence still belong in the private source store.
Never expose secret tokens or licensed raw odds on public GitHub.

## Adversarial tests

`python -m unittest -v sportsedge.markets.test_scenario_lineage`

The suite checks that changing dispersion widths, period shares, seed,
scenario count, projection means, dispersion model identity, player means and
player draw order changes the fingerprint; unchanged inputs produce identical
hashes and sampled outcomes. It also verifies that RUN IT carries the hash
while preserving `official_counted=0`, `approved_stake_u=0` and blocking
uncertified wagers.

The main engine `engine/sportsedge_v5.py`, risk policy, historical results,
manual original captures, grading and stakes are not modified. Per-market
A–E gates remain OPEN, and trained realistic event distributions remain
required before any output could be called a genuine +EV selection.

See `docs/markets/PROJECTION_TO_EDGE_DISCOVERY.md` and issue #239.
