import unittest
from unittest.mock import patch

from amr_scenario_routing import departure_state, segment_state, constant_amr_state
from simulator import Simulation
from tests.test_scenario_study import config, scenario, event


class ConstantAMRRoutingTests(unittest.TestCase):
    def make_sim(self, events):
        sim = Simulation(scenario(config(), events))
        self.addCleanup(lambda: sim.routing_executor.shutdown() if sim.routing_executor else None)
        return sim

    def permanent(self, **changes):
        return dict(resource_type='amr', resource_ids=['R'], availability_percent=100,
                    speed_factor=.5, start_time='00:00', end_time='00:00', days_active=[],
                    **changes)

    def test_permanent_factor_matches_general_state_across_midnights(self):
        sim = self.make_sim([self.permanent()])
        edge = dict(from_='A', to='B')
        edge['from'] = edge.pop('from_')
        for requested in (0, 86399, 86400, 10 * 86400):
            expected = segment_state(sim, sim.amrs[0], edge, requested)
            self.assertEqual(expected, departure_state(sim, sim.amrs[0], edge, requested, 100))
        with patch.object(sim, '_scenario_window', side_effect=AssertionError('Repeated window search')):
            self.assertEqual((123.0, .5, ''), departure_state(sim, sim.amrs[0], edge, 123, 100))

    def test_timed_weekday_closed_and_corridor_events_use_general_search(self):
        for changes in (dict(end_time='01:00'), dict(days_active=['mon']),
                        dict(availability_percent=0), dict(speed_factor=0),
                        dict(resource_type='corridor', resource_ids=['A -> B'])):
            with self.subTest(changes=changes):
                disruption = self.permanent()
                disruption.update(changes)
                sim = self.make_sim([disruption])
                self.assertIsNone(constant_amr_state(sim, sim.amrs[0]))
        sim = self.make_sim([event(resource='R', speed=.5)])
        self.assertIsNone(constant_amr_state(sim, sim.amrs[0]))

    def test_combined_factors_and_unaffected_robot_match_general_state(self):
        first = self.permanent()
        second = dict(first, speed_factor=.8, availability_percent=25)
        sim = self.make_sim([first, second])
        self.assertEqual((.25, ''), constant_amr_state(sim, sim.amrs[0]))
        sim.scenario_events = [dict(first, resource_ids=['unaffected'])]
        self.assertEqual((1.0, ''), constant_amr_state(sim, sim.amrs[0]))

    def test_route_and_reservation_timing_match_uncached_search(self):
        from tests.test_scenario_study import ScenarioRouteTests
        sim = Simulation(scenario(ScenarioRouteTests().network(), [self.permanent()]))
        self.addCleanup(lambda: sim.routing_executor.shutdown() if sim.routing_executor else None)
        sim.edge_reservations[sim._physical_edge_key('A', 'B')].append((0, 30, 'busy'))
        for requested in (0, 60, 86399, 86400 * 10):
            def route():
                return sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'],
                    payload=sim.payloads['Box'], start_time_value=requested)
            cached = route()
            with patch('amr_scenario_routing.constant_amr_state', return_value=None):
                self.assertEqual(cached, route())


if __name__ == '__main__':
    unittest.main()
