import contextlib
from copy import deepcopy
import io
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visualiser'))

from PySide6.QtCore import QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from amr_fleet_sizing import run_trial, search_fleet
from amr_memory_runs import MemoryRuns
from simulator import Simulation, TaskFailureStop
from tests.test_engineering_reference import reference_config
from visualiser.fleet_sizing_dialog import FleetSizingDialog
from visualiser.project_checks import check_project

LIMIT = 32 * 1024 ** 2


def workload():
    config = reference_config()
    config['tasks'] = [dict(id='T1', pickup='A', dropoff='B', payload='Box'),
                       dict(id='T2', pickup='A', dropoff='B', payload='Box', release_time=40)]
    return config


def outcome(count, status='passed', utilisation=99):
    return dict(count=count, total=count + 3, status=status, failed=int(status == 'failed'),
        completed=2, pending=int(status == 'incomplete'), utilisation_pct=utilisation,
        fleet_utilisation_pct=utilisation,
        first_failure=dict(task_id='T', sim_time_sec=1, reason='test failure') if status == 'failed' else None)


class TrialTests(unittest.TestCase):
    def test_real_descending_trials_do_not_mutate_or_create_files(self):
        inputs = workload()
        before = deepcopy(inputs)
        # Prime imports before observing simulation output writes.
        from report import amr_report_analysis
        with tempfile.TemporaryDirectory() as directory:
            with patch('builtins.open', wraps=open) as opened, patch('sqlite3.connect', wraps=__import__('sqlite3').connect) as connect:
                result = search_fleet(inputs, 'R', 3, 5, 0.1, memory_limit=LIMIT)
            self.assertTrue(all(call.args[0] == ':memory:' for call in connect.call_args_list))
            for call in opened.call_args_list:
                mode = call.args[1] if len(call.args) > 1 else call.kwargs.get('mode', 'r')
                self.assertFalse(any(flag in mode for flag in 'wax+'), call)
            self.assertEqual([], list(Path(directory).iterdir()))
        self.assertEqual(before, inputs)
        self.assertEqual([3, 2, 1, 0], [trial['count'] for trial in result['trials']])
        self.assertEqual(1, result['recommendation'])
        self.assertEqual(1, result['trials'][-1]['failed'])
        self.assertIsNone(result['trials'][-1]['utilisation_pct'])
        self.assertGreater(result['trials'][-2]['utilisation_pct'], result['target_pct'])

    def test_failing_trial_stops_at_first_failure_and_closes_store(self):
        config = workload()
        config['payloads'][0]['weight_kg'] = 1000
        seen, stores, events = [], [], []
        original_record = Simulation._record_failed_task
        original_init = Simulation.__init__
        original_event = Simulation._handle_event
        def record(sim, *args, **kwargs):
            seen.append(args[0])
            return original_record(sim, *args, **kwargs)
        def initialise(sim, *args, **kwargs):
            original_init(sim, *args, **kwargs)
            stores.append(sim.event_store)
        def handle(sim, event):
            events.append(event.time)
            return original_event(sim, event)
        with patch.object(Simulation, '_record_failed_task', record), patch.object(Simulation, '__init__', initialise), patch.object(Simulation, '_handle_event', handle):
            trial = run_trial(config, 'R', 1, memory_limit=LIMIT)
        self.assertEqual(['T1'], seen)
        self.assertEqual('failed', trial['status'])
        self.assertEqual('T1', trial['first_failure']['task_id'])
        self.assertTrue(stores[0].closed)
        self.assertEqual([0], events)

    def test_normal_engine_still_records_all_failures(self):
        config = workload()
        config['payloads'][0]['weight_kg'] = 1000
        sim = Simulation(config, verbose=True, memory_event_limit=LIMIT, console_progress=False)
        try:
            sim.run()
            self.assertEqual({'T1', 'T2'}, sim.failed_task_ids)
            self.assertEqual(2, len(sim.failed_tasks))
            self.assertEqual('finished', sim._evidence_run_status)
        finally:
            sim.event_store.close(flush=False)

    def test_actual_availability_failure_establishes_three_robot_boundary(self):
        config = workload()
        config['simulation'].update(max_task_deferral_minutes=.01, dispatch_available_amrs_only=True)
        config['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in range(3)]
        result = search_fleet(config, 'R', 4, 6, memory_limit=LIMIT)
        self.assertEqual([4, 3, 2], [row['count'] for row in result['trials']])
        self.assertEqual(3, result['recommendation'])
        failure = result['trials'][-1]['first_failure']
        self.assertEqual(.6, failure['sim_time_sec'])
        self.assertIn('Task deferral limit exceeded', failure['reason'])

    def test_user_cancellation_during_simulation_closes_store(self):
        cancelled = Event()
        stores = []
        handle = Simulation._handle_event
        def event(sim, item):
            stores.append(sim.event_store)
            handle(sim, item)
            cancelled.set()
        with patch.object(Simulation, '_handle_event', event):
            result = search_fleet(workload(), 'R', 2, 4, memory_limit=LIMIT, cancel=cancelled.is_set)
        self.assertEqual('cancelled', result['status'])
        self.assertEqual([], result['trials'])
        self.assertTrue(all(store.closed for store in stores))

    def test_real_expansion_and_fixed_other_type(self):
        config = workload()
        other = deepcopy(config['amrs'][0])
        other.update(id='Other', quantity=3, payload_capacity_kg=1)
        config['amrs'].append(other)
        result = search_fleet(config, 'R', 0, 3, memory_limit=LIMIT)
        self.assertEqual([0, 1], [row['count'] for row in result['trials']])
        self.assertEqual([3, 4], [row['total'] for row in result['trials']])
        self.assertEqual(1, result['recommendation'])
        self.assertEqual(3, config['amrs'][1]['quantity'])

    def test_cleanup_after_error_and_user_cancellation(self):
        stores = []
        def fail(sim):
            stores.append(sim.event_store)
            raise ValueError('broken trial')
        with patch.object(Simulation, 'run', fail), self.assertRaisesRegex(ValueError, 'broken trial'):
            run_trial(workload(), 'R', 1, memory_limit=LIMIT)
        self.assertTrue(stores[0].closed)
        with self.assertRaises(InterruptedError):
            run_trial(workload(), 'R', 1, memory_limit=LIMIT, cancel=lambda: True)


class SearchTests(unittest.TestCase):
    def test_boundary_order_target_is_reference_and_failure_is_not_retained(self):
        counts = []
        def trial(config, type_id, count, **kwargs):
            counts.append(count)
            return outcome(count, 'passed' if count >= 2 else 'failed')
        with patch('amr_fleet_sizing.run_trial', trial):
            result = search_fleet(workload(), 'R', 4, 8, 75, memory_limit=LIMIT)
        self.assertEqual([4, 3, 2, 1], counts)
        self.assertEqual(2, result['recommendation'])
        self.assertEqual(1, result['first_failing_count'])

    def test_maximum_incomplete_empty_and_zero_are_explicit(self):
        for status, expected in [('failed', 'limit'), ('incomplete', 'incomplete'), ('no_work', 'no_work')]:
            with self.subTest(status=status), patch('amr_fleet_sizing.run_trial', side_effect=lambda c, t, n, **kw: outcome(n, status)):
                result = search_fleet(workload(), 'R', 2, 3, memory_limit=LIMIT)
            self.assertEqual(expected, result['status'])
            self.assertIsNone(result['recommendation'])
        with patch('amr_fleet_sizing.run_trial', side_effect=lambda c, t, n, **kw: outcome(n)):
            result = search_fleet(workload(), 'R', 1, 3, memory_limit=LIMIT)
        self.assertEqual(0, result['recommendation'])
        self.assertIsNone(result['first_failing_count'])
        result = search_fleet(reference_config(), 'R', 1, 2, memory_limit=LIMIT)
        self.assertEqual('no_work', result['status'])

    def test_cancel_does_not_start_another_trial_or_claim_optimum(self):
        cancel = Event()
        def progress(message):
            if message['kind'] == 'trial_result':
                cancel.set()
        with patch('amr_fleet_sizing.run_trial', return_value=outcome(3)) as trial:
            result = search_fleet(workload(), 'R', 3, 5, memory_limit=LIMIT, cancel=cancel.is_set, progress=progress)
        self.assertEqual(1, trial.call_count)
        self.assertEqual('cancelled', result['status'])
        self.assertIsNone(result['recommendation'])

    def test_invalid_search_inputs(self):
        for start, maximum, target in [(3, 2, 75), (-1, 2, 75), (True, 3, 75), (1, 3, float('nan')), (1, 3, 0)]:
            with self.subTest(start=start, maximum=maximum, target=target), self.assertRaises(ValueError):
                search_fleet(workload(), 'R', start, maximum, target, memory_limit=LIMIT)


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate):
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if predicate() else None)
        poll.start(10)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        poll.stop()
        self.assertTrue(predicate(), 'worker did not finish')

    def test_dialog_full_search_checks_default_and_retained_runs(self):
        pool = MemoryRuns()
        dialog = FleetSizingDialog(workload(), ROOT, None, pool)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(75, dialog.target.value())
        self.assertEqual('R', dialog.amr_type.currentText())
        from visualiser.project_checks_panel import RunChecksDialog
        def accept(checks):
            checks.panel.check_now()
            checks.panel.report.acknowledge_warnings()
            return QDialog.Accepted
        with patch.object(RunChecksDialog, 'exec', accept):
            dialog.start_search()
            self.wait_for(lambda: dialog.job is None)
        self.assertEqual(1, dialog.result_data['recommendation'])
        self.assertIn('Recommended R count: 1', dialog.status.text())
        self.assertEqual(2, dialog.table.rowCount())
        self.assertIsNone(dialog.draft)
        self.assertEqual([], pool.runs)
        self.assertEqual(0, pool.usage())
        dialog.target.setValue(80)
        self.assertIsNone(dialog.result_data)
        self.assertEqual(0, dialog.table.rowCount())

    def test_input_checks_cancel_prevents_all_simulation(self):
        dialog = FleetSizingDialog(workload(), ROOT, None, MemoryRuns())
        self.addCleanup(dialog.deleteLater)
        with patch('visualiser.fleet_sizing_dialog.RunChecksDialog.exec', lambda checks: QDialog.Rejected), patch.object(Simulation, 'run', side_effect=AssertionError('Must not run')):
            dialog.start_search()
            self.wait_for(lambda: dialog.job is None)
        self.assertIsNone(dialog.draft)
        self.assertIsNone(dialog.result_data)
        self.assertIn('cancelled at input checks', dialog.status.text())

    def test_runs_panel_dialog_does_not_save_and_restores_editing_lock(self):
        from types import SimpleNamespace
        from visualiser.project_runs_panel import ProjectRunsPanel
        editor = QWidget()
        editor.project = None
        editor.current_json_path = None
        editor.store = SimpleNamespace(data=workload())
        editor._history_busy = lambda: False
        editor._finish_property_draft = lambda: True
        editor._commit_history = lambda: None
        locks = []
        panel = ProjectRunsPanel(editor)
        editor.sync_project_editing_lock = lambda: locks.append(panel.running())
        self.addCleanup(editor.deleteLater)
        def show(dialog):
            self.assertTrue(panel.running())
            self.assertFalse(panel.fleet_button.isEnabled())
            return QDialog.Rejected
        with patch.object(FleetSizingDialog, 'exec', show):
            panel.find_fleet_size()
        self.assertEqual([True, False], locks)
        self.assertFalse(panel.running())
        self.assertTrue(panel.fleet_button.isEnabled())

    def test_close_cancels_and_waits_for_worker_cleanup(self):
        from visualiser.fleet_sizing_dialog import SizingJob
        dialog = FleetSizingDialog(workload(), ROOT, None, MemoryRuns())
        self.addCleanup(dialog.deleteLater)
        def action(cancel, progress):
            while not cancel():
                Event().wait(.001)
            return dict(trials=[], recommendation=None, status='cancelled')
        dialog.show()
        dialog.launch(SizingJob('search', action))
        dialog.reject()
        self.assertTrue(dialog.close_when_stopped)
        self.wait_for(lambda: dialog.job is None)
        self.assertFalse(dialog.isVisible())
        self.assertIn('cancelled', dialog.status.text())


if __name__ == '__main__':
    unittest.main()
