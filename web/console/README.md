# SportsEdge Research Console V1 — static, mobile-first, fail-closed

**Purpose:** Owner-approved, read-only, front-end view of *public/sanitized* SportsEdge market-inventory statuses and source gaps. No bookmaker login, external data request, credential handling, probability calculation, betting execution, +EV claim, source authentication or independent release gate promotion is implemented.

## Open it

Open `index.html` from this folder in a desktop browser, or host this *static folder* on any HTTPS static site. No `npm install`, API keys, account, server, build pipeline, fonts or tracking needed. The UI uses relative paths so it can be hosted in any subdirectory. On a phone, use a static host or GitHub Pages **only after you explicitly authorize publishing**, and never publish private snapshots.

- **Overview**: 7-sport inventory counters, unconditionally blocked A–E Truth Gates, exception feed and 0u stake.
- **Market inventory**: filter by sport, explicit status and free-text; ALL counted rows retained. Up to 1,200 rows are rendered at once for performance, with the full filtered total disclosed.
- **Source evidence**: status-only registry; no status is independently verified.
- **AI toolkit**: links for the 7 design and 12 AI tools (Google’s former NotebookLM is now Gemini Notebook) shared in chat; links launch their sites only. These are not installed, paid, authenticated or endorsed source feeds.
- **Explore sample data**: entirely fictional event labels and 7-sport research blockers; never live games or price recommendations.
- **Import local snapshot**: browser file picker reads JSON **locally in memory** and never uploads/stores it. `Clear loaded data` removes all references; the page does not use localStorage or cookies.

## Contract: `sportsedge-public-research-v1`

Use a **sanitized status export**, not actual sportsbook feed JSON, internal customer identity, personal records, price quotes, API keys or raw evidence hashes.

```json
{
  "schema_version": "sportsedge-public-research-v1",
  "generated_at_utc": "2026-11-15T10:00:00Z",
  "synthetic": false,
  "markets": [
    {
      "sport": "CBB",
      "event_id": "public-event-id",
      "event_label": "Away @ Home",
      "event_start_utc": "2026-11-17T01:00:00Z",
      "family": "Team total",
      "state": "NO_PROVENANCE",
      "reason": "Source offer not independently authenticated"
    }
  ],
  "sources": [
    {
      "name": "DraftKings",
      "state": "NOT_CONNECTED",
      "note": "No provider-native source proof is connected to this dashboard"
    }
  ]
}
```

Supported sports: NFL, CFB, CBB, NBA, MLB, NHL, PGA. Market status must be one of `NOT_OFFERED`, `NOT_CAPTURED`, `NO_MODEL`, `NO_PROVENANCE`, `NO_INPUTS`, `STALE`, `UNSUPPORTED`, `LIVE_OR_CLOSED`, `BLOCKED`, `RESEARCH_ONLY`, `UNVERIFIED`. Source status must be one of `NOT_CONNECTED`, `UNVERIFIED`, `RESEARCH_ONLY`, `BLOCKED`. Unknown status, invalid field, malformed timestamp or disallowed sensitive fields block the **entire** import; no quiet row discard. Maximum JSON file 2 MB, maximum 6,000 market inventory rows, 100 sources.

The imported label `synthetic=false` means only that *the user provided that label*. It does **not** authenticate source origin. The UI hardcodes `approved_stake_u=0`, `official_count=0`, `independent_verification=false` and all Truth Gates **NOT CLEARED**. Do not modify those release boundaries merely to display a card.

No API URLs or credential input controls exist. A public site must not expose private source receipts, token-bearing URLs, raw original quote archives or model input bytes. External tool links open in separate tabs without sharing snapshot information.

## Tests

```bash
node --check web/console/core.js
node --check web/console/app.js
node --test web/console/test-core.js
```

Run from the repository root. Tests are offline and require only Node.js 20+; dedicated GitHub Actions workflow is included. The existing `moonshot/` app, legacy scoreboard, frozen `engine/sportsedge_v5.py`, original pregame odds, model predictions, quantitative audit code and risk controls remain unchanged.

## Integration roadmap (not yet implemented)

1. Add a **private, read-only, allowlist-only** backend exporter that reads the current market census/failure ledger, outputs solely the documented status fields, and validates every row before release.
2. Only after approved source licensing and private capture validation, attach the actual admin collector behind authenticated server-side APIs. Do not put DK, BestBook, Oxylabs, CBBD or any provider API key in the frontend.
3. Maintain an independently reviewable frozen Gate A–E release decision before ever displaying official recommendations; a frontend file import is not that decision.
4. Treat Roku separately: Roku BrightScript components cannot directly execute this HTML/JS interface; reuse visual style and information architecture, not React/DOM code.

This tool is a **visualization** of reported *ineligibility*, not a wagering service, provider bridge or certified model.

## Single-file offline edition (especially useful on a phone)

```bash
python web/console/build_standalone.py --out /private/SportsEdge_Research_Console_Standalone.html
```

The generated `.html` bundles **all CSS and JS** so no companion assets are needed. The separate version uses an inline-only CSP, keeps `connect-src 'none'` and still cannot fetch live odds or make official decisions. It does not embed any imported JSON, source credentials or historical data. Host privately or open from a local file viewer; depending on mobile OS, a standard Safari/Chrome tab may be required for scripts to run. The generator uses create-only output, never overwriting a prior copy.
