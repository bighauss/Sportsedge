import unittest
from research.audit.r4_pairing_adversarial import audit_rows, normalize_line

def row(side="HOME", line="-3.5", **kw):
    d=dict(sport="NFL",event_id="EVT-1",book="DK",market="SPREAD",
           period="FG",side=side,line=line,captured_utc="2026-11-15T19:00:00Z",
           player_id="",team_id="",stat="")
    d.update(kw)
    return d

class AdversarialPairTests(unittest.TestCase):
    def test_opposite_spread(self):
        self.assertEqual(audit_rows([row(),row("AWAY","+3.5")]),[])
    def test_reversed_spread_block(self):
        self.assertTrue(audit_rows([row(),row("AWAY","-3.5")]))
    def test_lone_side_block(self):
        self.assertTrue(audit_rows([row()]))
    def test_total_mismatch_block(self):
        self.assertTrue(audit_rows([row("OVER","45.5",market="TOTAL"),
                                    row("UNDER","46.5",market="TOTAL")]))
    def test_total_pair(self):
        self.assertEqual(audit_rows([row("OVER","45.5",market="TOTAL"),
                                     row("UNDER","45.5",market="TOTAL")]),[])
    def test_casefold_duplicate(self):
        self.assertTrue(audit_rows([row(player_id="P1"),row(player_id="p1")]))
    def test_zero_canonical(self):
        self.assertEqual(normalize_line("-0","SPREAD"),"0")
        self.assertEqual(normalize_line("0.00","ML"),"")
    def test_underscore_rejected(self):
        with self.assertRaises(ValueError):normalize_line("-3_5","SPREAD")
    def test_fullwidth_rejected(self):
        with self.assertRaises(ValueError):normalize_line("３.５","SPREAD")
    def test_negative_total_rejected(self):
        with self.assertRaises(ValueError):normalize_line("-2.5","TOTAL")
    def test_oversized_spread_rejected(self):
        with self.assertRaises(ValueError):normalize_line("1000000000","SPREAD")

    def test_two_spread_ladders(self):
        offers=[row("HOME","-3.5"),row("AWAY","+3.5"),
                row("HOME","-6.5"),row("AWAY","+6.5")]
        self.assertEqual(audit_rows(offers),[])
    def test_two_player_prop_ladders(self):
        offers=[row("OVER","249.5",market="PLAYER_PROP",player_id="P1",stat="PASS_YDS"),
                row("UNDER","249.5",market="PLAYER_PROP",player_id="P1",stat="PASS_YDS"),
                row("OVER","274.5",market="PLAYER_PROP",player_id="P1",stat="PASS_YDS"),
                row("UNDER","274.5",market="PLAYER_PROP",player_id="P1",stat="PASS_YDS")]
        self.assertEqual(audit_rows(offers),[])
    def test_partial_alt_ladder_still_blocked(self):
        offers=[row("HOME","-3.5"),row("AWAY","+3.5"),row("HOME","-6.5")]
        self.assertEqual([x["row"] for x in audit_rows(offers)],[4])
    def test_unknown_market_reason(self):
        with self.assertRaisesRegex(ValueError,"UNKNOWN_MARKET"):
            normalize_line("3.5","SPREAD_1H")

if __name__=="__main__":unittest.main()
