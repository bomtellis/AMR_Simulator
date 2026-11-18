"""Failure evidence, in-memory review and ETA regressions."""
from pathlib import Path
import tempfile
import unittest

from amr_failure_review import _breakdown, compare_failure_reviews, load_failure_review
from amr_memory_runs import MemoryRuns
from amr_simulation_progress import ProgressEstimate
from tests.test_engineering_reference import reference_config
from visualiser.project_checks import check_project


class FailureInvestigationTests(unittest.TestCase):
    def test_spare_delay_partitions_the_failure_window_and_links_events(self):
        rows = [
            dict(event_type='task_blocker_changed', task_id='full', sim_time_sec=10, event_id='wait',
                 details='{"blocker":"Spare bin","spares":[{"task_id":"spare"}]}'),
            dict(event_type='task_dispatch_committed', task_id='spare', sim_time_sec=20, event_id='booking',
                 details='{"start":35}'),
            dict(event_type='segment_corridor', task_id='spare', sim_time_sec=35, duration_sec=10, event_id='travel'),
            dict(event_type='segment_wait', task_id='spare', sim_time_sec=45, duration_sec=30, event_id='lift',
                 lift_id='Lift A'),
            dict(event_type='waste_replacement_staged', task_id='spare', sim_time_sec=80, event_id='arrival'),
        ]
        task = dict(id='full', release=10, end=60, end_id='failed', reason='Task deferral limit exceeded')
        parts = _breakdown(task, rows, {'full': '', 'spare': ''}, True)
        self.assertEqual([('Waiting for dispatch', 10), ('Booked AMR not started', 15),
                          ('Travel and handling', 10), ('Lift wait', 15)],
                         [(p['category'], p['end'] - p['start']) for p in parts])
        self.assertEqual(('failed', 'wait', 'booking', 'lift'), parts[-1]['event_ids'])

    def test_inspection_and_comparison_read_memory_until_explicit_save(self):
        config = reference_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool = MemoryRuns()
            self.addCleanup(pool.clear)
            run = pool.prepare(config, root)
            checks = check_project(run.config, asset_refs=run.asset_refs)
            checks.acknowledge_warnings()
            run.accept_checks(checks)
            messages = []
            run.execute(pool.reserve(run), progress=messages.append)
            pool.add(run)
            live = load_failure_review(run)
            self.assertTrue(live.structured)
            self.assertEqual('Completed', live.tasks['T']['outcome'])
            self.assertEqual(0, live.tasks['T']['dispatch'])
            self.assertEqual([], list(root.iterdir()))
            self.assertIn('simulation', [msg['stage'] for msg in messages])
            self.assertEqual('finalizing', messages[-1]['stage'])
            _, folder = run.publish(None, root / 'comparison.amrproj')
            disk = load_failure_review(folder)
            self.assertEqual(live.detail('T'), disk.detail('T'))
            self.assertEqual(dict(groups=[], requests=[], unmatched=[]), compare_failure_reviews(live, disk))
            pool.discard(run)
            with self.assertRaises((ValueError, InterruptedError)):
                live.detail('T')

    def test_eta_requires_advance_and_expires_when_stalled(self):
        estimate = ProgressEstimate()
        for timestamp, current in ((0, 0), (1, 10), (2, 20)):
            estimate.update(dict(stage='simulation', phase='Running simulation', clock=timestamp,
                                 current=current, total=100), timestamp)
            if timestamp < 2:
                self.assertIsNone(estimate.display(timestamp)[1])
        self.assertEqual((20, 8, ''), estimate.display(2))
        self.assertIsNone(estimate.display(12)[0])
        estimate.update(dict(stage='drain', phase='Finishing released work', clock=13), 13)
        self.assertIsNone(estimate.display(13)[1])
