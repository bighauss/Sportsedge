# SportsEdge historical price-history → CLV reference bridge (PAPER / 0u)

This is an **offline, authorized-export adapter**, not a live connection, scraper, or undocumented API. It accepts properly normalized **two-sided** price-history observations from **BestBook.app**, **Action Network**, **Covers**, and **ScoresAndOdds**, plus separately captured original sportsbook quotes. The user/operator must obtain the records legitimately and preserve the exact original bytes/screenshots privately. A market chart, a summary closing spread, or a consensus line is **not** an authentic same-book, two-sided quote.

## Source priority

1. **BestBook.app**: inspect its refreshed *price history* and *full book pricing*. It is a useful display/reference, **not verified here as an API or authorized CSV export**. Preserve original page/authorized export and timestamps. Never invent endpoint paths, infer history from current best price, or confuse BestBook-reported DraftKings with an independent DK feed.
2. **Action Network**: historical/line movement and per-book observations if a lawful export exists. These are relayed sportsbook prices, not first-party receipts.
3. **ScoresAndOdds**: the site documents `Game Details → Line Movements`; use that for reference when exact book, lines, side, timestamps, and paired odds are present.
4. **Covers Sports Odds History**: useful season/closing spread/total *context*, especially NFL, but published historical closing consensus without original same-book matched exact odds/quote time **cannot** be used for exact DK CLV.

External provider policies and paywall terms control reuse. This code performs **no network requests** and uses no paid APIs. It does not silently blend multiple sportsbooks, consensus, alternate lines, different periods, or post-kickoff prices.

## Normalized source CSV

Create one PRIVATE CSV for originally captured **TAKE** quotes, and one or more PRIVATE CSVs of the actual history you are allowed to export/transcribe. Each row is one selection and its **same-time opposite selection** at the SAME bookmaker, market and line. Columns (exact names):

```text
source,source_url,sport,event_id,source_event_id,source_market_id,mapping_version,book,market_kind,period,settlement,selection_id,opposite_selection_id,line,opposite_line,player_id,team_id,stat,price_american,opposite_price_american,observed_at_utc,captured_at_utc,kickoff_utc
```

- `source`: `BESTBOOK`, `ACTION_NETWORK`, `COVERS`, `SCORES_AND_ODDS`, `DIRECT_BOOK`; `book` is the **upstream bookmaker**, e.g. `DraftKings` (not website name). No independent-source inference from another site's DK price.
- `source_url`: genuine HTTPS reference where price was observed. `source_event_id` and `source_market_id` remain exactly as shown, **no fabricated provider IDs**. `source_market_id` may be blank if absent; output remains unauthenticated research. `event_id` is independently reconciled SportsEdge ID; `mapping_version` records versioned crosswalk. No fuzzy team-name guessing.
- `selection_id` and `opposite_selection_id` are distinct canonical participants/sides; `line` and `opposite_line` retain exact signed handicaps (`+3.5` vs `-3.5`) or identical total/prop thresholds. ML and categorical lines are empty. Explicit period, settlement, player, team, stat prevent cross-market matches.
- `price_american` and `opposite_price_american` are **actual, same-book paired offers**. Do not fill missing opposite odds with consensus, another book, or an inferred price.
- `observed_at_utc` is a claimed **price observation** time; `captured_at_utc` is when **your archival evidence** was saved, potentially after kickoff for an imported history. They are distinct. A retroactive chart alone does not prove that price was available pregame.
- `kickoff_utc` is UTC start. Timestamps need explicit UTC timezone (`Z` or `+00:00`). TAKE must be **captured before** kickoff; HISTORY can be imported after but is flagged.

`OTHER` market kind is allowed as an exact identity reference only; do not infer settlement. All markets may be seen, but only rows with required matched evidence are numerically compared.

## Run

```sh
python ledger/historical_clv_bridge.py \
  --taken /private/sportsedge/taken_two_sided.csv \
  --history /private/sportsedge/bestbook_history.csv \
  --history /private/sportsedge/action_history.csv \
  --output /private/sportsedge/historical_clv_reference.json
python -m unittest discover -s ledger -p 'test_historical_clv_bridge.py' -v
```

All private CSVs and output must remain **outside the public repository**. Output is create-only, records SHA256 of normalized input CSV bytes and always reports `official_counted=0` and `approved_stake_u=0`.

For each actual TAKE, choose the **latest matching observed** two-sided quote strictly after TAKE and **within 10 minutes before kickoff**, with same sport/event/period/settlement/market/side/line/opposite-line/player/stat/book. First select quotes from the **same source as TAKE**, if any. A later quote from a different aggregator must not displace the same-source closing quote. If no same-source quote exists, compare the latest cross-source quote as **reference-only**. Do not cherry-pick an older same-source quote when its later same-source close is retrospective, conflicting or lacks provider-market evidence. Competing same-source quotes at the latest timestamp = `AMBIGUOUS_LAST_CLOSE`; missing exact close = `NO_EXACT_MATCHED_CLOSE` (never zero CLV). Valid pairs calculate `100 × (close no-vig probability − take no-vig probability)`; positive means market-implied probability rose for original selection. Saved source timestamps and mapping remain unverified.

Statuses: `SAME_SOURCE_STRUCTURAL_PAPER`, `CROSS_SOURCE_REFERENCE_ONLY`, `PROVIDER_MARKET_CROSSWALK_UNVERIFIED`, `RETROSPECTIVE_HISTORY_UNVERIFIED`, `CLOSE_ARCHIVED_BEFORE_TAKE`, `AMBIGUOUS_LAST_CLOSE`, `NO_EXACT_MATCHED_CLOSE`.

**Output v2 trust boundary:** `clv_probability_points` is populated **only** for `SAME_SOURCE_STRUCTURAL_PAPER`, requiring matching nonblank provider-market identifiers and a close archived after the TAKE but before kickoff. Cross-source, retroactive and unverified-identifier comparisons expose `reference_delta_probability_points` instead. Do not combine reference deltas with CLV in averages or success claims. `comparable_rows` counts only source-consistent paper CLV; `reference_only_rows` is reported separately, along with `status_counts` and unchanged TAKE denominator. All remain **PAPER/0u and externally unauthenticated**. Normalize moneyline `0`/blank, enforce HOME/AWAY for ML/spreads, OVER/UNDER for totals/props, and YES/NO for binary outcomes.

**Limitations**: This adapter is not a live BestBook integration or proof of any past quote, independent sportsbook source, official CLV, profitable EV, recorded wager or ROI. It does not write to frozen v5, modify private grading, or change gates. For authorized automated capture, secure a documented API/export agreement, original source quote timestamp, entitlement/provenance, then add separately tested provider-specific parser and forward collector. Never scrape hidden endpoints or upload credentials/odds to public GitHub.
