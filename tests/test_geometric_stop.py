"""Stopped geometry retains auditable elapsed work without claiming deadlock."""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests.test_geometric_yielding import yielding_config
from tests.test_motion_dynamics_simulation import dynamics_config


class GeometricStopTests(unittest.TestCase):
    def run_saved(self, config, configure=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'steps.csv'
        sim = Simulation(config, verbose=True, verbose_csv_path=str(path))
        if configure:
            configure(sim)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        with path.open(newline='', encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        return sim, rows, json.loads(Path(str(path)+'.run.json').read_text(encoding='utf-8'))

    @staticmethod
    def blocked_config():
        config = yielding_config()
        config['geometry']['floors'][0]['passing_places'][0]['bounds'] = [23.9, -.1, 24.1, .1]
        return config

    def test_unfitting_retreat_stops_with_bound_reason_not_task_failure(self):
        sim, rows, evidence = self.run_saved(self.blocked_config())
        self.assertEqual('blocked', evidence['run_status'])
        self.assertFalse(sim.completed_task_records)
        self.assertFalse(sim.failed_task_ids)
        record = evidence['termination']
        self.assertEqual(['R-1', 'S-1'], record['amr_ids'])
        self.assertEqual(['T'], record['task_ids'])
        stop = [row for row in rows if row['event_type'] == 'geometric_simulation_stopped']
        self.assertEqual(1, len(stop))
        self.assertEqual(record['event_id'], stop[0]['event_id'])
        self.assertEqual({k: v for k, v in record.items() if k != 'event_id'}, json.loads(stop[0]['details']))
        self.assertIn('deadlock is not proven', record['message'])
        self.assertEqual('released_unfinished', evidence['partial_run']['task_outcomes'][0]['outcome'])

    def test_real_candidate_budget_exhaustion_is_search_limit(self):
        with patch('amr_geometric_recovery.MAX_RECOVERY_CANDIDATES', 1):
            _, _, evidence = self.run_saved(yielding_config())
        self.assertEqual('search_limit', evidence['run_status'])
        self.assertEqual(0, evidence['termination']['stop_time_sec'])
        self.assertIn('no deadlock', evidence['termination']['message'])

    def test_known_future_event_is_processed_before_blocked_decision(self):
        def configure(sim):
            sim.push_event(10, 'test_future_release', {})
        original = Simulation._handle_event
        visited = []
        def handle(sim, event):
            if event.event_type == 'test_future_release':
                visited.append(sim.current_time)
                sim.config['geometry']['floors'][0]['passing_places'][0]['bounds'] = [23, -1, 25, 1]
                sim._try_assign_tasks(sim.current_time)
            else:
                original(sim, event)
        with patch.object(Simulation, '_handle_event', handle):
            sim, _, evidence = self.run_saved(self.blocked_config(), configure)
        self.assertEqual([10], visited)
        self.assertEqual('finished', evidence['run_status'])
        self.assertEqual(['T'], [r['task_id'] for r in sim.completed_task_records])
        self.assertNotIn('termination', evidence)

    def test_mid_motion_stop_counts_elapsed_profile_not_committed_endpoint(self):
        original = Simulation._handle_event
        def configure(sim):
            sim.push_event(3, 'test_search_stop', {})
        def handle(sim, event):
            if event.event_type == 'test_search_stop':
                record = dict(schema_version=1, reason='search_limit', stop_time_sec=3.,
                              amr_ids=['R-1'], task_ids=['T'], message='Controlled search budget stop')
                record['event_id'] = sim.log_step(event_time=3, event_type='geometric_simulation_stopped',
                    start_time=3, end_time=3, status='search_limit', details=json.dumps(record))
                sim.geometric_termination = record
            else:
                original(sim, event)
        with patch.object(Simulation, '_handle_event', handle):
            _, _, evidence = self.run_saved(dynamics_config(), configure)
        projection = evidence['partial_run']
        self.assertFalse(evidence['summary']['completed_task_ids'])
        motion = next(a for a in projection['activities'] if a.get('planned_distance_m') == 20)
        self.assertAlmostEqual(.5, motion['elapsed_distance_m'])
        self.assertAlmostEqual(.5, motion['pose_at_cutoff']['x'])
        self.assertAlmostEqual(750*1.035/3600000, motion['elapsed_model_energy_kwh'])
        self.assertEqual('assigned_unfinished', projection['task_outcomes'][0]['outcome'])
        self.assertTrue(any(a['state'] == 'planned' for a in projection['activities']))
