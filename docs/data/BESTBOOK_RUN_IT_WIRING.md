# RUN IT — BestBook supplemental public-odds research integration

Status: added as a **supplemental** research source in the canonical seven-sport slate runner, November 15, 2026 (Central). This does not authenticate a sportsbook, close Issue #10 or authorize a wager.

## Exact command

Run from repository root using a private Python environment and privately stored, lawfully collected original BestBook homepage HTML/text:

    python -m sportsedge.markets.slate_orchestrator /private/sportsedge/slate.json /private/sportsedge/run_it_result.json --bestbook-page /private/sportsedge/bestbook_public_original.html --bestbook-event-map /private/sportsedge/bestbook_event_ids.json

All source files must be 0600 in owner-only 0700 directories outside public Git. The resulting file is new/create-only 0600. Keep sportsbook quotes, player data, any site sessions, and historical full boards out of public GitHub.

The only reference data automatically accepted by this mode is a permitted local copy of BestBook's publicly visible "Best NFL odds this week" article. The article offers best-price cross-book labels for moneyline, spread and full-game totals; the "at DraftKings" displayed label is not an original authenticated DK quote. The code does not modify the live pricing inputs, model projections or risk decisions.

## Mandatory manual exact-identity map

This map is private JSON, with exact scheduled SportsEdge event IDs, the literal public article game label, and two displayed team abbreviations. Example contains SYNTHETIC event ID and is not a live board:

    {
      "schema": "sportsedge-bestbook-slate-identity-map-v1",
      "events": [
        {
          "sport": "NFL",
          "event_id": "EXAMPLE_EXISTING_NFL_GAME_ID",
          "public_event_label": "Buffalo Bills at New York Jets odds",
          "away_selection": "BUF",
          "home_selection": "NYJ"
        }
      ]
    }

The event_id must already exist in the actual private scheduled slate. No fuzzy matching, generated event IDs or cross-sport reuse. Repeated/mismatched event maps block import. Manual mapping has not been independently verified by provider-native event IDs and must not be used to promote bets.

## Display in RUN IT results

For every scheduled event, the result now contains a separate bestbook_public_research section. The market-family matrix remains complete across the seven sport schemas, even if the public homepage only shows three NFL full-game markets. It reports explicit statuses including NOT_CAPTURED_IN_PUBLIC_BESTBOOK_VIEW, SPORT_NOT_PRESENT_ON_PUBLIC_BESTBOOK_HOMEPAGE, NO_EXACT_PUBLIC_EVENT_IDENTITY_MAPPING, MAPPED_LABEL_NOT_ON_PUBLIC_HOMEPAGE, PUBLIC_REFERENCE_STALE_GT_300S and PUBLIC_REFERENCE_POST_START_OR_LIVE.

Where the manually mapped NFL game has an EXACT same-market, side, line and full-game period as an existing SportsEdge research candidate, a supplemental candidate_comparisons entry provides the displayed book label, American price and original public page SHA. It is never a DK PriceReceipt, model probability, EV selection, official TAKE, CLV match or a wager.

No input to the canonical SportsEdge market pricer, v2.1/v2.2 strict 2u-event diagnostic ceiling, frozen v5 model or card release gate changes. All rows and the full result have approved_stake_u=0 and official_counted=0. The market's unobserved or missing odds families stay visible; missing is NOT the same as confirmed NOT_OFFERED.

## Obtaining public snapshots

Existing isolated BestBook importer supports an original user-supplied page or one explicit public homepage GET. The latter first checks robots.txt, refuses redirects, requires confirmation that the operator has reviewed site terms and retains the untouched original page bytes privately. Do not run unattended polling without real provider permission.

    python -m sportsedge.odds.bestbook_public_reference fetch-once --source-terms-reviewed --raw /private/sportsedge/bestbook_public_original.html --report /private/sportsedge/bestbook_public_research_archive.json

Do not set the source-terms-reviewed flag without a real provider policy review. The user's approval of work authorizes this engineering project, but it does not establish the website's automated-access terms or authenticity of the original sportsbooks. If robots is inaccessible or blocked, the fetch fails closed. Never guess API URLs, scrape accounts, reuse browser cookies, bypass restrictions or claim site data is an independently authenticated DK source.

A future genuine full-market connector requires documented BestBook API/export data rights and exact upstream source response, market IDs, timestamps, book lineage and separate original DK/independent sportsbook receipts. The free/no-signup research sources listed in NO_SIGNUP_FREE_SOURCES_20261115.md are candidates only, NOT 35 automatically connected live feeds. NHL, MLB, PGA, CBB and NBA props/alternates still require their own approved source adapters and game-time evidence.

## Verification

    python -m unittest sportsedge.markets.test_bestbook_slate_overlay -v
    python -m unittest sportsedge.markets.test_slate_orchestrator -v
    python -m unittest sportsedge.odds.test_bestbook_public_reference -v

Synthetic tests check exact candidate line matching, stale/after-start quarantine, duplicate mapping denial, unauthenticated source marking, owner-private file permissions, and preservation of existing event/research prices and risk outputs. The PR does not run against a genuine authenticated BestBook account or real sportsbook originals, and it does not close Gate A through E.
