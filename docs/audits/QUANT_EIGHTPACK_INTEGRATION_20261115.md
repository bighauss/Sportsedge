# SportsEdge Quant Eightpack — read-only integration

**Scope:** NFL, CFB, CBB, NBA, MLB, NHL; all supplied market inventories, including unsupported ones. **State:** research-only `PAPER / 0u`. Frozen `engine/sportsedge_v5.py` and risk rules remain untouched. No API secrets, raw sportsbook captures, credentials, or private settlement files are committed.

## Concrete deliverables

- `research/audit/quant_foundation.py`: original-row-preserving CSV inspection, row-level corrections and unresolved issues, empirical lag-only prop baseline with supplied opportunity inputs, American odds/no-vig/push-aware EV, create-only flat-unit paper ledger.
- `research/audit/quant_evidence.py`: pregame frozen-prediction **replay**, qualifications census, per-market P/L and Brier/log loss, 5-point probability calibration, matched upstream no-vig baseline only when paired receipt fields supplied, Wilson intervals, deterministic **event-clustered** ROI intervals, original-odds drawdown, bias slices, paired frozen-feature ablation and all-inventory market refusal reason display.
- `research/audit/quant_capture_preflight.py`: offline create-only manifest of existing private input bytes; row-level pre-kickoff and identity checks, SHA256, source labeling; **never** asserts a hash authenticates a sportsbook. Includes in-memory quota/cache decision policy for admins, not a live network collector.
- `.github/workflows/quant-eightpack.yml`: no-network Python 3.11 CI for module compilation and 25 synthetic tests (checked locally before PR).
- Original architecture/variable hypothesis and source guide: `docs/audits/SPORTSEDGE_EIGHT_PROMPTS_README.md`.

## Usage with private files

```bash
# source files must be stored privately and include real PIT timestamps
python research/audit/quant_foundation.py audit /private/frozen_snapshot.csv \
  --report /private/data_quality.json --cleaned /private/normalized_copy.csv
python research/audit/quant_foundation.py ledger /private/qualified_final_ledger.csv \
  --report /private/ledger_audit.json
python research/audit/quant_evidence.py replay /private/qualified_final_ledger.csv \
  --report /private/walkforward_replay.json
python research/audit/quant_evidence.py bias /private/paired_projection_actuals.csv \
  --report /private/projection_bias.json
python research/audit/quant_evidence.py ablation /private/frozen_baseline_vs_candidate.csv \
  --report /private/feature_ablation.json
python research/audit/quant_evidence.py census /private/all_market_inventory.csv \
  --report /private/market_status.json
python research/audit/quant_capture_preflight.py /private/board_capture.csv \
  --asof-utc '2026-11-15T20:00:00Z' --provider 'source-label' \
  --manifest /private/create_only_capture_manifest.json

python -m unittest discover -s research/audit -p 'test_quant_*.py' -v
```

Every `--report`, `--cleaned` and `--manifest` is **create-only**. Do not run on public/private Drive files by pretending GitHub has those bytes. Preserve hashes and original source files. No live bettor execution or public refresh endpoints exist here.

## Important evidence distinctions

1. **Replay != genuine walk-forward retraining.** `quant_evidence.py replay` scores explicitly frozen predictions; it does not reconstruct historic pregame model versions or train on future-fold data. Other existing `sportsedge/markets/chronological_calibration.py` and PR #71 G2/G3 provide complementary chronological/market calibration research. They do not prove provider historical existence either.
2. **Statistically valid result != authenticated quote.** Digest syntax and row-level `result_source` only provide format checks. Raw provider bytes, quote origin, as-of publication evidence, actual offers and executed lines still need independent private verification before any market is promoted.
3. **No invented market coverage.** The market census only classifies offer inventory supplied by source; it never assumes all sports have offered or validated prop/period markets. A `PAPER_UNTIL_FORWARD_ACCEPTANCE` census outcome is not admitted/approved.
4. **No historical ROI claim.** The Nov 9 CBB G-18 grading defect and mirrored prices require clean-room replay, and two EV-vs-displayed-p discrepancies on the Nov 11 formatted CBB card need the original full precision model records. Do not use those snapshots to report an authenticated long-run profit. Itemized private capture and grades should stay private.
5. **Unimplemented by design:** live provider adapters and credentials, 429/backoff durable persistent scheduler, secure external signature/receipt authority, historical data release snapshots for every source, all-market fitted probability distributions, predictive calibration acceptance, SGP covariance, and automatic publication/approved staking. These are data-and-acceptance dependencies, not permission to fabricate inputs.

## Review gates and acceptance

- Tests may only establish deterministic *software arithmetic and fail-closed behavior*. Review exact CI head, unchanged v5 hash, source/license checks and file diffs before merge.
- Forward acceptance is a separate decision per sport/market on preregistered unseen data. Count **unique events**; grouped confidence intervals and minimum 30-event flags cannot replace preregistration.
- A fully live service requires privately configured provider permissions, durable rate-limit/circuit-breaker state, true PIT capture and adversarial preflight. No code here claims completion of these external gates.
