# SportsEdge RUN IT operator runbook

This is one offline command for the existing SportsEdge research engines. It
accepts a prepared slate or transcribed lines and writes a private report. It
does not fetch odds, OCR a screenshot, prove source authenticity, send bets,
or approve stakes. A successful run means a report was written, not that
SportsEdge found a bet.

## Prepare and run

Run from the repository root with Python 3.12. Use a private directory outside
the checkout that only the operator can write. Keep input files, original
quotes and images, credentials, and the report out of GitHub and CI logs.

```sh
# Prepared slate: expected event schedule, pregame models, and source quotes.
python -m sportsedge.markets.run_it_operator \
  /private/slate.json /private/run-report.json

# Screenshot lane: already frozen and unpriced, plus transcriptions.
python -m sportsedge.markets.run_it_operator \
  /private/frozen-slate.json /private/screen-report.json \
  --screenshots /private/transcribed-screenshots.json
```

- **Prepared slate:** Follow the [full-slate schema](FIVE_SPORT_FULL_SLATE_RESEARCH.md).
  Put every in-scope scheduled event in `expected_events`, including events
  missing a model or price. Submit exact receipts for the selected side and
  the required counterpart; do not turn a public listing into a provider
  receipt. Supported research families vary by sport and model. PGA and NHL
  are schedule/coverage only in this lane.
- **Screenshot transcription:** Follow the
  [screenshot format](SCREENSHOT_ONLY_LINE_HANDOFF.md). Preserve and hash the
  original image, use actual observation/receipt times, and transcribe both
  sides of the exact same market from the same image. Supply an existing
  `projection_ref` per modeled event and empty `markets` lists. Do not include
  nonempty `projection_evidence` overlays: those are matched to specific
  quotes and are not portable across the two screenshot passes. This lane
  supports **CBB, CFB, and NFL only**. Captures older than 300 seconds at the
  decision time are rejected. A legible line is not an authenticated book
  receipt, and one side never licenses guessing the other.
- **Decision time:** Omit `--replay-at` for a current run. For offline
  reproduction, pass the recorded explicit UTC decision time with
  `--replay-at YYYY-MM-DDTHH:MM:SSZ`. Reports and stdout label that run
  `EXPLICIT_REPLAY`; never use it to make an expired quote look current.
  Reproduction requires the same software, JSON, referenced source bytes,
  and model settings. The report's JSON file hashes identify the input bytes;
  a matching hash does not authenticate who generated them.

## Review and report

- **`PAPER_RESEARCH_AVAILABLE`:** At least one submitted side passed the
  existing research pricer. This count is not a count of recommendations,
  positive edges, or markets independently offered. In screenshot mode, one
  pair can produce two side estimates; the schedule is counted once. Use
  `research.paired_markets` for unique screenshot pairs and inspect both
  orientations for the pricing results.
- **`NEEDS_LINES_OR_REVIEW`:** No sides priced. Use `next_actions`, event
  reasons and family statuses, and screenshot `blocked_offers` where
  applicable. The declared schedule remains visible even if no price was
  submitted. An invalid event model can block the event before individual
  market grades are available. A missing line is not evidence it did not
  exist.
- **`RUN_IT_REJECTED` (exit 2):** No new report was written. Use the safe
  reason and next action on stderr. Inputs must be bounded UTF-8 JSON objects
  with unique keys and finite numbers. A report path must be new; existing
  reports are never overwritten. Exit 0 means a private report was written,
  even if every event was blocked.

For either successful state, summarize scheduled coverage and any missing or
blocked market families before the research numbers. The report always has
`final_bets=null`, `official_counted=0`, and `approved_stake_u=0`. The
[release requirements](../../RISK_POLICY.md) and
[Issue #10](https://github.com/bighauss/Sportsedge/issues/10) still apply.
No provider or sports model is promoted by this wrapper.

## Handoff prompt for Claude or ChatGPT

> When I say **RUN IT**, use the requested sports, events and date (Central
> time), and attempt the full market inventory, not just main game lines.
> Use only authorized sources. Freeze independent model inputs before
> comparison with prices. Preserve the exact market, period, player/team,
> line, both offered prices, and collection time. If I supply screenshots,
> transcribe only what is visible and retain the original bytes and
> the matching existing pregame freeze. Run the local SportsEdge command
> documented here if the files, tool access and permissions are available.
> Otherwise say what is missing; do not claim to have run it. Report
> schedule/market coverage and blockers first. If no official release is
> possible, say `No official bets. PAPER / 0u.` Do not guess missing odds,
> fill in hidden markets, or promote paper estimates.

The prompt is not a hosted integration. An agent needs access to the checkout
and private files to run it. Automated quote acquisition and delivery are
separate work from this command.

## Verification

```sh
python -m unittest -q \
  sportsedge.markets.test_run_it_operator \
  sportsedge.markets.test_screenshot_line_handoff \
  sportsedge.markets.test_slate_orchestrator
```

These are synthetic software checks. Run them on the exact proposed GitHub
head before merge; the existing CI allowlist does not yet name the new
operator suite.
