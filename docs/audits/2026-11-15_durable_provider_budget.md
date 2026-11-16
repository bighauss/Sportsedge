# SportsEdge durable provider request-budget R1 (private research administration)

## Why

Prior `research/audit/quant_capture_preflight.py quota_decision()` accepted an in-memory list of prior request timestamps. That helps check a one-off source fetch but does **not** persist across fresh sessions, CLI processes, parallel hourly agents or failures. Consequently the same provider could be over-requested even if each individual agent respected a self-local hourly limit.

## Implementation

`research/audit/quant_provider_budget.py` is a **standard-library, offline SQLite reservation ledger**. It does not contact any provider, scrape an endpoint, read credentials, or alter frozen SportsEdge predictions. It requires a private parent directory outside the public repository, mode 0700; the database is 0600, forbids symlinks, and uses `BEGIN IMMEDIATE`, transactional unique provider/request IDs, full synchronous commits, separate rolling 1-hour and 24-hour request counts, and persistent 429 `Retry-After` backoff. It consumes quota **before** the caller issues a request. A crashed or failed request conservatively retains its budget cost; it is not silently refunded.

The source-provided cache age, provider timestamps and 429 response values are **caller assertions**. This code does not verify the provider identity or authenticate an HTTP response. It never grants permission to use a provider whose terms, token, identity, access scope or licensing has not been independently established.

## Example

```bash
mkdir -m 700 -p /private/sportsedge/provider_state
python research/audit/quant_provider_budget.py \
  --database /private/sportsedge/provider_state/budget.sqlite \
  --provider NFLVERSE --endpoint WEEKLY_STATS \
  --request-id request-20261115-123456-uuid \
  --max-hour 10 --max-day 50 --cache-age-seconds 900
```

Only the reply `ADMIN_REQUEST_RESERVED_PAPER_ONLY` with `allowed=true` indicates that quota was reserved. A separately authorized private admin collector must still decide if a call is lawful/available. `USE_EXISTING_PRIVATE_CACHE`, `PROVIDER_429_BACKOFF`, `HOURLY_REQUEST_BUDGET_EXHAUSTED`, `DAILY_REQUEST_BUDGET_EXHAUSTED`, `REQUEST_CLOCK_ROLLBACK_BLOCKED`, and `DUPLICATE_REQUEST_ID_BLOCKED` must prevent new calls. No dashboard source fetching and no auto-retry loops.

An administrator who *actually* receives an authenticated 429 can record its `Retry-After` as a conservatively held cooldown:

```bash
python research/audit/quant_provider_budget.py \
  --database /private/sportsedge/provider_state/budget.sqlite \
  --provider NFLVERSE --request-id request-20261115-123456-uuid \
  --record-429-seconds 600
```

The throttled state persists after restarts and cannot be shortened by a later shorter Retry-After. Backdated request timestamps and duplicate request IDs are refused. Keep this SQLite file outside public GitHub, archive it externally, and use trusted operator clocks. A local SQLite file is **not** a cryptographically signed, immutable request receipt.

## Verification and limitations

- `python -m unittest discover -s research/audit -p 'test_quant_provider_budget.py' -v` — **15** deterministic synthetic tests, including 15 concurrent simulated workers subject to a 3-request budget.
- Existing Quant suite: **64** tests, G18 14, printed CBB EV 7. Total local research suite: **100** tests.
- No live provider account is connected; no historical sportsbook quote is retrieved, no data retention rights are asserted, and no official wagers/CLV/ROI are validated.
- `approved_stake_u=0`, `official_counted=0`, and `source_authenticated=false` on every decision. Research **PAPER / 0u** until independent provider, odds and model validation gates pass.
