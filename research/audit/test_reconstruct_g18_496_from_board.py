"""Synthetic-only independent 248->496 derivative expansion probes."""
import csv
import io
import unittest

from reconstruct_g18_496_from_board import (FIELDS, ReconstructionError, reconstruct)

def boardrow(market="SPREAD", line="-3.5", price_a="-110", price_b="-110"):
    values={"sport": "CBB", "home": "Stanford", "away": "Rice",
            "home_proj": "78.8", "away_proj": "67.6", "market": market,
            "line": line, "price_a": price_a, "price_b": price_b}
    s=io.StringIO(newline="")
    writer=csv.DictWriter(s, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow({k:values.get(k, "") for k in FIELDS})
    return s.getvalue().encode()


def picks(raw):
    body, report=reconstruct(raw, strict_nov9=False)
    return list(csv.DictReader(io.StringIO(body.decode()))),report


class DerivedOnlyTest(unittest.TestCase):
    def test_two_sided_spread_signs(self):
        rows,report=picks(boardrow())
        self.assertEqual([r["pick"] for r in rows], ["Stanford -3.5", "Rice +3.5"])
        self.assertEqual(report["derived_priced_sides"],2)
        self.assertFalse(report["original_engine_picks_recovered"])

    def test_ml_can_have_no_line_and_positive_price(self):
        rows,_=picks(boardrow("ML", "", "-3200", "1400"))
        self.assertEqual([r["pick"] for r in rows],["Stanford ML","Rice ML"])
        self.assertEqual(rows[1]["price"],"+1400")

    def test_first_half_team_total(self):
        rows,report=picks(boardrow("1H_HOME_TT","39.5"))
        self.assertEqual(rows[0]["pick"],"1H Stanford Over 39.5")
        self.assertEqual(rows[1]["pick"],"1H Stanford Under 39.5")
        self.assertEqual(report["team_total_sides"],2)

    def test_no_strict_false_claim_on_one_board_row(self):
        with self.assertRaisesRegex(ReconstructionError,"CENSUS_MISMATCH"):
            reconstruct(boardrow(),strict_nov9=True)

    def test_bad_price_rejected(self):
        with self.assertRaisesRegex(ReconstructionError,"INVALID_PRICE"):
            reconstruct(boardrow(price_b="-99"),strict_nov9=False)

    def test_populated_sgp_field_rejected(self):
        raw=boardrow().decode()
        cols=raw.strip().split("\n")
        values=cols[1].split(",")
        values[FIELDS.index("sgp")]="sgp-incomplete"
        with self.assertRaisesRegex(ReconstructionError,"UNEXPECTED_POPULATED"):
            reconstruct((cols[0]+"\n"+",".join(values)+"\n").encode(),strict_nov9=False)


if __name__=="__main__":
    unittest.main()
