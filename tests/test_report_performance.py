"""Baseline comparison calculations and the actual Report worker entry point."""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from pypdf import PdfReader
from PySide6.QtCore import QEventLoop, QTimer, Qt

from amr_project import Project
from amr_project_report import report_sections
from amr_project_runs import PreparedRun, execute
from tests import test_lift_movement_charts_ui as charts_ui
from tests.test_lift_integration import two_lifts
from visualiser.project_checks import check_project
from visualiser.project_report_panel import ProjectReportPanel

report_sections()
from amr_report_performance import Observation, Request, assess_funnel, comparison_results, read_observation
from amr_route_analysis import CONFIRMED


class PerformanceCalculationTests(unittest.TestCase):
    def test_checkpoint_and_shared_time_are_counted_once(self):
        fields = ['event_id', 'event_type', 'task_id', 'sim_time_sec', 'amr_id', 'details', 'duration_sec', 'segment_type']

        def event(kind, identity, when, **values):
            return dict(event_type=kind, task_id=identity, sim_time_sec=when, **values)

        rows = [event('task_released', identity, 0, details='{"deadline": 80}') for identity in ('A', 'B', 'C')]
        rows += [event('task_assigned', identity, 10, amr_id='AMR-1') for identity in ('A', 'B')]
        rows += [event('segment_lift_reposition', 'A,B', 20, amr_id='AMR-1', duration_sec=30,
                       segment_type='lift_reposition'),
                 event('segment_wait_for_lift', 'A,B', 30, amr_id='AMR-1', duration_sec=15,
                       segment_type='wait_for_lift'),
                 event('task_complete', 'A', 60), event('task_complete', 'B', 120),
                 event('task_failed', 'C', 85, details='No permitted AMR route')]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.csv'
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(dict(row, event_id=index) for index, row in enumerate(rows))
            observation = read_observation(path, 100)
        self.assertEqual({'A': 60.}, observation.completed)
        self.assertEqual(1.5, observation.busy_minutes)
        self.assertEqual(.5, observation.wait_p95_minutes)
        self.assertEqual({'A', 'B', 'C'}, set(observation.planned(100)))
        self.assertEqual({'C': 'No permitted AMR route'}, observation.failures)

    def test_indices_explain_different_workloads_and_zero_wait(self):
        requests = {key: Request(0, 100, 'Waste', 'A', 'B', 'Box', 1) for key in ('A', 'B')}
        baseline = Observation(requests, {'A': 60, 'B': 65}, busy_minutes=2, wait_p95_minutes=0)
        scenario = Observation(dict(requests), {'A': 90}, busy_minutes=1.25, wait_p95_minutes=3)
        result = comparison_results(baseline, scenario, 100, None, {}, {}, 'base', 'trial')
        self.assertEqual(.5, result['scenario']['spi'])
        self.assertEqual(.8, result['scenario']['cpi'])
        self.assertEqual(.5, result['scenario']['sla'])
        self.assertIsNone(result['scenario']['wait_ratio'])
        scenario.requests.pop('B')
        self.assertIsNone(comparison_results(baseline, scenario, 100, None, {}, {}, 'base', 'trial')['scenario']['spi'])

    def test_funnel_distinguishes_pass_through_and_the_profiles_of_carried_tasks(self):
        def leg(identity, floor, lift):
            segment = SimpleNamespace(id=identity, kind='lift_transfer', start=(0, 0, 0), finish=(0, 0, floor),
                                      lift=lift, detail={'exit_time_sec': 1})
            return SimpleNamespace(segments=[segment], time=0, end=5, evidence=CONFIRMED,
                                   confirmation_ids=('done',), profile='dirty', purpose='Delivery')

        run = SimpleNamespace(config={}, complete=True, legs=[leg('compliant', 2, 'L1'),
            leg('crossing', 3, 'L1'), leg('exempt', 2, 'L5')])
        observation = Observation(confirmations={'done': 5}, profiles={'profiled': 'dirty'},
                                  onboard={'compliant': ('unprofiled',), 'crossing': ('unprofiled',),
                                           'exempt': ('unprofiled', 'profiled')})
        result = assess_funnel(run, (0, 2, {'L1'}), observation, 10)
        self.assertEqual({'compliant': 1, 'outside': 1, 'exempt': 1}, dict(result))


class PerformanceReportUiTests(unittest.TestCase):
    setUpClass = classmethod(charts_ui.LiftMovementChartUiTests.setUpClass.__func__)
    setUp = charts_ui.LiftMovementChartUiTests.setUp
    tearDown = charts_ui.LiftMovementChartUiTests.tearDown

    def test_panel_selects_a_baseline_and_generates_the_comparison(self):
        config = two_lifts()
        config['tasks'] = [dict(id='T1', pickup='A', dropoff='B2', payload='Box', target_time=600)]
        config['building'].update(force_via_floor_enabled=True, force_via_floor=2,
                                  forced_floor_lift_preference=dict(mode='off', from_floor=0, lift_ids=['NearOrigin']))
        paths = []
        for mode in ('off', 'required'):
            project = Project()
            target = Path(self.temp.name) / f'comparison-{mode}.amrproj'
            config['building']['forced_floor_lift_preference']['mode'] = mode
            project.save(target, config)
            prepared = PreparedRun(project, Path(self.temp.name) / 'runs')
            checks = check_project(prepared.config)
            checks.acknowledge_warnings()
            directory = prepared.commit(checks)
            with contextlib.redirect_stdout(io.StringIO()):
                execute(directory)
            paths.append(directory)
        self.editor.project = project
        panel = ProjectReportPanel(self.editor)
        panel.set_run(paths[1])
        section = 'lift_performance_comparison'
        for index in range(panel.sections.count()):
            item = panel.sections.item(index)
            self.assertTrue(item.data(Qt.UserRole) != section or item.checkState() == Qt.Unchecked)
            item.setCheckState(Qt.Unchecked)
        with self.assertRaisesRegex(ValueError, 'different completed run'):
            panel.set_baseline(paths[1])
        panel.set_baseline(paths[0])
        panel.generate()
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if not panel.running() else None)
        timer.start(20)
        QTimer.singleShot(60000, loop.quit)
        loop.exec()
        timer.stop()
        if panel.running():
            panel.cancel()
            self.fail('PDF comparison did not complete within one minute.')
        self.assertIsNotNone(panel.pdf, panel.log.toPlainText())
        manifest = json.loads((panel.output / 'report_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual([section], manifest['sections'])
        self.assertEqual(str(paths[0]), manifest['comparison_baseline']['path'])
        text = '\n'.join(page.extract_text() for page in PdfReader(panel.pdf).pages)
        self.assertIn('Lift preference performance comparison', text)
        self.assertIn('100.0% (1/1)', text)
        self.assertIn('Funnel compliance\n0.0% (0/1)\n100.0% (1/1)', text)
