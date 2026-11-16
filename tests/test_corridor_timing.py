"""Exact route timing at the compact corridor boundary."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests.test_multi_stop_route_rules import multi_route_config


class CorridorTimingTests(unittest.TestCase):
    def setUp(self):
        config = multi_route_config()
        config['building']['edge_slowdown_per_amr'] = .2
        self.sim = Simulation(config)

    def timing(self, backend='compact', timestamp=0., collect=True, reverse=False, orientation='lengthways'):
        start, end = ('B', 'A') if reverse else ('A', 'B')
        sim = self.sim
        with patch.object(sim, 'runtime_backend', backend):
            return sim._same_floor_segments(sim.amrs[0], sim.locations[start], sim.locations[end],
                                            start_time_value=timestamp, payload=sim.payloads['Box'],
                                            collect_segments=collect, orientation=orientation)

    def test_compact_matches_ordered_segments_at_edge_and_node_boundaries(self):
        sim = self.sim
        sim._reserve_edge('A', 'X', 0., 15., 'other')
        sim._reserve_edge('X', 'A', 4., 12., 'other')
        sim._reserve_node('B', 0., 44., 'other')
        for time in (0., 4., 12., 15., 43.999999999, 44.):
            for collect in (True, False):
                for reverse in (True, False):
                    with self.subTest(time=time, collect=collect, reverse=reverse):
                        expected = self.timing('reference', time, collect, reverse)
                        actual = self.timing('compact', time, collect, reverse)
                        self.assertEqual(json.dumps(expected), json.dumps(actual))

    def test_prepared_route_observes_new_reservations_without_writing_them(self):
        sim = self.sim
        before = self.timing()
        sim._reserve_node('B', 0., 100., 'other')
        current = deepcopy((sim.edge_reservations, sim.directed_edge_reservations, sim.node_reservations))
        after = self.timing()
        self.assertNotEqual(before, after)
        self.assertEqual(self.timing('reference'), after)
        self.assertEqual(current, (sim.edge_reservations, sim.directed_edge_reservations, sim.node_reservations))

    def test_segment_edits_do_not_change_templates_or_other_orientations(self):
        first = self.timing()
        expected = deepcopy(first)
        first[0][-1]['duration'] = 1000.
        self.assertEqual(expected, self.timing())
        self.assertEqual(self.timing('reference', orientation='sideways'),
                         self.timing(orientation='sideways'))

    def test_unavailable_extension_uses_the_python_timing_pass(self):
        with patch('amr_corridor_timing._native_corridor', None):
            self.sim = Simulation(multi_route_config())
        timing = self.sim._corridor_timing
        with patch.object(timing, 'time_path', wraps=timing.time_path) as python:
            self.assertEqual(self.timing('reference'), self.timing())
        python.assert_called_once()
        self.assertFalse(timing.native_used)

    def test_native_result_matches_python_with_live_bookings(self):
        timing = self.sim._corridor_timing
        if timing._native_evaluate is None:
            self.skipTest('The optional C++ extension is unavailable')
        self.sim._reserve_edge('A', 'X', 0., 15., 'other')
        self.sim._reserve_node('B', 0., 44., 'other')
        with patch.object(timing, '_native_evaluate', None):
            expected = self.timing(timestamp=4.)
        self.assertEqual(json.dumps(expected), json.dumps(self.timing(timestamp=4.)))
        self.assertTrue(timing.native_used)

    def test_untimed_and_people_routes_keep_existing_timing(self):
        sim = self.sim
        with patch.object(sim._corridor_timing, 'time_path', side_effect=AssertionError('compact timing')):
            self.assertEqual(self.timing('reference', timestamp=None), self.timing(timestamp=None))
            sim.people_edge_reservations['A', 'X'].append(dict(
                start=0., end=10., group_size=2, group_type='staff', speed_factor=.5))
            self.assertEqual(self.timing('reference'), self.timing())
