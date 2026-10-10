"""Verified partial playback stops at elapsed motion, not its booked endpoint."""
import contextlib
from datetime import timedelta
import io
import json
import unittest
from unittest.mock import patch

from tests import test_project_runs as runs
from tests.test_motion_dynamics_simulation import dynamics_config
from simulator import Simulation
from amr_project_runs import execute, read_json
from amr_run_review import verified_inputs
from visualiser.project_playback_panel import load_playback, BoundVisualizer, PartialSimulationLog
from visualiser.results_investigation_panel import load_review, ResultsInvestigationPanel
from amr_sim_visualiser_pyside6 import LayoutModel, VisualEvent
from amr_trajectories import plan_trajectory
from PySide6.QtWidgets import QApplication, QWidget


class PartialLogBoundaryTests(unittest.TestCase):
    def test_clipping_a_record_does_not_accelerate_its_geometry(self):
        layout = LayoutModel()
        layout.load_data(dynamics_config())
        start = layout.simulation_start_time
        trajectory = plan_trajectory([(0, 0), (10, 0)], minimum_radius_m=2,
            speed_m_per_sec=1, pivot_allowed=False, pivot_speed_deg_per_sec=45)
        row = dict(amr_id='R-1', task_id='T', event_type='segment_corridor',
            segment_type='corridor', status='planned', start_node='A', end_node='B',
            start_x='0', start_y='0', end_x='10', end_y='0', start_floor='0', end_floor='0',
            duration_sec='10', motion_model='geometric_v1', trajectory_json=json.dumps(trajectory.to_dict()))
        log = PartialSimulationLog()
        log.events = [VisualEvent(start, start+timedelta(seconds=10), row)]
        log.bound(start, dict(reason='blocked', message='Stop', stop_time_sec=3))
        self.assertEqual(start+timedelta(seconds=3), log.events[0].end_time)
        for seconds, expected in [(3, 3), (100, 3), (1, 1)]:
            state = log.state_at(start+timedelta(seconds=seconds), layout)[0]['R-1']
            self.assertAlmostEqual(expected, state['x'])


class PartialPlaybackTests(unittest.TestCase):
    prepare = runs.ProjectRunTests.prepare

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        runs.ProjectRunTests.setUp(self)
        self.config = dynamics_config()
        self.project.save(self.project.path, self.config)

    def partial_run(self, stop=3):
        directory = self.prepare()
        original = Simulation._handle_event

        def handle(sim, event):
            if event.event_type == 'test_partial_stop':
                record = dict(schema_version=1, reason='blocked', stop_time_sec=event.time,
                    message='Controlled stop during motion', amr_ids=['R-1'], task_ids=['T'])
                record['event_id'] = sim.log_step(event_time=event.time,
                    event_type='geometric_simulation_stopped', start_time=event.time,
                    end_time=event.time, status='blocked', details=json.dumps(record, sort_keys=True))
                sim.geometric_termination = record
                return
            original(sim, event)
            if event.event_type == 'task_release':
                sim.push_event(stop, 'test_partial_stop', {})

        with patch.object(Simulation, '_handle_event', handle), contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        self.assertEqual('partial', read_json(directory/'run_manifest.json')['status'])
        return directory

    def test_mid_motion_stop_preserves_position_and_hides_future_activity(self):
        directory = self.partial_run()
        before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        _, manifest, layout, log = load_playback(directory)
        cutoff = log.start_time+timedelta(seconds=3)
        self.assertEqual(cutoff, log.end_time)
        self.assertTrue(all(event.end_time <= cutoff for event in log.events))
        self.assertFalse(any(e.row['event_type'] == 'segment_dropoff' for e in log.events))
        for seconds, x in [(3, .5), (100, .5), (2.5, .125), (3, .5)]:
            state = log.state_at(log.start_time+timedelta(seconds=seconds), layout)[0]['R-1']
            self.assertAlmostEqual(x, state['x'], delta=.001)
            self.assertNotEqual('completed', state['raw']['status'])
        self.assertEqual('blocked', manifest['termination']['reason'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()})

    def test_viewer_clamps_configured_horizon_and_direct_seek(self):
        data = load_playback(self.partial_run())
        parent = QWidget()
        viewer = BoundVisualizer(parent)
        try:
            viewer.adopt(data)
            cutoff = data[3].stop_time
            self.assertEqual(cutoff, viewer.sim_log.end_time)
            viewer.on_timeline_seek(cutoff+timedelta(days=1))
            self.assertEqual(cutoff, viewer.current_time)
        finally:
            viewer.close()
            parent.close()

    def test_investigation_explains_stop_and_withholds_full_run_metrics(self):
        directory = self.partial_run()
        result = load_review(directory)
        self.assertFalse(result['complete_evidence'])
        self.assertEqual(3, result['termination']['stop_time_sec'])
        self.assertTrue(all(m['value'] is None and m['observed_count'] is None for m in result['metrics']))
        self.assertNotEqual('completed', result['tasks'][0]['outcome'])
        panel = ResultsInvestigationPanel()
        try:
            panel.accept_result(result)
            self.assertIn('blocked at 3 s', panel.summary.text())
            self.assertIn('Controlled stop', panel.summary.text())
        finally:
            panel.close()
        with self.assertRaises(ValueError):
            verified_inputs(directory)  # Reports retain the complete-only boundary.

    def test_changed_partial_evidence_is_not_opened(self):
        directory = self.partial_run()
        manifest = read_json(directory/'run_manifest.json')
        manifest['termination']['stop_time_sec'] = 100
        (directory/'run_manifest.json').write_text(json.dumps(manifest))
        for loader in (load_playback, load_review):
            with self.subTest(loader=loader.__name__), self.assertRaises(ValueError):
                loader(directory)


if __name__ == '__main__':
    unittest.main()
