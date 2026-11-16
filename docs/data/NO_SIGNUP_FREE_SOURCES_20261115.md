# SportsEdge free/no-signup source catalog — 2026-11-15 CT

Scope: NFL, CFB, CBB, NBA, MLB, NHL, PGA. Owner priority is genuinely free sites without creating an account, plus a research-only BestBook connection. **Publicly viewable does not mean licensed for automated mass collection or distribution.** No browseable comparison quote establishes verified DraftKings original pricing, market completeness, model calibration, CLV or approved betting. All markets PAPER / 0u; Gate A–E of issue #10 remain open.

## What is actually connected to BestBook in this PR

- Site: https://bestbook.app/ — publicly visible homepage displays a section titled "Best NFL odds this week" with best-book quote labels for full-game moneyline, spread and total; navigation also displays NFL, NHL, NBA and CBB plus Outliers and DFS. These homepage rows are **book-best comparisons**: one line may say "at DraftKings" and the next "at Novig." They are not a complete per-book DK board.
- Actual feature: sportsedge/odds/bestbook_public_reference.py reads a privately stored, permitted original homepage HTML/text file and writes a structured, private 0600, create-once JSON report. Its optional explicit one-shot homepage GET checks BestBook's robots.txt first, requires operator confirmation of reviewed source terms, follows no redirects, calls no hidden endpoints, sends no credentials and runs no background polling.
- Site terms/API status: **not verified**. No public permitted BestBook developer API, contracted data export, authenticated login transport, provider-native quote/market IDs or upstream quote publication UTC was established. If robots.txt is missing or refuses the homepage, automatic fetch must fail closed; use a legitimately saved user-supplied public page instead. This is NOT a live authenticated BestBook source.
- Parser scope: NFL public article, six displayed main-market sides per event where available, retaining displayed book, price, line, source page SHA and local read time. Malformed/missing/duplicate data is blocked and not silently repaired. Other sports, every player prop, period, team total, alternate and SGP remains NOT_CAPTURED in this public view, not NOT_OFFERED. Report: PAPER_0U_PUBLIC_PAGE_RESEARCH_ONLY, approved stake zero, source auth false, verified provider clocks false, Gate A/D false. No model weights or probabilities are changed.
- To make BestBook a genuine source-to-card feed, require written permission for data acquisition/storage, documented feed/schema and original authenticated book-by-book quote provenance with valid timestamps. Two book labels displayed by one aggregator do not prove independent source chains.

## Phone-friendly research or private terminal

Save the **original** public homepage HTML or visible page text lawfully in a private folder outside the repository, then process using the Python entry point. Do not share any website account password, cookie or personal token.

    mkdir -p /private/sportsedge-bestbook
    chmod 700 /private/sportsedge-bestbook
    chmod 600 /private/sportsedge-bestbook/bestbook_original.html
    python -m sportsedge.odds.bestbook_public_reference from-file /private/sportsedge-bestbook/bestbook_original.html --report /private/sportsedge-bestbook/bestbook_research_001.json
    python -m unittest sportsedge.odds.test_bestbook_public_reference -v

Optional **one-shot only** when the human operator has separately established permitted use/terms and robots allows crawling:

    python -m sportsedge.odds.bestbook_public_reference fetch-once --source-terms-reviewed --raw /private/sportsedge-bestbook/bestbook_original_002.html --report /private/sportsedge-bestbook/bestbook_research_002.json

The one-shot mode makes no claims of contractual permission and cannot authenticate any bookmaker; if policy/robots or the network fails, don't bypass them. Both raw and report are private create-only 0600; no auto-bet, cron job, unapproved API, session reuse, or public historical sportsbook receipts. Web access from this ChatGPT session does not install an always-on user-owned source runtime.

## Verified public research shortlist (no signup for the named free surface)

Access: WEB = public website surface; FILE = freely downloadable data; JSON = keyless publicly reachable JSON (may be unofficial and restricted for automation). Confirm each site's current terms and access before bulk storage, caching, commercial use or regular polling.

| Rank | Source | Access | Sport and use | Key limitations |
|---|---|---|---|---|
| 1 | [nflverse public releases](https://github.com/nflverse/nflverse-data/releases) | FILE | NFL play-by-play, roster, snap, weekly player inputs | Releases update **after** games; lag/availability proof needed for pregame backtests; already present in SportsEdge |
| 2 | [MoneyPuck downloads](https://www.moneypuck.com/data.htm) | FILE | NHL skaters, xG, shots, goalies and lines | Explicit noncommercial terms and attribution; site says non-approved scraping of other pages blocked |
| 3 | [Open-Meteo](https://open-meteo.com/) | JSON | NFL/CFB outdoor wind, MLB/PGA weather, forecast history | No key, 10k/day noncommercial limit, attribution; **archive actual forecast run**, not later historical weather |
| 4 | [Baseball Savant Statcast search](https://baseballsavant.mlb.com/statcast_search) | WEB + site CSV | MLB pitch, batter, pitcher, xwOBA, EV, K/HR quality | MLB terms and publication clocks; never use postgame data as pregame |
| 5 | [Hoop Explorer](https://hoop-explorer.com/) | WEB + visible export | CBB player, lineup WOWY, RAPM, usage, positional context | Public free site; API/export licensing and as-of history not confirmed |
| 6 | [Haslametrics](https://haslametrics.com/ratings.php) | WEB | CBB time-dependent efficiencies, shooting profiles | Displays source game-through dates; today’s page is not old PIT data |
| 7 | [Bart Torvik](https://barttorvik.com/) | WEB | CBB tempo and adjusted ratings; model comparison | Public pages; verify scraping/export rights and game-day inputs |
| 8 | [NFL.com stats](https://www.nfl.com/stats/) | WEB | NFL team/player box and official history checks | Public site not a licensed betting-data API |
| 9 | [PGA TOUR Stats](https://www.pgatour.com/stats/analytics) | WEB | PGA SG: total/approach/putting, driving, course ranking | Public page, as-of field/tee time and commercial rights unverified |
| 10 | [NHL stats](https://www.nhl.com/stats/) | WEB | NHL official skater, team and goalie history | Original goalie confirmation still required |
| 11 | [CollegeBasketballData free website CSV exporter](https://www.collegebasketballdata.com/college-basketball-api) | WEB + export | CBB game/team/box data | Website CSV requires **no key**, but the actual API **does require** free account/API key; 1,000 API calls/month across CFB/CBB |
| 12 | [TeamRankings CBB](https://www.teamrankings.com/ncb/) | WEB | CBB power numbers and forecast benchmark | Paid premium surfaces separate; cannot backfill today’s rating into past |
| 13 | [ESPN public sports pages](https://www.espn.com/) | WEB | NFL/CFB/CBB/NBA/MLB/NHL schedule, status, box and final | Unofficial no-key ESPN JSON endpoints exist but are undocumented, not an automatically permitted public API |
| 14 | [MLB Stats public endpoints](https://statsapi.mlb.com/api/v1/sports) | JSON (unofficial) | MLB event ID, start/status, teams, box | Keyless reachable; **MLB use/redistribution license still applies**, no blanket automation rights |
| 15 | [Baseball Reference](https://www.baseball-reference.com/) | WEB | MLB team/player seasons/boxes | Site automation limits and as-of safeguards |
| 16 | [Basketball Reference](https://www.basketball-reference.com/) | WEB | NBA players, historical box/roster | No original sportsbook price or verified early injury availability |
| 17 | [Pro Football Reference](https://www.pro-football-reference.com/) | WEB | NFL historical player/team baselines | Verify site restrictions before automation |
| 18 | [College Football Stats](https://www.cfbstats.com/) | WEB | CFB team/player season stats | Not original preseason or game-time weather/rosters |
| 19 | [Sports Reference CBB](https://www.sports-reference.com/cbb/) | WEB | College basketball game and roster history | Not independently time-frozen source |
| 20 | [Natural Stat Trick](https://www.naturalstattrick.com/) | WEB | NHL shots, xG context, situational splits | Rate/use policy unconfirmed |
| 21 | [Official World Golf Ranking](https://www.owgr.com/) | WEB | PGA field strength / golf ratings | Do not use updated later ranking for historical prediction |
| 22 | [NCAA Men's NET rankings](https://www.ncaa.com/rankings/basketball-men/d1/ncaa-mens-basketball-net-rankings) | WEB | CBB official ranking/strength reference | Published after games; source as-of required |
| 23 | [BestBook public homepage](https://bestbook.app/) | WEB | Market best-price sportsbook comparisons and research | **New public-page parser only**. Not authenticated DK book feed, no publication clock, not all markets |
| 24 | [The Odds Gap](https://theoddsgap.com/data) | WEB + FILE | Public odds/props + recent price snapshots | Operator advertises **last 7 days no signup**; expanded 45d access needs email. Terms/quote-origin unverified |
| 25 | [Betwatch public game/league pages](https://betwatch.io/) | WEB | Odds, movement, player-page odds, calculator | Operator says public pages no account; **full Live Board and full +EV require free account**; aggregator not independent DK origin |
| 26 | [Covers odds](https://www.covers.com/sport/football/nfl/odds) | WEB | NFL/CFB/NBA/CBB/MLB/NHL odds/consensus | Not a guaranteed book-original price receipt |
| 27 | [Scores and Odds](https://www.scoresandodds.com/) | WEB | Odds and game lines, consensus and movement | Public page/automated-use rights separate |
| 28 | [OddsPortal historical odds](https://www.oddsportal.com/results/) | WEB | Opening/closing odds by league | Displayed historical odds ≠ pre-recorded SportsEdge forecast |
| 29 | [OddsTrader](https://www.oddstrader.com/) | WEB | Public best odds and consensus | Browser comparator, not API |
| 30 | [Action Network](https://www.actionnetwork.com/) | WEB (free pages) | Odds and betting market reference | PRO paid; no anonymous authenticated feed |
| 31 | [BettingPros](https://www.bettingpros.com/) | WEB (free pages) | Public odds and player-prop reference | Some premium areas excluded |
| 32 | [OddsGuard](https://oddsguard.com/) | WEB / free app | Public odds comparisons, overlays | Vendor says free/no-registration; installing app is not a data API/license |
| 33 | [4C Odds](https://4codds.com/) | WEB (verify at use) | Broad free odds comparator | Third-party survey reports no-signup screen; terms/source rights not audited |
| 34 | [DRatings](https://www.dratings.com/) | WEB (free pages) | Model vs market projections | Third-party prediction never substitutes independent bookmaker line |
| 35 | [NWS US weather API](https://www.weather.gov/documentation/services-web-api) | JSON | NFL/CFB MLB outdoor wind and forecasts | Public/no key, needs descriptive User-Agent, verify rate/license terms |

### Excluded from *strict no signup*: free KEY or login necessary

- [CollegeBasketballData API](https://api.collegebasketballdata.com/getting-started): free API key via email and Bearer auth. Website export above is distinct.
- [CollegeFootballData API](https://collegefootballdata.com/): account/API key; browser pages may be public.
- [The Odds API](https://the-odds-api.com/): free monthly quota but registration/API key, insufficient every game/market.
- [DataGolf API](https://datagolf.com/api-access): key/entitlement, not a free no-key live PGA model feed.
- [PropSeason](https://www.propseason.com/): owner has account; logged-in tools are **not** a public developer feed. Research issue #214.
- Betwatch full authenticated Live Board: free login required even though basic site pages are publicly visible.

## How sources enter RUN IT

(1) **Public comparison**: record page and local observation clock, show supplementals/research only; unsupported or not captured families remain visible. (2) **Model feature**: need permitted file/API, stable player/game identity, original publication clock and frozen version before each game. (3) **Original DK + independent book**: need genuine authenticated book response, not two aggregator labels; exact event, price, line, period, selection, published UTC and receipt bytes. (4) **+EV and CLV admission**: only preregistered, calibrated forward models, real TAKE/CLOSE ledger, settlement and signed per-market acceptance after issue #10 A–E close. **No public research site grants official bets or positive-EV proof.**

No private keys, session cookies, bettor personal information or full private betting archives go in GitHub. Frozen v5 remains unchanged; strict selected policy 2u/event diagnostic but actual approved stake remains 0u.
