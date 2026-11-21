# Torvik exact-byte full-team candidate capture — research only

**No model adoption.** This addresses the authentic-byte blocker in draft CBB [PR #384](https://github.com/bighauss/Sportsedge/pull/384). The 102-team published slate snapshot is insufficient to establish league-wide constants; a full D-I source with proper custody is needed.

The standalone standard-library script fetches `https://barttorvik.com/2027_team_results.csv` over HTTPS **without any web summarizer**. It saves the exact byte response unchanged, SHA-256, local acquisition UTC, raw size, team count, sample mean offense/defense efficiency and tempo. It refuses 403/404, HTML instead of CSV, duplicate teams, missing or nonnumeric ratings, partial datasets and implausible statistical ranges. Never substitutes another source if the raw endpoint fails.

```bash
python research/audit/torvik_exact_raw_capture.py \
  --url https://barttorvik.com/2027_team_results.csv \
  --out-dir /private/torvik_full_source_2026-11-21_NEW
```

The output directory must not exist. `original_response.csv` preserves **original HTTP response bytes** (the script does not rewrite CSV); `capture_receipt.json` contains its SHA-256, capture timestamp, team count, arithmetic mean values and explicit booleans `season_census_verified=false`, `source_publication_verified=false`, `official_projection_parameters_adopted=false`. Timestamps are stamped in the process on acquisition, not taken from an operator argument.

The parser requires roughly 350–420 unique teams, but this count is only a **candidate completeness preflight**. It is NOT an authoritative membership census, a provider publication timestamp, a 2026 historical pregame archive, a validated Torvik schema, or proof of the correct model scale. The raw source file, even captured successfully today, cannot establish what Torvik showed on earlier dates. The 2027 in URL refers to the 2026–27 college basketball season.

**Some environments reject automated Torvik downloads with HTTP 403.** This script must then fail. The current chat cannot directly certify an exact Torvik original file through a 403 or a read-only summarizer, and does not claim to have captured one. Only a successful network run against the original endpoint with byte preservation can create that evidence.

After a successful candidate capture, a separate reviewer must:
1. Check the 2026–27 D-I roster census and names, verify all 360+ members, and compare endpoint header/units against independent published descriptions.
2. Preserve the original snapshot with independently verifiable timestamp/custody (local clock and SHA alone do not attest provider publication).
3. Run PR #384's league calculation on those exact bytes after canonical CSV parsing; compare mean efficiency and tempo to proposed 107.0 / 69.0, not just the 102-team slate.
4. Re-run the 51-game replay with proper as-of ratings and venue flags, and forward-grade on unseen scores with equal market comparator denominator. Four factors and games played remain incomplete.
5. Approve only a separate versioned model adoption after calibration; frozen v5 and historical forecasts stay unchanged.

**Offline synthetic regression tests:**

```bash
python -m unittest discover -s research/audit -p test_torvik_exact_raw_capture.py -v
```

The tests use 360 entirely fake teams and simulate HTTP 403 to confirm the tool refuses instead of inventing a dataset. The existing CBB CI test runner invokes them on this draft branch (no workflow file writes needed). Public repo contains scripts/tests only—not user-specific betting records or raw copied copyrighted source datasets.
