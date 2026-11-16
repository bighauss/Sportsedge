# SportsEdge G1 — original November 9 card versus original board source closure

**Scope:** forensic, read-only evidence integrity. **No** model revision,
retrospective prediction change, stake authorization, sportsbook account access,
or historical ledger overwrite.

## Original provider-unverified artifacts

| Original file | Saved time (UTC) | Identity |
|---|---|---|
| `board.csv` original Drive revision `0Bz5GGyFPXJYyTGFSZ3dlZzlIMW8vY0pmVHNldlZxdXVMT3hvPQ` | 2026-11-10 02:17:44.831Z | 248 rows / 16,269 bytes / SHA-256 `922f6a10b1c038a15ba0469d344b5015b767dca6c41a791110aa083fd9027ea4` |
| `CARD_2026-11-09_LATE_CBB_CHATGPT.md` | 2026-11-10 02:22:24.393Z | 150 CARD + 59 MODEL-DOUBTED rows / SHA-256 `e1d48d408f5e0cd444c7626c9e3ae7f1707b03130095615c2b4bf10528330a60` |

The original board file is retrievable with authenticated user's Google
Drive revision history, ID `1Kqqneaz-fvCfSF2z8eOm6z7d468KRHSh`. The
card was saved under ID `1SG4rLd9C-lb7cvxMglDje-3ebqbdriUj`.
**Do not use current overwritten board.csv**, corrected `board_hc.csv`
or the reconstructed retrospective census as a substitute.

## Independent proof completed

1. On the original SHA-pinned inputs, **209/209 printed selections** have
   exactly ONE matching original board row by game/team, market/period, signed
   home-side spread or total line, exact selected American odds and side;
   zero missing, zero duplicate ambiguities. Includes **61/61** originally
   unlabelled game totals and first-half totals.
2. The source files were archived prior to documented 21:00 CT / 23:00 CT
   tipoffs. The archived original board SHA agrees with a contemporaneous
   pregame handoff. This authenticates the *file snapshot*, **not** individual
   prices' provider origin or quote observation times.
3. Each printed model probability is separately compared with the exact
   two-sided no-vig probability from the paired original board. Printed EV
   is checked against model p with a separate-rounding interval **only for
   binary-settled markets**. First-half ML remains **UNRESOLVED** without
   original p_win/p_loss/p_push draws (details below).
4. The 248 original quote pairs have positive overround (approximately
   3.64%–7.82%) and no monotonic inverse probability ladders. This is a
   mathematical sanity check, not proof the odds existed at DraftKings.
5. For the largest-edge cohort, **18 of 20** originate from Nov 9 and have
   exact original two-sided prices; Nov 11 CBB and Nov 15 NFL require their
   *own* quote/provider receipts.
6. Historical original **V1** card projections omitted a home-court term.
   Subsequent V2 corrected a separate input, but neither original V1
   probability nor saved price is retroactively replaced.

## First-half moneyline push convention — source-code verified

I recovered the original `sportsedge.py` from Drive file
`13ntxjdZEzMiU255SR19kCnNNEkBlqmov`, saved at
**2026-11-10 02:11:38Z**, before the original board and card.

The original source's `diff()` uses halftime home minus away score;
`wl()` computes unconditional `pw=P(win)`, `pl=P(loss)`.
`emit()` then prints `model_p = cond(pw,pl)=pw/(pw+pl)` while computing
`ev = pw * payout(odds) - pl`. **The printed p excludes halftime ties**,
while EV is unconditional. Thus `printed p * decimal_odds - 1` is NOT a
valid EV check when halftime ties can push; a difference does not prove
an arithmetic defect.

For the two apparent discrepancies outside naive rounding:
- 1H **Rice ML +575**, printed p **24.1%**, printed EV **+60.3%**,
  naive binary EV **+62.675%**; the displayed values correspond to
  approximately **3.8%** pushes (approximate due rounding).
- 1H **Portland ML +190**, printed p **40.0%**, printed EV **+15.2%**,
  naive binary EV **+16.0%**; approximately **5.0%** pushes.

These are **inferred consistency checks**, not recovered actual push
frequencies; exact verification requires the original 40,000-simulation
win/loss/tie draws or original full-precision w,l aggregates.
The new audit returns `ev_math_check=PUSH_AWARE_1H_ML_ORIGINAL_WIN_LOSS_DRAWS_REQUIRED`
and `ev_arithmetic_consistent_with_display_rounding=null`, never
misclassifying this as a confirmed arithmetic error.

## Grading provenance limit — important correction

`census.json` contains a **retrospective representation** of 496
`portable_nov9` entries. Auditing THAT file against independently
settled final scores produces **70 changed labels: 35 L→W, 35 W→L**.
This confirms the defect's manifestation in the retrospective census.
It is NOT a clean-room reproduction from original `picks.csv` raw bytes:
**that original CSV is still missing**. The repository's
`docs/audits/G18_FORENSIC_RECOVERY_20261115.md` makes the same
distinction. Historical grade corrections remain a separate overlay,
never overwritten over original results.

The **209** printed selections are not equivalent to the **496**
original full-engine priced sides and are not **209 independent wagers**.
Correlated alternate lines must be grouped by event and market family.

## How to reproduce safely with original bytes

```bash
python research/audit/original_board_card_source_join.py \
  /private/original_board_2026-11-09_revision.csv \
  /private/CARD_2026-11-09_LATE_CBB_CHATGPT.md \
  --board-sha256 922f6a10b1c038a15ba0469d344b5015b767dca6c41a791110aa083fd9027ea4 \
  --card-sha256 e1d48d408f5e0cd444c7626c9e3ae7f1707b03130095615c2b4bf10528330a60 \
  --board-saved-utc 2026-11-10T02:17:44.831Z \
  --card-saved-utc 2026-11-10T02:22:24.393Z \
  --earliest-game-start-utc 2026-11-10T03:00:00Z \
  --expected-board-rows 248 \
  --out /private/nov9_board_card_audit_CREATE_ONLY.json
python research/audit/test_original_board_card_source_join.py
```

**Private evidence boundary:** Both original source paths and the detailed
output path must be outside the public checkout, including through symlink
aliases. The audit report contains per-quote odds and probabilities; it is
created exclusively with `0600` permissions and removed if disk write or
sync fails. Never attach raw inputs or generated detailed reports to public
GitHub commits, PRs or CI artifacts.

The JSON output is create-only and includes source row, game, market,
signed line, both odds, raw one-sided implied probability, exact same-board
no-vig probability, printed rounded model probability, raw EV and
separate-rounding consistency. Every row is permanently labelled
**PAPER / 0u / NOT_AUTHENTICATED**.

## Remaining evidence gates and exact next requirements

- Original offer/provider payload bytes and trustworthy independently observed
  UTC for both sides and the relevant event/market IDs.
- Original Nov 9 Torvik adjusted-efficiency, tempo, venue, injuries, roster
  and model-input **publication and capture** receipts preceding prediction
  freeze. A frozen probability or notebook hash alone does not establish
  source vintage.
- Exact original `picks.csv` 496-row output, original SHA and saved time
  for forensic G18 settlement replay; otherwise keep 70 as a retrospective
  census correction, not an original-picks result.
- Original November 4 longshot source forecasts + offer receipts, if they
  exist; later retrospective claims are excluded until recovered.
- Prospective pre-registered, game-clustered calibration, source-backed
  closed-line comparison, and the independent Issue #10 A–E release gates.

### Independence

Tests employ **synthetic fixtures** with no private actual raw book boards
committed to this repository. Source hashes and self-asserted capture times
are local integrity data, not independent sportsbook attestation.
**No verified betting edge; no real-money picks, 0u.**
