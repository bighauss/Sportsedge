# MLB input-safety versioned transition record — 2026-11-25

**Status: PENDING_OWNER_MERGE.** The owner's merge of this change is the recording act. Release stays PAPER_0U,
official_counted = 0, approved stake 0u, no certification, no source authentication. Machine-readable twin:
[`transition_mlb_input_safety_20261125.json`](transition_mlb_input_safety_20261125.json); candidate manifest entry:
[`code_identity_transitions_20261125_mlb_candidate.json`](code_identity_transitions_20261125_mlb_candidate.json); evidence:
[`transition_mlb_input_safety_20261125_equivalence.json`](transition_mlb_input_safety_20261125_equivalence.json).

| | git blob |
|---|---|
| Nov 15 pin (`frozen_baselines_20261115.json`) | `bdedf10c09c307ee51fcec0f7da32cb4fa7974b8` |
| Nov 18 approved candidate (PR #293, `85adaf5`; `code_identity_transitions_20261118.json`) | `3f630532e9ff499912bc06041906d3b7c11d9887` |
| Current `models/mlb/sportsedge_mlb_model.py` (PR #446, commit `b73874a`) | `30c6cb3355ac5f6b6cbb018729c4fdc41255e057` |

Owner decision (Nov 25): **keep** the input-safety fix, prepare a separate documented versioned transition, do not revert,
never bypass or weaken the verifier.

## 1. Diff 3f630532..30c6cb33 (+13 / −1, 2 hunks, both input-loader path)
| # | Location | Class | Change |
|---|---|---|---|
| 1 | after `load_csv()` (+4) | input loader | new `class DuplicateInputKey(ValueError)` |
| 2 | `load_keyed()` (+9 / −1) | input loader | one-line dict comprehension → loop that raises `DuplicateInputKey` (with line number) on a blank/missing key or a repeated key |

Coefficients 0 · game-projection path 0 · pricing path 0 · prop path 0 · other 0. A test asserts the diff is exactly these two
hunks and every other line is byte-identical.

**Behaviour change on invalid input only** (old → new): duplicate key, even identical rows or equal after strip: last row silently wins → refused ·
blank / whitespace-only key: stored under `""` → refused · short row with the key cell absent: stored under `None` → refused ·
key column absent from header: `KeyError` → `DuplicateInputKey` (still fail-closed). Blast radius: `load_inputs()` (pitchers/batters by `player_id`,
bullpen/defense by `team`, parks by `park`) and its callers `sportsedge/markets/projection_bridge.py` and `models/mlb/shared_inning_sim.py` now
refuse the whole folder instead of pricing from an arbitrary row — intended (pr-446 assumption).
Unchanged: valid unique keys, case-distinct keys (`a`/`A`), whitespace-padded keys, BOM header, header-only file, missing file → `{}`;
ragged-row `AttributeError` and invalid-UTF-8 `UnicodeDecodeError` come from the untouched `load_csv`.

## 2. Output equivalence on valid inputs (float.hex, zero tolerance)
Harness `mlb_input_safety_equivalence.py`; the approved source is kept as `pinned_blobs/3f630532_sportsedge_mlb_model.py.txt` (blob-hash checked).
Both versions run in isolated namespaces on byte-identical input **files**. **The repo commits no real MLB board or CSV**; inputs are the committed
`make_samples.py` output (seed 20261115) plus 100 seeded random slates × 15 games (seed 20261125; blank cells, partial lineups, missing bullpen/defense
rows, whole and half lines, one-sided books, all game and prop markets) — synthetic, so this proves code equivalence, not forecast quality.

| Folders | Games (priced / unpriced) | Market evaluations | Card rows (props) | Mismatches |
|---|---|---|---|---|
| 101 | 1,502 (1,327 / 175) | 20,703 | 14,190 (5,780) | **0** inputs · **0** projections/price tables · **0** market evals · **0** card rows · `mlb_card.csv`/`.md` byte-identical |

## 3. Fail-closed tests
19-case negative matrix (old vs new outcome recorded), every keyed file × {duplicate, blank} through `load_inputs` and `run_card`, malformed
files unchanged, and an end-to-end duplicate-starter demo (old priced a card silently from the wrong row; new raises `DuplicateInputKey`).

## 4. Pin mechanism (read first)
`verify_versioned_transition.py` hard-codes the exact Nov 18 set and requires MLB = `3f630532`, so the stock CI step *Seven code pin verification* cannot accept
`30c6cb33` without editing that verifier. **This change edits neither verifier, nor the Nov 15 or Nov 18 manifests** (byte hashes asserted by tests).
`verify_mlb_input_safety_transition.py` imports the stock verifier, runs all of its checks unchanged (immutable manifests, exact three-candidate set,
historical bytes and first-introducing-commit provenance for CBB/MLB/NBA), adds an explicit second MLB hop (`b73874a`: blob bytes, single parent still at `3f630532`,
ancestry, pr-446 governance record), moves the MLB pin only in memory, and hashes every pinned file. `--scope MLB` (default) gates on MLB and reports the other
sports; `--scope ALL` gates on all seven.

After the owner merges, either (A) add a CI step running the new verifier, or (B) adopt the candidate manifest content into a reviewed edit of the stock
verifier and Nov 18 manifest. Until then the stock step stays red for MLB; NBA (`8537ae4`, tied-period moneyline push, behavioural) is a separate owner decision,
untouched here and still red under `--scope ALL`.

## 5. Governance
Touches protected path `research/freezes/**`: the PR needs `docs/governance/changes/pr-<N>.json` once its number exists, and an exact-head independent review before the owner's merge.
