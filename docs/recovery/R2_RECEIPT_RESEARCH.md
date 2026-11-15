# Point-in-time receipt evidence recovery (R1 / R2; 2026-11-15)

Recovered candidate code from `SportsEdge_Receipt_Integration_R2_20261115.zip` on Drive: SHA-256 `ec42baad865be75f1abea063d687340ead8fb0ebd5b8c9f39f517ac53c718ea7`.

The **R2 byte-evidence gate** verifies raw saved JSON against its claimed SHA-256 and enforces matching quote ID, event, source timestamps, price, line and team. The **R1 gate** additionally validates chronology, team/player identity, projected point consistency and the frozen v5 SHA. These checks do **not** authenticate that a sportsbook actually published those odds or that the record truly existed before kickoff. No real wager or counted record is authorized.

To integrate the existing frozen v5 and research guard from PR #5, two source path references are adjusted (R1 runner import lookup and two test engine paths). The **model itself is unchanged**.

Fast offline synthetic suite (84 cases) from repository root:
```sh
cd research/receipt_integration_r2
PYTHONPATH=repair_r1:repair_r1/tests:repair_r2 python -m unittest discover -s repair_r1/tests -q
PYTHONPATH=repair_r1:repair_r1/tests:repair_r2 python -m unittest discover -s repair_r2/tests -q
```

Original full package also passed an 88-case release runner when the full historical ZIP was mounted locally. The extra four guarded-v5 tests depended on historical board data deliberately excluded from public GitHub.

The additional `research/audit_legacy_20261115`, `research/half_legacy_20261115`, and `research/props_candidates_20261115` directories are **archived research sources, not adopted production models**, and may need archived data to execute. Missing historical inputs must not be silently replaced with invented values. Existing models/risk rules/old cards are unchanged. Outputs remain **PAPER / 0u**.


## R2 CSV/JSON ambiguity hardening (Issue #10 follow-up)

The intake now rejects duplicate CSV header names (including case/whitespace variants), missing required columns, ragged rows, malformed UTF-8, and duplicate keys in captured quote JSON. It also refuses repeated `(book, quote_id)` pairs even when separate differently hashed receipt JSON files are presented. An invalid CSV returns a consistent blocked report with `official_counted=0` rather than a CLI report KeyError. Synthetic regression tests cover these controls.

These are **integrity safeguards only**. The JSON receipt still contains untrusted adapter claims about provider, source URL and observation time: checksums are not third-party signatures and cannot independently prove that DraftKings offered the price. This does not remove Issue #10's authenticated-odds, point-in-time, closing-line, calibration or end-to-end risk requirements. Existing frozen v5 pricing, engine hash and historical wagers remain untouched. PAPER / 0u.
