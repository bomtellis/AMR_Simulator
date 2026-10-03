"""Department clocks and demographic waste rates from independent arithmetic."""
import copy
import unittest
from unittest.mock import patch
from datetime import datetime

from amr_sim_task_generation import _department_active_seconds_between, _department_operating_hours_per_day
from simulator import Simulation
from tests.test_waste_conservation import legacy_config
from visualiser.models import JsonStore, calculated_operating_hours_per_day
from visualiser.project_checks import check_project


class DepartmentContractTests(unittest.TestCase):
    def test_legacy_overnight_hours_survive_import_and_repeat_normalisation(self):
        for start, hours, end in [('22:00', 8, '06:00'), ('09:00', 24, '09:00'), ('23:45', .5, '00:15')]:
            cfg = legacy_config()
            dept = cfg['departments'][0]
            dept.update(operating_start_time=start, hours_operated_per_day=hours)
            del dept['operating_end_time']
            before = copy.deepcopy(cfg)
            store = JsonStore(cfg)
            for _ in range(2):
                actual = store.data['departments'][0]
                self.assertEqual(end, actual['operating_end_time'])
                self.assertEqual(hours, _department_operating_hours_per_day(actual))
                self.assertEqual(hours, actual['hours_operated_per_day'])
                store.ensure_department_defaults()
            self.assertEqual(before, cfg)

    def test_subhour_waste_rate_uses_actual_operating_hours(self):
        cfg = legacy_config()
        cfg['departments'][0].update(operating_start_time='09:00', operating_end_time='09:30',
            bed_count=10, patient_turnover=2, staff_count=3,
            waste=dict(alpha=.01, beta=.2, gamma=.1, pickup_location='A', dropoff_location='B'))
        cfg['waste_streams'][0].update(container_capacity_m3=100, full_threshold_fraction=1)
        for data in (cfg, JsonStore(cfg).data):
            manager = Simulation(data).task_generation_manager
            generator = manager.generators[0]
            # .01*10 + .2*(2/.5) + .1*3 = 1.2 m3/hour; half an hour gives .6 m3.
            self.assertAlmostEqual(1.2, generator._department_hourly_waste_rate_m3(data['departments'][0]))
            manager.update_until(5400)
            self.assertAlmostEqual(.6, generator.runtime['D']['General']['generated_m3_total'])

    def test_explicit_end_wins_and_equal_times_mean_full_day(self):
        for start, end, expected in [('22:00', '06:00', 8), ('09:00', '09:00', 24),
                                      ('00:00', '24:00', 24), ('09:00', '09:01', 1/60)]:
            dept = dict(operating_start_time=start, operating_end_time=end, hours_operated_per_day=12)
            self.assertAlmostEqual(expected, _department_operating_hours_per_day(dept))
            self.assertAlmostEqual(expected, calculated_operating_hours_per_day(dept))

    def test_invalid_department_scalars_and_clocks_reject_without_mutation(self):
        for key, values in {'enabled': ['false', 0, None], 'bed_count': [-1, True, 'nan'],
            'staff_count': [-1, False, 'inf'], 'patient_turnover': [-.1, None],
            'hours_operated_per_day': [-1, 25, True], 'operating_start_time': ['25:00', '24:00', 9],
            'operating_end_time': ['12:60', None], 'days_active': ['mon', ['Monday'], [True]]}.items():
            for value in values:
                cfg = legacy_config()
                cfg['departments'][0][key] = value
                before = copy.deepcopy(cfg)
                for consumer in (JsonStore, Simulation):
                    with self.subTest(key=key, value=value, consumer=consumer.__name__), self.assertRaises(ValueError):
                        consumer(cfg)
                self.assertEqual(before, cfg)
                self.assertTrue(any(f.severity == 'error' and f.path == f'/departments/0/{key}'
                                    for f in check_project(cfg).findings))

    def test_negative_or_nonfinite_waste_coefficients_cannot_remove_demand(self):
        for key in ('alpha', 'beta', 'gamma'):
            for value in (-1, True, float('inf')):
                cfg = legacy_config()
                cfg['departments'][0]['waste'][key] = value
                for consumer in (JsonStore, Simulation):
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        consumer(cfg)

    def test_failed_department_update_is_atomic(self):
        store = JsonStore(legacy_config())
        before = copy.deepcopy(store.data)
        updated = copy.deepcopy(store.data['departments'][0])
        updated['enabled'] = 'false'
        with self.assertRaises(ValueError):
            store.upsert_department(updated)
        self.assertEqual(before, store.data)

    def test_zero_legacy_hours_and_empty_days_keep_full_day_convention(self):
        dept = dict(operating_start_time='09:00', hours_operated_per_day=0, days_active=[])
        self.assertEqual(24, _department_operating_hours_per_day(dept))
        self.assertEqual(24, calculated_operating_hours_per_day(dept))
        self.assertEqual('09:00', dept['operating_end_time'])
        self.assertEqual(86400, _department_active_seconds_between(dept,
            datetime(2026, 1, 5, 9), datetime(2026, 1, 6, 9)))

    def test_disabled_department_accumulates_no_waste(self):
        cfg = legacy_config()
        cfg['departments'][0]['enabled'] = False
        for data in (cfg, JsonStore(cfg).data):
            manager = Simulation(data).task_generation_manager
            self.assertEqual([], manager.update_until(90000))
            self.assertEqual(0, manager.generators[0].runtime['D']['General']['generated_m3_total'])

    def test_finite_inputs_cannot_overflow_derived_waste_rate(self):
        cfg = legacy_config()
        cfg['departments'][0].update(bed_count=2, waste=dict(alpha=1e308))
        for consumer in (JsonStore, Simulation):
            with self.assertRaisesRegex(ValueError, 'overflow'):
                consumer(cfg)

    def test_demographics_have_explicit_scope_finding(self):
        report = check_project(legacy_config())
        self.assertTrue(any(f.code == 'DEPARTMENT_DEMAND_SCOPE' and f.severity == 'info' for f in report.findings))


class DepartmentDialogContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    def test_dialog_preserves_fractional_counts_and_legacy_coefficients(self):
        from visualiser.dialogs import DepartmentEditorDialog, QMessageBox
        seed = copy.deepcopy(legacy_config()['departments'][0])
        seed.update(bed_count=10.25, staff_count=3.5, custom={'note': 'retain'})
        before = copy.deepcopy(seed)
        dialog = DepartmentEditorDialog(None, ['A', 'B'], ['General'], seed=seed)
        with patch.object(QMessageBox, 'critical') as critical:
            dialog.accept()
        self.assertFalse(critical.called, critical.call_args)
        self.assertEqual((10.25, 3.5), (dialog.result['bed_count'], dialog.result['staff_count']))
        self.assertEqual(before['waste'], dialog.result['waste'])
        self.assertEqual(before['custom'], dialog.result['custom'])
        self.assertEqual(before, seed)

    def test_dialog_rejects_negative_counts_without_a_result(self):
        from visualiser.dialogs import DepartmentEditorDialog, QMessageBox
        dialog = DepartmentEditorDialog(None, ['A', 'B'], ['General'], seed=legacy_config()['departments'][0])
        dialog.bed_count_edit.setText('-1')
        with patch.object(QMessageBox, 'critical') as critical:
            dialog.accept()
        self.assertTrue(critical.called)
        self.assertIsNone(dialog.result)
