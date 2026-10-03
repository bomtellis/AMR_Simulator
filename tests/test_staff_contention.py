"""Independent booking expectations for the existing staffing-sizing model.

Direct planner calls deliberately include out-of-order reservations: simulation
planning can reserve future services before an earlier service is assigned.
"""
import unittest

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_generation_contracts import return_config
from visualiser.models import JsonStore


def staff_task(name, location='B', policy='available_first', **settings):
    return Task(name, 'A', location, 'Box', requires_staff=True,
                staff_category_key='stores', staff_movement_policy=policy, **settings)


class StaffContentionTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(reference_config())

    def book(self, name, start, duration, location='B', policy='available_first', **settings):
        return self.sim._assign_staff_for_handling(
            staff_task(name, location, policy, **settings), start, duration)

    def test_busy_initial_person_expands_pool_instead_of_queueing(self):
        first = self.book('one', 100, 60)
        second = self.book('two', 110, 60)
        self.assertEqual((100, 160), (first['start_time'], first['finish_time']))
        self.assertEqual((110, 170), (second['start_time'], second['finish_time']))
        self.assertNotEqual(first['person_id'], second['person_id'])
        self.assertTrue(second['added_person'])
        self.assertEqual(2, second['staff_on_shift_people_required'])

    def test_initial_count_supplies_two_people_before_expanding(self):
        bookings = [self.book(str(i), 100, 60, staff_initial_count=2) for i in range(3)]
        self.assertEqual([False, False, True], [b['added_person'] for b in bookings])
        self.assertEqual([2, 2, 3], [b['staff_on_shift_people_required'] for b in bookings])
        self.assertEqual(3, len({b['person_id'] for b in bookings}))

    def test_group_staff_settings_override_category_in_raw_and_editor_inputs(self):
        cfg = return_config()
        category = cfg['task_generation']['categories']['stores']
        category.update(requires_staff=True, staff_initial_count=1,
                        staff_resource_name='Category', staff_movement_policy='available_first')
        category['department_groups'][0]['payload'].update(
            staff_initial_count=2, staff_resource_name='Group', staff_movement_policy='minimise_movement')
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            task = sim.task_generation_manager.update_until(61)[0].task
            effective = sim._task_staff_handling_config(task)
            self.assertEqual(2, effective['initial_count'])
            self.assertEqual('Group', effective['resource_name'])
            self.assertEqual('minimise_movement', effective['movement_policy'])

    def test_overlapping_same_location_batches_share_one_person(self):
        for policy in ('batch_same_location', 'minimise_movement'):
            with self.subTest(policy=policy):
                self.setUp()
                first = self.book('one', 100, 60, policy=policy)
                second = self.book('two', 110, 80, policy=policy)
                self.assertEqual(first['person_id'], second['person_id'])
                self.assertEqual((110, 190), (second['start_time'], second['finish_time']))
                self.assertTrue(second['shared_location_batch'])
                self.assertEqual(1, second['staff_on_shift_people_required'])
                self.assertEqual([190], self.sim.staff_resource_pools['stores']['available_times'])

    def test_touching_intervals_reuse_person_without_batching(self):
        first = self.book('one', 100, 60, policy='batch_same_location')
        second = self.book('two', 160, 20, policy='batch_same_location')
        self.assertEqual(first['person_id'], second['person_id'])
        self.assertFalse(second['shared_location_batch'])
        self.assertFalse(second['added_person'])
        self.assertEqual(180, second['finish_time'])

    def test_free_person_waits_for_ten_metre_walk_without_expansion(self):
        self.book('one', 100, 60)
        second = self.book('two', 160, 20, location='A')
        # B to A is 10 m; walking defaults to 1.2 m/s, so arrival is 168 1/3 s.
        self.assertEqual(10, second['travel_distance_m'])
        self.assertAlmostEqual(10 / 1.2, second['travel_duration_sec'], delta=.0005)
        self.assertAlmostEqual(160 + 10 / 1.2, second['start_time'], delta=.0005)
        self.assertFalse(second['added_person'])
        self.assertEqual(1, second['staff_on_shift_people_required'])

    def test_later_booking_elsewhere_cannot_be_overlapped_by_stale_batch(self):
        first = self.book('one', 100, 100, policy='batch_same_location')
        later = self.book('later', 300, 10, location='A', policy='batch_same_location')
        earlier = self.book('earlier', 150, 200, policy='batch_same_location')
        self.assertEqual(first['person_id'], later['person_id'])
        self.assertNotEqual(later['person_id'], earlier['person_id'])
        self.assertFalse(earlier['shared_location_batch'])
        self.assertEqual((150, 350), (earlier['start_time'], earlier['finish_time']))
        self.assertEqual('A', self.sim.staff_resource_pools['stores']['last_locations'][0])

    def test_future_batch_cannot_delay_an_earlier_nonoverlapping_service(self):
        future = self.book('future', 300, 60, policy='batch_same_location')
        earlier = self.book('earlier', 100, 60, policy='batch_same_location')
        self.assertEqual((100, 160), (earlier['start_time'], earlier['finish_time']))
        self.assertNotEqual(future['person_id'], earlier['person_id'])
        self.assertFalse(earlier['shared_location_batch'])

    def test_batch_cannot_extend_beyond_incoming_tasks_work_period(self):
        self.book('one', 50, 200, policy='batch_same_location')
        second = self.book('two', 100, 50, policy='batch_same_location',
                           staff_shift_start_time='00:00', staff_shift_end_time='00:03')
        self.assertEqual((100, 150), (second['start_time'], second['finish_time']))
        self.assertFalse(second['shared_location_batch'])
        self.assertTrue(second['added_person'])

    def test_service_that_does_not_fit_waits_until_next_work_period(self):
        # 120 s service cannot finish in the 60 s left today. Next day: 09:00.
        booking = self.book('one', 17 * 3600 - 60, 120,
                            staff_shift_start_time='09:00', staff_shift_end_time='17:00')
        self.assertEqual(33 * 3600, booking['start_time'])
        self.assertEqual(33 * 3600 + 120, booking['finish_time'])
        self.assertFalse(booking['working_hours_fallback'])

    def test_unusable_schedule_is_marked_as_fallback_not_valid_capacity(self):
        booking = self.book('one', 100, 60, staff_use_custom_working_hours=True,
                            staff_working_hours={})
        self.assertEqual((100, 160), (booking['start_time'], booking['finish_time']))
        self.assertTrue(booking['working_hours_fallback'])

    def test_resource_name_is_a_label_and_category_is_the_pool_key(self):
        first = self.book('one', 100, 60, staff_resource_name='Porters')
        second = self.book('two', 110, 60, staff_resource_name='Different label')
        task = staff_task('other', staff_resource_name='Porters')
        task.staff_category_key = 'cleaning'
        other = self.sim._assign_staff_for_handling(task, 110, 60)
        self.assertEqual('Porters', second['resource_name'])
        self.assertEqual(2, second['staff_on_shift_people_required'])
        self.assertEqual(1, other['staff_on_shift_people_required'])
        self.assertNotEqual(first['person_id'], other['person_id'])
        self.assertEqual({'stores', 'cleaning'}, set(self.sim.staff_resource_pools))


if __name__ == '__main__':
    unittest.main()
