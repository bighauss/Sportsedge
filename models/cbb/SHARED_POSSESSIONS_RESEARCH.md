# CBB connected possession/period scenario research

**PAPER / 0u only.** Not an official card or independently backtested model.

The incumbent sportsedge_cbb_model.py already calculates projected possessions,
home points and away points. cbb_shared_possessions.py accepts those exact means
and REQUIRES independently recorded per-team 0-to-6-point possession scoring
probabilities, historical pace variability, half split, original source and model
SHA256 and a feature-frozen UTC timestamp BEFORE tipoff. No probabilities,
variances or player opportunities are filled with silent league-wide guesses.

The engine generates a single coherent two-half game event stream: each team's
points in a possession are sampled from its own explicitly supplied historical
distribution. The same scenarios produce first-half and regulation totals,
margins and team score research summaries. If source PMF expected scores
contradict existing projected team scores by >5% or 3 points, the engine blocks.

**Not implemented; explicitly blocked:** regulation-to-OT continuation,
official DK full-game results (which may include OT), player stats, first basket,
rebounds, assists, DFS and correlated SGP settlement. A real PBP-derived
possession scoring distribution and frozen player ID/minutes roster are needed.

The probabilities currently in test_cbb_shared_possessions.py are clearly
synthetic, never treated as genuine CBB performance or current prices. Run
python -m unittest test_cbb_shared_possessions.py from models/cbb; the test
also runs in GitHub Actions.

Next engineering lane: build a first-party possession outcome extractor from
public College Hoops Data/game PBP with capture UTC, model fit cutoff and exact
event/roster binding; compare to authentic held-out outcomes, add overtime
event simulation, and only then admit full-game markets and DK DFS.
