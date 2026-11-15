"""No-network, synthetic salary discovery tests against the canonical DFS lane."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import fetch_dk_salaries as salary


def fixture(*, numbered=True, slots=True):
    players=[("Aaron Rodgers", "PIT", "QB", 9000),
             ("Ja'Marr Chase", "CIN", "WR", 11000)]
    js={"competitions":[{"competitionId":42,"name":"PIT@CIN 11/15/2026 08:20PM ET"}],
        "draftables":[]}
    if slots:
        js["rosterSlots"]=[{"rosterSlotId":11,"name":"FLEX"},
                           {"rosterSlotId":23,"name":"CPT"}]
    num=44900000
    for name,team,pos,flex in players:
        for label,slot_id,sal in (("FLEX",11,flex),("CPT",23,flex*3//2)):
            num+=1
            js["draftables"].append({"displayName":name,"teamAbbreviation":team,
              "position":pos,"draftableId":num,"salary":sal,
              "competition":{"competitionId":42},"status": "Q" if name=="Aaron Rodgers" else None,
              "rosterSlotId":slot_id if numbered else label,
              "draftStatAttributes":[{"id":90,"value":999999}]})
    return js


class SalaryLoaderContract(unittest.TestCase):
    def test_numeric_slot_with_verified_response_map(self):
        rows=salary.to_rows(fixture())
        self.assertEqual(len(rows),4)
        ar={r['Roster Position']:r for r in rows if r['Name']=="Aaron Rodgers"}
        self.assertEqual(ar['FLEX']['Salary'],9000)
        self.assertEqual(ar['CPT']['Salary'],13500)
        self.assertEqual(ar['FLEX']['Status'],'Q')
        self.assertTrue(all(r['AvgPointsPerGame']=='' for r in rows))

    def test_direct_cpt_flex_labels_are_safe_without_guessing(self):
        self.assertEqual(len(salary.to_rows(fixture(numbered=False,slots=False))),4)

    def test_unmapped_numeric_slot_id_blocks(self):
        with self.assertRaisesRegex(ValueError,'DK_SHOWDOWN_CPT_FLEX_SLOT_NOT_VERIFIED'):
            salary.to_rows(fixture(slots=False))

    def test_suspect_provider_metadata_blocks(self):
        f=fixture()
        f['rosterSlots'][1]['name']='UTILITY'
        with self.assertRaisesRegex(ValueError,'DK_ROSTER_SLOT_METADATA_UNVERIFIED'):
            salary.to_rows(f)

    def test_duplicate_roster_player_blocks(self):
        f=fixture(); f['draftables'].append(dict(f['draftables'][0], draftableId=12345678))
        with self.assertRaisesRegex(ValueError,'DK_DUPLICATE_PLAYER_ROSTER_SLOT'):
            salary.to_rows(f)

    def test_reused_provider_draftable_id_blocks(self):
        f=fixture(); f['draftables'][1]['draftableId']=f['draftables'][0]['draftableId']
        with self.assertRaisesRegex(ValueError,'DK_DRAFTABLE_ID_REUSED'):
            salary.to_rows(f)

    def test_bad_captain_multiplier_blocks(self):
        f=fixture(); f['draftables'][1]['salary']=13501
        with self.assertRaisesRegex(ValueError,'DK_CPT_SALARY_NOT_1P5_FLEX'):
            salary.to_rows(f)

    def test_half_pair_blocks(self):
        f=fixture();f['draftables'].pop()
        with self.assertRaisesRegex(ValueError,'DK_INCOMPLETE_CPT_FLEX_PAIR'):
            salary.to_rows(f)

    def test_wrong_competition_blocks(self):
        f=fixture();f['draftables'][1]['competition']['competitionId']=99
        with self.assertRaisesRegex(ValueError,'DK_DRAFTABLE_COMPETITION_ID_UNVERIFIED'):
            salary.to_rows(f)

    def test_wrong_id_blocks(self):
        f=fixture();f['draftables'][1]['draftableId']='../../bad'
        with self.assertRaisesRegex(ValueError,'DK_DRAFTABLE_ID_TEAM_POS_OR_SALARY_INVALID'):
            salary.to_rows(f)

    def test_public_url_allowlist(self):
        with self.assertRaisesRegex(ValueError,'UNREGISTERED_DK_PUBLIC_ENDPOINT'):
            salary.get('https://other.example/secret')

    def test_bad_lobby_draftgroup_id(self):
        with patch.object(salary,'get',return_value={'DraftGroups':[{'DraftGroupId':'../../secret'}]}):
            with self.assertRaisesRegex(ValueError,'DK_DRAFT_GROUP_ID_MISSING_OR_DUPLICATE'):
                salary.draft_groups('NFL')

    def test_provisional_snapshot_is_create_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'dk_auto.csv';rows=salary.to_rows(fixture())
            h=salary._write_provisional(path,rows)
            self.assertTrue(h.startswith('sha256:'))
            existing=path.read_bytes()
            with self.assertRaises(FileExistsError):salary._write_provisional(path,rows)
            self.assertEqual(existing,path.read_bytes())

    def test_actual_owner_game_config_matches_salary_csv(self):
        cfg=salary.HERE/'games'/'PIT_CIN_2026-11-15.json'
        csvpath=salary.HERE/'data'/'DKSalaries_PIT_CIN_2026-11-15.csv'
        report=salary.verify_owner_game(cfg,csvpath)
        self.assertEqual(report['engine'],'models/nfl_dfs/showdown_mc.py')
        self.assertEqual(report['seed'],7)
        self.assertFalse(report['DK_avg_fp_used'])
        self.assertFalse(report['owner_csv_modified'])
        self.assertEqual(report['player_count'],len(json.loads(cfg.read_text())['players']))
        # The actual canonical engine is used for scoring/optimization, not a fork.
        import showdown_mc
        authoritative=showdown_mc.load_salaries(csvpath)
        for player in json.loads(cfg.read_text())['players']:
            self.assertEqual(authoritative[player]['FLEX']*3, authoritative[player]['CPT']*2)

    def test_mismatched_config_team_refused_without_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            cf=base/'game.json';sf=base/'dk.csv'
            cf.write_text(json.dumps({'tag':'PIT_CIN_2026-11-15','players':{'A':{'team':'SEA','pos':'QB','p_active':1.0}}}))
            with sf.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=salary.FIELDS);w.writeheader()
                for slot,n in [('CPT',15000),('FLEX',10000)]:
                    w.writerow({'Position':'QB','Name':'A','ID':str(n),'Roster Position':slot,
                                'Salary':str(n),'TeamAbbrev':'LV','Game Info':'PIT@CIN 11/15/2026 08:20PM ET'})
            b=sf.read_bytes()
            with self.assertRaisesRegex(ValueError,'CONFIG_TEAM_POS_MISMATCH'):
                salary.verify_owner_game(cf,sf)
            self.assertEqual(b,sf.read_bytes())

    def test_other_matchup_csv_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);cf=d/'game.json';sf=d/'dk.csv'
            cf.write_text(json.dumps({'tag':'PIT_CIN_2026-11-15', 'players':{'A':{
                'team':'PIT','pos':'QB','p_active':1.0}}}))
            with sf.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=salary.FIELDS);w.writeheader()
                for slot,n in [('CPT',15000),('FLEX',10000)]:
                    w.writerow({'Position':'QB','Name':'A','ID':str(n),'Roster Position':slot,
                                'Salary':str(n),'TeamAbbrev':'PIT','Game Info':'PIT@BAL 11/15/2026 08:20PM ET'})
            with self.assertRaisesRegex(ValueError,'MATCHUP_NOT_CANONICAL_GAME'):
                salary.verify_owner_game(cf,sf)

    def test_provisional_cli_does_not_touch_owner_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=salary.HERE/'data'/'DKSalaries_PIT_CIN_2026-11-15.csv'
            before=owner.read_bytes()
            dg=[{'id':'22222','start':'','games':1,'suffix':''}]
            with patch.object(salary,'OUT',Path(tmp)), \
                 patch.object(salary,'draft_groups',return_value=dg), \
                 patch.object(salary,'get',return_value=fixture()):
                salary.main(['NFL'])
                with self.assertRaises(SystemExit):salary.main(['NFL'])
            self.assertEqual(before,owner.read_bytes())


if __name__=='__main__':unittest.main()
