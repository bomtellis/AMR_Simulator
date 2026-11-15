"""Retired GPU projects use CPU while frozen historical evidence stays verifiable."""
import contextlib
from copy import deepcopy
import io
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from amr_project import Project
from amr_project_runs import PreparedRun, execute, read_json, write_json
from amr_run_review import verified_events
from amr_scenario_study import create_study, validate_study
from amr_simulation_inputs import DEFAULTS, resolved_simulation_settings
from simulator import Simulation
from tests.test_compact_execution import normalise
from tests.test_scenario_study import config
from visualiser.dialogs import SimulationSettingsDialog
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class CpuOnlyComputationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.legacy = config()
        self.legacy['simulation']['computation_backend'] = 'gpu'

    def test_import_and_settings_save_remove_retired_selector(self):
        before = deepcopy(self.legacy)
        self.assertNotIn('computation_backend', DEFAULTS)
        self.assertNotIn('computation_backend', resolved_simulation_settings(self.legacy['simulation']))
        store = JsonStore(self.legacy)
        self.assertNotIn('computation_backend', store.data['simulation'])
        dialog = SimulationSettingsDialog(None, self.legacy['simulation'], full_config=self.legacy)
        self.addCleanup(dialog.close)
        self.assertNotIn('Computation', [dialog.delivery_tabs.tabText(i) for i in range(dialog.delivery_tabs.count())])
        dialog.accept()
        self.assertIsNotNone(dialog.project_result)
        self.assertNotIn('computation_backend', dialog.result)
        self.assertNotIn('computation_backend', dialog.project_result['simulation'])
        self.assertEqual(before, self.legacy)

    def test_retired_setting_has_identical_cpu_outcomes_and_evidence(self):
        simulations = []
        for index, source in enumerate((config(), self.legacy)):
            with contextlib.redirect_stdout(io.StringIO()):
                sim = Simulation(source, verbose=True, defer_exports=True,
                                 event_store_path=self.root / f'events-{index}.sqlite')
                self.addCleanup(sim.event_store.close)
                sim.run()
            simulations.append(sim)
        cpu, legacy = simulations
        self.assertEqual(cpu.current_time, legacy.current_time)
        self.assertEqual(cpu.failed_task_ids, legacy.failed_task_ids)
        self.assertEqual(normalise(cpu.completed_task_records, cpu.run_id),
                         normalise(legacy.completed_task_records, legacy.run_id))
        self.assertEqual(normalise(list(cpu.verbose_rows), cpu.run_id),
                         normalise(list(legacy.verbose_rows), legacy.run_id))
        self.assertEqual('gpu', self.legacy['simulation']['computation_backend'])

    def run_legacy_project(self):
        project = Project()
        project.save(self.root / 'legacy.amrproj', self.legacy)
        draft = PreparedRun(project, self.root / 'runs')
        checks = check_project(draft.config)
        self.assertFalse(any(item.code == 'COMPUTATION_UNAVAILABLE' for item in checks.findings))
        checks.acknowledge_warnings()
        directory = draft.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        return directory

    def test_new_run_from_retired_gpu_project_is_verified_without_backend(self):
        manifest, frozen, path, _ = verified_events(self.run_legacy_project())
        self.assertNotIn('computation', manifest)
        self.assertNotIn('computation', read_json(str(path) + '.run.json'))
        self.assertEqual('gpu', frozen['simulation']['computation_backend'])

    def test_historical_backend_provenance_remains_checked_without_cuda(self):
        directory = self.run_legacy_project()
        manifest, _, path, _ = verified_events(directory)
        identity = dict(requested='gpu', implementation='historical_cuda', device='archived GPU')
        manifest['computation'] = identity
        write_json(directory / 'run_manifest.json', manifest)
        evidence = read_json(str(path) + '.run.json')
        evidence['computation'] = dict(identity, statistics={'gpu_route_queries': 100})
        write_json(str(path) + '.run.json', evidence)
        verified_events(directory)
        evidence['computation']['device'] = 'different GPU'
        write_json(str(path) + '.run.json', evidence)
        with self.assertRaisesRegex(ValueError, 'computation identity'):
            verified_events(directory)
        evidence['computation']['requested'] = 'cpu'
        write_json(str(path) + '.run.json', evidence)
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            verified_events(directory)

    def test_studies_use_cpu_workers_without_gpu_identity(self):
        state = create_study(self.legacy, self.root / 'cpu.stress.json', dict(trial_budget=2))
        self.assertNotIn('computation', state)
        self.assertEqual(8, state['settings']['workers'])
        validate_study(state, self.legacy)
