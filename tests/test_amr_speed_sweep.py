"""Fleet speed sweeps are exhaustive, persistent, resumable and evidence-backed."""
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
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visualiser'))
sys.path.insert(0, str(ROOT / 'report'))
from amr_scenario_study import (amr_speed_sweep_settings, validated_settings, candidate_count,
    candidate_at, candidate_events, scenario_config, trial_counts, create_study, evaluate,
    validate_study, validate_study_document, speed_sweep_summary, speed_sweep_description)
from amr_project_runs import read_json
from amr_stress_report import collect_stress_report
from tests.test_scenario_study import config, deferred_config


class SpeedSweepUnitTests(unittest.TestCase):
    def test_exact_nineteen_levels_apply_to_whole_fleet(self):
        cfg = config()
        cfg['amrs'][0]['quantity'] = 12
        cfg['amrs'].append(dict(cfg['amrs'][0], id='Other', quantity=3, speed_m_per_sec=1))
        settings = validated_settings(cfg, {'test_mode': 'amr_speed_sweep', 'assets': [], 'trial_budget': 1,
                                           'workers': 8, 'corridor_sweep_scope': 'all'})
        self.assertEqual(19, candidate_count(settings))
        self.assertEqual(dict(baseline=1, corridors=0, combined=19, total=20, candidates=19), trial_counts(cfg, settings))
        self.assertEqual(8, settings['workers'])
        for rank, speed in enumerate(range(95, 0, -5)):
            events = candidate_events(cfg, settings, candidate_at(settings, rank))
            self.assertEqual(1, len(events))
            self.assertEqual(['Other', 'R'], events[0]['resource_ids'])
            self.assertAlmostEqual(speed / 100, events[0]['speed_factor'])
            self.assertEqual(100, events[0]['availability_percent'])
        with self.assertRaises(ValueError):
            candidate_at(settings, 19)
        with self.assertRaises(ValueError):
            candidate_events(cfg, settings, [[1, 0, 0]])

    def test_every_instance_is_slowed_even_after_demand_ends(self):
        from simulator import Simulation
        cfg = config()
        cfg['amrs'][0]['quantity'] = 2
        cfg['amrs'].append(dict(cfg['amrs'][0], id='Other', quantity=1, speed_m_per_sec=1))
        from visualiser.models import JsonStore
        cfg = JsonStore(cfg).data
        settings = amr_speed_sweep_settings(cfg)
        trial = scenario_config(cfg, candidate_events(cfg, settings, candidate_at(settings, 9)), 'Half speed')
        sim = Simulation(trial)
        self.addCleanup(lambda: sim.routing_executor.shutdown() if sim.routing_executor else None)
        for amr in sim.amrs:
            for time in [0, 600, 86400, 86400 * 3]:
                self.assertEqual(.5, sim._resource_speed_factor('amr', amr.id, time)[0])
                _, duration, distance = sim._same_floor_segments(amr, sim.locations['A'], sim.locations['B'],
                    payload=sim.payloads['Box'], start_time_value=time)
                self.assertAlmostEqual(10, distance)
                self.assertAlmostEqual(10 / (amr.speed_m_per_sec * .5), duration)
        self.assertEqual(1, sim._resource_speed_factor('lift', 'unaffected', 0)[0])
        self.assertFalse(cfg.get('scenario_testing', {}).get('enabled', False))

    def test_no_amrs_or_unknown_mode_is_rejected(self):
        cfg = config()
        cfg['amrs'] = []
        with self.assertRaises(ValueError):
            validated_settings(cfg, {'test_mode': 'amr_speed_sweep'})
        with self.assertRaises(ValueError):
            validated_settings(config(), {'test_mode': 'unknown'})

    def test_partial_nonmonotonic_and_floor_results_are_explicit(self):
        def record(speed, passed):
            return dict(events=[dict(speed_factor=speed/100)], metrics=dict(passed=passed))
        baseline = dict(metrics=dict(passed=True))
        summary = speed_sweep_summary([record(95, False), record(90, True)], baseline)
        self.assertEqual(90, summary['lowest_passing_percent'])
        self.assertEqual(95, summary['first_failing_percent'])
        self.assertTrue(summary['non_monotonic'])
        self.assertFalse(summary['complete'])
        self.assertIn('provisional', speed_sweep_description(summary))
        floor = speed_sweep_summary([record(p, True) for p in range(95, 0, -5)], baseline)
        self.assertTrue(floor['complete'])
        self.assertIn('below 5% were not tested', speed_sweep_description(floor))
        self.assertEqual(100, speed_sweep_summary([record(95, False)], baseline)['lowest_passing_percent'])


class SpeedSweepIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        cls.root = Path(cls.temp.name)
        cls.path = cls.root / 'speed.stress.json'
        cfg = deferred_config(limit=1)
        cfg['task_generation']['categories']['stores']['departments']['D1'].update(
            scheduled_times=['00:01', '00:04', '00:07'], staff_handling_minutes=0)
        from visualiser.models import JsonStore
        cfg = JsonStore(cfg).data
        cls.cfg = cfg
        create_study(cfg, cls.path, amr_speed_sweep_settings(cfg, {'data_mode': 'reduced'}))
        with contextlib.redirect_stdout(io.StringIO()):
            cls.partial = evaluate(cls.path, cancel=lambda: len(read_json(cls.path)['results']) >= 4)
            cls.state = evaluate(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_cancellation_resumes_in_order_without_repeating_saved_runs(self):
        self.assertEqual('cancelled', self.partial['status'])
        self.assertEqual('complete', self.state['status'])
        self.assertEqual(20, len(self.state['results']))
        self.assertTrue(self.state['coverage']['exhaustive'])
        self.assertEqual(list(range(95, 0, -5)), [round(r['events'][0]['speed_factor']*100)
            for r in self.state['results'].values() if r['kind'] != 'baseline'])
        for identity, record in self.partial['results'].items():
            self.assertEqual(record['directory'], self.state['results'][identity]['directory'])
        validate_study(self.state)
        validate_study_document(self.state)
        passed = [r['metrics']['passed'] for r in self.state['results'].values()]
        self.assertIn(True, passed)
        self.assertIn(False, passed)
        self.assertIsNotNone(self.state['speed_sweep']['first_failing_percent'])

    def test_reduced_data_and_selected_report_summary(self):
        from amr_event_store import EventStore
        trials = [r for r in self.state['results'].values() if r['kind'] != 'baseline']
        run = Path(trials[-1]['directory'])
        manifest = read_json(run / 'run_manifest.json')
        store = EventStore(run / manifest['canonical_events'], readonly=True)
        try:
            self.assertEqual(4, store.format_version)
        finally:
            store.close()
        self.assertFalse((run / 'simulation_steps.csv').exists())
        selection = [dict(study_path=str(self.path), study_root=self.state['root'], trial_ids=[r['id'] for r in trials[:2]])]
        with contextlib.redirect_stdout(io.StringIO()):
            snapshot, _ = collect_stress_report(selection, self.cfg)
        selected = snapshot['studies'][0]
        self.assertEqual(2, selected['speed_sweep']['completed_levels'])
        self.assertFalse(selected['speed_sweep']['complete'])
        self.assertEqual([95, 90], [r['amr_speed_percent'] for r in selected['trials']])

    def test_parallel_levels_match_sequential_outcomes(self):
        path = self.root / 'parallel.stress.json'
        create_study(self.cfg, path, amr_speed_sweep_settings(self.cfg, {'data_mode': 'reduced', 'workers': 4}))
        with contextlib.redirect_stdout(io.StringIO()):
            parallel = evaluate(path)
        self.assertEqual('complete', parallel['status'])
        self.assertEqual(list(self.state['results']), list(parallel['results']))
        fields = ('passed', 'unmet_count', 'failed', 'pending', 'completed', 'late',
                  'added_delay_sec', 'latest_completion_sec')
        for identity, record in parallel['results'].items():
            self.assertEqual({k: record['metrics'][k] for k in fields},
                             {k: self.state['results'][identity]['metrics'][k] for k in fields})
        validate_study(parallel)

    def test_full_sweep_pdf_contains_speed_summary_and_all_levels(self):
        from amr_project_report import generate
        from pypdf import PdfReader
        selection = [dict(study_path=str(self.path), study_root=self.state['root'],
                          trial_ids=[k for k in self.state['results'] if k != 'baseline'])]
        with contextlib.redirect_stdout(io.StringIO()):
            pdf = generate(self.state['results']['baseline']['directory'], self.root / 'pdf', ['stress_tests'],
                           stress_selection=selection, report_title='AMR speed sweep verification')
        text = ' '.join('\n'.join(p.extract_text() for p in PdfReader(pdf).pages).split())
        self.assertIn('All-AMR speed sweep summary', text)
        self.assertIn('19 / 19 speed levels tested', text)
        self.assertIn('Highest tested failing speed', text)
        self.assertNotIn('provisional', text)
        for p in range(95, 0, -5):
            self.assertIn(f'All AMRs at {p}% speed', text)
        qa = os.environ.get('AMR_SPEED_QA_DIR')
        if qa:
            import shutil
            target = Path(qa)
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, target / 'speed-sweep-test.pdf')


class SpeedSweepUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from tests.test_scenario_stress_ui import ScenarioStressUiTests
        ScenarioStressUiTests.setUp(self)

    def close_windows(self):
        from tests.test_scenario_stress_ui import ScenarioStressUiTests
        ScenarioStressUiTests.close_windows(self)

    def test_mode_selects_all_amrs_locks_irrelevant_controls_and_persists(self):
        self.dialog.test_mode.setCurrentIndex(1)
        settings = self.dialog.settings()
        self.assertEqual('amr_speed_sweep', settings['test_mode'])
        self.assertEqual('reduced', settings['data_mode'])
        self.assertEqual([['amr', 'R']], settings['assets'])
        self.assertIn('20 total', self.dialog.trial_plan.text())
        self.assertFalse(self.dialog.assets.isEnabled())
        self.assertFalse(self.dialog.budget.isEnabled())
        self.assertTrue(self.dialog.workers.isEnabled())
        self.dialog.save_settings()
        self.dialog.set_settings(self.editor.store.scenario_testing()['stress_test'])
        self.assertEqual(settings, self.dialog.settings())
        self.dialog.test_mode.setCurrentIndex(0)
        self.assertTrue(self.dialog.assets.isEnabled())
        self.assertTrue(self.dialog.workers.isEnabled())

    def test_new_study_uses_speed_sweep_and_reopens_without_stale_settings(self):
        self.dialog.test_mode.setCurrentIndex(1)
        path = self.root / 'speed.stress.json'
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName', return_value=(str(path), '')):
            with patch.object(self.dialog, 'start') as start:
                self.dialog.new_study()
        start.assert_called_once()
        self.assertEqual(20, read_json(path)['expected_trials'])
        self.dialog.load_study(str(path))
        self.assertEqual('amr_speed_sweep', self.dialog.test_mode.currentData())
        self.assertFalse(self.dialog.stale())
        self.assertIn('provisional', self.dialog.summary.text())
