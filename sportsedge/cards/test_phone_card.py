"""Synthetic Munich phone-card tests; no real or implied book prices."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import phone_card as m

H="0"*64


def fixture():
    return {
        "release":"PAPER_0U",
        "source":{"model_sha256":H,"feature_sha256":"1"*64,
                  "frozen_utc":"2026-11-14T15:00:00Z"},
        "game":{"sport":"NFL","away_name":"Patriots","home_name":"Lions",
                "away_abbr":"NE","home_abbr":"DET",
                "venue":"Munich, Germany","time_ct":"8:30 AM CT",
                "kickoff_utc":"2026-11-15T14:30:00Z",
                "away_projection":23.6,"home_projection":25.3,
                "total_projection":48.9},
        "plays":[
            {"rank":1,"play":"Game Under 50.5","market":"total",
             "game_time_ct":"8:30 AM CT","status":"PAPER_0U",
             "price":-105,"win_probability":.56,"projection":48.9,
             "ev_estimate_pct":7.8,"stars":3,
             "receipt_id":"SYNTHETIC_ONLY",
             "price_observed_utc":"2026-11-15T13:30:00Z"},
            {"rank":2,"play":"1H Under 25.5","market":"period_total",
             "game_time_ct":"8:30 AM CT","status":"PAPER_0U",
             "price":-108,"win_probability":.52,"projection":24.9,
             "ev_estimate_pct":4.4,"stars":2,
             "receipt_id":"SYNTHETIC_ONLY",
             "price_observed_utc":"2026-11-15T13:30:00Z"},
            {"rank":3,"play":"Player receptions","market":"player_prop",
             "game_time_ct":"8:30 AM CT","status":"BLOCKED"}
        ]
    }


class PhoneCardTests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.root=Path(self.d.name)

    def test_render_is_svg_and_deterministic(self):
        data=fixture()
        a=m.render(data,self.root)
        self.assertEqual(a,m.render(copy.deepcopy(data),self.root))
        root=ET.fromstring(a)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertEqual(root.attrib["viewBox"],"0 0 1080 1920")
        self.assertIn("SPORTSEDGE",a)
        self.assertIn("8:30 AM CT",a)
        self.assertIn("TOTAL 48.9",a)
        self.assertIn("NO DATA",a)
        self.assertIn("RESEARCH ONLY",a)
        self.assertIn("Win",a)

    def test_cannot_promote_official_status(self):
        d=fixture()
        d["release"]="VALIDATED_RESEARCH"
        with self.assertRaises(m.InvalidCard):
            m.render(d,self.root)

    def test_no_price_or_ev_allowed_for_blocked(self):
        d=fixture()
        d["plays"][2]["price"]=-110
        with self.assertRaises(m.InvalidCard):
            m.render(d,self.root)

    def test_frozen_source_and_timestamp_order(self):
        d=fixture()
        d["source"]["frozen_utc"]="2026-11-15T15:00:00Z"
        with self.assertRaises(m.InvalidCard):
            m.render(d,self.root)
        d=fixture()
        d["plays"][0]["price_observed_utc"]="2026-11-15T14:40:00Z"
        with self.assertRaises(m.InvalidCard):
            m.render(d,self.root)

    def test_rejects_unranked_or_fabricated_price(self):
        d=fixture()
        d["plays"][0]["price"]=-99
        with self.assertRaises(m.InvalidCard):m.render(d,self.root)
        d=fixture();d["plays"][0]["rank"]=3
        with self.assertRaises(m.InvalidCard):m.render(d,self.root)
        d=fixture();d["plays"][0].pop("receipt_id")
        with self.assertRaises(m.InvalidCard):m.render(d,self.root)

    def test_projected_score_must_match_total(self):
        d=fixture()
        d["game"]["total_projection"]=65
        with self.assertRaises(m.InvalidCard):m.render(d,self.root)

    def test_escaping_and_source_logo_file_gates(self):
        d=fixture()
        d["plays"][0]["play"]="A <script>&bad"
        image=m.render(d,self.root)
        self.assertNotIn("<script>",image)
        self.assertIn("&lt;script&gt;",image)
        d=fixture()
        d["game"]["away_logo"]={"path":"../secret.png","sha256":H,"rights":"OWNER_PROVIDED"}
        with self.assertRaises(m.InvalidCard):m.render(d,self.root)

    def test_unsupported_extra_rows_or_status(self):
        d=fixture()
        d["plays"]=d["plays"]*3
        with self.assertRaises(m.InvalidCard):m.render(d,self.root)
        d=fixture();d["plays"][0]["status"]="OFFICIAL"
        with self.assertRaises(m.InvalidCard):m.render(d,self.root)

    def test_same_inputs_same_svg_bytes(self):
        d=fixture()
        p=self.root/"demo.json";p.write_text(json.dumps(d))
        svg=m.render(json.loads(p.read_text()),self.root)
        (self.root/"demo.svg").write_text(svg)
        self.assertGreater((self.root/"demo.svg").stat().st_size,2500)


if __name__=="__main__":
    unittest.main()
