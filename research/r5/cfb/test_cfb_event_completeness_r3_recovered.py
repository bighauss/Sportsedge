"""Adversarial coverage for R3 recovered candidate; not original R3's test file."""
import copy
import unittest
from sportsedge_cfb_event_completeness_r3 import audit


def fixture():
    e = {"id": "11", "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": "22"}},
        {"homeAway": "away", "team": {"id": "33"}},
    ]}]}
    meta = {"primary_url":"https://a.example/snap", "control_url":"https://b.example/snap",
            "independent_census_source_url":"https://third.example/census",
            "captured_at_utc":"2026-11-12T20:00:00Z", "census_captured_at_utc":"2026-11-12T19:00:00Z",
            "independent_census_verified": True}
    p={"events":[e]}
    return [p, copy.deepcopy(p), {"event_ids":["11"]},
            [{"team_id":"22", "team_name":"Home"}, {"team_id":"33", "team_name":"Away"}], meta]


class RecoveredR3Tests(unittest.TestCase):
    def assert_bad(self, mutate, match=None):
        a=fixture(); mutate(a)
        if match:
            with self.assertRaisesRegex(ValueError, match): audit(*a)
        else:
            with self.assertRaises(ValueError): audit(*a)

    def test_valid_structural_only(self):
        result=audit(*fixture())
        self.assertEqual(result['status'],'STRUCTURAL_PASS_SOURCE_AUTH_PENDING')
        self.assertFalse(result['source_admitted'])
        self.assertEqual(result['release_status'],'PAPER_0U')
        self.assertEqual(result['event_count'],1)
    def test_string_false_flag(self): self.assert_bad(lambda a:a[4].update(independent_census_verified='false'), 'boolean')
    def test_number_one_flag(self): self.assert_bad(lambda a:a[4].update(independent_census_verified=1), 'boolean')
    def test_flag_missing(self): self.assert_bad(lambda a:a[4].pop('independent_census_verified'), 'boolean')
    def test_empty_team_primary(self): self.assert_bad(lambda a:a[0]['events'][0]['competitions'][0]['competitors'][0]['team'].update(id=' '), 'blank_team_id')
    def test_empty_team_control(self): self.assert_bad(lambda a:a[1]['events'][0]['competitions'][0]['competitors'][1]['team'].update(id=''), 'blank_team_id')
    def test_duplicate_role_primary(self): self.assert_bad(lambda a:a[0]['events'][0]['competitions'][0]['competitors'][0].update(homeAway='away'), 'duplicate_homeAway')
    def test_duplicate_role_control(self): self.assert_bad(lambda a:a[1]['events'][0]['competitions'][0]['competitors'][0].update(homeAway='away'), 'duplicate_homeAway')
    def test_missing_role(self): self.assert_bad(lambda a:a[0]['events'][0]['competitions'][0]['competitors'][0].pop('homeAway'), 'invalid_homeAway')
    def test_diff_competitors_same_event(self): self.assert_bad(lambda a:a[1]['events'][0]['competitions'][0]['competitors'][0]['team'].update(id='44'), 'competitor_identity_disagreement')
    def test_shared_truncated(self): self.assert_bad(lambda a:a[2]['event_ids'].append('99'), 'event_census_disagreement')
    def test_duplicate_census(self): self.assert_bad(lambda a:a[2]['event_ids'].append('11'), 'duplicate_census_event_id')
    def test_duplicate_primary(self): self.assert_bad(lambda a:a[0]['events'].append(copy.deepcopy(a[0]['events'][0])), 'duplicate_event_id')
    def test_empty_mapping(self):
        a=fixture(); a[3]=[]
        self.assertEqual(audit(*a)['status'],'QUARANTINE')
    def test_missing_mapped_competitor(self):
        a=fixture(); a[3].pop()
        self.assertEqual(audit(*a)['status'],'QUARANTINE')
    def test_duplicate_mapping(self): self.assert_bad(lambda a:a[3].append(copy.deepcopy(a[3][0])), 'duplicate_team_mapping')
    def test_same_census_url(self): self.assert_bad(lambda a:a[4].update(independent_census_source_url=a[4]['primary_url']), 'repeated_source_url')
    def test_bad_url(self): self.assert_bad(lambda a:a[4].update(control_url='file:///tmp/clone'), 'invalid_control_url')
    def test_naive_capture(self): self.assert_bad(lambda a:a[4].update(captured_at_utc='2026-11-12T20:00:00'), 'naive_capture_timestamp')
    def test_future_census(self): self.assert_bad(lambda a:a[4].update(census_captured_at_utc='2026-11-12T21:00:00Z'), 'future_census')
    def test_control_competitions_missing(self): self.assert_bad(lambda a:a[1]['events'][0].update(competitions=[]), 'invalid_competitions')
    def test_empty_event_id(self): self.assert_bad(lambda a:a[0]['events'][0].update(id=None), 'invalid_event_id')
    def test_non_dict(self): self.assert_bad(lambda a:a.__setitem__(0, [1]), 'primary_not_object')
    def test_blank_map_id(self): self.assert_bad(lambda a:a[3][0].update(team_id=''), 'bad_team_mapping')


if __name__ == '__main__':unittest.main()
