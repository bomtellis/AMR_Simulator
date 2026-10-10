"""Independent stationary-footprint and stopping-area engineering references."""
import copy
import math
import unittest

from amr_trajectories import Pose, TrajectoryError, plan_trajectory
from amr_geometric_traffic import first_traffic_slot, swept_cells
from amr_geometric_occupancy import (
    area_input_findings, automatic_stop_areas, stopping_findings,
    stationary_claim, select_passing_place,
)


def model_floor():
    return {'floor': 0, 'bounds': [-10, -10, 10, 10], 'obstacles': []}


def graph():
    return {'building': {}, 'locations': [], 'corridors': {
        'nodes': [{'name': 'J', 'floor': 0, 'x': 0, 'y': 0},
                  {'name': 'W', 'floor': 0, 'x': -8, 'y': 0},
                  {'name': 'E', 'floor': 0, 'x': 8, 'y': 0},
                  {'name': 'N', 'floor': 0, 'x': 0, 'y': 8}],
        'edges': [{'from': 'J', 'to': name, 'width_m': 2}
                  for name in ('W', 'E', 'N')]}}


class GeometricOccupancyTests(unittest.TestCase):
    def findings(self, floor=None, pose=None, **overrides):
        options = dict(length_m=2, width_m=1, wall_clearance_m=.1,
                       floor=floor if floor is not None else model_floor())
        options.update(overrides)
        return stopping_findings(pose or Pose(0, 0, 0), **options)

    def test_optional_drawn_areas_are_not_required_to_stop(self):
        self.assertEqual([], area_input_findings(model_floor()))
        self.assertEqual([], self.findings())
        self.assertIsNone(select_passing_place(model_floor(), [], length_m=2,
                            width_m=1, wall_clearance_m=.1))

    def test_area_schema_reports_invalid_shapes_ids_duplicates_and_outside_floor(self):
        for bad in (None, {}, 'area'):
            floor = model_floor()
            floor['no_queuing_areas'] = bad
            self.assertTrue(area_input_findings(floor))
        floor = model_floor()
        floor['passing_places'] = [
            {'id': 'P', 'bounds': [0, 0, 2, 2]},
            {'id': 'P', 'bounds': [0, 0, 2, 2]},
            {'id': '', 'bounds': [2, 0, 1, 1]},
            {'id': 'outside', 'bounds': [9, 9, 11, 11]},
            {'id': 'bad', 'bounds': [False, 0, 1, 1]},
        ]
        issues = area_input_findings(floor, '/geometry/floors/4')
        self.assertEqual(5, len(issues))
        self.assertTrue(all(path.startswith('/geometry/floors/4/passing_places/') for path, _ in issues))

    def test_floor_wall_clearance_and_exact_boundary_contact(self):
        floor = model_floor()
        # Half-length 1 + gap .1: centre 8.9 puts the outer clearance at x=10.
        self.assertEqual([], self.findings(floor, Pose(8.9, 0, 0)))
        self.assertEqual('floor_clearance', self.findings(floor, Pose(8.9001, 0, 0))[0]['code'])
        floor['obstacles'] = [[1.1, -1, 3, 1]]
        self.assertEqual([], self.findings(floor))
        floor['obstacles'][0][0] -= .0001
        self.assertEqual('obstacle_clearance', self.findings(floor)[0]['code'])

    def test_no_queue_checks_entire_load_and_not_just_centre(self):
        floor = model_floor()
        floor['no_queuing_areas'] = [{'id': 'Exit', 'bounds': [.8, -.2, 2, .2]}]
        issues = self.findings(floor)
        self.assertEqual([('no_queuing_area', 'Exit')], [(i['code'], i['area_id']) for i in issues])
        # The loaded rectangle is 2 m long; a smaller robot alone would fit.
        self.assertEqual([], self.findings(floor, length_m=1))

    def test_no_queue_uses_rotated_rectangle_and_allows_touch_without_extra_wall_margin(self):
        floor = model_floor()
        floor['no_queuing_areas'] = [{'id': 'Exit', 'bounds': [1, -.2, 2, .2]}]
        self.assertEqual([], self.findings(floor))  # exact physical contact
        floor['no_queuing_areas'][0]['bounds'] = [-.2, .8, .2, 2]
        self.assertEqual([], self.findings(floor))
        self.assertEqual('no_queuing_area', self.findings(floor, Pose(0, 0, math.pi/2))[0]['code'])

    def test_junction_has_distinct_neighbours_and_protects_full_loaded_footprint(self):
        config = graph()
        areas = automatic_stop_areas(config, 0)
        self.assertEqual(1, len(areas))
        self.assertEqual(('J', 'junction', (-1, -1, 1, 1)),
                         (areas[0]['id'], areas[0]['source'], areas[0]['envelope']))
        # Centre outside core, nose inside: still prohibited.
        self.assertEqual('protected_junction', self.findings(pose=Pose(1.5, 0, 0), protected_areas=areas)[0]['code'])
        self.assertEqual([], self.findings(pose=Pose(2, 0, 0), protected_areas=areas))
        config['corridors']['edges'] = [config['corridors']['edges'][0],
            {'from': 'W', 'to': 'J', 'width_m': 2},
            {'from': 'J', 'to': 'W', 'width_m': 2}]
        self.assertEqual([], automatic_stop_areas(config, 0))

    def test_doors_are_automatically_protected_with_no_custom_areas(self):
        config = graph()
        config['corridors']['edges'] = config['corridors']['edges'][:1]
        config['corridors']['nodes'][0].update(has_door=True, door_clear_width_m=1)
        areas = automatic_stop_areas(config, 0)
        self.assertEqual('door', areas[0]['source'])
        self.assertEqual((-1, -1, 1, 1), areas[0]['envelope'])
        self.assertEqual('protected_door', self.findings(protected_areas=areas)[0]['code'])

    def test_explicit_building_width_defaults_are_used_but_missing_geometry_is_not_invented(self):
        config = graph()
        for edge in config['corridors']['edges']:
            del edge['width_m']
        with self.assertRaises(TrajectoryError) as error:
            automatic_stop_areas(config, 0)
        self.assertEqual('missing_geometry', error.exception.reason)
        config['building']['default_corridor_width_m'] = 4
        config['building']['default_door_clear_width_m'] = 1
        config['corridors']['nodes'][0]['has_door'] = True
        area = automatic_stop_areas(config, 0)[0]
        self.assertEqual('door_junction', area['source'])
        self.assertEqual((-2, -2, 2, 2), area['envelope'])

    def test_graph_floors_do_not_share_junction_degree(self):
        config = graph()
        config['corridors']['nodes'][-1]['floor'] = 1
        self.assertEqual([], automatic_stop_areas(config, 0))
        self.assertEqual([], automatic_stop_areas(config, 1))

    def test_stationary_claim_is_continuous_and_does_not_double_pair_clearance(self):
        claim = stationary_claim(Pose(0, 0, math.pi/2), start=4, end=20,
            owner='R1', length_m=2, width_m=1, robot_clearance_m=.3)
        self.assertEqual((4, 20, 'R1', .3),
                         (claim['start'], claim['end'], claim['owner'], claim['robot_clearance_m']))
        for observed, expected in zip(claim['envelope'], (-.5, -1, .5, 1)):
            self.assertAlmostEqual(expected, observed)
        # A full moving interval across the occupied position must wait for 20.
        moving = stationary_claim(Pose(0, 0, 0), start=0, end=2, owner='R2', length_m=1, width_m=1)
        self.assertEqual((20, ['R1']), first_traffic_slot([claim], [moving], 5, 'R2', 0))
        self.assertEqual((5, []), first_traffic_slot([claim], [moving], 5, 'R1', 0))

    def test_stationary_claim_blocks_real_moving_swept_cells_between_samples(self):
        route = plan_trajectory([(-2, 0), (2, 0)], minimum_radius_m=1,
            speed_m_per_sec=4, pivot_allowed=False, pivot_speed_deg_per_sec=45)
        cells = swept_cells(route, length_m=.1, width_m=.1, clearance_m=0)
        stationary = stationary_claim(Pose(-.3, 0, 0), start=0, end=1,
            owner='Parked', length_m=.1, width_m=.1)
        slot, blockers = first_traffic_slot([stationary], cells, 0, 'Moving', 0)
        self.assertGreater(slot, 0)
        self.assertEqual(['Parked'], blockers)
        stationary['end'] = math.inf
        self.assertEqual(math.inf, first_traffic_slot([stationary], cells, 0, 'Moving', 0)[0])

    def test_stationary_invalid_times_and_dimensions_do_not_create_claims(self):
        base = dict(start=0, end=1, owner='R', length_m=2, width_m=1)
        for update in ({'start': -1}, {'end': 0}, {'end': math.nan},
                       {'end': -math.inf}, {'owner': ''}, {'length_m': 0},
                       {'robot_clearance_m': -.1}, {'start': True}):
            with self.subTest(update=update), self.assertRaises(TrajectoryError):
                stationary_claim(Pose(0, 0, 0), **{**base, **update})
        indefinite = stationary_claim(Pose(0, 0, 0), **{**base, 'end': math.inf})
        self.assertEqual(math.inf, indefinite['end'])

    def test_nearest_reachable_passing_place_uses_route_distance_not_euclidean_distance(self):
        floor = model_floor()
        floor['passing_places'] = [{'id': 'Near', 'bounds': [0, -1, 2, 1]},
                                   {'id': 'Far', 'bounds': [5, -1, 7, 1]}]
        candidates = [{'area_id': 'Near', 'pose': Pose(1, 0, 0), 'route_distance_m': 20},
                      {'area_id': 'Far', 'pose': Pose(6, 0, 0), 'route_distance_m': 6}]
        original = copy.deepcopy((floor, candidates))
        chosen = select_passing_place(floor, candidates, length_m=2, width_m=1, wall_clearance_m=.1)
        self.assertEqual('Far', chosen['area_id'])
        self.assertEqual(original, (floor, candidates))
        candidates[1]['route_distance_m'] = math.inf
        self.assertEqual('Near', select_passing_place(floor, candidates, length_m=2, width_m=1,
                                                    wall_clearance_m=.1)['area_id'])

    def test_passing_place_fit_uses_loaded_footprint_and_checks_no_queue_obstacles(self):
        floor = model_floor()
        floor['passing_places'] = [{'id': 'P', 'bounds': [-1, -.5, 1, .5]}]
        candidate = [{'area_id': 'P', 'pose': Pose(0, 0, 0), 'route_distance_m': 2}]
        options = dict(length_m=2, width_m=1, wall_clearance_m=.1)
        self.assertIsNotNone(select_passing_place(floor, candidate, **options))
        self.assertIsNone(select_passing_place(floor, candidate, **{**options, 'length_m': 2.01}))
        candidate[0]['pose'] = Pose(0, 0, math.pi/2)
        self.assertIsNone(select_passing_place(floor, candidate, **options))
        candidate[0]['pose'] = Pose(0, 0, 0)
        floor['no_queuing_areas'] = [{'id': 'NoStop', 'bounds': [.9, -.1, 2, .1]}]
        self.assertIsNone(select_passing_place(floor, candidate, **options))
        del floor['no_queuing_areas']
        floor['obstacles'] = [[1.05, -.1, 2, .1]]
        self.assertIsNone(select_passing_place(floor, candidate, **options))

    def test_passing_candidate_invalid_reachability_is_not_guessed(self):
        floor = model_floor()
        floor['passing_places'] = [{'id': 'P', 'bounds': [-2, -2, 2, 2]}]
        for distance in (-1, math.nan, True, None):
            with self.subTest(distance=distance), self.assertRaises(TrajectoryError):
                select_passing_place(floor, [{'area_id': 'P', 'pose': Pose(0, 0, 0),
                    'route_distance_m': distance}], length_m=2, width_m=1, wall_clearance_m=0)

    def test_passing_place_equal_distance_tie_is_stable_and_door_protection_wins(self):
        floor = model_floor()
        floor['passing_places'] = [{'id': 'Z', 'bounds': [-2, -2, 2, 2]},
                                   {'id': 'A', 'bounds': [4, -2, 8, 2]}]
        candidates = [{'area_id': 'Z', 'pose': Pose(0, 0, 0), 'route_distance_m': 4},
                      {'area_id': 'A', 'pose': Pose(6, 0, 0), 'route_distance_m': 4}]
        options = dict(length_m=2, width_m=1, wall_clearance_m=0)
        for rows in (candidates, list(reversed(candidates))):
            self.assertEqual('A', select_passing_place(floor, rows, **options)['area_id'])
        config = graph()
        protected = automatic_stop_areas(config, 0)
        self.assertIsNone(select_passing_place(floor, candidates[:1], protected_areas=protected, **options))

    def test_bad_pose_and_missing_floor_obstacles_are_errors_not_free_space(self):
        for pose in (None, Pose(math.nan, 0, 0), Pose(0, 0, math.inf), Pose(False, 0, 0)):
            with self.subTest(pose=pose), self.assertRaises(TrajectoryError):
                stationary_claim(pose, start=0, end=1, owner='R', length_m=2, width_m=1)
        floor = model_floor()
        del floor['obstacles']
        with self.assertRaises(TrajectoryError):
            self.findings(floor)

    def test_invalid_automatic_width_and_graph_reference_are_reported(self):
        for width in (0, -1, math.nan, True):
            config = graph()
            config['corridors']['edges'][0]['width_m'] = width
            with self.subTest(width=width), self.assertRaises(TrajectoryError):
                automatic_stop_areas(config, 0)
        config = graph()
        config['corridors']['edges'][0]['to'] = 'Missing'
        with self.assertRaises(TrajectoryError):
            automatic_stop_areas(config, 0)


if __name__ == '__main__':
    unittest.main()
