import copy, unittest
from sportsedge_cfb_event_completeness_r2 import audit

def fixture():
    e={'id':'1','competitions':[{'competitors':[{'team':{'id':'10'}},{'team':{'id':'20'}}]}]}
    p={'events':[e]}; c=copy.deepcopy(p); census={'event_ids':['1']}
    teams=[{'team_id':'10','team_name':'A'},{'team_id':'20','team_name':'B'}]
    meta={'primary_url':'https://example.org/a','control_url':'https://example.org/b','independent_census_source_url':'https://example.org/c', 'captured_at_utc':'2026-11-12T20:00:00Z','census_captured_at_utc':'2026-11-12T19:00:00Z','independent_census_verified':True}
    return p,c,census,teams,meta
class Tests(unittest.TestCase):
    def test_valid_research_only(self):self.assertEqual(audit(*fixture())['status'],'CENSUS_VERIFIED_RESEARCH')
    def test_both_truncated(self):
        a=list(fixture());a[2]['event_ids']=['1','2'];self.assertRaisesRegex(ValueError,'event_census_disagreement',audit,*a)
    def test_primary_truncated(self):
        a=list(fixture());a[1]['events'].append({'id':'2'});self.assertRaisesRegex(ValueError,'event_census_disagreement',audit,*a)
    def test_unverified_census(self):
        a=list(fixture());a[4]['independent_census_verified']=False;self.assertRaises(ValueError,audit,*a)
    def test_future_census(self):
        a=list(fixture());a[4]['census_captured_at_utc']='2026-11-13T01:00:00Z';self.assertRaises(ValueError,audit,*a)
    def test_missing_source(self):
        a=list(fixture());a[4]['primary_url']='';self.assertRaises(ValueError,audit,*a)
    def test_duplicate_mapping(self):
        a=list(fixture());a[3].append(dict(a[3][0]));self.assertRaises(ValueError,audit,*a)
    def test_unmapped_quarantine(self):
        a=list(fixture());a[3].pop();self.assertEqual(audit(*a)['status'],'QUARANTINE')
    def test_duplicate_competitor(self):
        a=list(fixture());a[0]['events'][0]['competitions'][0]['competitors'][1]['team']['id']='10';self.assertRaises(ValueError,audit,*a)
    def test_duplicate_event(self):
        a=list(fixture());a[0]['events'].append(copy.deepcopy(a[0]['events'][0]));self.assertRaises(ValueError,audit,*a)
    def test_naive_timestamp(self):
        a=list(fixture());a[4]['captured_at_utc']='2026-11-12T20:00:00';self.assertRaises(ValueError,audit,*a)
    def test_identical_source_url(self):
        a=list(fixture());a[4]['control_url']=a[4]['primary_url'];self.assertRaises(ValueError,audit,*a)
if __name__=='__main__':unittest.main()
