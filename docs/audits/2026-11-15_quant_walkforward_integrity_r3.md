# SportsEdge Quant Eightpack — release-aware walk-forward R3 integrity

**Scope:** Audit-only source, no historical record edits, no production engine v5
changes, no wagers, no model calibration claims. This isolated PR advances
Issue #80 and coordinates through Issue #57. Paper/0u remains compulsory.

## Reproduced baseline data-selection defect

The previous `quant_walkforward_baseline._parse` inserted each event/market/line
into `keys` on its first encounter, rejecting only later duplicates. If the
same game was submitted as both `W` and `L`, the order of CSV rows decided
which outcome became training history. In the supplied synthetic fixture,
reversing two conflicting rows changed the baseline Brier score from **0.347222**
to **0.336806**. These are intentionally fake records, **not real SportsEdge
performance numbers**.

There was also a cross-market pooling defect. The baseline grouped only by
sport, market, period, side, line, and player_id. Consequently, team totals for
two teams with the same points line, same-period outcomes from different books,
or moneylines using different settlement rules could enter the same empirical
training stratum. These are not necessarily the same target probability.

## R3 corrected contract

1. **All-copy duplicate quarantine, before scoring.** Identify each record by
   normalized `(sport, market, period, side, line, player, team, stat, book,
   settlement, event_id)` *without* the snapshot timestamp. All copies of a
   repeated decision are marked `DUPLICATE_EVENT_MARKET_ALL_COPIES_QUARANTINED`,
   even if they disagree on outcome, timestamp, price, or model version. No
   first/last preference. Missing/invalid raw rows remain in `invalid_rows`.
2. **Identity-complete strata.** Require `book` and `settlement` for every
   input; require explicit `team_id` for `TEAM_TOTAL`, `player_id` and `stat`
   for player props and binary scorer props. Canonicalize DK/DraftKings,
   standard numeric lines, and zero/blank ML; do not collapse different alt
   lines, teams, statistics, or books. This intentionally strengthens the prior
   CSV contract. Data without these details is **unusable, not backfilled**.
3. **Release chronology and truthful denominator.** Preserve the existing
   strict order `features_published <= forecast_asof < kickoff <
   final_published` and `fitted_until < forecast_asof`; only *prior published*
   unambiguous decided outcomes may train the Beta(1,1) baseline. Pushes never
   count as binary losses. An invalid or duplicate push stays rejected, not
   silently treated as another observation. Report `raw_rows`, rejected row
   indices/reasons, `duplicate_rows_quarantined`, `valid_decided_rows`,
   `push_rows_excluded_from_binary_scoring`, `insufficient_training_rows`, and
   matched model sample counts separately.
4. **Private original data and reports.** CLI rejects input/output inside
   public Git checkout (lexical and resolved), path aliases through symlinks,
   duplicate/missing CSV headers and oversized/malformed source files. It
   writes a create-only `0600` JSON report with the SHA256 of original CSV
   bytes, fsyncs it and rolls back a partially written report on an error.
   Original historical files are never rewritten. Run only from a controlled
   private admin environment.
5. **No automatic adoption.** A prequential naive smoothed win rate is a
   *baseline*, not the production model; caller-supplied timestamps and source
   tags cannot prove independent provider publication or pregame availability.

## Usage (operator-controlled, offline)

```bash
python research/audit/quant_walkforward_baseline.py \
  /private/sportsedge/frozen_released_binary_outcomes.csv \
  --min-prior 30 --report /private/sportsedge/walkforward_r3.json

python -m unittest discover -s research/audit -p 'test_quant_*.py' -v
```

Each CSV row must now contain at least:

```text
sport,event_id,market,period,side,book,settlement,game_start_utc,forecast_asof_utc,features_published_utc,fitted_until_utc,final_published_utc,model_sha256,result_source,outcome
```

`line` is required for numeric spreads/totals/props; `team_id` for team
market, `player_id` and `stat` for player/first-scorer props. `p_model` is
optional for baseline-only analysis. Valid binary outcomes are W/L; P is
explicitly excluded. `source_sha256` in the report is a **local file digest**,
not signed provider evidence. Do not populate missing columns retrospectively
from modern scores, team names, consensus odds or today's player roster.

## Acceptance and outstanding evidence

The local regression run contains **93 Quant tests**, **14 G-18 tests** and
**7 printed-card tests** = **114 synthetic tests** (original research suite
was 100). New cases reproduce conflict-order sensitivity, two-books/settlement
separation, team and player stat isolation, alt-line preservation, ML aliases,
invalid `p_model`, malformed headers, protected outputs and all-copy quarantine.
CI must pass on exact GitHub PR HEAD before merging.

This improvement cannot close the external gates: Nov 9 original 496 priced
selections + authoritative historical finals remain unavailable; original
Nov 11 full-precision probability and two-sided book quotes are still missing;
provider source publication clocks and correct roster IDs need independent
attestation; forward acceptance sample and independent contemporaneous
market baseline still need genuine data. No authentic wager or ROI is certified.
