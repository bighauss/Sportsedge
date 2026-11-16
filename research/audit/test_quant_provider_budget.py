"""Offline tests; no network, credentials, or provider identity assertions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from quant_provider_budget import reserve, record_429

NOW = '2026-11-15T20:00:00Z'

def request(path, rid='request-0001', *, provider='NFLVERSE', now=NOW,
            cache=None, mh=3, md=6):
    return reserve(path, provider=provider, endpoint='WEEKLY_STATS',
                   request_id=rid, max_hour=mh, max_day=md,
                   cache_age_seconds=cache, now_utc=now)

class DurableBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'budget.sqlite'

    def test_reservation_is_paper_not_authentication(self):
        x = request(self.path)
        self.assertTrue(x['allowed'])
        self.assertEqual(x['approved_stake_u'],0)
        self.assertFalse(x['source_authenticated'])
        self.assertTrue(self.path.exists())
        self.assertEqual(self.path.stat().st_mode & 0o077,0)

    def test_persistent_duplicate_across_invocations(self):
        self.assertTrue(request(self.path)['allowed'])
        self.assertEqual(request(self.path)['status'],'DUPLICATE_REQUEST_ID_BLOCKED')

    def test_fresh_cache_never_spends_budget(self):
        x=request(self.path,cache=2)
        self.assertEqual(x['status'],'USE_EXISTING_PRIVATE_CACHE')
        self.assertTrue(request(self.path)['allowed'])

    def test_hourly_limit_persists(self):
        for i in range(2):
            self.assertTrue(request(self.path,'request-%04d'%i,mh=2)['allowed'])
        self.assertEqual(request(self.path,'request-9999',mh=2)['status'],
                         'HOURLY_REQUEST_BUDGET_EXHAUSTED')

    def test_day_limit_with_older_hour_entries(self):
        for n,clock in enumerate(('2026-11-15T15:00:00Z','2026-11-15T16:00:00Z')):
            self.assertTrue(request(self.path,'request-%04d'%n,now=clock,md=2)['allowed'])
        self.assertEqual(request(self.path,'request-last',md=2)['status'],
                         'DAILY_REQUEST_BUDGET_EXHAUSTED')

    def test_provider_isolation(self):
        self.assertTrue(request(self.path,'request-one',provider='NFLVERSE',mh=1)['allowed'])
        self.assertTrue(request(self.path,'request-two',provider='TORVIK',mh=1)['allowed'])

    def test_429_persists_after_restart(self):
        self.assertTrue(request(self.path)['allowed'])
        x=record_429(self.path,provider='NFLVERSE',request_id='request-0001',
                     retry_after_seconds=600,now_utc=NOW)
        self.assertEqual(x['status'],'429_BACKOFF_RECORDED_PAPER_ONLY')
        self.assertEqual(request(self.path,'request-0002')['status'],'PROVIDER_429_BACKOFF')
        self.assertTrue(request(self.path,'request-0002',now='2026-11-15T20:10:01Z')['allowed'])

    def test_429_extension_cannot_shorten_existing_backoff(self):
        request(self.path)
        record_429(self.path,provider='NFLVERSE',request_id='request-0001',
                   retry_after_seconds=600,now_utc=NOW)
        x=record_429(self.path,provider='NFLVERSE',request_id='request-0001',
                     retry_after_seconds=30,now_utc='2026-11-15T20:01:00Z')
        self.assertTrue(x['backoff_until_utc'].startswith('2026-11-15T20:10:00'))

    def test_429_requires_prior_reservation(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_OR_FUTURE_REQUEST'):
            record_429(self.path,provider='NFLVERSE',request_id='request-missing',
                       retry_after_seconds=60,now_utc=NOW)

    def test_rollback_clock_rejected(self):
        request(self.path,now=NOW)
        self.assertEqual(request(self.path,'request-earlier',now='2026-11-15T19:59:59Z')['status'],
                         'REQUEST_CLOCK_ROLLBACK_BLOCKED')

    def test_invalid_policies_rejected(self):
        for val in (0,-1,True,2.5):
            with self.subTest(val=val), self.assertRaises(ValueError):
                request(self.path,mh=val)
        with self.assertRaises(ValueError):
            request(self.path,cache=float('nan'))
        with self.assertRaises(ValueError):
            request(self.path,provider='NFLVERSE;TOKEN=x')
        with self.assertRaises(ValueError):
            record_429(self.path,provider='NFLVERSE',request_id='request-0001',
                       retry_after_seconds=True,now_utc=NOW)

    def test_concurrent_workers_do_not_exceed_quota(self):
        def attempt(i):return request(self.path,f'request-{i:04d}',mh=3,md=3)
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes=list(pool.map(attempt,range(15)))
        self.assertEqual(sum(x['allowed'] for x in outcomes),3)
        self.assertEqual(sum(x['status']=='HOURLY_REQUEST_BUDGET_EXHAUSTED' or
                             x['status']=='DAILY_REQUEST_BUDGET_EXHAUSTED' for x in outcomes),12)

    def test_symlink_to_private_database_blocked(self):
        other=Path(self.tmp.name)/'private.sqlite'
        self.assertTrue(request(other)['allowed'])
        link=Path(self.tmp.name)/'link.sqlite'
        link.symlink_to(other)
        with self.assertRaisesRegex(ValueError,'SYMLINK'):
            request(link)

    def test_world_readable_budget_directory_refused(self):
        unsafe=Path(self.tmp.name)/'unsafe'
        unsafe.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError,'DIRECTORY_NOT_PRIVATE'):
            request(unsafe/'quota.sqlite')

    def test_existing_world_readable_file_refused(self):
        self.path.write_bytes(b'')
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'NOT_PRIVATE'):
            request(self.path)

if __name__ == '__main__':
    unittest.main()
