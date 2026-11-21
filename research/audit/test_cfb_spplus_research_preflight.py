"""Synthetic integrity and unit regression tests, never authentic ratings."""
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from cfb_spplus_research_preflight import run, Rejected


class SPPlusTests(unittest.TestCase):
    def setUp(self):
        d = TemporaryDirectory(); self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.ratings = self.root / 'ratings.csv'
        self.games = self.root / 'games.csv'
        self.manifest = self.root / 'manifest.json'
        with self.ratings.open('w', newline='') as f:
            w = csv.writer(f); w.writerow(['team','offense','defense','special_teams'])
            w.writerow(['Alpha',40,15,0.6]); w.writerow(['Beta',25,30,-0.2])
            for i in range(136): w.writerow([f'T{i}',28,28,0])
        self.games.write_text('game_id,home,away,kickoff_utc,neutral\ng1,Alpha,Beta,2026-11-21T18:00:00Z,0\n',encoding='utf-8')
        self.obj = dict(source_kind='ESPN_SPPLUS_2026', source_url='https://www.espn.com/college-football/story/_/id/49868647/2026-college-football-sp+-rankings-all-138-fbs-teams',
                        published_utc='2026-11-15T22:00:00Z', captured_utc='2026-11-21T12:30:00Z',
                        data_through_utc='2026-11-15T20:00:00Z', model_asof_utc='2026-11-21T13:00:00Z',
                        expected_games=1)
        self.update_manifest()

    def update_manifest(self):
        self.obj['ratings_sha256'] = hashlib.sha256(self.ratings.read_bytes()).hexdigest()
        self.obj['games_sha256'] = hashlib.sha256(self.games.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(self.obj),encoding='utf-8')

    def test_raw_spplus_is_not_added_to_28(self):
        p = run(self.ratings,self.games,self.manifest)
        row = p['rows'][0]
        self.assertEqual(p['ratings_teams'],138)
        self.assertLess(row['research_projection']['home_neutral_points'],55)
        self.assertGreater(row['research_projection']['home_neutral_points'],35)
        self.assertEqual(row['ev'],None)
        self.assertFalse(row['wager_eligible'])
        self.assertEqual(row['stake_u'],0)

    def test_zero_official_positions(self):
        p = run(self.ratings,self.games,self.manifest)
        self.assertEqual(p['wagers'],0)
        self.assertEqual(p['research_paper'],1)
        self.assertIn('NO_GAME_SPECIFIC_PACE_OR_ADVANCED_STATS',p['rows'][0]['reason_codes'])

    def test_missing_fcs_blocked_and_censused(self):
        self.games.write_text(self.games.read_text().replace('Beta','FCS'),encoding='utf-8')
        self.update_manifest()
        r = run(self.ratings,self.games,self.manifest)['rows'][0]
        self.assertEqual(r['status'],'BLOCKED')
        self.assertIsNone(r['research_projection'])
        self.assertIn('TEAM_NOT_IN_FBS_SPPLUS_CENSUS',r['reason_codes'])

    def test_neutral_must_be_explicit(self):
        self.games.write_text(self.games.read_text().replace(',0\n',',\n'),encoding='utf-8')
        self.update_manifest()
        with self.assertRaisesRegex(Rejected,'NEUTRAL_FLAG_UNVERIFIED'):
            run(self.ratings,self.games,self.manifest)

    def test_missing_team_census(self):
        self.ratings.write_text('\n'.join(self.ratings.read_text().splitlines()[:-1])+'\n',encoding='utf-8')
        self.update_manifest()
        with self.assertRaisesRegex(Rejected,'CENSUS_INCOMPLETE'):
            run(self.ratings,self.games,self.manifest)

    def test_sha_tamper_rejected(self):
        self.obj['ratings_sha256']='a'*64
        self.manifest.write_text(json.dumps(self.obj))
        with self.assertRaisesRegex(Rejected,'SOURCE_SHA_MISMATCH'):
            run(self.ratings,self.games,self.manifest)

    def test_utc_clocks_required(self):
        self.obj['captured_utc']='2026-11-21T13:00:00'
        self.manifest.write_text(json.dumps(self.obj))
        with self.assertRaisesRegex(Rejected,'OFFSET_REQUIRED'):
            run(self.ratings,self.games,self.manifest)

    def test_after_kickoff_blocked(self):
        self.obj['model_asof_utc']='2026-11-21T19:00:00Z';self.manifest.write_text(json.dumps(self.obj))
        r = run(self.ratings,self.games,self.manifest)['rows'][0]
        self.assertEqual(r['status'],'BLOCKED')
        self.assertIn('ASOF_AFTER_KICKOFF',r['reason_codes'])

    def test_future_source_time_refused(self):
        self.obj['data_through_utc']='2026-11-22T00:00:00Z';self.manifest.write_text(json.dumps(self.obj))
        with self.assertRaisesRegex(Rejected,'SOURCE_CLOCKS_OUT_OF_ORDER'):
            run(self.ratings,self.games,self.manifest)

    def test_duplicate_teams_blocked(self):
        self.ratings.write_text(self.ratings.read_text().replace('T135,28,28,0','T134,28,28,0'),encoding='utf-8')
        self.update_manifest()
        with self.assertRaisesRegex(Rejected,'DUPLICATE_OR_BLANK_TEAM'):
            run(self.ratings,self.games,self.manifest)

    def test_nonfinite_ratings_refused(self):
        self.ratings.write_text(self.ratings.read_text().replace('Alpha,40,15,0.6','Alpha,nan,15,0.6'),encoding='utf-8')
        self.update_manifest()
        with self.assertRaisesRegex(Rejected,'OFFENSE_PPG:OUT_OF_RANGE'):
            run(self.ratings,self.games,self.manifest)

    def test_mismatch_game_count_refused(self):
        self.obj['expected_games']=58;self.manifest.write_text(json.dumps(self.obj))
        with self.assertRaisesRegex(Rejected,'CENSUS_INCOMPLETE'):
            run(self.ratings,self.games,self.manifest)


if __name__=='__main__': unittest.main()
