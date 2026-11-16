# NFL point-in-time same-line market benchmark evaluator (R1)

**PAPER / 0u.** This is a diagnostic on claimed archived records, not a validated betting edge or CLV engine. Use actual pregame prices and frozen model probabilities; do NOT invent missing lines, reconstruct original quotes from final closing lines, or treat a local SHA as original provider authentication.

## Purpose

- Evaluate every original *candidate* row, including losers and pushes, at the **original price**.
- Form no-vig **conditional-on-nonpush** market win probability from **two opposite-side American prices for the same event, exact market, line, period and bookmaker**. The caller must supply both sides from one verified provider snapshot; the code cannot independently prove that they are correctly paired.
- Compare model conditional probability `p_win / (p_win+p_loss)` to same-line no-vig `q_taken/(q_taken+q_opposite)`; report Brier score and log loss **excluding pushes**, which are still graded and counted in original-odds hypothetical ROI.
- Report paired Brier gain `market Brier - model Brier`. **Positive means model beats the market baseline on that observed set, not proof of profit.**
- Bootstrap the paired Brier difference **clustered by game**, rather than counting markets from the same NFL game as independent. Confidence interval is only shown when at least **30 distinct games** have nonpush outcomes.
- Preserve invalid/late/stale/duplicate rows in a reason-coded rejection inventory. **Quarantine all copies** of a repeated same-book/period/market/line/selection/decision, including contradictory versions, not just the second copy. Report their original row numbers and exclude them from hypothetical ROI and calibration regardless of input order. Enforce both provider-observed and local-captured quote ages at the decision, default ≤300 seconds pregame. Neither timestamp is independently authenticated here.
- Detect exact push from the signed **home** spread, game/individual team total, or an explicit **two-way NFL moneyline tie-push rule**. No three-way ML, period or prop pricing is inferred.
- Display NO CAPTURE for missing families rather than inferring not offered.

## Input

One JSON array of records, one per candidate outcome/line/book/time. Each record has exactly these fields:

```text
sport,game_id,home_id,away_id,market,selection,book,period,
provider_event_id,provider_market_id,provider_outcome_id,
provider_opposite_outcome_id,quote_receipt_id,
home_spread_or_total_line,american_taken,american_opposite,
model_p_win,model_p_push,model_p_loss,
model_sha256,model_forecast_sha256,provider_quote_sha256,
kickoff_utc,model_features_observed_utc,model_asof_utc,
quote_observed_utc,quote_captured_utc,decision_utc,
final_utc,result_available_utc,final_home,final_away,tie_settlement
```

Period is explicitly `FG` only. Provider event, market, taken-outcome, opposite-outcome and quote receipt IDs are required, nonempty and the two provider outcome IDs must be distinct. These are caller assertions until independently matched to original provider records. No 1H/1Q/prop result can enter this scorer under an FG label.

Markets: `MONEYLINE_2WAY`, `SPREAD`, `TOTAL`, `HOME_TEAM_TOTAL`, `AWAY_TEAM_TOTAL`. Moneyline uses `selection=HOME|AWAY`, `line=null` and `tie_settlement=TIE_PUSH`. Signed home spread uses `selection=HOME|AWAY` and `tie_settlement=PUSH_ON_EXACT_LINE`. Totals use `selection=OVER|UNDER`, positive posted line and `tie_settlement=PUSH_ON_EXACT_LINE`. Only original American odds integers with absolute magnitude ≥100 are valid (except -100). All SHA256 fields are `sha256:` plus 64 lowercase hex chars; hashes **alone are not independent provenance**. Scores are actual nonnegative integer finals, and official result availability must follow final.

The model/quote input chronology is:

```text
model_features_observed <= model_asof <= decision < kickoff
quote_observed <= quote_captured <= decision < kickoff
kickoff < final <= result_available
```

The source and provider quote must have been captured **before the recorded decision**. Existing forward historical captures are required; do not backdate.

## Run

```sh
python models/nfl/market_benchmark_pit.py \
  --rows /private/verified_asof_nfl_candidates.json \
  --out /private/nfl_market_benchmark_paper.json \
  --freshness-seconds 300

python -m unittest discover -s models/nfl -p 'test_market_benchmark_pit.py' -v
```

The output includes original input hash, every rejected source row+reason, each accepted diagnostic row, outcomes, hypothetical 1u-per-row ROI and net units, market-only/no-vig conditional Brier and log-loss, and clustered 95% bootstrap interval. Its `approved_stake_u` and `official_counted` are always zero.

**Private evidence protection:** Original candidate JSON and result paths are rejected if their lexical or symlink-resolved paths fall inside the public checkout. Raw JSON rejects duplicated keys at any nesting level and nonfinite `NaN`/`Infinity` literals (never last-key-wins). Output is exclusive-create (`0600`), fsynced before success, and deleted if the newly-created file fails writing or syncing; original source bytes are not modified. These structural controls are not publisher attestations or proof of genuine pregame prices.

### Key limitations

- **Hypothetical one-unit per row is not a wagering portfolio.** Correlated alternate spreads and both sides of a market can inflate the denominator; evaluate unique selections and correlated exposure separately before any bankroll inference.
- Independent source authentication, exact upstream outcome IDs, complete two-sided contemporaneous quotes, official period/settlement rules and original provider transport cannot be established with self-reported fields. All live admission gates remain closed.
- The model-vs-market comparison does not establish true CLV. Matched independently timed TAKE/CLOSE triples require a separate workflow.
- These probabilities must be generated by a frozen, previously calibrated model and assessed on unseen games. Do not select thresholds or coefficients from these evaluation results.
- Bootstrap CI only describes sample variability; it is not a multiplicity-corrected proof of a positive edge. See Issue #10 A–E for real market promotion.
