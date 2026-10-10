"""Four-day team boundaries constrain the whole travel-and-service reservation."""
import contextlib
import io
import unittest

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_staff_contention import staff_task
from tests.test_generation_contracts import return_config
from visualiser.models import JsonStore


BLOCK = 4 * 24 * 3600
PATTERN = 'four_on_four_off_12h'


class StaffShiftBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(reference_config(), verbose=True)

    def book(self, name, start, duration, location='B', policy='available_first', **settings):
        task = staff_task(name, location=location, policy=policy,
                          staff_shift_pattern=PATTERN, **settings)
        booking = self.sim._assign_staff_for_handling(task, start, duration)
        with contextlib.redirect_stdout(io.StringIO()):
            self.sim._log_staff_handling_assignment(task, booking)
        return booking

    def test_travel_deferral_reselects_team_without_mutating_previous_roster(self):
        for policy in ('available_first', 'batch_same_location', 'minimise_movement'):
            with self.subTest(policy=policy):
                self.setUp()
                self.book('last-A', BLOCK - 60, 55, policy=policy)
                booking = self.book('next', BLOCK - 1, 1, 'A', policy)
                self.assertEqual('B', booking['staff_shift_team'])
                self.assertEqual((BLOCK, BLOCK + 1), (booking['start_time'], booking['finish_time']))
                self.assertEqual(BLOCK - 1, booking['requested_start_time'])
                self.assertEqual(1, booking['staff_wait_for_travel_sec'])
                self.assertEqual(0, booking['travel_duration_sec'])
                rosters = self.sim.staff_resource_pools['stores']['shift_rosters']
                self.assertEqual([BLOCK - 5], rosters['A']['available_times'])
                self.assertEqual(['B'], rosters['A']['last_locations'])
                self.assertEqual([BLOCK + 1], rosters['B']['available_times'])
                records = [row for row in self.sim.verbose_rows if row['task_id'] == 'next'
                           and row['event_type'] == 'staff_payload_handling']
                self.assertEqual('B', records[0]['staff_shift_team'])
                self.assertEqual(booking['person_id'], records[0]['person_id'])
                self.assertEqual(2, len(self.sim.staff_assignments))

    def test_returning_team_recomputes_travel_from_its_own_location(self):
        self.book('old-B', BLOCK + 10, 1)  # Team B ends at B in its earlier block.
        self.book('last-A', 3 * BLOCK - 60, 55)
        booking = self.book('returning-B', 3 * BLOCK - 1, 1, 'A')
        self.assertEqual('B', booking['staff_shift_team'])
        self.assertEqual('B', booking['travel_from_location'])
        self.assertEqual(3 * BLOCK, booking['travel_start_time'])
        self.assertAlmostEqual(3 * BLOCK + 10 / 1.2, booking['start_time'], delta=.0005)
        self.assertEqual(10, booking['travel_distance_m'])

    def test_busy_incoming_roster_expands_without_using_outgoing_person(self):
        self.book('future-B', BLOCK, 60)
        self.book('last-A', BLOCK - 60, 55)
        booking = self.book('next', BLOCK - 1, 1, 'A')
        self.assertEqual('stores-shift-B-person-2', booking['person_id'])
        self.assertTrue(booking['added_person'])
        self.assertEqual(BLOCK, booking['start_time'])
        self.assertEqual(4, booking['people_required'])  # Peak 2 per team, two teams.

    def test_overnight_service_cannot_straddle_the_team_boundary(self):
        booking = self.book('overnight', BLOCK - 1, 2,
                            staff_shift_start_time='22:00', staff_shift_end_time='06:00')
        self.assertEqual('B', booking['staff_shift_team'])
        self.assertEqual((BLOCK, BLOCK + 2), (booking['start_time'], booking['finish_time']))
        self.assertFalse(booking['working_hours_fallback'])

    def test_exact_finish_at_boundary_is_allowed_for_outgoing_team(self):
        booking = self.book('last-second', BLOCK - 1, 1)
        self.assertEqual('A', booking['staff_shift_team'])
        self.assertEqual(BLOCK, booking['finish_time'])

    def test_block_origin_is_simulation_start_even_when_it_is_midday(self):
        cfg = reference_config()
        cfg['simulation']['start_datetime'] = '2026-01-05T12:00:00'
        cfg['simulation']['end_datetime'] = '2026-01-05T12:10:00'
        self.sim = Simulation(cfg)
        self.book('last-A', BLOCK - 60, 55)
        booking = self.book('next', BLOCK - 1, 1, 'A')
        self.assertEqual('B', booking['staff_shift_team'])
        self.assertEqual((BLOCK, BLOCK + 1), (booking['start_time'], booking['finish_time']))

    def test_impossible_travel_is_bounded_and_exposes_schedule_fallback(self):
        cfg = reference_config()
        cfg['locations'][1].update(x=1000000, y=0)
        self.sim = Simulation(cfg, verbose=True)
        self.book('old-A', 100, 1)
        self.book('old-B', BLOCK + 100, 1)
        booking = self.book('impossible-walk', 2 * BLOCK + 100, 1, 'A')
        self.assertTrue(booking['working_hours_fallback'])
        self.assertGreater(booking['travel_duration_sec'], BLOCK)
        rows = [r for r in self.sim.verbose_rows if r['task_id'] == 'impossible-walk'
                and r['event_type'] == 'staff_payload_handling']
        self.assertTrue(rows[0]['staff_working_hours_fallback'])
        self.assertEqual(3, len(self.sim.staff_assignments))

    def test_available_person_within_block_is_used_before_waiting_for_next_team(self):
        self.book('at-B', BLOCK - 60, 55, staff_initial_count=2)
        self.book('at-A', BLOCK - 60, 55, location='A', staff_initial_count=2)
        booking = self.book('last-second', BLOCK - 1, 1, 'A')
        self.assertEqual('stores-shift-A-person-2', booking['person_id'])
        self.assertEqual((BLOCK - 1, BLOCK), (booking['start_time'], booking['finish_time']))
        self.assertFalse(booking['added_person'])

    def test_generated_pattern_and_group_override_reach_runtime_with_editor_parity(self):
        for override, expected_pattern, expected_start, people in [
            (None, PATTERN, 7 * 3600, 2), ('none', 'none', 9 * 3600, 1)
        ]:
            cfg = return_config()
            category = cfg['task_generation']['categories']['stores']
            category.update(requires_staff=True, staff_shift_pattern=PATTERN)
            if override is not None:
                category['department_groups'][0]['payload']['staff_shift_pattern'] = override
            for data in (cfg, JsonStore(cfg).data):
                with self.subTest(override=override, editor=data is not cfg):
                    sim = Simulation(data)
                    task = sim.task_generation_manager.update_until(61)[0].task
                    self.assertEqual(expected_pattern, task.staff_shift_pattern)
                    booking = sim._assign_staff_for_handling(task, 60, 60)
                    self.assertEqual(expected_start, booking['start_time'])
                    self.assertEqual(people, booking['people_required'])


if __name__ == '__main__':
    unittest.main()
