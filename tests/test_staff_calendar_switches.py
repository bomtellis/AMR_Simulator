"""Independent staff calendar and timeframe-release switch expectations."""
import copy
import unittest

from amr_demand_preview import build_demand_preview
from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore


def timeframe_config():
    config = grouped_config()
    config['simulation']['end_datetime'] = '2026-01-05T18:00:00'
    config['task_generation']['categories']['stores'].update(
        generation_mode='timeframe', timeframe_start='08:00', timeframe_end='18:00',
        timeframe_payload_multiple=4)
    return config


class StaffCalendarSwitchTests(unittest.TestCase):
    def records(self, config):
        sim = Simulation(config)
        records = sim.task_generation_manager.update_until(18 * 3600)
        return sim, [r.task for r in records]

    def test_omission_and_true_spread_identically_and_false_remains_unstaffed(self):
        for choice in (None, True, False):
            for editor in (False, True):
                with self.subTest(choice=choice, editor=editor):
                    config = timeframe_config()
                    if choice is not None:
                        config['task_generation']['categories']['stores']['requires_staff'] = choice
                    if editor:
                        config = JsonStore(config).data
                    sim, tasks = self.records(config)
                    expected = [8 * 3600] * 4 if choice is False else [h * 3600 for h in (9, 11, 13, 15)]
                    self.assertEqual(expected, [t.release_time for t in tasks])
                    self.assertEqual(expected, [t['release_seconds'] for t in build_demand_preview(config)['tasks']])
                    booking = sim._assign_staff_for_handling(tasks[0], 60, 60)
                    if choice is False:
                        self.assertIsNone(booking)
                    else:
                        self.assertEqual(9 * 3600, booking['start_time'])

    def test_spread_off_changes_releases_but_not_runtime_hours(self):
        config = timeframe_config()
        config['task_generation']['staff_config'] = {'spread_timeframe_tasks': False}
        sim, tasks = self.records(config)
        self.assertEqual([8 * 3600] * 4, [t.release_time for t in tasks])
        self.assertEqual(9 * 3600, sim._assign_staff_for_handling(tasks[0], 60, 60)['start_time'])

    def test_global_patterns_off_disables_global_hours_and_rotation_not_staff(self):
        config = timeframe_config()
        config['task_generation']['staff_config'] = {'enabled': False}
        config['task_generation']['categories']['stores']['staff_shift_pattern'] = 'four_on_four_off_12h'
        for data in (config, JsonStore(config).data):
            sim, tasks = self.records(data)
            self.assertEqual([8 * 3600] * 4, [t.release_time for t in tasks])
            booking = sim._assign_staff_for_handling(tasks[0], 60, 60)
            self.assertEqual((60, 120), (booking['start_time'], booking['finish_time']))
            self.assertEqual(('', 1), (booking['staff_shift_team'], booking['people_required']))

    def test_custom_hours_and_spreading_survive_global_pattern_disable(self):
        config = timeframe_config()
        config['task_generation']['staff_config'] = {'enabled': False, 'spread_timeframe_tasks': True}
        config['task_generation']['categories']['stores'].update(
            staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '10:00', 'end_time': '14:00'}})
        for data in (config, JsonStore(config).data):
            sim, tasks = self.records(data)
            self.assertEqual([h * 3600 for h in (10, 11, 12, 13)], [t.release_time for t in tasks])
            self.assertEqual(10 * 3600, sim._assign_staff_for_handling(tasks[0], 60, 60)['start_time'])

    def test_two_groups_share_four_slots_and_calendar_does_not_consume_them(self):
        config = timeframe_config()
        category = config['task_generation']['categories']['stores']
        category['timeframe_payload_multiple'] = 2
        other = copy.deepcopy(category['department_groups'][0])
        other['id'] = 'G2'
        category['department_groups'].append(other)
        sim = Simulation(config)
        expected = [h * 3600 for h in (9, 11, 13, 15)]
        manager = sim.task_generation_manager
        self.assertEqual(expected, manager.scheduled_wake_times(18 * 3600))
        self.assertEqual(expected, sorted(r.task.release_time for r in manager.update_until(18 * 3600)))
        self.assertEqual([], manager.update_until(18 * 3600))

    def test_partial_horizon_does_not_claim_independent_unspaced_count(self):
        config = timeframe_config()
        config['simulation']['end_datetime'] = '2026-01-05T10:00:00'
        preview = build_demand_preview(config)
        self.assertEqual([9 * 3600], [t['release_seconds'] for t in preview['tasks']])
        self.assertIsNone(preview['rules'][0]['expected_fixed_records'])

    def test_fixed_scheduled_releases_do_not_move_with_staff_calendar(self):
        config = grouped_config()
        sim, tasks = self.records(config)
        self.assertEqual([60], [t.release_time for t in tasks])
        self.assertEqual(9 * 3600, sim._assign_staff_for_handling(tasks[0], 69, 60)['start_time'])

    def test_disabled_patterns_do_not_split_custom_hour_group_slots(self):
        config = timeframe_config()
        config['task_generation']['staff_config'] = {'enabled': False}
        category = config['task_generation']['categories']['stores']
        category.update(timeframe_payload_multiple=2, staff_use_custom_working_hours=True,
                        staff_working_hours={'mon': {'enabled': True, 'start_time': '09:00', 'end_time': '17:00'}})
        other = copy.deepcopy(category['department_groups'][0])
        other['id'] = 'G2'
        other['payload']['staff_shift_pattern'] = 'four_on_four_off_12h'
        category['department_groups'].append(other)
        _, tasks = self.records(config)
        self.assertEqual([h * 3600 for h in (9, 11, 13, 15)], sorted(t.release_time for t in tasks))

    def test_legacy_source_payload_and_id_routes_share_runtime_resolution(self):
        for mode in ('source', 'payload', 'id', 'id_punctuation'):
            with self.subTest(mode=mode):
                config = timeframe_config()
                categories = config['task_generation']['categories']
                category = categories.pop('stores')
                key = {'id': 'stores_extra', 'id_punctuation': '_stores-extra_'}.get(mode, 'other')
                categories[key] = category
                if mode == 'source':
                    category['task_source'] = 'stores'
                elif mode == 'payload':
                    config['payloads'][0]['name'] = 'stores'
                    category['payload'] = 'stores'
                sim, tasks = self.records(config)
                self.assertEqual([h * 3600 for h in (9, 11, 13, 15)], [t.release_time for t in tasks])
                self.assertIsNotNone(sim._task_staff_handling_config(tasks[0]))


if __name__ == '__main__':
    unittest.main()
