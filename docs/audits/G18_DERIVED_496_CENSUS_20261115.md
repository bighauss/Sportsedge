# Nov 9 CBB: original board → private 496-side DERIVATIVE (not original picks)

**Research / PAPER 0u.** As-of review on Nov 15 CT.

## Verified source lineage

- Google Drive file `board.csv` ID `1Kqqneaz-fvCfSF2z8eOm6z7d468KRHSh` is mutable; **do not read its current contents as if they were Nov 9 source**.
- Retrieved **original historical revision** `0Bz5GGyFPXJYyTGFSZ3dlZzlIMW8vY0pmVHNldlZxdXVMT3hvPQ`, first saved November 10 2026 at 02:17:44.831Z.
- Previously independently recorded original revision SHA-256 `922f6a10b1c038a15ba0469d344b5015b767dca6c41a791110aa083fd9027ea4`. Recompute and match hash on a private export before running CLI.
- 248 source rows and exact per-family counts: FG spread 75, total 75, home TT 43, away TT 43, ML 2; 1H spread 2, total 2, home TT 2, away TT 2, ML 2.
- Each original market has **two priced outcomes** (`price_a` and `price_b`). Expanding the above without inventing odds yields **496 DERIVED priced-side records**. Exactly **180 DERIVED team-total sides**: `2*(43+43+2+2)`. This validates the historical 496/180 *structural denominator* from the original board, not the original portable engine's row IDs or selected/qualified bets.

## Actual private derivative created and verified

A separate private Drive spreadsheet now contains `PICKS_DERIVED`: **497 populated rows including `game,pick,price` header** and 496 expanded selections, plus a `PROVENANCE` tab. Its first derived selection is `Mississippi Valley @ Washington | Washington -31.5 | -110`; its final derived selection is `Portland @ Hawaii | Under 168.5 | -395`. Both endpoints and all 497 row counts were read back. The spreadsheet title visibly says **DERIVED, not original**. The link is intentionally not copied into public GitHub because original market prices are private source artifacts.

The deterministic converter `research/audit/reconstruct_g18_496_from_board.py` separately accepts a **private mode-0600 exact original board revision export**, verifies the original SHA-256, enforces exact source schema, 248/496 and market count contract, models side-relative home/away spread signs and 1H prefixes, and writes a **new private create-only CSV** in exact `game,pick,price` schema plus a derived SHA-256 sidecar. It refuses partial or changed source files. No historical picks file, event result, payout or model weights are overwritten.

```bash
python research/audit/reconstruct_g18_496_from_board.py \
 --board /private/nov9/original_board_revision.csv \
 --out /private/nov9/DERIVED_nov9_496_priced_sides.csv

python -m unittest discover -s research/audit -p 'test_reconstruct_g18_496_from_board.py' -v
```

## Why G-18 is still not an original replay

1. The original `picks.csv` emitted by the Nov 9 portable engine has **not been found**, so its exact IDs/order/qualifications and original SHA are still unknown. The new 496-side file is an independently generated reconstruction of offered board rows only.
2. The original `run7_finals.json` source bytes/hash and original upstream score observation receipt remain missing. Without these, a clean-room **exact-original** G-18 grading pass is impossible.
3. The earlier **70 changed labels** were recorded on a retrospective census; this derived 496 does not establish that all 70 are the original portable engine's changed decisions. Never force labels to match.
4. [PR #175](https://github.com/bighauss/Sportsedge/pull/175) **already merged** and independently hardens CBBD raw-finals consistency for future score joins. That work is not evidence an original Nov 9 finals response was recovered.
5. Original DraftKings sportsbook authorization, capture clocks and independent odds remains unauthenticated. No historical wagers or valid ROI can be inferred from a set containing both sides of markets.

**Gate outcome:** DERIVED 496 / TT 180 census now created privately; G-18 original-gradability remains BLOCKED; CBB forecast-model freeze and official promotion remain BLOCKED. Continue with new truly prospective 2027-season frozen outputs, while recovering the independent original finals artifact for forensic comparison.
