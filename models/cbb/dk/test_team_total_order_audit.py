import csv
import io
import unittest
from models.cbb.dk.team_total_order_audit import audit

def board(*rows):
    defaults = {"row_key":"r1","market":"TT_HOME","period":"FG","price_a":"-110",
                "price_b":"-110","disposition":"HELD","reason_codes":"TOTALS_ORDER_UNVERIFIED",
                "totals_order":"","line":"70.5"}
    f=io.StringIO()
    w=csv.DictWriter(f,fieldnames=list(defaults))
    w.writeheader()
    for r in rows:w.writerow({**defaults,**r})
    return f.getvalue().encode()

class TeamTotalOrderAudit(unittest.TestCase):
    def test_equal_and_unequal(self):
        report=audit(board({},{"row_key":"r2","price_b":"-120"}))
        self.assertEqual(report["released"],0)
        a,b=report["rows"]
        self.assertEqual(a["state"],"ORDER_INVARIANT_DIAGNOSTIC_ONLY")
        self.assertEqual(a["hypothetical_price_assignments"],[{"over":-110,"under":-110}])
        self.assertEqual(b["state"],"EXPLICIT_LABEL_EVIDENCE_REQUIRED")
        self.assertEqual(len(b["hypothetical_price_assignments"]),2)
        self.assertTrue(all(not r["admission_changed"] for r in report["rows"]))
    def test_other_hold_and_invalid(self):
        r=audit(board({"reason_codes":"TOTALS_ORDER_UNVERIFIED;OTHER"},
                      {"row_key":"r2","price_a":"NaN"}))["rows"]
        self.assertEqual(r[0]["hypothetical_price_assignments"],[])
        self.assertEqual(r[1]["state"],"INVALID_PRICE")
    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            audit(board({},{}))
if __name__=="__main__":unittest.main()
