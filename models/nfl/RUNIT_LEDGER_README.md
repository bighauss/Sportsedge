# NFL RUN IT complete-denominator ledger

`runit_ledger.py` wraps the frozen v3 RUN IT pricing (formulas, constants and the total-filter rounding reproduced; see the boundary note below) so that every attempted offer gets one ledger row before any filter.

- Each game produces 12 market directions. Each prop produces exactly one row. Input rows that are missing a field, duplicated, unsupported, or for a game not on the slate are kept as `rejected_input` with a reason.
- `filtered_contradicts_projection` rows keep their full-precision `model_p`, `raw_ev` and `blended_ev`.
- `qualifies` is the v3 card rule: raw EV between 2% and 25%, blended EV above 0, deduplicated by signal in blended-EV order. `on_image` / `display_rank` is the display subset: the top 20 by raw EV, with at most 3 props per game. That rule was reconstructed from the v3 card and matches it row for row (20/20).
- v3 labeled in-range rows with blended EV ≤ 0 as `deduped_same_signal`. The ledger labels them `nonpositive_blended_ev`.
- Malformed offers never abort the batch. Odds of 0, odds under 100 in absolute value, non-numeric, NaN or bool odds; empty or one-team `game` lists; unknown teams; invalid lines; bad projections; and any pricing exception each become a retained `rejected_input` row with a reason, and valid offers keep pricing.
- Total direction filter: by default (`legacy_note_rounding=True`) the ledger reproduces v3, which compared the one-decimal projection from `note`. A 44.54 projection against a 44.5 line filters **both** Over and Under. `legacy_note_rounding=False` compares at full precision and is a separate, versioned correction, not v3. On Week 11, both settings give identical statuses (the closest total is 0.22 from its line).
- Known v3 limitations are recorded on each prop row rather than fixed: `scaling=whole_game_total_ratio` and `vig_basis=assumed_one_sided_1.045`.

Frozen v3 is not modified. Private quotes and the Week 11 reconciliation live only in private Drive storage.
