import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from research.market_implied import muse_cbb_intake as m
BODY='DraftKings NCAAB league scan — Tuesday, November 24, 2026\nSource: signed-out public league page (Game Lines, All). Capture: 5:46–5:47 AM CT (page footer server time matched CT). All 78 games pregame at capture.\n\n1. Wright State @ Saint Bonaventure — 9:00 AM CT — Spread: Wright State +1.5 -112 / Saint Bonaventure -1.5 -108 — ML: -105 / -115 — Total 146.5: O -105 / U -115 — ID 35078383\n2. Ohio @ New Mexico State — 10:00 AM CT — Spread: Ohio -4.5 -112 / NMSU +4.5 -108 — ML: -198 / +164 — Total 149.5: O -112 / U -108 — ID 35078384\n'
FULL='FULL DRAFTKINGS BOARD — Wright State @ Saint Bonaventure (NCAAB), DK event ID 35078383\nTip-off: Tue Nov 24, 2026, 9:00 AM CT. Capture: 5:49–6:04 AM CT, signed out, rendered public event page.\nGAME LINES: Spread Wright +1.5 -115 / St. Bona -1.5 -105 (final reading; -112/-108 at 5:49 AM). Total 146.5: O -105 / U -115. ML: Wright -105 / St. Bona -115.\nALT TOTAL (O/U; main excluded): 145.5 -120/-110 (5:57 AM; moved to -125/-105 by 5:59 AM)\nTEAM TOTALS MAIN: St. Bona 73.5 O -115 / U -115; Wright 72.5 O -120 / U -110.\n'
class IntakeRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.obj=dict(id=7130582591,body=BODY,html_url='https://github.com/bighauss/Sportsedge/issues/57#issuecomment-7130582591',user=dict(id=356830325),updated_at='2026-11-24T11:48:43Z')
    def kw(self,obj=None):
        return dict(raw=json.dumps(obj or self.obj).encode(),allowed_author_ids={356830325},expected_comment_id=7130582591,day_ct='2026-11-24',expected_games=2,output_dir=Path(self.tmp.name)/'capture',team_aliases={'New Mexico State':['NMSU']})
    def test_league_contract_binding(self):
        kw=self.kw();result=m.run(**kw)
        self.assertEqual((result['games'],result['paired_markets'],result['offered_sides']),(2,6,12))
        contracts=json.loads((kw['output_dir']/'contracts.json').read_text())
        self.assertTrue(all(c['dk_event_id'] and c['tipoff_ct'] for c in contracts))
        self.assertEqual((contracts[0]['line'],contracts[0]['price_a']),(-1.5,-108))
        self.assertEqual((contracts[1]['price_a'],contracts[1]['price_b']),(-105,-115))
        self.assertTrue(all(not c['eligible_for_pricing'] for c in contracts))
    def test_unauthorized_account(self):
        obj=copy.deepcopy(self.obj);obj['user']['id']=99
        with self.assertRaises(ValueError):m.run(**self.kw(obj))
    def test_raw_comment_mismatch(self):
        obj=copy.deepcopy(self.obj);obj['body']+='tamper'
        with self.assertRaises(ValueError):m.run(comment=obj,**self.kw())
    def test_timestamp_spoof(self):
        with self.assertRaises(ValueError):m.run(capture_start_ct='2026-11-24T06:45:00-06:00',**self.kw())
    def test_wrong_date(self):
        kw=self.kw();kw['day_ct']='2026-11-25'
        with self.assertRaises(ValueError):m.run(**kw)
    def test_individual_hashes_and_create_only(self):
        kw=self.kw();result=m.run(**kw)
        for name,digest in result['output_sha256'].items():
            self.assertEqual(hashlib.sha256((kw['output_dir']/name).read_bytes()).hexdigest(),digest)
        with self.assertRaises(FileExistsError):m.run(**kw)
    def test_alias_requires_config(self):
        kw=self.kw();kw['team_aliases']={}
        with self.assertRaises(ValueError):m.run(**kw)
    def test_duplicates_and_malformed_and_bad_spread(self):
        for body in [BODY+'\n'+BODY.splitlines()[3],BODY.replace('Total 146.5','Total BAD'),BODY.replace('NMSU +4.5','NMSU +5.5')]:
            obj=dict(self.obj,body=body)
            with self.assertRaises(ValueError):m.run(**self.kw(obj))
    def test_json_duplicate_keys(self):
        kw=self.kw();kw['raw']=b'{"id":1,"id":2}'
        with self.assertRaises(ValueError):m.run(**kw)
    def test_full_board_archives_movements_without_pricing(self):
        obj=dict(self.obj,body=FULL,id=7131618597,html_url='https://github.com/bighauss/Sportsedge/issues/57#issuecomment-7131618597',updated_at='2026-11-24T12:34:02Z')
        kw=dict(raw=json.dumps(obj).encode(),allowed_author_ids={356830325},expected_comment_id=7131618597,day_ct='2026-11-24',expected_games=1,output_dir=Path(self.tmp.name)/'full')
        result=m.archive_full_board(**kw)
        self.assertEqual(result['normalized_market_count'],0)
        self.assertIn('moved to -125/-105',(kw['output_dir']/'sections.json').read_text())
    def test_full_board_rejected_by_league_path(self):
        obj=dict(self.obj,body=FULL)
        with self.assertRaises(ValueError):m.run(**self.kw(obj))
    def test_game_denominator_mismatch(self):
        kw=self.kw();kw['expected_games']=1
        with self.assertRaises(ValueError):m.run(**kw)
