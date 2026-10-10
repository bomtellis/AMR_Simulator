"""Independent run-period, scheduling and editor-preservation references."""
import contextlib
import copy
import io
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication
from simulator import Simulation
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from visualiser.dialogs import SimulationSettingsDialog
from amr_demand_preview import build_demand_preview
from tests.test_engineering_reference import reference_config
from tests.test_generation_reference import grouped_config


class SimulationRunControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_import_preserves_missing_runtime_defaults_and_duration(self):
        config = reference_config()
        config['simulation'] = {'duration_hours': 2}
        before = copy.deepcopy(config)
        direct, imported = Simulation(config), Simulation(JsonStore(config).data)
        self.assertEqual(config, before)
        self.assertEqual(7200, direct.task_generation_horizon_sec)
        self.assertEqual(direct.task_generation_horizon_sec, imported.task_generation_horizon_sec)
        self.assertEqual(direct.clock.start_datetime, imported.clock.start_datetime)
        self.assertEqual(direct.clock.tick_rate, imported.clock.tick_rate)
        self.assertEqual(direct.max_assignments_per_tick, imported.max_assignments_per_tick)

    def test_import_preserves_release_spacing_alias(self):
        config = reference_config()
        config['simulation']['task_release_stagger_sec'] = 2.5
        self.assertEqual(2.5, Simulation(JsonStore(config).data).generated_release_stagger_sec)
        config['simulation']['generated_task_release_stagger_sec'] = 0
        self.assertEqual(0, Simulation(JsonStore(config).data).generated_release_stagger_sec)

    def test_horizon_precedence_and_static_release_fallback(self):
        config = reference_config()
        config['simulation'].update(duration_hours=2, duration_days=3)
        self.assertEqual(600, Simulation(config).task_generation_horizon_sec)
        config['simulation'].pop('end_datetime')
        self.assertEqual(7200, Simulation(config).task_generation_horizon_sec)
        config['simulation'].pop('duration_hours')
        self.assertEqual(259200, Simulation(config).task_generation_horizon_sec)
        config['simulation'].pop('duration_days')
        config['tasks'] = [{'id': 'late', 'pickup': 'A', 'dropoff': 'B', 'payload': 'Box', 'release_time': 90000}]
        self.assertEqual(176400, Simulation(config).task_generation_horizon_sec)
        self.assertEqual(176400, Simulation(JsonStore(config).data).task_generation_horizon_sec)

    def test_preview_uses_duration_horizon_and_inclusive_end(self):
        config = grouped_config()
        config['simulation'].pop('end_datetime')
        config['simulation']['duration_hours'] = 1
        config['task_generation']['categories']['stores']['scheduled_times'] = ['00:30', '01:00', '01:30']
        preview = build_demand_preview(config)
        self.assertEqual([1800, 3600], [t['release_seconds'] for t in preview['tasks']])
        records = Simulation(config).task_generation_manager.update_until(3600)
        self.assertEqual([1800, 3600], [r.task.release_time for r in records])

    def test_malformed_controls_reject_at_all_entry_points_without_mutation(self):
        invalid = {
            'start_datetime': [None, 'nonsense'], 'end_datetime': ['bad', '2026-01-04T00:00:00', '2026-01-05T01:00:00+00:00'],
            'tick_rate': [0, -1, True, 'NaN'], 'duration_hours': [-1, float('inf')],
            'generated_task_release_stagger_sec': [-0.1, True],
            'max_assignments_per_tick': [-1, 1.5, True],
            'max_single_candidate_tasks': [0, 1.5], 'max_multi_stop_candidate_tasks': [1, 2.5],
            'assignment_continue_delay_sec': [0, -1], 'idle_return_check_interval_sec': [0],
            'reservation_prune_interval_sec': [-1], 'reservation_history_retention_sec': [-1],
            'opportunity_charging_idle_period_sec': [-1], 'route_precompute_max_pairs': [-1, 1.2],
            'precompute_static_routes': ['maybe'], 'enable_opportunity_charging': [2],
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    config = reference_config()
                    config['simulation'][key] = value
                    before = copy.deepcopy(config)
                    for constructor in (Simulation, JsonStore):
                        with self.assertRaises(ValueError):
                            constructor(config)
                    report = check_project(config, include_legacy=False)
                    self.assertTrue(any(f.severity == 'error' and f.path == '/simulation/' + key for f in report.findings))
                    self.assertEqual(before, config)

    def test_boolean_legacy_forms_are_consistent_in_runtime_and_dialog(self):
        for value, expected in [('false', False), ('true', True), (0, False), (1, True)]:
            config = reference_config()
            config['simulation'].update(precompute_static_routes=value, enable_opportunity_charging=value)
            sim = Simulation(config)
            dialog = SimulationSettingsDialog(None, config['simulation'])
            try:
                self.assertEqual(expected, sim.route_precompute_enabled)
                self.assertEqual(expected, sim.enable_opportunity_charging)
                self.assertEqual(expected, dialog.precompute_routes_check.isChecked())
                self.assertEqual(expected, dialog.enable_opportunity_charging_check.isChecked())
            finally:
                dialog.close()

    def test_dialog_noop_preserves_unlimited_zero_and_precision(self):
        values = {'start_datetime': '2026-01-05T00:00:00.123456+02:00',
                  'max_assignments_per_tick': 0, 'generated_task_release_stagger_sec': 0.123456789,
                  'opportunity_charging_idle_period_sec': 0, 'duration_hours': 2,
                  'assignment_continue_delay_sec': 0.00123456789, 'custom': {'note': 'retain'}}
        dialog = SimulationSettingsDialog(None, values)
        try:
            self.assertEqual(0, dialog.max_assignments_per_tick_spin.value())
            self.assertEqual(0, dialog.opportunity_charging_idle_minutes_spin.value())
            self.assertFalse(dialog.use_end_datetime_check.isChecked())
            dialog.accept()
            self.assertEqual(values, dialog.result)
        finally:
            dialog.close()

    def test_dialog_changes_only_edited_control(self):
        values = {'start_datetime': '2026-01-05T00:00:00', 'duration_hours': 2,
                  'generated_task_release_stagger_sec': 0.123456789}
        dialog = SimulationSettingsDialog(None, values)
        try:
            dialog.max_assignments_per_tick_spin.setValue(0)
            dialog.accept()
            self.assertEqual({**values, 'max_assignments_per_tick': 0}, dialog.result)
        finally:
            dialog.close()

    def test_end_is_demand_horizon_not_transport_cutoff_and_rate_is_metadata(self):
        outcomes = []
        for rate in (0.5, 1000000):
            config = reference_config()
            config['simulation'].update(end_datetime='2026-01-05T00:00:01', tick_rate=rate)
            config['tasks'] = [{'id': 'T', 'pickup': 'A', 'dropoff': 'B', 'payload': 'Box', 'release_time': 1}]
            sim = Simulation(config)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            # Released at 1; load 2 + 10m / 2m/s + unload 2 = finishes at 10.
            self.assertEqual(1, len(sim.completed_task_records))
            self.assertAlmostEqual(10, sim.current_time)
            outcomes.append(sim.current_time)
        self.assertEqual(outcomes[0], outcomes[1])

    def test_precompute_limits_do_not_change_reference_route(self):
        for enabled, limit in [(False, 0), (True, 0), (True, 1), (True, 100000)]:
            config = reference_config()
            config['simulation'].update(precompute_static_routes=enabled, route_precompute_max_pairs=limit)
            sim = Simulation(config)
            self.assertEqual(10, sim._shortest_path_same_floor(0, 'A', 'B')['distance_m'])


if __name__ == '__main__':
    unittest.main()
