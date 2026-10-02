"""Independent local centreline safety cases; not swept-footprint validation."""
import contextlib
import io
import unittest
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_route_reservation_atomicity import storage_config
from tests.test_single_charge_atomicity import state


RING = [(-1, -1, 1, -.8), (-1, .8, 1, 1),
        (-1, -1, -.8, 1), (.8, -1, 1, 1)]


class LocalManoeuvreSafetyTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(reference_config())

    def test_enclosed_start_cannot_be_replaced_by_blocked_direct_path(self):
        # A closed four-wall ring separates (0,0) from (4,0).
        with self.assertRaisesRegex(ValueError, 'search_exhausted'):
            self.sim._local_manoeuvre_waypoints((0, 0), (4, 0), RING)

    def test_invalid_endpoints_are_not_replaced_by_obstacle_corners(self):
        for start, end in [((0, 0), (2, 0)), ((0, 0), (4, 0)), ((4, 0), (2, 0))]:
            with self.subTest(start=start, end=end):
                with self.assertRaisesRegex(ValueError, 'invalid_endpoint'):
                    self.sim._local_manoeuvre_waypoints(start, end, [(-1, -1, 3, 1)])

    def test_distinct_close_endpoints_are_preserved(self):
        start, end = (0, 0), (.00001, 0)
        self.assertEqual([start, end], self.sim._local_manoeuvre_waypoints(start, end, []))

    def test_unobstructed_three_four_five_path(self):
        self.assertEqual([(0, 0), (3, 4)],
                         self.sim._local_manoeuvre_waypoints((0, 0), (3, 4), []))

    def test_nonfinite_endpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid_endpoint'):
            self.sim._local_manoeuvre_waypoints((float('nan'), 0), (4, 0), [])

    def test_unpositioned_bay_preserves_legacy_no_movement_contract(self):
        # No travel is requested for bays at their parent node. Their inferred
        # default drawing boxes are not a new explicit geometry requirement.
        with patch.object(self.sim, '_local_obstacle_bboxes', return_value=[(-1, -1, 1, 1)]):
            self.assertEqual(([], 0.0, 0.0), self.sim._local_manoeuvre_segments_to_inventory_space(
                self.sim.amrs[0], 'A', dict(name='Bay'), 0))

    def test_blocked_departure_preserves_robot_and_bay(self):
        bay = dict(name='Parked', stores_amr=True, points=[dict(dx=4, dy=0)])
        self.sim.inventory_spaces_by_location['A'] = [bay]
        self.sim.amrs[0].inventory_space_name = 'Parked'
        task = Task('T', 'A', 'B', 'Box')
        before = state(self.sim)
        with patch.object(self.sim, '_local_obstacle_bboxes', return_value=RING):
            self.assertIsNone(self.sim._estimate_task_for_amr(self.sim.amrs[0], task, reserve=True))
        self.assertIn('search_exhausted', task.pending_reason)
        self.assertEqual(before, state(self.sim))

    def test_real_obstacles_do_not_create_completed_payload_movement(self):
        cfg = storage_config()
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        spaces = cfg['locations'][1]['inventory_spaces']
        spaces[0]['points'] = [dict(dx=3.5, dy=-.5), dict(dx=4.5, dy=-.5),
                               dict(dx=4.5, dy=.5), dict(dx=3.5, dy=.5)]
        for i, (a,b,c,d) in enumerate(RING):
            spaces.append(dict(name=f'Obstacle-{i}', points=[dict(dx=a,dy=b),
                dict(dx=c,dy=b), dict(dx=c,dy=d), dict(dx=a,dy=d)],
                payload_slots=[dict(payload='Other')]))
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(cfg, verbose=True)
            sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertFalse(sim.payload_instance_store.records_at('B'))
        self.assertFalse(any(row['event_type'] == 'local_manoeuvre' for row in sim.verbose_rows))
        self.assertTrue(sim.failed_tasks or sim.pending_tasks)

    def test_rectangle_detour_preserves_endpoints_and_clears_its_bounds(self):
        path = self.sim._local_manoeuvre_waypoints((0, 0), (4, 0), [(1, -1, 3, 1)])
        self.assertEqual((0, 0), path[0])
        self.assertEqual((4, 0), path[-1])
        # A route must go above y=1 or below y=-1 to cross this rectangle's x span.
        for a, b in zip(path, path[1:]):
            if a[0] == b[0]:
                continue
            for x in (1, 2, 3):
                fraction = (x-a[0])/(b[0]-a[0])
                if 0 <= fraction <= 1:
                    self.assertGreater(abs(a[1] + fraction*(b[1]-a[1])), 1)

    def test_unsafe_smoothing_cannot_replace_safe_waypoints(self):
        bay = dict(name='Bay', points=[dict(dx=4, dy=0)])
        with patch.object(self.sim, '_local_obstacle_bboxes', return_value=[(1, -1, 3, 1)]), \
             patch.object(self.sim, '_smooth_vehicle_waypoints', return_value=[(0, 0), (4, 0)]):
            segments, _, _ = self.sim._local_manoeuvre_segments_to_inventory_space(
                self.sim.amrs[0], 'A', bay, 0)
        self.assertGreater(len(segments), 1)

    def test_blocked_dropoff_rolls_back_single_and_batch_resources(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                cfg = storage_config(2 if batch else 1)
                # B is (6,8); target bay is (10,8), outside the enclosing ring.
                for bay in cfg['locations'][1]['inventory_spaces']:
                    bay['points'] = [dict(dx=4, dy=0)]
                sim = Simulation(cfg)
                tasks = [Task('T1', 'A', 'B', 'Box')]
                if batch:
                    tasks.append(Task('T2', 'A', 'B', 'Box'))
                before = state(sim)
                obstacles = [(a+6, b+8, c+6, d+8) for a,b,c,d in RING]
                with patch.object(sim, '_local_obstacle_bboxes', return_value=obstacles):
                    result = (sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True)
                              if batch else sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
                self.assertIsNone(result)
                self.assertEqual(before, state(sim))
                self.assertTrue(all('search_exhausted' in t.pending_reason for t in tasks))
                self.assertFalse(sim.completed_task_records)
                self.assertFalse(sim.local_manoeuvre_waypoint_cache)


if __name__ == '__main__':
    unittest.main()
