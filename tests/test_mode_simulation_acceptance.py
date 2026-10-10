"""The explicit mode selects a physical model, with independent expected results."""
import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest

from tests.test_motion_dynamics_simulation import dynamics_config
from amr_movement_inputs import migrate_movement_inputs
from amr_reference_inputs import DEFAULT_REFERENCE_POINT
from amr_simulation_modes import apply_mode_change, preview_mode_change
from simulator import Simulation
from visualiser.project_checks import check_project
from visualiser.models import JsonStore
from amr_project import Project
from PySide6.QtWidgets import QApplication
from amr_results_investigation import load_investigation
from visualiser.results_investigation_panel import ResultsInvestigationPanel


def prepared_config():
    config = dynamics_config()
    robot = config['amrs'][0]
    robot['movement'] = migrate_movement_inputs(robot['movement'])['movement']
    robot['manoeuvring']['reference_point'] = copy.deepcopy(DEFAULT_REFERENCE_POINT)
    config['geometry']['clearances'] = {'wall_m': 0, 'robot_m': 0}
    config['geometry']['initial_placements'] = [
        {'amr_id': 'R-1', 'location': 'A', 'heading_deg': 0}]
    return config


def run(config):
    sim = Simulation(config, verbose=True)
    with contextlib.redirect_stdout(io.StringIO()):
        sim.run()
    return sim


class ModeSimulationAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_same_inputs_use_graph_time_or_loaded_acceleration_as_selected(self):
        config = prepared_config()
        original = copy.deepcopy(config)
        simple = run(apply_mode_change(config, 'simple'))
        detailed = run(apply_mode_change(config, 'detailed'))
        # Twenty metres at 2m/s plus two 2s handling stages = 14s Simple.
        # Detailed: a=b=1m/s², peak2, 2m acceleration +16m cruise +2m brake
        # => 12s motion +4s handling =16s. Distances and payload are identical.
        self.assertAlmostEqual(14, simple.current_time)
        self.assertAlmostEqual(16, detailed.current_time)
        for sim in (simple, detailed):
            self.assertEqual(['T'], [item['task_id'] for item in sim.completed_task_records])
            self.assertFalse(sim.failed_task_ids)
        self.assertAlmostEqual(750*1.035*12/3600000, detailed.amrs[0].total_energy_used_kwh)
        self.assertFalse(any(row.get('trajectory_json') for row in simple.verbose_rows))
        self.assertTrue(any(row.get('trajectory_json') for row in detailed.verbose_rows))
        self.assertEqual(original, config)

    def test_incomplete_detailed_selection_is_editable_but_checks_and_run_block(self):
        config = prepared_config()
        del config['amrs'][0]['movement']
        del config['geometry']['initial_placements']
        preview = preview_mode_change(config, 'detailed')
        self.assertTrue(preview['findings'])
        selected = apply_mode_change(config, 'detailed')
        report = check_project(selected, include_legacy=False)
        paths = {f.path for f in report.findings if f.severity == 'error'}
        self.assertTrue(any(path.startswith('/amrs/0/movement') for path in paths))
        self.assertIn('/geometry/initial_placements', paths)
        report.acknowledge_warnings()
        self.assertFalse(report.can_run(selected))
        with self.assertRaises(ValueError):
            Simulation(selected)
        self.assertNotIn('movement', selected['amrs'][0])
        self.assertNotIn('initial_placements', selected['geometry'])

    def test_incomplete_selection_saves_and_reopens_without_inventing_physical_inputs(self):
        config = prepared_config()
        del config['amrs'][0]['movement']
        del config['amrs'][0]['manoeuvring']
        del config['geometry']
        selected = apply_mode_change(config, 'detailed')
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder/'draft.amrproj'
            draft = JsonStore(selected).data
            Project().save(path, draft, base_dir=folder)
            reopened = JsonStore(Project.open(path).materialize(folder/'cache')).data
            self.assertEqual({'traffic_model': 'keep_right_v1'}, reopened['geometry'])
            self.assertEqual('detailed', reopened['simulation']['mode'])
            self.assertNotIn('movement', reopened['amrs'][0])
            self.assertNotIn('manoeuvring', reopened['amrs'][0])
            self.assertTrue([f for f in check_project(reopened).findings if f.severity == 'error'])
            with self.assertRaises(ValueError):
                Simulation(reopened)

    def test_mode_edit_invalidates_previous_acknowledgements_and_requires_recheck(self):
        detailed = apply_mode_change(prepared_config(), 'detailed')
        report = check_project(detailed, include_legacy=False)
        self.assertFalse([f.message for f in report.findings if f.severity == 'error'])
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(detailed))
        simple = apply_mode_change(detailed, 'simple')
        self.assertFalse(report.can_run(simple))
        fresh = check_project(simple, include_legacy=False)
        fresh.acknowledge_warnings()
        self.assertTrue(fresh.can_run(simple))
        self.assertEqual(detailed['geometry'], simple['geometry'])
        self.assertEqual(detailed['amrs'], simple['amrs'])

    def test_unavailable_interactions_remain_blocked_in_detailed(self):
        for section, value in (('people_movements', [{'id': 'unimplemented'}]),
                               ('scenario_testing', {'enabled': True})):
            with self.subTest(section=section):
                config = prepared_config()
                config[section] = value
                preview = preview_mode_change(config, 'detailed')
                self.assertTrue(any(path.startswith('/'+section) for path, _ in preview['findings']))
                with self.assertRaises(ValueError):
                    Simulation(preview['config'])

    def test_review_displays_saved_mode_after_editor_model_changes(self):
        config = apply_mode_change(prepared_config(), 'detailed')
        with tempfile.TemporaryDirectory() as folder:
            csv = Path(folder)/'steps.csv'
            sim = Simulation(config, verbose=True, verbose_csv_path=str(csv))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            config['simulation'].update(mode='simple', motion_model='legacy')
            sim.write_verbose_csv()
            panel = ResultsInvestigationPanel()
            try:
                panel.accept_result(load_investigation(csv))
                self.assertIn('Simulation mode: Detailed; explicitly selected in frozen inputs',
                              panel.evidence.toPlainText())
                legacy = load_investigation(csv)
                legacy['simulation_mode'] = None
                panel.accept_result(legacy)
                self.assertIn('Simulation mode: Unknown; no verified mode evidence',
                              panel.evidence.toPlainText())
            finally:
                panel.close()


if __name__ == '__main__':
    unittest.main()
