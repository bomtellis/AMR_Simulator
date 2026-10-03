"""Generated tasks carry effective hours even when staff choice is unspecified."""
import contextlib
import io
import json
import unittest
from pathlib import Path

from simulator import Simulation
from tests.test_generation_contracts import return_config
from visualiser.models import JsonStore


class GeneratedStaffHoursTests(unittest.TestCase):
    def generated(self, config):
        sim = Simulation(config)
        return sim, sim.task_generation_manager.update_until(61)[0].task

    def test_omission_and_true_use_global_hours_but_false_allocates_no_staff(self):
        for choice in (None, True, False):
            for normalise in (False, True):
                with self.subTest(choice=choice, editor=normalise):
                    config = return_config()
                    if choice is not None:
                        config['task_generation']['categories']['stores']['requires_staff'] = choice
                    if normalise:
                        config = JsonStore(config).data
                    sim, task = self.generated(config)
                    self.assertIs(choice, task.requires_staff)
                    booking = sim._assign_staff_for_handling(task, 69, 60)
                    if choice is False:
                        self.assertIsNone(booking)
                        self.assertFalse(sim.staff_resource_pools)
                    else:
                        self.assertEqual(('09:00', '17:00'), (task.staff_shift_start_time, task.staff_shift_end_time))
                        self.assertEqual((32400, 32460), (booking['start_time'], booking['finish_time']))

    def test_global_active_days_are_applied_to_legacy_omission(self):
        config = return_config()
        config['task_generation']['staff_config'] = {'shift_patterns': {'none': {
            'start_time': '10:00', 'end_time': '18:00', 'days_active': ['tue']}}}
        for data in (config, JsonStore(config).data):
            sim, task = self.generated(data)
            booking = sim._assign_staff_for_handling(task, 69, 60)
            self.assertEqual(['tue'], task.staff_shift_days_active)
            self.assertEqual(86400 + 10 * 3600, booking['start_time'])

    def test_global_end_time_defers_work_that_cannot_fit(self):
        config = return_config()
        config['task_generation']['staff_config'] = {'shift_patterns': {'none': {
            'start_time': '00:00', 'end_time': '00:01', 'days_active': ['mon']}}}
        for data in (config, JsonStore(config).data):
            sim, task = self.generated(data)
            booking = sim._assign_staff_for_handling(task, 50, 30)
            # Only ten seconds remain this Monday; next Monday has a full minute.
            self.assertEqual(7 * 86400, booking['start_time'])
            self.assertFalse(booking['working_hours_fallback'])

    def test_attaching_hours_does_not_create_staff_for_nonstores_omission(self):
        config = return_config()
        categories = config['task_generation']['categories']
        categories['linen'] = categories.pop('stores')
        sim, task = self.generated(config)
        self.assertIsNone(task.requires_staff)
        self.assertEqual('09:00', task.staff_shift_start_time)
        self.assertIsNone(sim._assign_staff_for_handling(task, 69, 60))
        self.assertFalse(sim.staff_resource_pools)

    def test_group_rotating_pattern_and_custom_weekly_hours_remain_effective(self):
        config = return_config()
        group = config['task_generation']['categories']['stores']['department_groups'][0]['payload']
        group.update(staff_shift_pattern='four_on_four_off_12h', staff_use_custom_working_hours=True,
                     staff_working_hours={'mon': {'enabled': True, 'start_time': '11:00', 'end_time': '15:00'}})
        sim, task = self.generated(config)
        self.assertEqual(('07:00', '19:00'), (task.staff_shift_start_time, task.staff_shift_end_time))
        booking = sim._assign_staff_for_handling(task, 69, 60)
        self.assertEqual(11 * 3600, booking['start_time'])  # Custom hours override global 07:00.
        self.assertEqual(('A', 2), (booking['staff_shift_team'], booking['people_required']))

    def test_return_timing_reconciles_with_recorded_staff_finish(self):
        for choice, expected, count in [(None, '09:03:00.000', 1), (True, '09:03:00.000', 1),
                                        (False, '00:02:09.000', 0)]:
            for normalise in (False, True):
                with self.subTest(choice=choice, editor=normalise):
                    config = return_config()
                    category = config['task_generation']['categories']['stores']
                    category['staff_handling_minutes'] = 3
                    if choice is not None:
                        category['requires_staff'] = choice
                    if normalise:
                        config = JsonStore(config).data
                    sim = Simulation(config, verbose=True)
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim.run()
                    self.assertFalse(sim.failed_tasks)
                    self.assertEqual(2, len(sim.completed_task_records))
                    self.assertEqual('2026-01-05 '+expected, sim.completed_task_records[1]['start_datetime'])
                    handling = [row for row in sim.verbose_rows if row['event_type'] == 'staff_payload_handling']
                    self.assertEqual(count, len(handling))
                    if count:
                        self.assertEqual(180, handling[0]['duration_sec'])
                        self.assertEqual('2026-01-05 09:03:00.000', handling[0]['end_time'])

    def test_existing_saved_return_reference_observes_default_hours(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/generation-return-import.json'
        config = json.loads(path.read_text(encoding='utf-8'))
        for data in (config, JsonStore(config).data):
            sim = Simulation(data)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual(2, len(sim.completed_task_records))
            self.assertEqual('2026-01-05 09:01:00.000', sim.completed_task_records[1]['start_datetime'])

    def test_forced_zone_handoff_still_attaches_hours_despite_explicit_false(self):
        config = return_config()
        config['locations'].append({'name': 'C', 'floor': 0, 'x': 20, 'y': 20})
        config['task_generation']['categories']['stores']['requires_staff'] = False
        config['departments'][0]['task_generation_locations'] = {'stores': {
            'pickup_dropoff_locations': ['C'], 'dropoff_zone_locations': ['B']}}
        sim, task = self.generated(config)
        self.assertTrue(task.requires_staff)
        self.assertEqual(('B', 'C'), (task.dropoff_zone, task.final_destination))
        self.assertEqual('09:00', task.staff_shift_start_time)
        self.assertIsNotNone(sim._task_staff_handling_config(task))


if __name__ == '__main__':
    unittest.main()
