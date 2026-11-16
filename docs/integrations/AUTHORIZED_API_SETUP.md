# Authorized provider API setup — research only

Manual workflow: **Authorized API secret presence preflight (no network)**.

GitHub Actions repository secrets (never commit values):
- `CFBD_API_KEY` — CollegeFootballData primary
- `CFBD_API_KEY_BACKUP` — optional second credential for same provider, **not independent evidence**
- `ODDS_API_KEY` — odds provider credential, exact provider/plan to be verified
- `ODDS_API_KEY_BACKUP` — optional second credential; do not assume a distinct upstream feed
- `API_SPORTS_KEY` — API-Sports credential

The workflow only checks whether names are populated. It does **not** transmit credentials, query an endpoint, test auth, validate account plan/quotas, authenticate book-original bytes, or close any gate. The second odds key's provider is not yet confirmed. Never log raw secrets, Authorization headers, URLs containing credentials, or raw private responses.

Before adding a live adapter, confirm **each provider's exact hostname, documented endpoint, allowed use, secret header name, plan, sport/market coverage, response timestamps and original book provenance**. Build isolated, opt-in private tests with response sanitization and failure-closed identity/chronology checks. A provider's displayed DraftKings line and another aggregator's displayed DK line are not independent original bookmaker sources.

No modification to frozen v5 or risk policy. No live wagers. All markets remain PAPER / 0u and Gates A–E OPEN until independently verified evidence and approval.
