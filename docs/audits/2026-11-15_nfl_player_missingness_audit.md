# Player-week holdout missingness audit — 2026-11-15

The newly merged NFL nflverse / Next Gen Stats retrospective player-stat replay distinguishes candidate, graded and ungraded rows. However, its `missing_actual_stat` counter was never incremented. A real current-week player/team row with a blank or nonnumeric stat was incorrectly classified as `not_observed_in_holdout`, the label reserved for genuinely absent player-week records.

**Fix:** When the player-week row exists but the requested stat has no usable value, increment `missing_actual_stat`; when the player-week row itself is absent, increment `not_observed_in_holdout`. Both continue to be **ungraded**, not filled as losses, wins or zeroes. Exact observed zero is still a legitimate graded value. Add a hard invariant `conditional_roster_candidates = graded + missing_actual_stat + not_observed_in_holdout`, rejecting silently incomplete research denominators.

Three synthetic regressions check missing stat rows, true zeroes and a combined missing-stat/absent-player case. Existing real asset publisher hashes and the frozen v5 engine are unchanged. This is a measurement correction, not a new conditional player distribution, a point-in-time roster forecast, an executable odds path, a bet, or evidence of positive EV. Always PAPER / 0u.

The historical study's 2,258 candidate count, 1,819 graded outcomes and 439 ungraded records remain the last independently observed output. This repair should not be described as having been replayed against real assets until its new exact-head real-source CI job finishes.
