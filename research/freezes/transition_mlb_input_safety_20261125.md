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

## 4. Pin mechanism — Option B (PR #535)
The owner chose a reviewed, unified update of the stock verifier `verify_versioned_transition.py`. The Nov 15 freeze and the Nov 18 first-hop
manifest stay **byte-immutable** (hashes asserted by tests and by the verifier itself). A hash mismatch of either manifest, of
`verify_code_freezes.py`, or of this verifier exits non-zero (the earlier standalone MLB verifier only *reported* a mismatch; that is fixed here
and covered by a failing-exit test). The standalone `verify_mlb_input_safety_transition.py` is retired.

Additional hops live in [`code_identity_transitions_20261125.json`](code_identity_transitions_20261125.json). The verifier exact-matches that
document to a reviewed list and applies the hops in memory only. Registered hops:

| Sport | From (Nov 18) | To | Introducing commit | Governance | Class | Evidence |
|---|---|---|---|---|---|---|
| MLB | `3f630532` | `30c6cb33` | `b73874a` | pr-446 | input-safety fail-closed loader | this record |
| NBA | `da0c1503` | `b353de86` | `8537ae48` | pr-460 | behavioral 1H/1Q two-way ML tie-as-push | `grok-cbb/nba-push-accounting-transition-20261125@737dd2a3` (`code_identity_transitions_20261125_nba_candidate.json`) |

Each hop is checked for: prior and approved blobs, first introducing commit, single-parent ancestry (the only parent holds the prior blob; for NBA that parent holds `da0c1503`), and a valid zero-release governance record. An unknown extra hop is refused.

### Entry format for a further hop
A new hop is one object in `candidates`. Required keys (exact):

```
sport, path,
original_git_blob_sha1,                    # Nov 15 pin
prior_approved_candidate_git_blob_sha1,    # previous hop's approved blob
prior_first_introducing_commit,
prior_change_pr,
approved_candidate_git_blob_sha1,
first_introducing_commit,
change_pr,
governance_record,                         # docs/governance/changes/pr-<N>.json
change_class
```

Adding a hop is a reviewed change: append the object to this manifest **and** to `EXPECTED_ADDITIONAL_CANDIDATES` in `verify_versioned_transition.py`, then recompute `verify_versioned_transition_git_blob_sha1` in the manifest. Editing only one of the two is refused.

Adding a hop also changes base-pinned files, so the independent gate (§4b) fails that PR until the owner merges it.

### 4b. Independent, base-pinned integrity gate (owner review of #535 at `bfef2eb4`)
Finding: the verifier's self-hash sits in a manifest the same PR can edit, so a coordinated edit to both passes. The self-hash stays as defense in depth, but it is **not** the trust anchor.

The trust anchor is [`integrity_pins.json`](integrity_pins.json) **as committed on the base branch**. It holds expected git blobs for these files:
- `verify_versioned_transition.py`
- `verify_code_freezes.py`
- the Nov 15 freeze
- the Nov 18 and Nov 25 transition manifests
- `integrity_gate.py`
- `.github/workflows/freeze-integrity-trusted.yml`
- `.github/workflows/risk-lock-research.yml`

The workflow `freeze-integrity-trusted.yml` runs on `pull_request_target`:
1. It checks out the **base** SHA and fetches the PR head as git objects only.
2. It runs the **base** copy of `integrity_gate.py`.
3. That copy compares each head blob, and the head pins file itself, with the base values. It never executes head code.

The gate's outcomes (exit 2 means the job fails):
- **No pinned file changed:** `PASS_INTEGRITY_PINS_UNCHANGED`.
- **Pinned files changed, no exact declaration:** `BLOCK INTEGRITY_PIN_CHANGE_UNDECLARED`, exit 2. "Exact" means `docs/governance/integrity/pr-<N>.json` lists every change as a path with its base blob and head blob.
- **Pinned files changed, with an exact declaration:** still `BLOCK INTEGRITY_PIN_CHANGE_DECLARED_REQUIRES_OWNER_MERGE`, exit 2. The owner merge is the only recording act. After the merge, the new base pins become the expected values.
- **Base tree does not match the base pins:** `INTEGRITY_BASE_PINS_INCONSISTENT`, exit 2.
- **Pins file missing or malformed:** fails closed, exit 2.

On push to main and on PRs, `tree-matches-own-pins` checks that the committed tree matches its own pins. This is consistency evidence, not the anchor.

The owner review also brought these hardenings to the verifier:
- `verify_code_freezes.py` is hashed **before** it is imported. A tampered helper is refused (`CODE_FREEZE_VERIFIER_TAMPERED_PREIMPORT`) without running any of its code.
- Governance records must use exact types and the exact zero-release claim set. For example, `False` is not accepted for `0`, `0.0` is not accepted, and a `true` claim is rejected.
- Each governance record must be byte-identical to the record committed at its hop's introducing commit (`GOVERNANCE_RECORD_NOT_BOUND_TO_INTRODUCING_COMMIT`).

**Bootstrap limit:** `pull_request_target` uses the base branch's workflows, and the base for #535 (`7fc5aaa9`) has neither the gate nor the pins. So the gate cannot independently check PR #535 itself. The owner's exact-head review of #535 bootstraps the anchor. From the merge on, every PR that touches a pinned file fails the trusted job until the owner merges it.

The stock CI step `python research/freezes/verify_versioned_transition.py` is the single all-sport gate.

## 5. Governance
PR #535: `docs/governance/changes/pr-535.json`. Exact-head independent review is still required before the owner's merge (the recording act). Status stays PENDING_OWNER_MERGE, PAPER_0U, official_counted = 0, approved stake 0u.
