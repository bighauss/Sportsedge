# CBB Feast Week venue evidence — November 23, 2026

**Research only, PAPER / 0u.** No game, market, bet or model promotion. This branch is an independent source-linked venue comparison, not a production change.

## Exact inputs and scope

- 32 unique Monday November 23 games extracted from the owner's nine DraftKings screenshot PDFs around 05:41–05:44 Central. The paired spreadsheet is an *unauthenticated operator screenshot capture*, not a real-time book API receipt.
- Owner-side extracted game-board CSV SHA-256: `3f65656f764ead36395c87f07410c49725b52eea17b356fc6cfd0d7ee38dc124`.
- Original main screenshot PDF SHA-256: `0b1daac2648f9545ffe14662856c8d7ac5a37d6b4de2e4746922d0c4fdd59301`.
- Compared to Claude fallback `research/cbb_web_fallback/run.py` on `claude/cbb-web-fallback`, Git blob `7de0edb47e4751583f401bd1cf770d0f52205aad`.
- Machine-readable mapping: [`cbb_feast_week_venue_2026_11_23.json`](cbb_feast_week_venue_2026_11_23.json). Each game has an explicit event/source link, nominal venue and source grade. Public pages are **not independently authenticated point-in-time originals**.

## Results

| Census | Number |
|---|---:|
| Captured Monday matchups | 32 |
| Public schedule identifies neutral | 19 |
| Public schedule identifies campus home | 13 |
| Present in Claude fallback `G` | 30 |
| Absent from Claude fallback `G` | 2 |
| Incorrect +3-point fallback HCA on Monday neutral games | 13 |

The omitted Monday games are **Temple vs UT Martin** and **Utah Valley vs Stephen F. Austin**, both part of Paradise Jam. On the same Claude branch a *Tuesday* game, Oregon vs St. John's, was erroneously treated as home despite neutral-site Players Era scheduling; it is outside this 32-game Monday registry.

### Research-only fixed-venue sensitivity

The calculation below is a manual independent JavaScript transcription of Claude's published formulas and captured model input constants, not execution of the GitHub Python module. The calculation changes venue flags, then refits the *same-board* margin scale, with odds/rating inputs held constant. Since the model uses the same DK market board to fit its margin scale `k` and total offset, **its blended “EV” is circular and is not a validated edge**.

| Market side | Old blended paper EV | Conditional corrected-venue paper EV |
|---|---:|---:|
| Southern Utah +7.5 -112 | +16.4% | +5.1% |
| Belmont -3.5 -102 | +16.6% | +4.7% |
| East Carolina -3.5 -106 | +11.8% | -0.2% |
| Tulsa/Oregon State Over 154.5 -105 | +14.5% | +14.5% |
| Georgia Southern/NKU Under 166.5 -110 | +14.3% | +14.3% |
| Akron/Wright State Under 147.5 -105 | +9.7% | +9.7% |
| Washington/BYU Under 165.5 -110 | +9.3% | +9.3% |
| Northern Iowa/Davidson Over 142.5 -105 | +8.0% | +8.0% |

Under the captured `run.py` model, the same-board fit `k` changes `1.1971683054820195 → 1.207546269592647`. Total offset remains `+0.640749862734169`. In this particular model adding/subtracting HCA to home/away scores cancels out of the total; **that does not validate total scoring or its uncalibrated total SD**.

## Regression checks

`python -m unittest research/audit/test_cbb_feast_week_venue_2026_11_23.py -v`

Seven stdlib test methods check cardinalities, coverage and IDs, source/venue fail-closed behavior, neutral-vs-campus census, eight-card classifications and symmetric HCA conservation.

**Execution status:** Tests were *authored* and committed on the research branch; seven independent structural checks of the actual fetched JSON passed in the ChatGPT JavaScript tool runtime. Python unittest/CI has **not** been run against the exact branch because a compatible authenticated checkout/runner was not available in this session. Do not claim the seven Python cases passed.

## Remaining release blockers

1. Merge no changes until Claude's branch uses an eligible, timestamped, full-event venue registry and resolves missing games.
2. Reject “only Maui neutral” and any heuristic that guesses neutral status from the listed home team. The “home” column is a sportsbook orientation, not proof of home court.
3. Stop pricing based on in-sample DK market-fit parameters as if the model found independent edges.
4. Gather provenance-verified pregame ratings, game/team crosswalks, injuries/player IDs, season-specific walk-forward calibration, and correct settlement/OT handling before official EV claims.
5. Resolve player minutes and usage, two-sided quotes or an independently defended one-sided hold model, and historical uncertainty before any prop promotions.
6. Preserve exact screenshot times, source hashes, original bookmaker quote pairs, and blocked market denominator.

**Ownership:** ChatGPT writes this branch only; Claude and Perplexity retain their separate research branches. Nothing in this branch modifies `main`, `models/cbb`, running production workflows, bets or ledgers. Coordination is centralized at [SportsEdge issue #57](https://github.com/bighauss/Sportsedge/issues/57).
