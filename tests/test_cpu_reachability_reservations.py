"""Keep structural reachability and reservation timing exact on the CPU."""
import unittest
from unittest.mock import patch

from amr_forced_floor import _reachable, _search_reachability
from simulator import Simulation
from tests.test_forced_floor import configured


class ForcedFloorReachabilityCacheTests(unittest.TestCase):
    def reach(self, sim, *, rules=None, final_lift=None, selected=None):
        return _reachable(sim, sim.amrs[0], sim.locations['A'], sim.locations['B5'],
                          sim.payloads['Box'], rules, 'lengthways', final_lift, selected)

    def test_cache_reuses_reachability_across_bookings_but_checks_health_and_width(self):
        sim = Simulation(configured())
        lift = sim.lifts[0]
        with patch('amr_forced_floor._search_reachability', wraps=_search_reachability) as search:
            self.assertTrue(self.reach(sim))
            lift.health_percent = 99
            lift.available_time = 300
            sim.lift_reservations[lift.id].append((10, 300, 0, 5, 'R'))
            self.assertTrue(self.reach(sim))
            self.assertEqual(1, search.call_count)

            lift.health_percent = lift.minimum_operational_health_percent - 1
            self.assertFalse(self.reach(sim))
            self.assertFalse(self.reach(sim))
            self.assertEqual(2, search.call_count)

            lift.health_percent = 100
            sim.amrs[0].width_m = 4  # Fits the car but cannot traverse a 3 m corridor.
            self.assertFalse(self.reach(sim))
            self.assertEqual(3, search.call_count)

    def test_cache_separates_final_lift_preference_and_route_rules(self):
        sim = Simulation(configured(transfer=True))
        low, high = sim.lifts
        self.assertTrue(self.reach(sim, final_lift=high))
        self.assertFalse(self.reach(sim, final_lift=low))
        self.assertFalse(self.reach(sim, final_lift=high, selected=frozenset({low.id})))
        self.assertFalse(self.reach(sim, final_lift=high, rules={'allowed_nodes': {'A', 'B5'}}))
        self.assertTrue(self.reach(sim, final_lift=high))

    def test_cached_result_checks_cancellation(self):
        sim = Simulation(configured())
        self.assertTrue(self.reach(sim))
        sim.cancel_requested = lambda: True
        with self.assertRaises(InterruptedError):
            self.reach(sim)

    def test_scenarios_threaded_routing_and_speed_based_transfers_recompute(self):
        for flag in ('scenario_mode', 'parallel_routing_enabled', 'speed_based'):
            with self.subTest(flag=flag):
                sim = Simulation(configured(speed_based=(flag == 'speed_based')))
                if flag != 'speed_based':
                    setattr(sim, flag, True)
                with patch('amr_forced_floor._search_reachability', wraps=_search_reachability) as search:
                    self.assertEqual(self.reach(sim), self.reach(sim))
                    self.assertEqual(2, search.call_count)


class EmptyReservationTests(unittest.TestCase):
    def test_empty_edge_and_node_return_without_scanning(self):
        sim = Simulation(configured())
        direction = ('A', 'L-F0')
        edge = sim._physical_edge_key(*direction)
        with patch.object(sim, '_reservation_scan_start', side_effect=AssertionError('empty scan')):
            self.assertEqual(0, sim._edge_recent_demand(edge, 2.))
            self.assertEqual(2., sim._directed_no_overtake_start(direction, 2., 2., 1.))
            self.assertEqual((2., 0), sim._find_next_edge_start(edge, 2., 2., 1., direction))
            self.assertEqual(2., sim._find_next_node_arrival('L-F0', 2., 1.))
        self.assertNotIn(edge, sim.edge_reservations)
        self.assertNotIn(direction, sim.directed_edge_reservations)
        self.assertNotIn('L-F0', sim.node_reservations)

    def test_directed_reservation_still_applies_when_physical_index_is_empty(self):
        sim = Simulation(configured())
        direction = ('A', 'L-F0')
        edge = sim._physical_edge_key(*direction)
        sim._reserve_edge(*direction, 0., 10., 'R')
        del sim.edge_reservations[edge]
        del sim.edge_reservation_max_duration[edge]
        self.assertEqual((9., 0), sim._find_next_edge_start(edge, 2., 2., 1., direction))
        self.assertEqual((2., 0), sim._find_next_edge_start(edge, 2., 2., 1.))
        sim._reserve_node('L-F0', 1., 10., 'R')
        self.assertEqual(11., sim._find_next_node_arrival('L-F0', 10., 1.))
        self.assertEqual(11., sim._find_next_node_arrival('L-F0', 11., 1.))
