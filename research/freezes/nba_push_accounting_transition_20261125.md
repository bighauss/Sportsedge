# NBA push-accounting — versioned BEHAVIORAL transition record — 2026-11-25

**Status: PENDING_OWNER_MERGE.** The owner's merge is the recording act. Release stays PAPER_0U, official_counted = 0,
approved stake 0u, no certification, no source authentication. Machine-readable twin:
[`nba_push_accounting_transition_20261125.json`](nba_push_accounting_transition_20261125.json); candidate entry (Nov 18 format):
[`code_identity_transitions_20261125.json`](code_identity_transitions_20261125.json); verifier:
[`verify_nba_behavioral_transition.py`](verify_nba_behavioral_transition.py).

Owner decision (Nov 25): **KEEP** the fix in `8537ae4` (pr-460); prepare a separate versioned *behavioral* transition; do **not** revert;
never bypass or weaken a verifier.

| link | git blob | commit | PR |
|---|---|---|---|
| Nov 15 pin | `0036cb9a2a7eff9fed9b175a0175a963d20e6b3e` | `29c85365` | — |
| Nov 18 approved (input hygiene) | `da0c1503af5ed9ad548d1458588505f695b749e5` | `098c92bf` | #294 |
| **this candidate (behavioral)** | `b353de86445188288cab4050f6cae13eee76bff6` | `8537ae481a34fa6972a67389a6ac75172ee1f59c` | #460 |

## 1. Diff da0c1503 → b353de86 (+6 / −1, one hunk, `price_game_market`, `base == "ML"`)
| line | class | effect |
|---|---|---|
| `if seg != "FG":` | **behavioral** | new branch, only `1H_ML` / `1Q_ML` |
| two `#` comment lines | comment | none |
| `po, push = p_over(mu, SD["margin"]*sm, 0)` | **behavioral** | win = P(period margin ≥ +0.5); push = P(\|margin\| < 0.5) |
| `return po, push, mu, "margin"` | **behavioral** | push mass reaches `_pick`, settled as stake refund |
| `p = 1 - N.cdf(...)   # full game: OT, no tie` | comment-only | expression byte-identical; full-game ML unchanged |

Coefficients 0, projection path 0, other markets 0, props 0, full-game ML 0. The same commit also adds tests, the `nba-period-ml.yml` workflow and `pr-460.json` (not model code).
The diff is content-addressed in the record (sha256 of the n=0 unified diff) and checked by the verifier and a test.

## 2. Contract and normalization
* **Two-way** period ML (selections = the two teams): a tied period is refunded → push. **Three-way** (Tie/Draw selection): a tie loses both team bets, the Tie leg wins. The model has no three-way pricing.
* Three-way boards fail closed in **both** versions: H/A/TIE under one market, or any market not named `1H_ML`/`1Q_ML`, yields no price (`contract_probes`).
* **DraftKings' own rule text was NOT retrieved** (its help pages render client-side and return "not found" to non-browser fetch). pr-460's "per published DraftKings General Rules" is therefore unverified here; third-party rule texts (BetNow, BetJets, Betgr8) match the 2-way-push / 3-way-draw split but are not DK. Contract enforcement relies on correct market labelling at capture.
* **Known pre-existing gap (both versions, not caused by this change):** a *partial* three-way capture (H + TIE rows only) is paired as a two-way market and the TIE row is priced as the away team (EV +358% in the probe). Needs a capture/adapter guard, not a frozen-model edit.
* Normalization: win_home + win_away + push = 1 within 1.2e-16 on 1,601 margins × {1H, 1Q, FG}; push symmetric (1.7e-16); push equals the closed-form tie band (1.2e-16); push range 1H [1.8e-6, 0.0449], 1Q [8.5e-11, 0.0638]; full-game ML push ≡ 0. Previous version: two outcomes summing to 1, push ≡ 0.

## 3. Unaffected markets are bit-identical (zero tolerance, float.hex)
Harness `nba_push_accounting_equivalence.py`; previous bytes kept in `pinned_blobs/` (blob-checked). **No real NBA boards are committed on main** (the sample CSVs exist only in history on other branches and are synthetic), so inputs are synthetic: the `make_samples.py` board, the same board plus 1H/1Q ML rows, and a seeded random corpus (seed 20261125, 2,000 games). This proves code behavior, not forecast quality.

| | games | non-1H/1Q-ML rows compared | mismatches | props | prop mismatches | affected rows (1H_ML/1Q_ML) |
|---|---|---|---|---|---|---|
| sample board (no period-ML rows) | 2 | 28 | 0 (card csv/md **byte-identical**) | 12 | 0 | 0 |
| sample + synthetic period ML | 2 | 28 | 0 | 12 | 0 | 8, all changed |
| seeded corpus | 2,000 | 32,000 | 0 | 1,182 | 0 | 8,000, all changed |
| **total** | **2,004** | **32,056** | **0** | **1,206** | **0** | **8,008** |

Also identical: all 2,004 game projections and every non-affected card row (all fields except rank-derived).

## 4. Backtest of the affected markets
**No real NBA data in the repo or CI.** Supplementary, external, disclosed: ESPN public linescores + closing full-game spread/total, 2023-24 and 2024-25 (2,644 final games; per-event response hashes in `nba_push_accounting_hist/games.csv`). **No 1H/1Q moneyline prices exist anywhere available, so real ROI/CLV is not computable and is not reported.** The SportsEdge projection is replaced by a market-implied stand-in (margin = −closing spread).

| | 1H | 1Q |
|---|---|---|
| tie rate observed | 3.45% (91/2,641, Wilson95 2.81–4.21) | 4.88% (129/2,641, 4.13–5.77) |
| mean push mass modeled by new version | 4.10% | 6.08% |
| mean win-prob shift (new − old) | −2.06 pts | −3.05 pts |
| conditional (non-tie) Brier old / new | 0.22068 / 0.22064 | 0.23482 / 0.23484 |
| 3-outcome Brier new vs old (old gives ties P=0) | 0.4783 vs 0.4801 | 0.5185 vs 0.5220 |
| log loss, old | infinite on the 91 tie games | infinite on 128 |
| log loss, new (3-outcome) | 0.7615 | 0.8272 |

Findings: ties are real and common (≈1 in 29 first halves, ≈1 in 20 first quarters), so the old half-win accounting was wrong; the new push mass is calibrated for 1H (modeled 4.1% inside the CI) and **overstated for 1Q** (6.1% vs 4.9%, above the CI) because the model's assumed period SDs (8.9, 6.3) are narrower than observed residuals (11.0, 8.3 vs market-implied margin). That SD issue pre-dates this change and also inflates win-probability confidence. Conditional win probabilities are essentially unchanged (Brier within 5e-5).
EV shift: raw EV = p·dec − 1 + push, so shift = Δp·dec + push ≈ push·(1 − dec/2): favorites/short prices gain, underdogs above +100 lose. At −110 both sides: +0.19 pts (1H) / +0.28 pts (1Q); at +300 −4.1 / −6.1 pts. No side flips sign at −110 (hypothetical price; none exists in the repo).
Seeded synthetic corpus: 54 period-ML picks flip from +blend EV to ≤0, net card −6 rows of 15,515, 210 star-bucket changes.

## 5. Verification and CI wiring
`python research/freezes/verify_nba_behavioral_transition.py` re-runs the Nov 15/Nov 18 authority unchanged (`checked_manifest`, `check_provenance`), requires the Nov-18-format entry to match exactly, checks that `8537ae4` is the first introducing commit (every parent has `da0c1503`) and an ancestor of HEAD, that the on-disk file is `b353de86`, the record, evidence hashes and the exact diff. Scope is the NBA file only; other sports' pins are listed informationally (MLB still drifts).
**This change edits no existing pin file or verifier.** The existing "Seven code pin verification" step stays red (MLB first in sort order, then NBA). The minimal edit that would make that step accept NBA's chained candidate is provided, **not applied**, in `nba_push_accounting_20261125_wiring_proposal.patch`; it edits the Nov 18 authority and verifier, so it needs explicit owner approval, and MLB is a separate decision.
Governance follow-up: opening a PR touches `research/freezes/**`; add `docs/governance/changes/pr-<N>.json` once the number is known.

### Scratch demonstration of the proposed wiring (not on this branch)
Applying the patch in a scratch clone: `checked_manifest` and `check_provenance` pass for all three sports, NBA's on-disk pin verifies as `b353de86`, the 10 existing `test_versioned_transition` / `test_verify_code_freezes` tests pass, and the first remaining failure is `CODE_CHANGED_SINCE_FREEZE:models/mlb/sportsedge_mlb_model.py` (MLB, separate decision). If the owner approves the patch, `verify_nba_behavioral_transition.py` (which pins the Nov 18 manifest blob) must be retired in the same change.
