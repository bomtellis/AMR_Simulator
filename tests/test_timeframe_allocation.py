"""Reference allocations preserve eligible slots across day/calendar boundaries."""
import copy
import unittest
from datetime import datetime

from amr_demand_preview import build_demand_preview
from simulator import Simulation
from tests.test_staff_calendar_switches import timeframe_config
from visualiser.models import JsonStore


def overnight_config(days):
    config = timeframe_config()
    config['simulation'].update(start_datetime='2026-01-05T20:00:00', end_datetime='2026-01-06T08:00:00')
    config['task_generation']['categories']['stores'].update(
        timeframe_start='22:00', timeframe_end='06:00', days_active=days,
        staff_use_custom_working_hours=True,
        staff_working_hours={'mon': {'enabled': True, 'start_time': '22:00', 'end_time': '06:00'}})
    return config


class TimeframeAllocationTests(unittest.TestCase):
    def assert_plan(self, config, expected):
        records, preview = [], {'rules': []}
        for editor in (False, True):
            with self.subTest(editor=editor):
                data = JsonStore(config).data if editor else copy.deepcopy(config)
                sim = Simulation(data)
                duration = (datetime.fromisoformat(data['simulation']['end_datetime']) - sim.clock.start_datetime).total_seconds()
                manager = sim.task_generation_manager
                wakes = manager.scheduled_wake_times(duration)
                self.assertEqual(sorted(set(expected)), wakes)
                records = []
                for instant in sorted(set([0, duration] + wakes)):
                    records.extend(manager.update_until(instant))
                self.assertEqual(expected, sorted(r.task.release_time for r in records))
                self.assertEqual([], manager.update_until(duration))
                preview = build_demand_preview(data)
                self.assertEqual(expected, [t['release_seconds'] for t in preview['tasks']])
        return records, preview

    def test_next_active_day_preserves_three_of_four_overnight_slots(self):
        # Four nominal slots: Mon 22, Tue 00,02,04. Only Monday's slot is excluded.
        _, preview = self.assert_plan(overnight_config(['tue']), [14400, 21600, 28800])
        rule = next(r for r in preview['rules'] if r['department'] == 'D')
        self.assertEqual(3, rule['planned_records'])
        accounting = rule['timeframe_slot_accounting']
        self.assertEqual((4, 3, 1, 0), tuple(accounting[k] for k in
                         ('candidate_records', 'eligible_records', 'excluded_records', 'count_difference')))
        self.assertEqual({'inactive_release_date': 1}, accounting['exclusions'])
        self.assertEqual([7200, 14400, 21600, 28800], [s['planned_release_seconds'] for s in rule['timeframe_slots']])
        self.assertIn('1 of 4', rule['explanation'])

    def test_nominal_active_day_keeps_only_its_own_slot(self):
        self.assert_plan(overnight_config(['mon']), [7200])

    def test_inactive_overnight_window_does_not_emit_any_slot(self):
        self.assert_plan(overnight_config(['wed']), [])

    def test_fortnight_boundary_checks_actual_release_date(self):
        config = overnight_config(['sun', 'mon'])
        config['simulation']['end_datetime'] = '2026-01-19T06:00:00'
        category = config['task_generation']['categories']['stores']
        category.update(run_every_fortnight=True,
                        staff_working_hours={day: {'enabled': True, 'start_time': '22:00', 'end_time': '06:00'}
                                             for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')})
        # Week 0 runs, week 1 is closed, week 2 begins at Jan 19 midnight.
        # Jan 11 Sunday slots at 00/02/04 come from Saturday's timeframe.
        # Only Sun/Mon dates are active: Sun Jan 11 is 124..128 and 146;
        # Sun Jan 18 is in the skipped week; Mon Jan 19 is 316..320.
        hours = [2, 124, 126, 128, 146, 316, 318, 320]
        self.assert_plan(config, [h * 3600 for h in hours])

    def test_department_opening_on_next_active_day_participates_in_pool(self):
        config = overnight_config(['tue'])
        config['departments'][0].update(days_active=['tue'], operating_start_time='00:00', operating_end_time='06:00')
        self.assert_plan(config, [14400, 19800, 25200, 30600])

    def test_different_department_windows_preserve_both_groups_demand(self):
        config = timeframe_config()
        category = config['task_generation']['categories']['stores']
        category['timeframe_payload_multiple'] = 2
        config['departments'][0].update(operating_start_time='09:00', operating_end_time='11:00')
        config['departments'].append(dict(config['departments'][0], id='E', name='Evening',
                                          operating_start_time='15:00', operating_end_time='17:00'))
        other = copy.deepcopy(category['department_groups'][0])
        other.update(id='H', departments=['E'])
        category['department_groups'].append(other)
        # Pool of four slots: D uses fractions 0/4,1/4 of its two hours;
        # E uses 2/4,3/4 of its two hours. This is not a capacity reservation.
        records, _ = self.assert_plan(config, [32400, 34200, 57600, 59400])
        self.assertEqual(['D', 'D', 'E', 'E'], [r.task.department_id for r in sorted(records, key=lambda r: r.task.release_time)])

    def test_fully_closed_department_does_not_take_slots_from_open_member(self):
        config = timeframe_config()
        category = config['task_generation']['categories']['stores']
        category['timeframe_payload_multiple'] = 2
        config['departments'].append(dict(config['departments'][0], id='E', name='Closed', days_active=['tue']))
        other = copy.deepcopy(category['department_groups'][0])
        other.update(id='H', departments=['E'])
        category['department_groups'].append(other)
        self.assert_plan(config, [32400, 46800])

    def test_import_omitted_department_weekdays_keeps_weekend_demand(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-11T00:00:00', end_datetime='2026-01-11T18:00:00')
        config['task_generation']['categories']['stores'].update(requires_staff=False, timeframe_start='09:00', timeframe_end='10:00')
        self.assertNotIn('days_active', config['departments'][0])
        self.assert_plan(config, [32400] * 4)

    def test_explicit_weekday_restrictions_survive_import_and_group_override(self):
        config = timeframe_config()
        config['simulation'].update(start_datetime='2026-01-11T00:00:00', end_datetime='2026-01-11T18:00:00')
        category = config['task_generation']['categories']['stores']
        category.update(requires_staff=False, timeframe_start='09:00', timeframe_end='10:00', days_active=['mon'])
        self.assert_plan(config, [])
        category['department_groups'][0]['payload']['days_active'] = []
        self.assert_plan(config, [32400] * 4)
        config['departments'][0]['days_active'] = ['mon']
        self.assert_plan(config, [])

    def test_partial_preview_accounts_for_future_slots_separately_from_inactive_date(self):
        config = overnight_config(['tue'])
        config['simulation']['end_datetime'] = '2026-01-06T01:00:00'
        _, preview = self.assert_plan(config, [14400])
        rule = next(r for r in preview['rules'] if r['department'] == 'D')
        self.assertEqual({'inactive_release_date': 1, 'outside_preview': 2},
                         rule['timeframe_slot_accounting']['exclusions'])
        self.assertEqual(1, rule['timeframe_slot_accounting']['eligible_records'])
        self.assertEqual(0, rule['timeframe_slot_accounting']['count_difference'])
        from visualiser.demand_preview_panel import rule_explanation
        text = rule_explanation(rule)
        self.assertIn('Candidates: 4; eligible: 1; excluded: 3; emitted: 1', text)
        self.assertIn('not an independent expectation', text)

    def test_preview_accounting_is_repeatable_and_does_not_modify_source(self):
        config = overnight_config(['tue'])
        before = copy.deepcopy(config)
        first = build_demand_preview(config)
        self.assertEqual(first, build_demand_preview(config))
        self.assertEqual(before, config)
        rule = next(r for r in first['rules'] if r['department'] == 'D')
        self.assertEqual(3, rule['timeframe_slot_accounting']['emitted_records'])

    def test_dialogs_display_unrestricted_days_as_all_seven(self):
        import os
        import sys
        from pathlib import Path
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
        from PySide6.QtWidgets import QApplication
        from visualiser.dialogs import (DepartmentEditorDialog, TaskGenerationSettingsDialog,
                                        BulkDepartmentTaskGenerationDialog)
        app = QApplication.instance() or QApplication([])
        data = JsonStore(timeframe_config()).data
        generation = data['task_generation']
        department = DepartmentEditorDialog(None, ['A', 'B'], [], seed=data['departments'][0])
        settings = TaskGenerationSettingsDialog(None, generation, ['A', 'B'], ['Box'], [], data['departments'], lambda value: None)
        bulk = BulkDepartmentTaskGenerationDialog(None, 'stores', 'Stores', data['departments'],
                generation['categories']['stores'], ['A', 'B'], ['Box'], [])
        try:
            settings._load_category('stores')
            for dialog in (department, settings, bulk):
                self.assertEqual(7, sum(check.isChecked() for check in dialog.day_checks.values()))
        finally:
            for dialog in (department, settings, bulk):
                dialog.close()


if __name__ == '__main__':
    unittest.main()
