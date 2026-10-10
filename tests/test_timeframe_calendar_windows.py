"""Independent release arithmetic across overnight and disjoint work periods."""
import copy
import unittest
from datetime import datetime

from amr_demand_preview import build_demand_preview
from simulator import Simulation
from tests.test_staff_calendar_switches import timeframe_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class TimeframeCalendarWindowTests(unittest.TestCase):
    def check_releases(self, config, expected):
        for editor in (False, True):
            data = JsonStore(config).data if editor else copy.deepcopy(config)
            sim = Simulation(data)
            horizon = (datetime.fromisoformat(data['simulation']['end_datetime']) - sim.clock.start_datetime).total_seconds()
            manager = sim.task_generation_manager
            self.assertEqual(sorted(set(expected)), manager.scheduled_wake_times(horizon))
            records = manager.update_until(horizon)
            tasks = sorted((r.task for r in records), key=lambda t: t.release_time)
            self.assertEqual(expected, [t.release_time for t in tasks])
            preview = build_demand_preview(data)
            self.assertEqual(expected, [t['release_seconds'] for t in preview['tasks']])
            self.assertEqual([], manager.update_until(horizon))
        return sim, tasks, preview

    def test_previous_day_custom_shift_is_available_after_midnight(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-06T00:00:00', end_datetime='2026-01-06T06:00:00')
        config['task_generation']['categories']['stores'].update(
            timeframe_start='00:00', timeframe_end='06:00', staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '22:00', 'end_time': '06:00'}})
        sim, tasks, preview = self.check_releases(config, [0, 5400, 10800, 16200])
        self.assertTrue(all(t.staff_timeframe_spaced and not t.staff_out_of_hours_required for t in tasks))
        self.assertEqual(0, sim._assign_staff_for_handling(tasks[0], 0, 60)['start_time'])
        self.assertEqual(0, preview['totals']['out_of_hours_records'])

    def test_previous_day_global_fixed_shift_is_also_available(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-06T00:00:00', end_datetime='2026-01-06T06:00:00')
        config['task_generation']['categories']['stores'].update(timeframe_start='00:00', timeframe_end='06:00')
        config['task_generation']['staff_config'] = {'shift_patterns': {
            'none': {'start_time': '22:00', 'end_time': '06:00', 'days_active': ['mon']}}}
        self.check_releases(config, [0, 5400, 10800, 16200])

    def test_disjoint_staff_periods_use_working_duration_without_releasing_in_gap(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-05T20:00:00', end_datetime='2026-01-06T08:00:00')
        config['task_generation']['categories']['stores'].update(
            timeframe_start='20:00', timeframe_end='08:00', staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '22:00', 'end_time': '02:00'},
                                 'tue': {'enabled': True, 'start_time': '06:00', 'end_time': '08:00'}})
        # Six working hours / four records = 90 min. Skip the four-hour closure.
        sim, tasks, _ = self.check_releases(config, [7200, 12600, 18000, 37800])
        self.assertTrue(all(t.timeframe_deadline_time == 43200 for t in tasks))
        for task in tasks:
            self.assertEqual(task.release_time, sim._assign_staff_for_handling(task, task.release_time, 60)['start_time'])

    def test_department_closure_is_removed_from_spreading_duration(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-05T20:00:00', end_datetime='2026-01-06T08:00:00')
        config['departments'][0].update(operating_start_time='06:00', operating_end_time='22:00')
        config['task_generation']['categories']['stores'].update(
            timeframe_start='20:00', timeframe_end='08:00', staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '20:00', 'end_time': '08:00'}})
        # 20-22 and 06-08: four hours / four records, with an eight-hour gap.
        self.check_releases(config, [0, 3600, 36000, 39600])

    def test_no_staff_overlap_retains_demand_and_explains_deadline_risk(self):
        config = timeframe_config()
        config['task_generation']['categories']['stores'].update(timeframe_start='07:00', timeframe_end='08:00')
        sim, tasks, preview = self.check_releases(config, [25200] * 4)
        self.assertTrue(all(t.staff_out_of_hours_required and not t.staff_timeframe_spaced for t in tasks))
        self.assertEqual(32400, sim._assign_staff_for_handling(tasks[0], 25200, 60)['start_time'])
        self.assertEqual(4, preview['totals']['out_of_hours_records'])
        rule = next(r for r in preview['rules'] if r['planned_records'])
        self.assertEqual(4, rule['out_of_hours_records'])
        self.assertIn('deadline', rule['explanation'])
        self.assertIn('staff working period', preview['tasks'][0]['explanation'])

    def test_no_staff_department_overlap_is_explained_without_claiming_no_demand(self):
        config = timeframe_config()
        config['departments'][0].update(operating_start_time='18:00', operating_end_time='19:00')
        config['task_generation']['categories']['stores'].update(timeframe_start='08:00', timeframe_end='20:00')
        config['simulation']['end_datetime'] = '2026-01-05T20:00:00'
        _, tasks, preview = self.check_releases(config, [64800] * 4)
        self.assertTrue(all(t.staff_out_of_hours_required for t in tasks))
        self.assertIn('department opening hours', preview['tasks'][0]['explanation'])

    def test_equal_staff_start_and_end_is_closed_like_runtime(self):
        config = timeframe_config()
        config['task_generation']['categories']['stores'].update(
            staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '09:00', 'end_time': '09:00'}})
        _, tasks, preview = self.check_releases(config, [28800] * 4)
        self.assertTrue(all(t.staff_out_of_hours_required for t in tasks))
        self.assertEqual(4, preview['totals']['out_of_hours_records'])

    def test_department_opens_at_deadline_so_no_work_is_generated(self):
        config = timeframe_config()
        config['departments'][0].update(operating_start_time='18:00', operating_end_time='19:00')
        _, _, preview = self.check_releases(config, [])
        rule = next(r for r in preview['rules'] if r['category'] == 'stores' and r['department'] == 'D')
        self.assertEqual(('no-work', 0), (rule['status'], rule['total_demand']))
        self.assertIn('department opens at or after the timeframe deadline', rule['explanation'])
        self.assertTrue(rule['no_work_reasons'])

    def test_overnight_department_from_previous_active_day_keeps_all_slots(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-06T00:00:00', end_datetime='2026-01-06T06:00:00')
        config['departments'][0].update(operating_start_time='22:00', operating_end_time='06:00', days_active=['mon'])
        config['task_generation']['categories']['stores'].update(
            timeframe_start='00:00', timeframe_end='06:00', staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '22:00', 'end_time': '06:00'}})
        self.check_releases(config, [0, 5400, 10800, 16200])

    def test_rotating_pattern_weekday_list_does_not_disable_runtime_available_team(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-06T00:00:00', end_datetime='2026-01-06T18:00:00')
        config['task_generation']['categories']['stores'].update(staff_shift_pattern='four_on_four_off_12h')
        config['task_generation']['staff_config'] = {'shift_patterns': {
            'four_on_four_off_12h': {'start_time': '09:00', 'end_time': '17:00', 'days_active': ['mon']}}}
        sim, tasks, _ = self.check_releases(config, [h * 3600 for h in (9, 11, 13, 15)])
        self.assertEqual(32400, sim._assign_staff_for_handling(tasks[0], 32400, 60)['start_time'])
        self.assertTrue(any(f.code == 'GENERATION_UNSUPPORTED' and f.path.endswith('/days_active')
                            for f in check_project(config).findings))

    def test_overlapping_daily_periods_do_not_double_count_available_hours(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-06T00:00:00', end_datetime='2026-01-06T18:00:00')
        config['task_generation']['categories']['stores'].update(
            timeframe_start='00:00', timeframe_end='18:00', staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '22:00', 'end_time': '20:00'},
                                 'tue': {'enabled': True, 'start_time': '06:00', 'end_time': '18:00'}})
        _, tasks, _ = self.check_releases(config, [0, 16200, 32400, 48600])
        self.assertEqual([[0, 64800]], tasks[0].staff_work_periods)

    def test_out_of_hours_warning_is_visible_in_existing_preview_workspace(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from visualiser.demand_preview_panel import DemandPreviewPanel, rule_explanation
        app = QApplication.instance() or QApplication([])
        config = timeframe_config()
        config['task_generation']['categories']['stores'].update(timeframe_start='07:00', timeframe_end='08:00')
        preview = build_demand_preview(config)
        panel = DemandPreviewPanel(lambda: config)
        try:
            panel.accept_preview(preview)
            self.assertIn('4 releases flagged for no staff/department working window', panel.summary.text())
            rule = next(r for r in preview['rules'] if r['planned_records'])
            self.assertIn('working window: 4', rule_explanation(rule))
            self.assertIn('deadline', rule_explanation(rule))
        finally:
            panel.timer.stop()
            panel.close()


if __name__ == '__main__':
    unittest.main()
