"""Verify reusable lift topology and conservative corridor timing cutoffs."""
import math
import unittest
from unittest.mock import patch

from amr_floor_routing import lift_plan_journeys, minimum_lift_journey_seconds
from amr_forced_floor import _search_forced_lift_plan
from amr_sim_models import Lift
from simulator import Simulation
from tests.test_forced_floor import configured
from tests.test_lift_integration import two_lifts


class LiftPlanningCPUPathTests(unittest.TestCase):
    def search(self, sim, cutoff=math.inf):
        return _search_forced_lift_plan(sim, 0., sim.amrs[0], sim.locations['A'],
                                       sim.locations['B2'], sim.payloads['Box'], None,
                                       'lengthways', False, None, cutoff)

    def test_simple_planning_reuses_landings_in_configured_order_per_run(self):
        cfg = configured(transfer=True)
        cfg['lifts'][0]['served_floors'] = [2, 0]
        sim = Simulation(cfg)
        second_sim = Simulation(cfg)
        lift = sim.lifts[0]
        landing = sim.graph_nodes['Low-F0']
        self.assertIsNot(landing, second_sim.graph_nodes['Low-F0'])
        self.assertEqual([2, 0], [floor for floor, _ in sim._lift_connections[lift.id]])
        with patch.object(Lift, 'location_on_floor', side_effect=AssertionError('recreated landing')):
            self.assertIs(landing, sim._lift_location_on_floor(lift, 0))
            self.assertIsNotNone(self.search(sim))

    def test_free_flow_cutoff_avoids_timing_without_caching_a_failure(self):
        cfg = configured()
        cfg['simulation']['precompute_static_routes'] = True
        sim = Simulation(cfg)
        lift = sim.lifts[0]
        ride = minimum_lift_journey_seconds(lift, 0, 2)
        bound = (ride + sim._free_flow_lift_distances[0, 'A', 'L-F0'] / sim.amrs[0].speed_m_per_sec
                 + sim._free_flow_lift_distances[2, 'L-F2', 'B2'] / sim.amrs[0].speed_m_per_sec)
        cutoff = (ride + bound) / 2
        sim._forced_lift_estimate_batch = {}
        with patch.object(sim, '_direct_lift_plan', wraps=sim._direct_lift_plan) as direct:
            self.assertIsNone(self.search(sim, cutoff))
            direct.assert_not_called()
            result = self.search(sim)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result['final_finish'], bound - 1e-9)
        self.assertEqual(result['final_finish'],
                         self.search(sim, math.nextafter(result['final_finish'], math.inf))['final_finish'])

    def test_equal_distance_and_finish_keep_the_lift_id_tie_break(self):
        cfg = two_lifts()
        cfg['building'].update(force_via_floor_enabled=True, force_via_floor=2)
        cfg['simulation']['precompute_static_routes'] = True
        for edge in cfg['corridors']['edges']:
            edge['distance_m'] = 1.
        sim = Simulation(cfg)
        with patch.object(sim, '_free_flow_lift_distances', {}):
            reference = self.search(sim)
        result = self.search(sim)
        self.assertEqual(reference, result)
        self.assertEqual('NearDestination', lift_plan_journeys(result)[-1]['lift'].id)

    def test_lift_health_fast_cache_retains_the_rounded_cache_result(self):
        sim = Simulation(configured())
        lift = sim.lifts[0]
        threshold = lift.minimum_operational_health_percent
        lift.health_percent = threshold + 1e-7
        first = sim._lift_health_speed_factor(lift)
        self.assertGreater(first, 0.)
        lift.health_percent = threshold - 1e-7
        self.assertEqual(first, sim._lift_health_speed_factor(lift))
        self.assertEqual(first, sim._lift_health_speed_factor(lift))
        lift.health_percent = threshold - 1.
        self.assertEqual(0., sim._lift_health_speed_factor(lift))

    def test_missing_precomputed_distances_fall_back_to_exact_timing(self):
        cfg = configured()
        cfg['simulation']['precompute_static_routes'] = False
        sim = Simulation(cfg)
        self.assertFalse(sim._free_flow_lift_distances)
        with patch.object(sim, '_direct_lift_plan', wraps=sim._direct_lift_plan) as direct:
            self.assertIsNone(self.search(sim, 9.))
            self.assertGreater(direct.call_count, 0)
