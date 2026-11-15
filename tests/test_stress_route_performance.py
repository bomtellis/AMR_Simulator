"""Lift-only disruptions must retain normal corridor routing and lift effects."""
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests import test_scenario_study
from tests.test_scenario_study import config, event, scenario
from tests.test_lift_reservation_order import config as lift_config


class LiftOnlyRoutingTests(unittest.TestCase):
    def test_lift_events_preserve_normal_corridor_path_and_reservation_timing(self):
        cfg = test_scenario_study.ScenarioRouteTests().network()
        normal = Simulation(cfg)
        disrupted = Simulation(scenario(cfg, [dict(event(resource='L1'), resource_type='lift')]))
        # Congestion must not switch unrelated corridor routing to another algorithm.
        for sim in (normal, disrupted):
            sim.edge_reservations[sim._physical_edge_key('A', 'B')].append((0, 30, 'busy'))
        with patch('amr_scenario_routing.earliest_route', side_effect=AssertionError('Unrelated floor search')):
            for start in (None, 0, 60):
                actual = []
                for sim in (normal, disrupted):
                    route = sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'],
                        payload=sim.payloads['Box'], start_time_value=start)
                    segments, duration, distance = route
                    actual.append(([{k:v for k,v in seg.items() if k != 'scenario_name'} for seg in segments], duration, distance))
                self.assertEqual(actual[0], actual[1])

    def test_lift_slowdown_and_outage_still_apply(self):
        cfg = lift_config()
        slowdown = dict(event(resource='L1', start=0, end=60, availability=100, speed=.5), resource_type='lift')
        sim = Simulation(scenario(cfg, [slowdown]))
        lift = sim.lifts[0]
        self.assertEqual(2, sim._lift_vertical_seconds(lift, 0, 1, at_time=0))
        self.assertEqual(1, sim._lift_vertical_seconds(lift, 0, 1, at_time=60))
        outage = dict(slowdown, availability_percent=0)
        sim = Simulation(scenario(cfg, [outage]))
        def plan(ready):
            return sim._nearest_compatible_lift_plan(ready, sim.amrs[0], sim.locations['A'],
                                                     sim.locations['B'], sim.payloads['Box'])
        self.assertIsNone(plan(0))
        self.assertGreaterEqual(plan(60)['lift_start'], 60)

    def test_corridor_door_and_amr_events_keep_time_dependent_search(self):
        from amr_scenario_routing import earliest_route
        for kind, identity in (('corridor', 'A -> B'), ('corridor_node', 'B'), ('amr', 'R')):
            with self.subTest(kind=kind):
                disruption = dict(event(resource=identity), resource_type=kind)
                lift_event = dict(event(resource='L1'), resource_type='lift')
                sim = Simulation(scenario(config(), [lift_event, disruption]))
                with patch('amr_scenario_routing.earliest_route', wraps=earliest_route) as search:
                    result = sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'],
                        payload=sim.payloads['Box'], start_time_value=0)
                self.assertEqual(1, search.call_count)
                self.assertGreater(result[1], 5)


if __name__ == '__main__':
    unittest.main()
