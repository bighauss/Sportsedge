# Private original-receipt observability bridge

**PAPER / 0u, research-only.** This adapter takes one private JSONL record per attempted decision and checks locally preserved files for an original freeze, forecast, feature source, TAKE quote, and optional CLOSE and outcome. It exports normalized research rows for the existing local observability quality gate, plus a separate sanitized refusal report.

## Privacy and original sources

The runner requires absolute original paths outside the public repository, an owner-private 0700 containing directory and 0600 original files; symlinks and nonregular files are refused. Every original file's exact bytes must match its declared lowercase sha256 digest. Strict JSON decoding rejects duplicate keys, NaN/Infinity and exponent-overflow nonfinite values. The forecast must bind the original freeze digest and exact selected market and probability; locally normalized TAKE/CLOSE/outcome record content must agree with the selection, price, book and claimed source clock. The local original source file need not be a specific provider JSON shape.

These **locally normalized quote snapshots are NOT independently authenticated original DraftKings or other sportsbook responses**. They are operator-permitted research records with locally consistent hashes. Source publication time, quote origin, actual wager and model prediction time remain independently unverified.

## Input envelope

Each JSONL object has schema sportsedge-private-observability-attempt-v1, decision_id, state PAPER_0U, selection, model, source, take, freeze_sha256 and originals; close and outcome are optional. For an explicitly omitted or rejected offered market, state BLOCKED and nonempty block_reason retain that attempt without pretending the price was never offered.

Selection carries sport, event_id, period, market, side, line if needed, tipoff_utc, and subject_id for props. Model carries sha256, trained_until_utc, freeze_utc, probability, forecast_sha256. Source carries provider, sha256, data_through_utc, published_utc, captured_utc. TAKE carries book, sha256, price_american and captured_utc. CLOSE additionally carries exact selection identity and capture before kickoff. Outcome carries sha256, W/L/P result, settled_utc, observed_utc and captured_utc.

Originals contains exactly freeze, forecast, source, take plus close/outcome if present. Each maps to an object with path and sha256. The freeze file can be a separately produced prospective original. The forecast file must contain schema SPORTSEDGE_OBS_FORECAST_ROW_V1, selection, model_sha256, freeze_sha256, model_probability. Quote files must contain schema SPORTSEDGE_OBS_QUOTE_ROW_V1, selection, book, price_american, captured_utc. An outcome file uses schema SPORTSEDGE_OBS_OUTCOME_ROW_V1, selection, result, settled_utc. These are operator-normalized research snapshots, not invented provider API contracts.

## Private execution

Run the Python module integrations.observability.private_source_bridge with three flags: --attempts /private/.../attempts.jsonl --normalized /private/.../quality-input.jsonl --report /private/.../bridge-report.json. Then run integrations/observability/quality_gate.py with --input pointing to the normalized JSONL and --out to a new private report. Outputs are create-only mode 0600, fsynced. Use a private authorized runner, not public GitHub Actions for actual original receipts.

Every attempt produces one downstream row. Missing, late, tampered, blocked and conflicting entries become blocked placeholder rows, not silently deleted. Duplicated canonical selections and duplicated decision IDs quarantine **all copies**. Valid distinct alternate lines remain separate. A missing close stays unmatched. A missing or mismatched outcome is never converted into a zero or a win. The local refusal report contains per-attempt input index, digest, and reason, but no event/player/book name.

Even on a clean local report, source_original_book_authenticated, provider_publication_clock_authenticated, genuine_clv_certified, forward_validated and official are false; approved_stake_u is zero. The existing quality-gate same-book same-side implied-price movement is descriptive, **not no-vig certified CLV**. This bridge alone does not prove a genuine as-of forecast, complete offered book inventory, or independently available odds. Actual provider permissions, primary DK and independent other-book responses, and prospective captured outcome/close evidence are still needed for Issue #10 Gates A–E.

## Synthetic tests

Run: python -m unittest integrations.observability.test_private_source_bridge -v

Tests cover tampering, duplicates, full failed-attempt denominator, original event/quote mismatch, source lookahead, missing close/final, nonfinite JSON, private create-only output and strict privacy. They never use real bookmaker credentials or odds.
