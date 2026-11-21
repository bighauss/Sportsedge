# NFL featured odds capture pilot — manual-only, encrypted, zero wagers

This workflow is a **research/PAPER 0u** data-collection pilot. It makes at most one provider odds request **per successful, separately claimed Central calendar date** through the manual GitHub Actions workflow. The request is for NFL h2h/spreads/totals from DraftKings and FanDuel using `ODDS_API_KEY`. It never emits official +EV bets, stakes or a full market board.

## Why manual-only?

The first draft of PR #393 had a daily `schedule` trigger and wrote its per-day attempt record to `runner.temp`, which GitHub discards between workflow runs. Re-runs could consume multiple credits in one day, and merging would have activated the schedule automatically. That configuration was **unsafe for a limited-budget pilot**. The workflow now uses **workflow_dispatch only**. Scheduled automation requires a separate reviewed opt-in change after a successful pilot.

## Required GitHub repository secrets

Open **Repository → Settings → Secrets and variables → Actions → Repository secrets**.

- `ODDS_API_KEY`: access to The Odds API (read-only selected market quote intake). No API call occurs if missing.
- `SPORTSEDGE_ARCHIVE_FERNET_KEY`: a **Fernet-format secret encryption key**, not an Odds API key. Must be valid and verified before paid capture. Never place it in a public repository, screenshot, issue, chat message or workflow log.

Generate a fresh Fernet key **on a trusted local machine** with the `cryptography` Python package (not inside public CI logs):

```sh
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Add the output directly as GitHub Actions secret `SPORTSEDGE_ARCHIVE_FERNET_KEY`. Keep a **secure private backup** of the encryption key: without it, old encrypted artifacts may become unreadable. Rotate only with an audited re-encryption or managed key-version process; do not silently overwrite keys needed to decrypt prior archives.

The existing secret *names* `ODDS_API_KEY_BACKUP`, `CFBD_API_KEY` and `API_SPORTS_KEY` may be referenced elsewhere in the repository but are **not used** by this pilot. Referencing an environment variable in code does not establish the secret is configured. GitHub's linked connector used for this review cannot enumerate repository secret names or values.

## First manual run

1. Merge the reviewed PR to `main`, leaving the workflow **manual-only**.
2. Navigate to **Actions → NFL daily featured-odds pilot (encrypted, PAPER) → Run workflow**, select `main`.
3. The job checks required secrets, installs/pins the encryption package, validates the Fernet format, and runs **offline** tests before any paid request. A missing/invalid key stops with `BLOCK_SOURCE_AUTH` or `BLOCK_ARCHIVE_ENCRYPTION` and **zero API credits spent**.
4. It queries GitHub Actions' **artifact metadata** for prior attempts and unresolved quota holds. Metadata-read failure, existing same-Central-date claim, or quota hold blocks the request.
5. It creates and uploads the `nfl-daily-odds-attempt-YYYY-MM-DD` artifact, then **re-reads it and checks the run ID**, before making one selected provider request.
6. It archives raw response and receipts **privately on the ephemeral runner**, encrypts each file with Fernet, and uploads **encrypted files only** for up to 90 days. It also retains a non-sensitive JSON index listing original SHA-256 hashes. It does not upload raw quotes or the encryption key in clear.
7. If the response reports unexpected or unverifiable API cost/remaining quota—or if capture fails after the request may have been billed—the job writes a non-sensitive `nfl-daily-odds-quota-hold` artifact. The next day's attempt fails closed until reviewed.

The provider billing headers are checked **after** the request. The 3-credit figure is an **expected/authorized threshold**, not a pre-authorization cap guaranteed by the provider. The theoretical 93-credit/31-date figure assumes one successful call per date and provider charging no more than 3 credits per call; it is **not an absolute enforced provider-billing maximum**. Owner review is required if headers disagree.

## Persistence and limitations

The day claim is stored as a GitHub Actions artifact, not only in `runner.temp`. This controls ordinary manual reruns and retry attempts within the artifact retention window, with workflow concurrency serialized. **A repo administrator can delete or expire artifacts**, circumventing the protection; do not manually delete claim/hold artifacts to retry without verifying billable history. No data are gathered on days when nobody manually dispatches the job.

Encrypted artifacts have 90-day retention (subject to repository limits); a dedicated durable external archive is still needed for long-term research. Source quote capture timestamps are not upstream DraftKings authentication. This workflow never bypasses SportsEdge's **PAPER / 0u** wager gate.

No CI or manual test should use an actual Odds API key; all unit tests inject a mock capture transport.
