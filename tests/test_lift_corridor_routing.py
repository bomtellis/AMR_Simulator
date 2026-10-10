"""Lift stops require a floor change, rather than joining adjacent corridors."""
import contextlib
from copy import deepcopy
import io
import unittest

from amr_sim_models import Task
from simulator import Simulation
from tests.test_delivery_energy_reference import lift_config
from tests.test_generation_reference import grouped_config
from visualiser.project_checks import check_project


def junction_config(bypass=False):
    config = lift_config()
    config['amrs'][0]['multi_stop_enabled'] = False
    config['locations'] = [dict(name=n, floor=f, x=x, y=y) for n, f, x, y in
                           [('A', 0, 0, 0), ('B', 0, 4, 0), ('C', 1, 4, 0)]]
    config['corridors']['nodes'] = [dict(name=n, floor=f, x=x, y=y) for n, f, x, y in
                                   [('West', 0, 1, 0), ('East', 0, 3, 0), ('Upper', 1, 3, 0)]]
    config['lifts'][0]['floor_locations'] = {'0': dict(x=2, y=0), '1': dict(x=2, y=0)}
    pairs = [('A', 'West', 1), ('West', 'L1-F0', 1), ('L1-F0', 'East', 1),
             ('East', 'B', 1), ('L1-F1', 'Upper', 1), ('Upper', 'C', 1)]
    if bypass:
        config['corridors']['nodes'].append(dict(name='Around', floor=0, x=2, y=4))
        pairs.extend([('West', 'Around', 5), ('Around', 'East', 5)])
    config['corridors']['edges'] = [dict(zip(('from', 'to', 'distance_m'), pair), width_m=3)
                                    for pair in pairs]
    return config


class LiftCorridorRoutingTests(unittest.TestCase):
    def run_case(self, config):
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            sim.run()
        return sim

    def test_lift_cannot_be_a_forward_reverse_or_bidirectional_meeting_point(self):
        for directed in (False, True):
            config = junction_config()
            for edge in config['corridors']['edges']:
                edge['bidirectional'] = not directed
            sim = Simulation(config)
            for start, end in [('A', 'B'), ('West', 'East'), ('B', 'A'), ('East', 'West')]:
                with self.subTest(directed=directed, start=start, end=end):
                    self.assertIsNone(sim._shortest_path_same_floor(0, start, end))
                    # Cached failure must also stay blocked.
                    self.assertIsNone(sim._shortest_path_same_floor(0, start, end))

    def test_longer_corridor_route_is_used_in_both_directions(self):
        sim = Simulation(junction_config(bypass=True))
        for start, end, expected in [('A', 'B', ['West', 'Around', 'East', 'B']),
                                      ('B', 'A', ['East', 'Around', 'West', 'A'])]:
            route = sim._shortest_path_same_floor(0, start, end)
            self.assertEqual(12, route['distance_m'])
            self.assertEqual(expected, [edge['to'] for edge in route['edges']])

    def test_lift_approach_departure_and_zero_length_endpoints_remain_available(self):
        sim = Simulation(junction_config())
        for floor, start, end in [(0, 'A', 'L1-F0'), (0, 'L1-F0', 'A'),
                                   (0, 'B', 'L1-F0'), (0, 'L1-F0', 'B'),
                                   (1, 'L1-F1', 'C'), (1, 'C', 'L1-F1')]:
            with self.subTest(start=start, end=end):
                self.assertEqual(2, sim._shortest_path_same_floor(floor, start, end)['distance_m'])
        self.assertEqual([], sim._shortest_path_same_floor(0, 'L1-F0', 'L1-F0')['edges'])

    def test_executed_same_floor_delivery_uses_corridors_for_all_estimate_and_cache_modes(self):
        for fast in (False, True):
            for precompute in (False, True):
                with self.subTest(fast=fast, precompute=precompute):
                    config = junction_config(bypass=True)
                    config['simulation'].update(fast_assignment_estimates=fast,
                                                precompute_static_routes=precompute)
                    config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
                    sim = self.run_case(config)
                    self.assertEqual(1, len(sim.completed_task_records))
                    rows = [r for r in sim.verbose_rows if r['event_type'] == 'segment_corridor']
                    self.assertEqual([('A', 'West'), ('West', 'Around'), ('Around', 'East'), ('East', 'B')],
                                     [(r['from_location'], r['to_location']) for r in rows])
                    self.assertFalse(any(r['segment_type'] == 'lift_transfer' for r in sim.verbose_rows))

    def test_no_corridor_bypass_fails_feasibility_and_delivery(self):
        config = junction_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        sim = self.run_case(config)
        self.assertEqual({'T'}, sim.failed_task_ids)
        self.assertEqual([], sim.completed_task_records)
        self.assertFalse(sim._route_possible_between_locations(
            sim.amrs[0], sim.locations['A'], sim.locations['B'], sim.payloads['Box']))

    def test_actual_floor_change_still_boards_and_alights_from_either_corridor_side(self):
        for pickup in ('A', 'B'):
            config = junction_config()
            config['building']['charge_location'] = pickup
            config['tasks'] = [dict(id='T', pickup=pickup, dropoff='C', payload='Box',
                                     return_enabled=True, return_payload='Box')]
            sim = self.run_case(config)
            self.assertEqual(2, len(sim.completed_task_records))
            self.assertFalse(sim.failed_task_ids)
            transfers = [r for r in sim.verbose_rows if r['segment_type'] == 'lift_transfer']
            self.assertEqual(2, len(transfers))
            self.assertTrue(all(r['start_floor'] != r['end_floor'] for r in transfers))

    def test_multistop_loaded_legs_cannot_cross_a_same_floor_lift(self):
        for bypass in (False, True):
            config = junction_config(bypass)
            config['amrs'][0]['multi_stop_enabled'] = True
            sim = Simulation(config)
            tasks = [Task(f'T{i}', 'A', 'B', 'Box') for i in (1, 2)]
            plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=False)
            if not bypass:
                self.assertIsNone(plan)
            else:
                self.assertIsNotNone(plan)
                self.assertFalse(any('L1-F' in s.get('from', '') + s.get('to', '') for s in plan['segments']))

    def test_cross_floor_approach_cannot_cut_through_another_lift(self):
        config = junction_config()
        other = deepcopy(config['lifts'][0]); other['id'] = 'L2'
        config['lifts'].append(other)
        config['corridors']['edges'] = [e for e in config['corridors']['edges']
                                        if e['from'] != 'West']
        config['corridors']['edges'].extend([
            dict(**{'from': 'West', 'to': 'L2-F0'}, width_m=3),
            dict(**{'from': 'L2-F0', 'to': 'East'}, width_m=3)])
        config['tasks'] = [dict(id='T', pickup='A', dropoff='C', payload='Box')]
        sim = self.run_case(config)
        self.assertEqual({'T'}, sim.failed_task_ids)
        self.assertEqual('Blocked', check_project(config, include_legacy=False).route_checks[0]['status'])

    def test_profile_permissions_cannot_turn_lift_stops_into_corridor_junctions(self):
        config = junction_config(bypass=True)
        config['route_profiles'] = {'p': {'allowed_nodes': ['A', 'West', 'L1-F0', 'East', 'B'],
                                          'allowed_lifts': ['L1']}}
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='p')]
        sim = Simulation(config)
        rules = sim._resolve_task_route_rules(Task(**config['tasks'][0]))
        self.assertIsNone(sim._shortest_path_same_floor(0, 'A', 'B', rules))
        report = check_project(config, include_legacy=False)
        self.assertEqual('Blocked', report.route_checks[0]['status'])
        self.assertIn('permissions', report.route_checks[0]['reason'])

    def test_manual_generated_and_return_checks_follow_runtime_rule(self):
        for bypass, status in [(False, 'Blocked'), (True, 'Reachable')]:
            config = junction_config(bypass)
            generation = grouped_config()
            config['task_generation'] = generation['task_generation']
            config['departments'] = generation['departments']
            config['tasks'] = [dict(id='Same', pickup='A', dropoff='B', payload='Box',
                                     return_enabled=True, return_payload='Box'),
                               dict(id='Vertical', pickup='A', dropoff='C', payload='Box')]
            before = deepcopy(config)
            report = check_project(config, include_legacy=False)
            self.assertEqual(before, config)
            rows = report.route_checks
            self.assertEqual([status, status, 'Reachable', status], [r['status'] for r in rows])
            self.assertEqual('Generated rule', rows[-1]['source'])
            if not bypass:
                self.assertIn('Lift stops cannot connect corridors', rows[0]['reason'])

    def test_check_does_not_allow_an_up_and_down_detour_to_bypass_a_gap(self):
        config = junction_config()
        # A different lift offers a path back to B, but runtime requires a
        # corridor path for A -> B on floor 0, never an up-and-down detour.
        other = deepcopy(config['lifts'][0]); other['id'] = 'L2'
        config['lifts'].append(other)
        config['corridors']['edges'].extend([
            dict(**{'from': 'C', 'to': 'L2-F1'}, width_m=3),
            dict(**{'from': 'L2-F0', 'to': 'B'}, width_m=3)])
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        self.assertEqual('Blocked', check_project(config, include_legacy=False).route_checks[0]['status'])

    def test_one_floor_lift_is_also_an_endpoint_not_a_junction(self):
        config = junction_config()
        config['lifts'][0].update(served_floors=[0], floor_locations={'0': dict(x=2, y=0)})
        config['corridors']['edges'] = [e for e in config['corridors']['edges']
                                        if e['from'] not in ('L1-F1', 'Upper')]
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        self.assertIsNone(Simulation(config)._shortest_path_same_floor(0, 'A', 'B'))
        self.assertEqual('Blocked', check_project(config, include_legacy=False).route_checks[0]['status'])


if __name__ == '__main__':
    unittest.main()
