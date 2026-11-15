"""Impact rankings must preserve failures, selection scope and outage comparability."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'report'))
from amr_report_stress import impact_summary


def trial(identity, assets, delay, unmet=0, **event_changes):
    return dict(id=identity, name=identity, events=[dict(resource_type='lift', resource_ids=assets,
        availability_percent=0, speed_factor=1, start_datetime='2026-01-01T00:00:00',
        end_datetime='2026-01-02T00:00:00', **event_changes)], metrics=dict(passed=not unmet,
        unmet_count=unmet, failed=unmet, pending=0, added_delay_sec=delay, latest_completion_sec=1000))


class StressImpactSummaryTests(unittest.TestCase):
    def test_failed_work_is_separate_from_largest_completed_delays(self):
        records = [trial('slow', ['L1'], 900), trial('failed', ['L2'], 10, 1),
                   trial('more-unmet', ['L3'], 0, 2)]
        summary = impact_summary(dict(trials=records))
        self.assertEqual(['more-unmet', 'failed'], [r['id'] for r in summary['failures']])
        self.assertEqual(['slow'], [r['id'] for r in summary['delays']])

    def test_complete_singles_pairs_matrix_and_criticality(self):
        records = [trial('a', ['L1'], 100), trial('b', ['L2'], 200), trial('c', ['L3'], 50),
                   trial('ab', ['L1', 'L2'], 500), trial('ac', ['L1', 'L3'], 20, 1),
                   trial('bc', ['L2', 'L3'], 300)]
        cohort = impact_summary(dict(trials=records))['cohorts'][0]
        self.assertTrue(cohort['complete_singles_pairs'])
        self.assertEqual(['L2', 'L1', 'L3'], [r['lift'] for r in cohort['criticality']])
        stats = {r['lift']: r for r in cohort['criticality']}
        self.assertEqual(400, stats['L2']['mean_pair_delay_sec'])
        self.assertEqual(500, stats['L1']['mean_pair_delay_sec'])
        self.assertEqual(1, stats['L1']['failing_pairs'])
        self.assertEqual(1, stats['L1']['passing_pairs'])
        self.assertEqual('ab', cohort['cells'][('L1', 'L2')]['id'])

    def test_different_windows_slowdowns_and_mixed_resources_are_not_pooled(self):
        a = trial('a', ['L1'], 100)
        b = trial('b', ['L2'], 200)
        b['events'][0]['start_datetime'] = '2026-01-01T01:00:00'
        slow = trial('slow', ['L1', 'L2'], 300)
        slow['events'][0].update(availability_percent=100, speed_factor=.5)
        mixed = trial('mixed', ['L1'], 400)
        mixed['events'].append(dict(a['events'][0], resource_type='corridor'))
        staggered = trial('staggered', ['L1'], 500)
        staggered['events'].append(b['events'][0])
        summary = impact_summary(dict(trials=[a, b, slow, mixed, staggered]))
        self.assertEqual(5, len(summary['delays']))
        self.assertEqual(2, len(summary['cohorts']))
        self.assertTrue(all(len(c['singles']) == 1 and not c['pairs'] for c in summary['cohorts']))

    def test_missing_single_and_pair_are_not_assumed_zero(self):
        cohort = impact_summary(dict(trials=[trial('a', ['L1'], 100),
                     trial('bc', ['L2', 'L3'], 300)]))['cohorts'][0]
        self.assertFalse(cohort['complete_singles_pairs'])
        stats = {r['lift']: r for r in cohort['criticality']}
        self.assertIsNone(stats['L2']['single'])
        self.assertIsNone(stats['L1']['mean_pair_delay_sec'])
        self.assertNotIn(('L1', 'L2'), cohort['cells'])

    def test_duplicate_pair_is_conservative_and_does_not_double_count(self):
        good = trial('good', ['L1', 'L2'], 900)
        bad = trial('bad', ['L2', 'L1'], 10, 1)
        cohort = impact_summary(dict(trials=[good, bad]))['cohorts'][0]
        self.assertEqual(1, cohort['repeated'])
        self.assertEqual(1, len(cohort['pairs']))
        self.assertEqual('bad', cohort['cells'][('L1', 'L2')]['id'])
        self.assertIsNone(cohort['criticality'][0]['mean_pair_delay_sec'])

    def test_triples_are_ranked_but_do_not_fill_single_pair_matrix(self):
        summary = impact_summary(dict(trials=[trial('abc', ['L1', 'L2', 'L3'], 1000)]))
        self.assertEqual('abc', summary['delays'][0]['id'])
        self.assertFalse(summary['cohorts'][0]['complete_singles_pairs'])
        self.assertEqual([], summary['cohorts'][0]['pairs'])

    def test_zero_speed_counts_as_shutdown_and_summary_does_not_mutate(self):
        a = trial('a', ['L1'], 100)
        a['events'][0].update(availability_percent=100, speed_factor=0)
        original = deepcopy(a)
        self.assertEqual(1, len(impact_summary(dict(trials=[a]))['cohorts']))
        self.assertEqual(original, a)
        self.assertEqual([], impact_summary(dict(trials=[]))['cohorts'])
