# CBB CollegeBasketballData prospective capture (free-tier key; no betting admissions)

A permissioned **prospective** source intake for game schedules/finals via documented CBBD HTTPS /games. NOT a retrospective pregame Torvik archive, an odds provider, or proof of +EV. Status: PAPER / 0u.

Official references checked November 15, 2026:
- https://api.collegebasketballdata.com/getting-started
- https://api.collegebasketballdata.com/api/games
- https://api.collegebasketballdata.com/data-availability
- https://collegebasketballdata.com/college-basketball-api

CBBD currently offers a free key (1,000 calls/month shared with football) at https://collegebasketballdata.com/key. The documented /games endpoint uses Authorization Bearer with season, startDateRange and endDateRange, returning up to 3,000 results. Game status: scheduled / in_progress / final / postponed / cancelled. Data can be corrected after publication. Prefer a daily UTC window, NOT an entire season, to avoid truncation. **No account/API key is currently connected.**

## Secure user setup

1. Request a free key on the official CBBD site. Keep it in an environment variable named CBBD_API_KEY or authenticated secrets manager. Never paste a key into ChatGPT, source code, public GitHub files, request URLs, screenshots or docs.
2. Prepare a private directory outside the PUBLIC Sportsedge checkout with access controls and durable storage.
3. From models/cbb, for a single UTC date in the 2026-27 ending-year-2027 season, run:

    python cbbd_prospective_capture.py capture --season 2027 --start-utc 2026-11-15T00:00:00Z --end-utc 2026-11-15T23:59:59Z --private-dir /private/sportsedge/cbb

The command returns only sanitized private output paths and digest. The original response bytes and a separate manifest are create-only, hashed, timestamped by the local capture process, and written outside GitHub. The destination is checked BEFORE the credentialed request, rejecting both lexical public-checkout paths and symlink-resolved paths; a private mode-0700 directory is required. Individual raw, manifest and final-report files are exclusive mode-0600 writes with fsync and rollback of partial individual files. The Bearer key is transmitted only in the HTTPS request header. No credential means NO NETWORK. Redirects, unexpected URL/content type, oversized body, duplicate JSON keys, wrong season and possible 3,000-game truncation are rejected. An interrupted pair write can leave an orphan; never overwrite or silently discard it.

4. Convert the original response OFFLINE using the exact returned filenames:

    python cbbd_prospective_capture.py finals --raw /private/sportsedge/cbb/EXACT.raw.json --manifest /private/sportsedge/cbb/EXACT.manifest.json --output /private/sportsedge/cbb/new_finals.json

The offline converter verifies original SHA-256 and row count and retains one result per original provider row. Only explicit final-status, full-game incl-OT scores with valid CBBD IDs are normalized. Every duplicate event ID is BLOCKED including the first copy. Incomplete, unknown, future or TBD games remain NOT_FINAL or BLOCKED, not zero.

## Crucial no-lookahead limitation

The documented /games schema does not advertise each game's original publication timestamp. The converter therefore assigns BOTH final.published_utc and final.captured_utc to the **first locally observed timestamp of THIS receipt**, a deliberately conservative upper bound. The row contains publication_basis=UPPER_BOUND_LOCAL_OBSERVATION_NOT_PROVIDER_PUBLICATION. It does NOT claim publisher-authenticated time. Fetching an old 2015 game today cannot make it available before a 2015 forecast.

The offline output is an intermediate source report, NOT automatically merged into the existing CBB walk-forward audit. Its integer provider game/team IDs become exact strings for a verified join; never join by fuzzy team names. Other providers' team IDs require an explicit independently checked crosswalk. No private raw game records, keys, bookmaker prices or historical predictions should be uploaded to public GitHub.

The verified pregame model baseline remains contingent on permissioned archived Torvik AdjO/AdjD/tempo snapshots, fitted HCA, league averages, genuine source clocks and team identity joins. toRvik archive morning-day labels do not certify an exact intraday publication clock; never invent one. Present-day Torvik ratings must NOT backfill earlier game prediction inputs.

## Still blocked

- Exact original historical provider observations prior to every prediction freeze.
- Independently verified draftkings / separate sportsbook full two-sided lines.
- Genuine postgame final receipts, original team and event identity crosswalks and long-range completeness.
- Preregistered untouched chronological score/probability calibration, no-vig market baseline comparisons and forward evaluation.

Issue #10 hard gates A-E, including 100 complete forward slates and 200 authentic matched settled selection triples, remain required before promotion. No staking, CLV or winning probability is certified by this script.

Synthetic-only test:

    cd models/cbb && python -m unittest -v test_cbbd_prospective_capture.py
