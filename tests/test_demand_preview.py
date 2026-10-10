"""Hand-calculated schedule totals and preview integrity checks."""
import copy
import json
import os
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from amr_demand_preview import build_demand_preview, filter_tasks, timetable
from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.demand_preview_panel import DemandPreviewPanel


class DemandPreviewTests(unittest.TestCase):
    def setUp(self):
        self.config = grouped_config()
        self.category = self.config['task_generation']['categories']['stores']

    def preview(self):
        return build_demand_preview(self.config)

    def test_one_group_one_task_at_sixty_seconds(self):
        p = self.preview()
        self.assertEqual(1, p['totals']['planned_task_records'])
        task = p['tasks'][0]
        self.assertEqual((60, 'A', 'B', 'Box', 'D'), tuple(task[k] for k in ('release_seconds', 'pickup', 'dropoff', 'payload', 'department')))
        self.assertEqual('/task_generation/categories/stores/department_groups/0/payload', task['rule_path'])

    def test_three_times_over_two_days_is_six_records(self):
        self.config['simulation']['end_datetime'] = '2026-01-06T23:59:59'
        self.category['scheduled_times'] = ['00:01', '12:00', '23:59']
        p = self.preview()
        self.assertEqual([60, 43200, 86340, 86460, 129600, 172740], [t['release_seconds'] for t in p['tasks']])
        self.assertEqual(6, p['totals']['reconciled_rule_records'])
        self.assertEqual(6, p['rules'][0]['expected_fixed_records'])
        self.assertEqual(0, p['rules'][0]['count_difference'])
        self.assertEqual(6, sum(t['planned_records'] for t in timetable(p['tasks'])))

    def test_inclusive_end_excludes_releases_before_start(self):
        self.config['simulation'].update(start_datetime='2026-01-05T00:01:30', end_datetime='2026-01-05T00:02:00')
        self.category['scheduled_times'] = ['00:01', '00:02', '00:03']
        # D014 removes the legacy clamp that replayed a past service at zero.
        preview = self.preview()
        self.assertEqual([30], [t['release_seconds'] for t in preview['tasks']])
        self.assertEqual(1, preview['rules'][0]['expected_fixed_records'])
        self.assertEqual(0, preview['rules'][0]['count_difference'])
        records = Simulation(copy.deepcopy(self.config)).task_generation_manager.update_until(30)
        self.assertEqual([30], [r.task.release_time for r in records])

    def test_timeframe_multiple_has_three_records(self):
        self.category['requires_staff'] = False  # Unspaced independent-count reference.
        self.category.update(generation_mode='timeframe', timeframe_start='00:02', timeframe_end='00:08', timeframe_payload_multiple=3)
        p = self.preview()
        self.assertEqual([120, 120, 120], [t['release_seconds'] for t in p['tasks']])
        self.assertEqual(3, p['rules'][0]['expected_fixed_records'])
        self.assertTrue(all(t['effective_task']['timeframe_deadline_time'] == 480 for t in p['tasks']))

    def test_two_groups_generate_independent_services(self):
        second = copy.deepcopy(self.category['department_groups'][0])
        second['id'] = 'G2'
        second['payload']['scheduled_times'] = ['00:02']
        self.category['department_groups'].append(second)
        p = self.preview()
        self.assertEqual([60, 120], [t['release_seconds'] for t in p['tasks']])
        self.assertEqual(2, len({t['rule_id'] for t in p['tasks']}))

    def test_effective_precedence_and_department_destination(self):
        self.category['departments'] = {'D': {'enabled': True, 'priority': 99}}
        self.category['department_groups'][0]['payload']['dropoff_zone_capacity_policy'] = 'allow_temporary_overflow'
        self.config['locations'].append({'name': 'C', 'floor': 0, 'x': 20, 'y': 20})
        self.config['departments'][0]['task_generation_locations'] = {'stores': {'pickup_dropoff_locations': ['C']}}
        p = self.preview()
        task = p['tasks'][0]
        rule = next(r for r in p['rules'] if r['id'] == task['rule_id'])
        self.assertEqual('C', task['dropoff'])
        self.assertEqual(7, task['effective_task']['priority'])
        self.assertEqual('wait_for_space', task['effective_task']['dropoff_zone_capacity_policy'])
        self.assertIn('/department_groups/0/payload', rule['field_sources']['priority'])
        self.assertIn('category-wide', rule['field_sources']['dropoff_zone_capacity_policy'])
        self.assertTrue(any(r['explanation'] == 'Suppressed by group membership.' for r in p['rules']))

    def test_runtime_threshold_is_unknown_not_zero(self):
        self.category['generation_mode'] = 'threshold'
        p = self.preview()
        self.assertEqual([], p['tasks'])
        rule = next(r for r in p['rules'] if r['id'] == 'stores:D:group:G')
        self.assertIsNone(rule['total_demand'])
        self.assertEqual('runtime-dependent', rule['status'])

    def test_returns_are_explained_not_counted_as_fixed_tasks(self):
        self.category.update(return_enabled=True, return_payload='Box', return_delay_minutes=2)
        p = self.preview()
        self.assertEqual(1, len(p['tasks']))
        self.assertIn('not counted', p['rules'][0]['returns'])
        self.assertTrue(p['tasks'][0]['effective_task']['return_enabled'])
        self.assertIsNone(p['rules'][0]['total_demand'])

    def test_disabled_and_empty_schedules_have_reasons(self):
        self.config['task_generation']['enabled'] = False
        p = self.preview()
        self.assertEqual([], p['tasks'])
        self.assertTrue(all('disabled' in r['explanation'] for r in p['rules']))
        self.config['task_generation']['enabled'] = True
        self.category['scheduled_times'] = []
        p = self.preview()
        self.assertEqual('No scheduled times are configured.', p['rules'][0]['explanation'])

    def test_closed_active_day_has_no_work_reason(self):
        self.category['days_active'] = ['tue']  # Reference date is Monday.
        p = self.preview()
        self.assertEqual([], p['tasks'])
        self.assertIn('active days', p['rules'][0]['explanation'])

    def test_missing_member_remains_visible_in_partly_active_group(self):
        self.category['department_groups'][0]['departments'].append('Missing')
        p = self.preview()
        self.assertEqual(1, len(p['tasks']))
        self.assertTrue(any(r['department'] == 'Missing' and r['status'] == 'no-work' for r in p['rules']))

    def test_static_quantity_is_separate_from_record_count(self):
        self.config['tasks'] = [{'id': 'S', 'pickup': 'A', 'dropoff': 'B', 'payload': 'Box', 'release_time': 5, 'quantity': 3}]
        p = self.preview()
        self.assertEqual(2, p['totals']['planned_task_records'])
        self.assertEqual(4, p['totals']['configured_quantity_units'])

    def test_filters_and_timetable_reconcile(self):
        self.config['route_profiles'] = {'clean': {}}
        self.category['route_profile'] = 'clean'
        p = self.preview()
        tasks = filter_tasks(p, department='D', category='stores', payload='Box', route_profile='clean', date='2026-01-05', query='A')
        self.assertEqual(1, len(tasks))
        self.assertEqual(1, timetable(tasks)[0]['planned_records'])
        self.assertEqual([], filter_tasks(p, department='Other'))

    def test_repeatable_non_mutating_json_snapshot(self):
        original = copy.deepcopy(self.config)
        a, b = self.preview(), self.preview()
        self.assertEqual(original, self.config)
        self.assertEqual(a, b)
        self.assertEqual(a, json.loads(json.dumps(a)))
        self.config['locations'][0]['x'] = 99
        self.assertEqual(0, a['frozen_inputs']['locations'][0]['x'])

    def test_preview_matches_runtime_schedule_and_record_provenance(self):
        p = self.preview()
        records = Simulation(copy.deepcopy(self.config)).task_generation_manager.update_until(61)
        self.assertEqual(p['tasks'][0]['rule_id'], records[0].rule_id)
        self.assertEqual(p['tasks'][0]['rule_path'], records[0].rule_path)
        self.assertEqual(p['tasks'][0]['release_seconds'], records[0].task.release_time)

    def test_limits_fail_explicitly_without_partial_totals(self):
        with self.assertRaisesRegex(ValueError, '31 days'):
            build_demand_preview(self.config, end_datetime='2027-01-01T00:00:00')
        self.category['timeframe_payload_multiple'] = 999999999
        with self.assertRaisesRegex(ValueError, 'limit'):
            self.preview()

    def test_ltn_preview_preserves_user_project_and_reconciles(self):
        path = Path(__file__).resolve().parents[1] / 'ltn.json'
        raw = path.read_bytes()
        p = build_demand_preview(json.loads(raw))
        self.assertEqual(raw, path.read_bytes())
        self.assertEqual(len(p['tasks']), sum(r['planned_records'] for r in p['rules']))
        self.assertGreater(p['totals']['runtime_dependent_rules'], 0)


class DemandPreviewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_filters_and_stale_export(self):
        config = grouped_config()
        panel = DemandPreviewPanel(lambda: config)
        try:
            panel.accept_preview(build_demand_preview(config))
            self.assertTrue(panel.export_button.isEnabled())
            self.assertEqual(1, panel.tasks.rowCount())
            panel.search.setText('does-not-exist')
            self.assertEqual(0, panel.tasks.rowCount())
            self.assertEqual(0, panel.hours.rowCount())
            self.assertGreater(panel.rules.rowCount(), 0)
            config['locations'][0]['x'] = 99
            panel.check_staleness()
            self.assertIn('STALE', panel.summary.text())
            self.assertFalse(panel.export_button.isEnabled())
        finally:
            panel.timer.stop()
            panel.close()

    def test_background_build_completes_and_shows_origin(self):
        from PySide6.QtCore import QEventLoop, QTimer
        panel = DemandPreviewPanel(grouped_config)
        try:
            loop = QEventLoop()
            panel.build()
            panel.job.signals.finished.connect(lambda *_: loop.quit())
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.assertIsNotNone(panel.preview)
            self.assertTrue(panel.build_button.isEnabled())
            panel.tasks.selectRow(0)
            self.assertIn('/department_groups/0/payload', panel.details.toPlainText())
        finally:
            panel.timer.stop()
            panel.close()


if __name__ == '__main__':
    unittest.main()
