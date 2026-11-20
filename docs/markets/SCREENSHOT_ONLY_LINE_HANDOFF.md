# SportsEdge — Screenshot-only line handoff (RESEARCH, not wager release)

Owner target: SportsEdge should collect and freeze its own CBB/CFB/NFL projections **before** a lines screenshot arrives. The last step must only need a new photo or PDF of actual quoted lines, with no owner-supplied projections, player stat estimates, or manually typed bookmaker prices.

## What exists now

`sportsedge.markets.screenshot_line_handoff` accepts an already-frozen, **private** CBB/CFB/NFL full-slate JSON containing real `projection_ref` per ready game. It expects an exact-byte hash of the uploaded source screenshot and structured transcriptions of the quoted prices. Transcription may be done by the ChatGPT image reader when the owner provides screenshots; **the module does not OCR images itself**. The source image bytes must be archived privately for audit.

From the original image and transcribed numbers, the runner checks:
- exact scheduled event ID/sport and pregame time; no matching by approximate team/player names
- a pre-existing independent `projection_ref` (caller-supplied unverified `projection` objects are refused)
- screenshot original bytes and SHA256, observed/received UTC, no poststart or stale-over-300-second quotes
- each reported American price in its own row, true opposite side at the identical line/stat/player/period/settlement (spread sign inversion enforced)
- duplicate and missing offers appear as visible blocked rows; no automatically invented -110, prices, native sportsbook IDs or absent prop lines

For every exact pair, two separate mirrored research slate runs evaluate each possible bet direction. This prevents one actual screen quote from being presented as **two independent provider observations in one slate**. All internal quote keys explicitly begin `LOCAL_SCREEN_`; provider identity is `MANUAL_SCREENSHOT_UNVERIFIED`. Screenshots do not authenticate DraftKings API responses or provide a second original sportsbook. Every output stays **PAPER / 0u**, without an official card, regardless of a positive model/quote disagreement.

## Typed handoff schema (fictional test data, not live odds)

The screenshot-reader submits a private JSON object, like:

```json
{
  "schema": "sportsedge-screenshot-lines-v1",
  "captures": [
    {
      "image_path": "/private/screenshots/20261120_screen.png",
      "image_sha256": "sha256:<sha256-of-exact-image-bytes>",
      "observed_at_utc": "<actual observation UTC>",
      "received_at_utc": "<actual receipt UTC>",
      "source_surface": "DK_APP_SCREENSHOT",
      "offers": [
        {"market":{"sport":"NFL","event_id":"NFL-TEST","kind":"TOTAL","period":"FG","selection":"OVER","line":"42.5","team_id":"","player_id":"","stat":"","settlement":"REGULATION"},"odds_american":-110},
        {"market":{"sport":"NFL","event_id":"NFL-TEST","kind":"TOTAL","period":"FG","selection":"UNDER","line":"42.5","team_id":"","player_id":"","stat":"","settlement":"REGULATION"},"odds_american":-110}
      ]
    }
  ]
}
```

Replace these with the **actual** screenshot transcription, exact league event/player identity and image hash. Do **not** invent a price, observation time, identification or settlement rule. Use `BESTBOOK_DK_DISPLAY_SCREENSHOT` as the surface only if that's where the DK number was visible; it is not a second independently authenticated book.

Run from a private environment after the separate independent model workers have written a pregame complete-schedule slate with frozen source files:

```sh
python -m sportsedge.markets.screenshot_line_handoff \
  /private/frozen_20261120_slate.json \
  /private/screenshots/typed_capture.json \
  /private/new_research_report.json
```

The report includes `captured_offers`, `paired_markets`, `blocked_offers`, and two full-slate `orientations`; for each it retains every scheduled event, CBB/CFB/NFL five-family receipt matrix, all research rows, source and risk blocks, and 0u. It refuses overwriting an existing report.

## What the owner should actually need to send

**One fresh set of lines screenshots per targeted game/market.** ChatGPT can read visible values, transcribe actual prices, and identify potential errors. If the images do not show the opposite side, official settlement or player identity unambiguously, the corresponding market is blocked. This is *not* a promise that every picture alone can prove authentic source provenance.

## Readiness requirements before making any wagering claim

1. Automated genuinely pregame original independent team/roster/stat/injury/usage/schedule feature capture for CBB, CFB and NFL, with legal access, exact event/athlete IDs, timestamped immutable bytes and source manifests. This is **not** supplied by a screenshot or this adapter.
2. Autonomous daily private `projection_ref` and optional `player_features_ref` production *for every eligible game*, derived from source-frozen stats. Independently trained residual-score widths, per-player variance and joint relationships; non-supported props remain `NO_MODEL`.
3. Evidence of bookmaker original, exact same-line two-sided DK price and separate true independent book corroboration, not a screenshot or BestBook UI alone.
4. Preregistered walk-forward on untouched future games, calibration and CLV evaluation, full betting risk and issue #10 A–E release clearance. An engine passing synthetic tests has **not** passed a genuine model edge test.

Until all prerequisites are independently demonstrated, screenshots can produce **research-only, non-counted paper comparisons**, not validated wagers or stakes. The frozen v5 engine and history are unchanged. No owner action is needed to build missing research software; connected data access and empirical unseen-time outcomes cannot be manufactured by code alone.

Related: issues #341, #239, #10; PRs #340, #342, #343.
