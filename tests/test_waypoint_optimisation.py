"""Differential checks against the saved, unmodified waypoint implementation."""
from copy import deepcopy
import contextlib
import importlib.util
import io
import math
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

from amr_floor_routing import lift_plan_journeys, lift_plan_segments, optimistic_remaining_times
from amr_run_exports import encode
from simulator import Simulation
from tests.test_floor_waypoints import floor_config

REFERENCE = Path(__file__).resolve().parents[1] / 'verification/waypoint-search-20261109'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, REFERENCE / filename)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


original_floor = module('waypoint_original_floor', 'original_amr_floor_routing.py')
original_simulator = module('waypoint_original_simulator', 'original_simulator.py')
original_simulator.connecting_lift_plan = original_floor.connecting_lift_plan
original_simulator.projected_lift = original_floor.projected_lift


def network(seed):
    rng = random.Random(seed)
    cfg = floor_config(waypoint=True)
    cfg['building'].update(lift_transfer_floor=2,
        destination_side_lift_floors=[2] if seed % 5 else [],
        edge_slowdown_per_amr=.15 if seed % 3 else 0)
    cfg['lifts'] = []
    cfg['corridors']['edges'] = []
    for index in range(3):
        floors = list(range(6)) if seed % 4 == 0 else sorted(rng.sample(range(6), rng.randint(2, 6)))
        lift = dict(id=f'L{index}', served_floors=floors, start_floor=floors[0],
            speed_floors_per_sec=rng.choice([.5, 1, 2]), door_time_sec=rng.choice([0, 1, 2]),
            boarding_time_sec=rng.choice([0, 1, 3]), capacity_length_m=5,
            capacity_width_m=rng.choice([.5, 2, 5]), capacity_height_m=5,
            health_percent=rng.choice([50, 80, 100]), health_loss_per_journey_percent=rng.choice([0, .1, 5]),
            mean_time_between_failures_hours=0 if seed % 3 else 2 / 3600,
            mean_time_to_repair_hours=5/3600,
            floor_locations={str(f): dict(x=index*4+2, y=0) for f in floors})
        if seed % 7 == 0:
            lift['transfer_timing_mode'] = 'speed_based'
            cfg['amrs'][0].update(lift_entry_speed_m_per_sec=.3, lift_exit_speed_m_per_sec=.5)
        cfg['lifts'].append(lift)
        for floor in floors:
            endpoint = 'A' if floor == 0 else f'B{floor}'
            cfg['corridors']['edges'].append(dict(**{'from': endpoint, 'to': f'L{index}-F{floor}'},
                bidirectional=True, distance_m=rng.choice([0, 1, 2, 5, 10, 25]) if seed % 7 else rng.choice([1, 2, 5, 10]),
                width_m=rng.choice([.5, 2, 3])))
    cfg['amrs'][0]['speed_m_per_sec'] = rng.choice([.5, 1, 2])
    return cfg


def asset_state(sim):
    return encode(dict(amrs=sim.amrs, lifts=sim.lifts, lift_reservations=sim.lift_reservations,
        edge_reservations=sim.edge_reservations, node_reservations=sim.node_reservations))


class WaypointOptimisationTests(unittest.TestCase):
    def test_complete_simulation_results_match_original(self):
        for transfer, speed_based in ((False, False), (True, False), (False, True), (True, True)):
            cfg = floor_config(transfer=transfer)
            cfg['building']['destination_side_lift_floors'] = [2]
            cfg['amrs'][0]['quantity'] = 2
            if speed_based:
                cfg['amrs'][0].update(lift_entry_speed_m_per_sec=.3, lift_exit_speed_m_per_sec=.5)
                for lift in cfg['lifts']:
                    lift['transfer_timing_mode'] = 'speed_based'
            cfg['tasks'] = [dict(id=f'T{i}', pickup='A' if i % 2 == 0 else f'B{i%5+1}',
                dropoff=f'B{i%5+1}' if i % 2 == 0 else 'A', payload='Box', release_time=i*12)
                for i in range(24)]
            with self.subTest(transfer=transfer, speed_based=speed_based):
                with contextlib.redirect_stdout(io.StringIO()):
                    old = original_simulator.Simulation(deepcopy(cfg))
                    new = Simulation(deepcopy(cfg))
                    old.run()
                    new.run()
                self.assertEqual(24, len(old.completed_task_records))
                self.assertEqual([], list(old.failed_task_ids))
                self.assertEqual(old.current_time, new.current_time)
                self.assertEqual(encode(old.completed_task_records), encode(new.completed_task_records))
                self.assertEqual(old.failed_task_ids, new.failed_task_ids)
                self.assertEqual(asset_state(old), asset_state(new))
                for attribute in ('location_reservations', 'inventory_spaces_by_location'):
                    self.assertEqual(encode(getattr(old, attribute)), encode(getattr(new, attribute)))

    def test_randomised_route_and_booking_parity_with_original(self):
        # 480 varied route queries; every other successful query commits its
        # reservations and wear so subsequent queries see changing real state.
        for seed in range(80):
            cfg = network(seed)
            old, new = original_simulator.Simulation(deepcopy(cfg)), Simulation(deepcopy(cfg))
            rng = random.Random(seed + 900)
            for index in range(6):
                start_floor = 0 if index < 4 else rng.choice(range(6))
                finish_floor = rng.choice([f for f in range(6) if f != start_floor])
                origin = 'A' if start_floor == 0 else f'B{start_floor}'
                destination = 'A' if finish_floor == 0 else f'B{finish_floor}'
                ready = index * 40.0
                collect = index % 3 != 0
                with self.subTest(seed=seed, index=index, origin=origin, destination=destination):
                    plans = []
                    for sim in (old, new):
                        rules = sim._empty_route_rules()
                        if seed % 11 == 0:
                            rules['allowed_lifts'] = {'L0', 'L2'}
                        before = asset_state(sim)
                        plan = sim._nearest_compatible_lift_plan(ready, sim.amrs[0], sim.locations[origin],
                            sim.locations[destination], sim.payloads['Box'], rules, 'lengthways', collect)
                        self.assertEqual(before, asset_state(sim), 'read-only query mutated assets/bookings')
                        plans.append(plan)
                    self.assertEqual(encode(plans[0]), encode(plans[1]))
                    if plans[1] is not None:
                        via = original_floor.required_waypoint(cfg, start_floor, finish_floor)
                        if via is None:
                            via = cfg['building'].get('lift_transfer_floor') if len(lift_plan_journeys(plans[1])) > 1 else None
                        bound = optimistic_remaining_times(new, new.amrs[0], new.locations[destination], via)
                        if bound is not None:
                            optimistic = bound.get((origin, via is None or via == start_floor), math.inf)
                            self.assertLessEqual(optimistic, plans[1]['final_finish']-ready + 1e-7)
                    if collect and index % 2 == 1 and plans[0] is not None:
                        for sim, plan in zip((old, new), plans):
                            lift_plan_segments(sim, plan, sim.amrs[0], sim.payloads['Box'], ready, reserve=True)
                        self.assertEqual(asset_state(old), asset_state(new))

    def test_equal_distance_nearest_lift_and_busy_car_match_original(self):
        from tests.test_lift_integration import two_lifts
        for equal in (False, True):
            cfg = two_lifts()
            cfg['building']['mandatory_floor_waypoints'] = [dict(from_floor=0, to_floors=[3], via_floor=2)]
            if equal:
                for edge in cfg['corridors']['edges']:
                    edge['distance_m'] = 1
            old, new = original_simulator.Simulation(deepcopy(cfg)), Simulation(deepcopy(cfg))
            for sim in (old, new):
                sim.lifts[1].available_time = 200
            plans = [sim._nearest_compatible_lift_plan(0, sim.amrs[0], sim.locations['A'], sim.locations['B3'],
                sim.payloads['Box'], sim._empty_route_rules(), 'lengthways', True) for sim in (old, new)]
            self.assertEqual(encode(plans[0]), encode(plans[1]))
            self.assertIn(2, [leg['destination_lift'].floor for leg in lift_plan_journeys(plans[1])])

    def test_scenario_queries_keep_exact_original_results(self):
        from tests.test_scenario_study import event, scenario
        for seed in range(8):
            cfg = network(seed+10)
            cfg = scenario(cfg, [event('A -> L0-F0', start=0, end=120, availability=0)])
            old, new = original_simulator.Simulation(deepcopy(cfg)), Simulation(deepcopy(cfg))
            plans = [sim._nearest_compatible_lift_plan(0, sim.amrs[0], sim.locations['A'], sim.locations['B3'],
                sim.payloads['Box'], sim._empty_route_rules(), 'lengthways', True) for sim in (old, new)]
            self.assertEqual(encode(plans[0]), encode(plans[1]))
            self.assertIsNone(optimistic_remaining_times(new, new.amrs[0], new.locations['B3'], 2))

    def test_explicit_lift_filter_only_projects_requested_car(self):
        from tests.test_lift_integration import two_lifts
        sim = Simulation(two_lifts())
        from simulator import projected_lift
        with patch('simulator.projected_lift', wraps=projected_lift) as project:
            sim._direct_lift_plan(0, sim.amrs[0], sim.locations['A'], sim.locations['B3'],
                sim.payloads['Box'], only_lift='NearDestination')
        self.assertEqual(['NearDestination'], [call.args[0].id for call in project.call_args_list])


if __name__ == '__main__':
    unittest.main()
