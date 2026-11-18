import contextlib
from copy import deepcopy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))

from PySide6.QtCore import QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QWidget
from amr_memory_runs import MemoryRuns
from amr_run_utilisation import load_memory_utilisation, summarise_utilisation
from tests.test_engineering_reference import reference_config
from visualiser.project_checks import check_project
from visualiser.project_runs_panel import ProjectRunsPanel
from visualiser.run_utilisation_dialog import RunUtilisationDialog


def evidence(seconds=100):
    return dict(frozen_inputs=dict(simulation=dict(start_datetime='2026-01-01T00:00:00',
                                                 duration_hours=seconds / 3600),
                                   lifts=[dict(id='L1'), dict(id='L2')]),
                summary=dict(battery_amr_ids=['R-1', 'R-2']))


def segment(start, duration, *, amr='R-1', lift='', kind='corridor'):
    return dict(sim_time_sec=start, duration_sec=duration, amr_id=amr, lift_id=lift,
                event_type='segment_' + kind, segment_type=kind)


class UtilisationMathTests(unittest.TestCase):
    def test_overlaps_shared_routes_idle_resources_and_waits(self):
        rows = [segment(10, 20), segment(10, 20), segment(20, 20),
                segment(40, 10, kind='wait'), segment(60, 10, kind='charge'),
                segment(15, 10, lift='L1', kind='lift_transfer'),
                segment(20, 10, amr='', lift='L1', kind='lift_reposition'),
                segment(0, 80, amr='-')]
        result = summarise_utilisation(rows, evidence())
        self.assertEqual(100, result['horizon_seconds'])
        first, idle = result['amrs']
        self.assertEqual(('R-1', 50, 50, 50),
                         (first['id'], first['busy_seconds'], first['idle_seconds'], first['utilisation_pct']))
        self.assertEqual(0, idle['busy_seconds'])
        self.assertEqual(100, idle['idle_seconds'])
        self.assertEqual(15, result['lifts'][0]['busy_seconds'])
        self.assertEqual(0, result['lifts'][1]['utilisation_pct'])

    def test_window_includes_delayed_start_and_post_horizon_work(self):
        result = summarise_utilisation([segment(80, 70), dict(sim_time_sec=150)], evidence())
        self.assertEqual(150, result['horizon_seconds'])
        self.assertEqual(70, result['amrs'][0]['busy_seconds'])
        self.assertAlmostEqual(100 * 70 / 150, result['amrs'][0]['utilisation_pct'])

    def test_future_plans_are_bounded_and_zero_window_is_unknown(self):
        result = summarise_utilisation([segment(80, 100)], evidence())
        self.assertEqual(20, result['amrs'][0]['busy_seconds'])
        zero = summarise_utilisation([], evidence(0))
        self.assertIsNone(zero['amrs'][0]['utilisation_pct'])

    def test_report_gap_convention_and_precise_time(self):
        first = segment(10, 10)
        first['precise_time_sec'] = 10.25
        result = summarise_utilisation([first, segment(21, 9)], evidence())
        self.assertEqual(19.75, result['amrs'][0]['busy_seconds'])

    def test_cancelled_scan_stops(self):
        with self.assertRaises(InterruptedError):
            summarise_utilisation([segment(0, 10)], evidence(), cancel=lambda: True)


class MemoryUtilisationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.pool = MemoryRuns()
        self.addCleanup(self.pool.clear)
        inputs = reference_config()
        inputs['amrs'][0]['quantity'] = 2
        inputs['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        self.run = self.retain(inputs)

    def retain(self, inputs):
        run = self.pool.prepare(inputs, self.temporary.name)
        checks = check_project(run.config, asset_refs=run.asset_refs)
        checks.acknowledge_warnings()
        run.accept_checks(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            run.execute(self.pool.reserve(run))
        self.pool.add(run)
        return run

    def test_real_shared_lift_journey_counts_once_and_includes_idle_lift(self):
        from tests.test_multi_stop_route_rules import multi_lift_config
        inputs = multi_lift_config()
        inputs['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
        run = self.retain(inputs)
        result = load_memory_utilisation(run)
        self.assertEqual(2, len(run.evidence['summary']['completed_task_ids']))
        self.assertEqual(['L1', 'L2'], [row['id'] for row in result['lifts']])
        self.assertEqual(1, result['lifts'][0]['busy_seconds'])
        self.assertEqual(0, result['lifts'][1]['busy_seconds'])
        # Shared pickup 2s, two 0.5s connectors, 1s lift, two dropoffs 4s.
        self.assertEqual(8, result['amrs'][0]['busy_seconds'])
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))

    def test_memory_summary_never_reruns_or_exports_and_uses_frozen_inputs(self):
        from simulator import Simulation
        with patch.object(Simulation, 'run', side_effect=AssertionError('Must not rerun')):
            result = load_memory_utilisation(self.run)
        self.assertEqual([], list(Path(self.temporary.name).iterdir()))
        self.assertEqual(600, result['horizon_seconds'])
        self.assertEqual(['R-1', 'R-2'], [row['id'] for row in result['amrs']])
        self.assertGreater(sum(row['busy_seconds'] for row in result['amrs']), 0)
        self.assertEqual(0, result['amrs'][1]['busy_seconds'])
        self.assertEqual([], result['lifts'])
        self.assertEqual(result, load_memory_utilisation(self.run))

    def test_partial_reduced_and_discarded_runs_cannot_claim_utilisation(self):
        self.run.status = 'partial'
        with self.assertRaisesRegex(ValueError, 'completed runs'):
            load_memory_utilisation(self.run)
        self.run.status = 'complete'
        metadata = deepcopy(self.run.evidence)
        metadata['reduced_logging'] = True
        with patch.object(type(self.run), 'evidence', new=property(lambda _: metadata)):
            with self.assertRaisesRegex(ValueError, 'full event evidence'):
                load_memory_utilisation(self.run)
        self.pool.discard(self.run)
        with self.assertRaises(ValueError):
            load_memory_utilisation(self.run)

    def test_background_dialog_loads_both_resource_tabs(self):
        dialog = RunUtilisationDialog(self.run)
        self.addCleanup(dialog.deleteLater)
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if dialog.result_data is not None else None)
        poll.start(10)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        poll.stop()
        self.assertIsNotNone(dialog.result_data, dialog.summary.text())
        self.assertEqual(2, dialog.tables['amrs'].rowCount())
        self.assertEqual(0, dialog.tables['lifts'].rowCount())
        self.assertIn('No lifts', dialog.summary.text())
        dialog.reject()
        self.assertTrue(QThreadPool.globalInstance().waitForDone(10000))

    def test_selection_action_cache_and_discard_lifecycle(self):
        editor = QWidget()
        editor.project = None
        panel = ProjectRunsPanel(editor)
        self.addCleanup(editor.deleteLater)
        self.assertFalse(panel.utilisation_button.isEnabled())
        panel.memory = self.pool
        panel.refresh_runs(select=self.run)
        self.assertTrue(panel.utilisation_button.isEnabled())
        result = load_memory_utilisation(self.run)
        with patch('visualiser.run_utilisation_dialog.RunUtilisationDialog') as constructor:
            constructor.return_value.result_data = result
            panel.view_utilisation()
            self.assertIsNone(constructor.call_args.kwargs['cached'])
            panel.view_utilisation()
            self.assertIs(result, constructor.call_args.kwargs['cached'])
        self.run.status = 'partial'
        panel._update_selection_actions()
        self.assertFalse(panel.utilisation_button.isEnabled())
        self.run.status = 'complete'
        panel.discard_memory_run()
        self.assertEqual({}, panel.utilisation_cache)
        self.assertFalse(panel.utilisation_button.isEnabled())

    def test_closing_dialog_cancels_worker_and_ignores_late_result(self):
        with patch('visualiser.run_utilisation_dialog.QThreadPool.globalInstance'):
            dialog = RunUtilisationDialog(self.run)
        job = dialog.job
        dialog.reject()
        self.assertTrue(job.cancelled.is_set())
        dialog.loaded(dict(horizon_seconds=1, amrs=[], lifts=[]), '')
        self.assertIsNone(dialog.result_data)
        dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
