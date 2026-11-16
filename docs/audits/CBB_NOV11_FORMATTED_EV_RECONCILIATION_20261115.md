# Nov 11 CBB late card — displayed EV arithmetic reconciliation

**Source:** user-connected Google Drive file `picks_2026-11-11_1934CT_CBB_late_v5_plain.csv`, Drive file ID `1tSPOPxP988zFTZOF1HGPOBHEIaZKU-bu`, representing a **formatted plain-text report**, not the original row-level quote or full-precision model evidence. Saved card heading states `Wed Nov 11, 2026, run 19:34 CT`, `sportsedge_v5`, and `PAPER/0u`.

## Full formatted-text census

- **65** numbered rows under the main CARD section, 10 games; **10** rows in a separate **MODEL-DOUBTED** appendix (the engine flags those for input checks); **75** displayed text table rows, not 75 independently accepted bets.
- Header says 188 original priced sides and 75 originally positive-EV raw rows. That source assertion is not independently proved by the displayed 75-row file.
- **22 of the main 65** display binary EV of at least 20%. No claim of valid or executable positive EV is warranted from display text.

## Rounding-aware arithmetic checks

For American price \(o\) with decimal gross return \(D\), the displayed-probability binary-only EV is \(100(p_{\mathrm{display}}D - 1)\) percent. A displayed probability rounded to one decimal percentage point allows an unrounded probability error of at most 0.05 percentage point; EV printed to one decimal allows another 0.05 pp. Therefore max unexplained gap from rounding alone is \((0.05D + 0.05)\) pp. That tolerance does not account for pushes, fees or other model transformations; such differences require original full-precision inputs and formula path, not guesswork.

| Printed selection | American price | Display p | Printed EV | Binary EV from displayed p | Rounding upper bound | Disposition |
|---|---:|---:|---:|---:|---:|---|
| #24 **1H UTSA ML** | +470 | 21.1% | +19.7% | **+20.27%** | 0.335 pp | **Mismatch beyond display rounding**; full precision p or calculation path required |
| #32 **1H California ML** | +200 | 38.6% | +15.1% | **+15.8%** | 0.200 pp | **Mismatch beyond display rounding**; full precision p or calculation path required |

The other 73 formatted entries' displayed single-price binary EV values fall within this rounding allowance. That is **not** a sportsbook price authentication or confirmation that those 73 projected probabilities are calibrated.

## Implementation

`research/audit/printed_card_ev_audit.py` is read-only and audits the format while keeping main selections and the model-doubted appendix distinct; flags malformed rows, count/rank mismatches and discrepancies beyond probability/EV rounding; writes a create-only report. Synthetic tests include the two known anomalies and the section-separation requirement. It does not promote picks, compute portfolio returns, assign stakes or assume the source text was a bookmaker receipt.

```bash
python research/audit/printed_card_ev_audit.py /private/original_display_card.txt \
  --report /private/printed_card_ev_audit.json
python -m unittest discover -s research/audit -p 'test_printed_card_*.py' -v
```

**Unresolved:** obtain the operative Nov 11 engine's exact `picks.csv` with full-precision probabilities, the original complete DK offer receipts (including both sides), model SHA and as-of feature source times. Pair each displayed selection with those original records. The model may have computed an adjustment not visible on the card; do not silently overwrite the display or patch formulas to force a match. Continue **PAPER / 0u**.
