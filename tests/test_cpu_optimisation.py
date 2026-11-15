"""Exact booking, calendar and route semantics under CPU optimisations."""
import copy
from datetime import datetime, timedelta, timezone
import random
import unittest
from unittest.mock import Mock, patch

from amr_route_reservations import (LiftReservations, latest_lift_reservation,
                                    RouteReservationTransaction)
from amr_sim_task_generation import (DynamicCategoryTaskGenerator,
    _department_operating_periods_for_date, _department_periods_cached)
from amr_sim_models import Task
from simulator import Simulation
from tests.test_lift_reservation_order import simulation, book
from tests.test_charge_travel_reference import config as corridor_config
from tests.test_route_reservation_atomicity import resource_state


class LiftBookingIndexTests(unittest.TestCase):
    def assert_index(self, rows):
        expected = max(rows, key=lambda row: row[1], default=None)
        self.assertIs(expected, latest_lift_reservation(rows))

    def test_mutations_match_linear_max_including_ties_and_out_of_order_ends(self):
        rng = random.Random(77)
        rows = LiftReservations()
        for step in range(500):
            value = (step, rng.randrange(5), 0, 1, str(step))
            operation = rng.randrange(8)
            if operation == 0:
                rows.append(value)
            elif operation == 1:
                rows.insert(rng.randrange(len(rows) + 1), value)
            elif operation == 2:
                rows.extend([value, (step, 9, 1, 0, str(step))])
            elif operation == 3 and rows:
                rows.pop(rng.randrange(len(rows)))
            elif operation == 4 and rows:
                rows[rng.randrange(len(rows))] = value
            elif operation == 5:
                rows.reverse()
            elif operation == 6:
                rows.sort()
            elif rows:
                del rows[:rng.randrange(len(rows) + 1)]
            self.assert_index(rows)
        rows += rows
        self.assert_index(rows)
        rows *= 2
        self.assert_index(rows)
        self.assert_index(copy.deepcopy(rows))
        rows.clear()
        self.assert_index(rows)

    def test_plain_lists_keep_max_finish_and_first_on_ties(self):
        first = (0, 100, 0, 1, 'first')
        rows = [first, (5, 100, 1, 0, 'tie'), (10, 20, 0, 1, 'last')]
        self.assertIs(first, latest_lift_reservation(rows))
        indexed = LiftReservations(rows)
        self.assertIs(first, indexed.latest)
        indexed.insert(0, (0, 100, 0, 0, 'earlier tie'))
        self.assert_index(indexed)
        indexed.remove(indexed.latest)
        self.assertIs(first, indexed.latest)

    def test_rollback_restores_tail_and_complete_booking_history(self):
        sim = simulation(wear=10)
        book(sim, 100, 0, 1, 'committed')
        before = copy.deepcopy(resource_state(sim))
        with RouteReservationTransaction(sim, sim.amrs[0], [Task('T', 'A', 'B', 'Box')]):
            book(sim, 200, 1, 0, 'rolled back')
            self.assertEqual('rolled back', sim.lift_reservations['L1'].latest[4])
        self.assertEqual(before, resource_state(sim))
        self.assertEqual('committed', sim.lift_reservations['L1'].latest[4])
        self.assert_index(sim.lift_reservations['L1'])


class CalendarCacheTests(unittest.TestCase):
    def test_raw_clock_types_do_not_share_a_cache_entry(self):
        day = datetime(2026, 1, 5)
        self.assertTrue(_department_operating_periods_for_date(
            dict(operating_start_time=0), day))
        with self.assertRaises(ValueError):
            _department_operating_periods_for_date(dict(operating_start_time=False), day)

    def test_equal_instants_in_different_zones_keep_their_local_active_day(self):
        monday = datetime(2026, 1, 5, tzinfo=timezone(timedelta(hours=14)))
        sunday = datetime(2026, 1, 4, tzinfo=timezone(timedelta(hours=-10)))
        self.assertEqual(monday, sunday)
        dept = dict(days_active=['mon'])
        self.assertTrue(_department_operating_periods_for_date(dept, monday))
        self.assertEqual([], _department_operating_periods_for_date(dept, sunday))

    def test_overnight_mutation_disabled_days_and_result_isolation(self):
        day = datetime(2026, 1, 5)
        dept = dict(days_active=['mon'], operating_start_time='22:00',
                    operating_end_time='06:00')
        expected = [(day + timedelta(hours=22), day + timedelta(days=1, hours=6))]
        self.assertEqual(expected, _department_operating_periods_for_date(dept, day))
        returned = _department_operating_periods_for_date(dept, day)
        returned.clear()
        self.assertEqual(expected, _department_operating_periods_for_date(dept, day))
        dept['operating_end_time'] = '07:00'
        self.assertEqual(day + timedelta(days=1, hours=7),
                         _department_operating_periods_for_date(dept, day)[0][1])
        dept['days_active'] = ['tue']
        self.assertEqual([], _department_operating_periods_for_date(dept, day))
        dept['days_active'] = ['']
        self.assertEqual([], _department_operating_periods_for_date(dept, day))
        dept['days_active'] = []
        self.assertTrue(_department_operating_periods_for_date(dept, day))
        dept['enabled'] = False
        self.assertEqual([], _department_operating_periods_for_date(dept, day))

    def test_legacy_hours_equal_clocks_and_bounded_cache_hits(self):
        day = datetime(2026, 1, 5)
        dept = dict(operating_start_time='08', hours_operated_per_day=0)
        _department_periods_cached.cache_clear()
        expected = [(day + timedelta(hours=8), day + timedelta(days=1, hours=8))]
        self.assertEqual(expected, _department_operating_periods_for_date(dept, day))
        self.assertEqual(expected, _department_operating_periods_for_date(dept, day))
        self.assertEqual(1, _department_periods_cached.cache_info().hits)
        dept['hours_operated_per_day'] = 2
        self.assertEqual(day + timedelta(hours=10),
                         _department_operating_periods_for_date(dept, day)[0][1])

    def test_excluded_member_fallback_is_cached_without_redistribution(self):
        gen = DynamicCategoryTaskGenerator.__new__(DynamicCategoryTaskGenerator)
        included, excluded = {'key': 'active'}, {'key': 'excluded'}
        gen._timeframe_allocation_cache = {}
        gen._timeframe_group_members = {'group': [included, excluded]}
        gen._timeframe_group_key = Mock(return_value='group')
        gen._instance_has_active_timeframe = Mock(side_effect=lambda item, day: item is included)
        gen._timeframe_instance_task_count = Mock(return_value=4)
        day = datetime(2026, 1, 5)
        self.assertEqual((0, 4), gen._timeframe_group_allocation(excluded, day))
        calls = gen._instance_has_active_timeframe.call_count
        self.assertEqual((0, 4), gen._timeframe_group_allocation(excluded, day))
        self.assertEqual(calls, gen._instance_has_active_timeframe.call_count)
        self.assertEqual((0, 4), gen._timeframe_group_allocation(included, day))


class CorridorFastPathTests(unittest.TestCase):
    def check_lift_pruning(self, detailed):
        sim = simulation()
        for identity in ('L2', 'L3'):
            lift = copy.deepcopy(sim.lifts[0])
            lift.id = identity
            sim.lifts.append(lift)
        sim.geometric_motion = detailed
        finishes = {'L1': 50, 'L2': 70, 'L3': 40}
        outgoing = []

        def slot(lift, arrival, origin, destination):
            finish = finishes[lift.id]
            return dict(lift_start=finish - 5, lift_finish=finish,
                reposition_from_floor=0, reposition_to_floor=0, reposition_sec=0,
                reposition_finish=finish - 5, loaded_start=finish - 4,
                loaded_finish=finish - 1, loaded_travel_sec=3)

        def route(robot, start, end, **kwargs):
            if start.floor == 0:
                return [], 0, 0
            identity = start.name.split('-F')[0]
            outgoing.append(identity)
            return [], (0 if identity == 'L2' else 20), 1

        with patch.object(sim, '_find_lift_journey_slot', side_effect=slot), \
             patch.object(sim, '_same_floor_segments', side_effect=route):
            plan = sim._nearest_compatible_lift_plan(0, sim.amrs[0],
                sim.locations['A'], sim.locations['B'], sim.payloads['Box'])
        self.assertEqual('L3', plan['lift'].id)
        self.assertEqual(60, plan['final_finish'])
        self.assertEqual(['L1', 'L2', 'L3'] if detailed else ['L1', 'L3'], outgoing)

    def test_simple_lift_bound_skips_only_a_proven_nonwinning_alternative(self):
        self.check_lift_pruning(False)

    def test_detailed_lift_alternatives_still_require_outgoing_geometry(self):
        self.check_lift_pruning(True)

    def test_no_people_skips_queries_without_changing_reserved_traffic_timing(self):
        sim = Simulation(corridor_config())
        robot = sim.amrs[0]
        sim._reserve_edge('A', 'B', 0, 4, 'blocker')
        with patch.object(sim, '_people_on_edge', side_effect=AssertionError('empty people query')):
            full = sim._same_floor_segments(robot, sim.locations['A'], sim.locations['B'],
                                            start_time_value=0)
            numeric = sim._same_floor_segments(robot, sim.locations['A'], sim.locations['B'],
                                               start_time_value=0, collect_segments=False)
        self.assertEqual(full[1:], numeric[1:])
        self.assertGreater(full[1], 4)
        self.assertEqual([], numeric[0])

    def test_people_overlap_still_changes_duration_and_report_fields(self):
        sim = Simulation(corridor_config())
        robot = sim.amrs[0]
        key = sim._physical_edge_key('A', 'B')
        sim.people_edge_reservations[key] = [dict(start=0, end=100, count=2,
                                                speed_factor=.5, group_type='staff')]
        with patch.object(sim, '_people_on_edge', wraps=sim._people_on_edge) as query:
            route = sim._same_floor_segments(robot, sim.locations['A'], sim.locations['B'],
                                             start_time_value=0)
        self.assertTrue(query.called)
        corridor = next(row for row in route[0] if row['type'] == 'corridor')
        self.assertEqual(2, corridor['people_count'])
        self.assertEqual('staff', corridor['people_groups'])
        self.assertGreater(corridor['people_delay_sec'], 0)

    def test_stowed_idle_return_exits_before_destination_search(self):
        sim = Simulation(corridor_config())
        with patch.object(sim, '_amr_is_stowed_at_configured_charge_space', return_value=True), \
             patch.object(sim, '_charge_location_for_idle_return', side_effect=AssertionError('route search')):
            self.assertIsNone(sim._create_idle_return_task(sim.amrs[0], 0))


if __name__ == '__main__':
    unittest.main()
