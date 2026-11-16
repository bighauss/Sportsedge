# SportsEdge independent original-top-20 forensic evidence gate

**November 16, 2026 · source-only audit · PAPER / 0u.** This is a follow-on to the independently documented November 9 and November 11 top-20 model-edge audit. It is **not** a modification of SportsEdge v5, its weights, saved historical projections, original win/loss records, risk policy, bet issuance or official card. It does **not** use outcomes to rank predictions or fit a calibration parameter.

## Why this guard exists

The forensic audit recovered *pregame-saved* cards with 20 large EV claims across three event clusters, but each row was MODEL-DOUBTED. Seven Washington TT-under rows (and Rice TT-over) need independently corrected outcome views. The original Nov 9 496-row `picks.csv` and original finals file remain unrecovered; G-18's 70 reversed retrospective labels are **not** a verified recreation of those original bytes. The existing audit report ranks research claims but has not verified book-original quote publication clocks, team/period IDs, model feature vintage, or executed wagers. An unflagged arithmetic formula is not an authentic edge.

This new program processes **all original pregame claim rows**, including malformed, stale, enormous, duplicate and suspicious ones. It ranks by the **stored, original `saved_claimed_ev`**, not a corrected postgame model. It keeps **every** input row and a second independent final-score overlay. It never drops the top claims for being suspicious, because doing so would hide precisely the failures an auditor needs to see. It also counts distinct game clusters separately from individual alternate lines; several Rice +points offers remain separate market rows, not independent trial outcomes.

## Private source inputs only

The first JSON source is a claim census supplied by an operator from actual retained pregame forecast files. Structure:

```json
{
  "schema": "sportsedge-original-claim-census-v1",
  "rows": [{
    "sport": "CBB",
    "event_id": "EXAMPLE_EVENT_A",
    "home_team_id": "HOME",
    "away_team_id": "AWAY",
    "event_start_utc": "2026-11-17T02:00:00Z",
    "period": "FG",
    "market": "TEAM_TOTAL",
    "side": "UNDER",
    "line": "85.5",
    "team_id": "HOME",
    "player_id": "",
    "price_american": 100,
    "p_model": 0.6,
    "saved_claimed_ev": 0.2,
    "historical_grade": "L",
    "book": "EXAMPLE_BOOK",
    "provider_market_id": "EXAMPLE_MARKET_ID",
    "provider_event_id": "EXAMPLE_PROVIDER_EVENT_ID",
    "upstream_book_id": "EXAMPLE_BOOK",
    "source_transport_id": "EXAMPLE_TRANSPORT",
    "model_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "model_input_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "original_quote_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "model_frozen_utc": "2026-11-17T00:00:00Z",
    "quote_captured_utc": "2026-11-17T01:51:00Z",
    "quote_published_utc": "2026-11-17T01:50:00Z",
    "selected_utc": "2026-11-17T01:55:00Z",
    "model_features_published_utc": "2026-11-16T23:00:00Z",
    "model_features_available_utc": "2026-11-16T23:01:00Z",
    "fitted_until_utc": "2026-11-16T22:00:00Z"
  }]
}
```

The above is **synthetic** and illustrates field shape, not a legitimate source receipt. Numeric `saved_claimed_ev` is **EV per dollar** (0.2 = +20%), not a percentage point. Do not silently convert historical displayed percentages except under a clearly separately documented extraction with original text preserved.

The second source is a **separate** original final-score collection; never put updated outcomes into the pregame forecast file:

```json
{
  "schema": "sportsedge-independent-final-overlay-v1",
  "rows": [{
    "sport": "CBB", "event_id": "EXAMPLE_EVENT_A",
    "home_team_id": "HOME", "away_team_id": "AWAY",
    "event_start_utc": "2026-11-17T02:00:00Z",
    "home_score": 80, "away_score": 60,
    "home_1h": 40, "away_1h": 30,
    "settled_utc": "2026-11-17T04:30:00Z",
    "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }]
}
```

Do **not** assign example IDs, venue, bookmaker, quote clock, player ID or source SHA to actual games; supply originals or let the audit show `MISSING_*`. Local SHA256 and self-reported UTC cannot independently authenticate external bookmaker or settlement feeds. The processor always marks third-party authentication `UNVERIFIED` and official stakes `0u` regardless of hash completeness.

## Audit command

Run from repository root with both complete original sources in a secure owner-only private **0700** folder, each original JSON **0600**, not in the Git checkout. Output must not exist and is created exclusively 0600 with flush/fsync. Never upload the results or original books to public GitHub:

```bash
python research/audit/top20_original_evidence_gate.py \
  /private/sportsedge/pregame_claims_original.json \
  /private/sportsedge/final_score_originals.json \
  --private-report /private/sportsedge/top20_forensic_report_CREATE_ONLY.json \
  --top 20
python -m unittest discover -s research/audit -p 'test_top20_original_evidence_gate.py' -v
```

## Tests enforced, with explicit limitations

1. **PIT:** frozen model, original feature availability and source publication, fitting cutoff, original book published/observed/captured, decision time and kickoff ordering. Default `QUOTE_STALE_AT_DECISION` is 300 seconds measured from price capture to **selection** (not capture-to-kickoff), a source freshness diagnostic only; this is *not* proof of provider publication.
2. **Identity:** exact sport/game/period/market/team selection and player ID requirements. Distinct teams' team totals remain distinct. Exact duplicate selection/line copies, even across books, are all flagged; alternate lines remain separate offer rows and one event cluster.
3. **Market consistency:** reported binary EV independently recalculated from American odds and *saved* p, with separate raw implied probability (no no-vig misuse). Historical printed p/EV rounding tolerance 1.5 percentage points is a diagnostic window, not a fitted calibration. First-half ML and integer-line pushes are never treated as unconditional binary EV without original `p_win_unconditional` and `p_loss_unconditional` masses.
4. **Model disagreement:** optional saved model home margin, model total and team total are compared with paired **original** main book anchors. Fixed ≥6-point disagreement threshold was already documented in the historical guard; no new optimized threshold is learned from outcomes. No paired source -> no fabricated discrepancy. Do not infer a model weight change.
5. **Independent corrected final view:** recompute FG/1H ML, spread, total, team-total against the correct home/away/period/team score, detect historical grade conflicts, and leave original historical grade unchanged. Missing/duplicate/misaligned original finals do not become settled outcomes. Other periods, quarters, PGA matchups and unsupported props remain unresolved until exact original settlement contracts are available.
6. **All-census inclusion:** rank **all** original saved claimed EVs, even when flagged/rejected. Preserve missing-EV rows and full denominator, report distinct event clusters. Do not calculate bankroll ROI or success from overlapping offers/alternate lines. Even mathematical success and a W are not a bookmaker-certified edge.
7. **Privacy:** reject path inside repo, file or ancestor symlinks, nonprivate source parent, non-0600 original, duplicate JSON key, oversized file, nonfinite literal/overflow and overwrite. The validator must never fetch external resources.

## Real acceptance still absent

Original Nov 9 `picks.csv` 496-row engine output and finals bytes remain missing; original Nov 11 simulation win/loss/push draws are missing. Price/source data shown in public screenshots or formatted cards lack independently proven provider offer clocks. This gate cannot retroactively establish those artifacts, build a true authenticated DK/second-book bridge, guarantee accurate predictive features, or certify historical ROI. Issue #10 A–E remains OPEN, frozen v5 and official exposure remain PAPER / 0u. For new unseen games, preregister the guard and probability tests *before* capturing decisions, retain every qualification rejection and final, compare market-only vs model-only vs pooled forecasts by event, and use game-clustered intervals after enough independent games rather than alternate-line row counts.