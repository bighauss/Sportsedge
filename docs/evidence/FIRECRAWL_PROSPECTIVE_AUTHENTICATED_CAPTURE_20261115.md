# Firecrawl-to-GitHub prospective NFL injury capture

**Release state: PAPER / 0u.** This is a gated, on-demand source-research pipeline, not a certified injury model or sportsbook integration. The ChatGPT Firecrawl OAuth connection does not automatically authorize GitHub Actions. This implementation uses a separately issued Firecrawl API key and an independently generated archive-encryption key. Neither is embedded in the repository. The workflow deliberately fails before network activity until both are configured.

## One-time phone setup

1. Sign into the Firecrawl account you choose for GitHub Actions and generate an API key under its API keys dashboard. Do not post a key into chat, issues, PRs, workflow inputs, files or public URLs. Check usage and billing first: the ESPN provider was advertised as **5 credits per execution** when discovered.
2. Generate a separate **Fernet encryption key**, 32 random bytes URL-safe base64-encoded, in a private trusted environment. Python users can run the standard cryptography Fernet.generate_key() operation and store the result directly into a password manager. Never generate or print keys in a public Actions log. **Retain a separate backup**: losing this key renders archives unreadable.
3. In bighauss/Sportsedge on GitHub open **Settings → Secrets and variables → Actions → New repository secret**. Add the account-issued API key as **SPORTSEDGE_FIRECRAWL_API_KEY**, and the independent encryption key as **SPORTSEDGE_ARCHIVE_FERNET_KEY**. Use Secrets, not ordinary repository Variables.
4. Open **Actions → Firecrawl ESPN prospective encrypted research capture → Run workflow**, select main, then supply an independently verified NFL team code, verified canonical event ID, and verified kickoff time in full UTC, such as YYYY-MM-DDTHH:MM:SSZ. The pipeline itself cannot validate the game schedule.
5. Only if both secrets exist and the capture succeeds, Actions saves a downloadable artifact, firecrawl-espn-private-pit-RUN-ATTEMPT, containing only an authenticated encrypted original Firecrawl response plus sanitized private report (.fernet) and minimal public status JSON.

**This repository is public.** GitHub Actions artifacts are readable by anyone with repository read access. The archive is encrypted; never upload original source JSON or secrets in plaintext. GitHub public-repo artifacts expire in up to **90 days**, so the owner must copy the encrypted archive to long-term private storage before expiry and preserve the encryption key separately.

## Implementation and security behavior

The workflow is manually dispatched only. It does not trigger for pull requests or unattended hourly/scheduled tasks; it requires main and both secrets before an optional billed call. It runs offline model source-guard tests before network access.

The transport uses HTTPS POST https://api.firecrawl.dev/v2/scrape with an Alexandria request for provider espn-com, capability sports-data/injuries, and options sport=football, league=nfl, team=the verified NFL team code. The Firecrawl v2 SDK also documents calling scrape with alexandria. The request sends a unique x-request-id and is bounded to one 10 MB HTTP response. Errors and timeouts fail without retrying uncertain, possibly billable requests.

The preexisting Firecrawl injury intake checks the expected provider and capability, actual response, workflow digest, team and player ID consistency, duplicate/ambiguous JSON, publication/observation/actual-capture order, and the provided event start. Active and healthy rows are NOT injured player designations, and empty, stale or unknown rows must remain blocked. Complete model-feature admission and original provider publication authentication are **not** established.

The original HTTP bytes and redacted source report are packaged and encrypted with Fernet (AES + authenticated HMAC), round-trip verified, and stored only in the encrypted artifact. Runner scratch is deleted even when a step fails. Ciphertext cannot independently certify original publication time or event/player truth. All model feature, CLV, odds coverage, betting release and gate flags remain false; official count 0 and approved stake 0u.

## Running synthetic tests

Run Python unittest modules sportsedge.validation.test_firecrawl_espn_injury_intake and sportsedge.validation.test_firecrawl_espn_forward_archive after installing the pinned cryptography package. The seven-sport freeze-contract CI also runs the adversarial source and transport tests automatically. Synthetic green checks validate code but NOT the actual provider account, evidence provenance, matchup identity, historical PIT source coverage, genuine EV, or official stakes.

## Remaining live acceptance evidence

- An operator-configured, independently authorized Firecrawl API key and a separate Fernet encryption key must actually be set in GitHub secrets. ChatGPT cannot access or transfer its OAuth token to GitHub.
- A first genuine prospective workflow dispatch must run before a verified game, preserve original received source bytes encrypted with matching hashes, and be independently reconciled against actual published source timing, rosters, and official NFL game/practice designations.
- Historical injury statuses must not be retrospectively used as if they were available earlier. A healthy team cannot be inferred from an empty provider response.
- This is **research-only** and does not close sportsbook or other SportsEdge A–E gates. Until other market-specific evidence gates clear, all official bets remain blocked at PAPER / 0u.
