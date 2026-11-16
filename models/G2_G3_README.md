# G2/G3 audit and historical markdown converter

Research only: never modifies model weights, picks, official stakes or production cards.

Run from the models directory:

    python -m unittest test_audit_disagreement_calibration test_ledger_grades_to_audit_csv
    python ledger_grades_to_audit_csv.py ../ledger/grades_2026-11-15.md --output /private/grades_intake.csv
    python audit_disagreement_calibration.py /private/grades_intake.csv

The converter is intentionally **fail-closed**. The markdown grade ledger has
odds, text picks and some asserted results but does **not** contain the original
immutable pregame model probabilities, independently sourced market probabilities,
snapshot capture times, kickoff/final timestamps, verified match/player keys or
sportsbook quote hashes. Every output row retains NOT_CAPTURED in those fields and
**will be rejected by the statistical audit**. Inferred, likely, pending or
ungraded outcomes also stay UNVERIFIED. The ledger markdown hash is not a provider
quote hash. A generated CSV is NOT a validated backtest or CLV record.

Fill missing fields only from actual archived pregame raw source bytes and exact
point-in-time model artifacts; do not reconstruct them from final scores or today's
code. Use an authenticated provider/second independent source for market fair odds,
not a de-vig from the same DK bet sides. Verify player/event mappings and original
odds, then rerun the audit without changing historical decisions.

Audited rows are grouped by market, direction and absolute model-market gap.
A 10.0000 pp difference enters 10-20pp (rounded to four decimal places).
Results include model/market Brier and log loss, flat 1u hypothetical ROI at the
captured American odds, Wilson 95% observed hit-rate intervals, and n<30 warnings.
These diagnostics are not evidence of a profitable tradable edge without independent
closing prices, execution and walk-forward out-of-sample testing.
