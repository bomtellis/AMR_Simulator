import copy
import math
import unittest

from amr_occupancy_plan import occupancy_plan
from amr_trajectories import Pose, TrajectoryError, plan_trajectory


def move(points):
    path = plan_trajectory(points, minimum_radius_m=1, speed_m_per_sec=1,
                           pivot_allowed=True, pivot_speed_deg_per_sec=90)
    return {'type': 'corridor', 'motion_model': 'geometric_v1', 'trajectory': path.to_dict(),
            'duration': path.duration_sec, 'distance_m': path.length_m}


def claims(segments, **changes):
    kwargs = dict(initial_pose=Pose(0, 0, 0), floor=2, start=10, owner='R1',
                  robot_length_m=1, robot_width_m=.6, loaded_length_m=2, loaded_width_m=1,
                  robot_clearance_m=.1, segments=segments)
    kwargs.update(changes)
    return occupancy_plan(**kwargs)


class OccupancyPlanTests(unittest.TestCase):
    def test_empty_plan_has_indefinite_physical_footprint(self):
        result = claims([])
        self.assertEqual(1, len(result))
        row = result[0]
        self.assertEqual((10, math.inf, 'stationary', 'terminal', 2),
                         (row['start'], row['end'], row['occupancy_kind'], row['segment_type'], row['floor']))
        self.assertEqual((-.5, -.3, .5, .3), row['envelope'])
        self.assertEqual(.1, row['robot_clearance_m'])
        self.assertEqual(Pose(0, 0, 0), row['pose'])

    def test_load_lifecycle_covers_pickup_and_dropoff_with_loaded_footprint(self):
        rows = claims([{'type': 'wait_for_location', 'duration': 2},
                       {'type': 'pickup', 'duration': 3}, move([(0, 0), (4, 0)]),
                       {'type': 'dropoff', 'duration': 5}, {'type': 'wash_cycle', 'duration': 6}])
        stationary = [r for r in rows if r['occupancy_kind'] == 'stationary']
        self.assertEqual([(10, 12), (12, 15), (19, 24), (24, 30), (30, math.inf)],
                         [(r['start'], r['end']) for r in stationary])
        self.assertEqual([1, 2, 2, 1, 1], [r['length_m'] for r in stationary])
        self.assertEqual([False, True, True, False, False], [r['loaded'] for r in stationary])
        self.assertEqual((3, -.5, 5, .5), stationary[2]['envelope'])
        self.assertEqual((3.5, -.3, 4.5, .3), rows[-1]['envelope'])
        self.assertTrue(all(r['floor'] == 2 and r['owner'] == 'R1' for r in rows))
        for first, second in zip(rows, rows[1:]):
            self.assertEqual(first['end'], second['start'])

    def test_curved_endpoint_and_heading_come_only_from_decoded_path(self):
        segment = move([(0, 0), (3, 0), (3, 3)])
        rows = claims([segment, {'type': 'charge', 'duration': 5}])
        self.assertEqual(Pose(3, 3, math.pi / 2), rows[-1]['pose'])
        for expected, actual in zip((2.7, 2.5, 3.3, 3.5), rows[-1]['envelope']):
            self.assertAlmostEqual(expected, actual)
        self.assertAlmostEqual(10 + 4 + math.pi / 2 + 5, rows[-1]['start'])

    def test_cached_cells_cannot_hide_loaded_overhang_or_change_timing(self):
        segment = move([(0, 0), (4, 0)])
        segment['traffic_cells'] = [{'start': 0, 'end': 1, 'polygon': [(100, 100)]}]
        original = copy.deepcopy(segment)
        rows = claims([{'type': 'pickup', 'duration': 0}, segment, {'type': 'dropoff', 'duration': 0}])
        moving = [r for r in rows if r['occupancy_kind'] == 'moving']
        self.assertEqual(-1, moving[0]['envelope'][0])
        self.assertEqual(-.5, moving[0]['envelope'][1])
        self.assertEqual(14, moving[-1]['end'])
        self.assertFalse(rows[-1]['loaded'])
        self.assertEqual(original, segment)

    def test_initial_and_unfinished_loaded_state_is_preserved(self):
        rows = claims([{'type': 'wait', 'duration': 1}], initial_loaded=True)
        self.assertTrue(rows[-1]['loaded'])
        self.assertEqual(2, rows[-1]['length_m'])
        rows = claims([{'type': 'pickup', 'duration': 1}])
        self.assertTrue(rows[-1]['loaded'])
        self.assertEqual(2, rows[-1]['length_m'])

    def test_zero_duration_handling_has_explicit_instantaneous_loaded_claims(self):
        rows = claims([{'type': 'pickup', 'duration': 0}, {'type': 'dropoff', 'duration': 0}])
        self.assertEqual(['instantaneous', 'instantaneous', 'stationary'],
                         [r['occupancy_kind'] for r in rows])
        self.assertEqual([(10, 10), (10, 10), (10, math.inf)],
                         [(r['start'], r['end']) for r in rows])
        self.assertEqual([2, 2, 1], [r['length_m'] for r in rows])
        self.assertEqual([True, True, False], [r['loaded'] for r in rows])
        self.assertEqual(['0:pickup', '1:dropoff', '2:terminal'], [r['source_id'] for r in rows])

    def test_zero_duration_handling_overhang_conflicts_at_the_actual_transition_time(self):
        from amr_occupancy_ledger import OccupancyLedger
        ledger = OccupancyLedger().initialise(owner='R1', floor=2, pose=Pose(0, 0, 0), start=0,
                                             length_m=1, width_m=.6, robot_clearance_m=.1).ledger
        other = ledger.initialise(owner='R2', floor=2, pose=Pose(0, .8, 0), start=0,
                                  length_m=1, width_m=.6, robot_clearance_m=.1)
        self.assertTrue(other.accepted)
        rows = claims([{'type': 'pickup', 'duration': 0}, {'type': 'dropoff', 'duration': 0}],
                      loaded_width_m=2)
        outcome = other.ledger.replace_plan('R1', 10, rows)
        self.assertFalse(outcome.accepted)
        self.assertIs(other.ledger, outcome.ledger)
        self.assertEqual(2, len(outcome.conflicts))
        self.assertTrue(all(c.start == 10 and c.end == 10 and c.blocking_owner == 'R2'
                            for c in outcome.conflicts))
    def test_robot_larger_than_load_retains_union_dimensions(self):
        rows = claims([{'type': 'pickup', 'duration': 1}], loaded_length_m=.5, loaded_width_m=.2)
        self.assertEqual(1, rows[0]['length_m'])
        self.assertEqual(.6, rows[0]['width_m'])

    def test_discontinuous_path_or_stationary_metadata_is_rejected(self):
        for segments in ([move([(1, 0), (4, 0)])],
                         [move([(0, 0), (4, 0)]), move([(0, 0), (2, 0)])],
                         [{'type': 'wait', 'duration': 1, 'to_x': 1}],
                         [{'type': 'pickup', 'duration': 1, 'amr_rotation_end_deg': 90}]):
            with self.subTest(segments=segments), self.assertRaises(TrajectoryError) as raised:
                claims(segments)
            self.assertEqual('invalid_evidence', raised.exception.reason)

    def test_unsupported_motion_and_floor_transfers_are_not_fabricated(self):
        for segment in ({'type': 'lift_reposition', 'duration': 1},
                        {'type': 'corridor', 'duration': 1, 'distance_m': 1},
                        {'type': 'wait', 'duration': 1, 'distance_m': 1},
                        {'type': 'wait', 'duration': 1, 'to_floor': 3},
                        {'type': 'charge', 'duration': 1, 'wait_time': 1}):
            with self.subTest(segment=segment), self.assertRaises(TrajectoryError) as raised:
                claims([segment])
            self.assertEqual('unsupported_movement', raised.exception.reason)

    def test_invalid_evidence_and_load_transitions_are_rejected(self):
        for segment in ({'type': 'dropoff', 'duration': 1},
                        {**move([(0, 0), (4, 0)]), 'duration': 3},
                        {**move([(0, 0), (4, 0)]), 'trajectory': {}},
                        {**move([(0, 0), (4, 0)]), 'distance_m': 8}):
            with self.subTest(segment=segment), self.assertRaises(TrajectoryError):
                claims([segment])
        with self.assertRaises(TrajectoryError):
            claims([{'type': 'pickup', 'duration': 1}], initial_loaded=True)

    def test_inputs_are_explicit_and_finite(self):
        for override in ({'start': math.inf}, {'floor': True}, {'owner': ''},
                         {'robot_length_m': 0}, {'robot_clearance_m': -.1},
                         {'initial_loaded': 1}, {'initial_pose': Pose(math.nan, 0, 0)}):
            with self.subTest(override=override), self.assertRaises(TrajectoryError):
                claims([], **override)
        for duration in (-1, math.inf, math.nan, True, None):
            with self.assertRaises(TrajectoryError):
                claims([{'type': 'wait', 'duration': duration}])

    def test_builder_output_accepted_by_complete_plan_ledger(self):
        from amr_occupancy_ledger import OccupancyLedger
        ledger = OccupancyLedger().initialise(owner='R1', floor=2, pose=Pose(0, 0, 0), start=0,
                                             length_m=1, width_m=.6, robot_clearance_m=.1).ledger
        rows = claims([{'type': 'pickup', 'duration': 2}, move([(0, 0), (4, 0)]),
                       {'type': 'dropoff', 'duration': 2}])
        outcome = ledger.replace_plan('R1', 10, rows)
        self.assertTrue(outcome.accepted)
        saved = outcome.ledger.rows()
        self.assertEqual(0, saved[0]['start'])
        self.assertEqual(10, saved[0]['end'])
        self.assertEqual(math.inf, saved[-1]['end'])
        self.assertEqual('3:terminal', saved[-1]['source_id'])


if __name__ == '__main__':
    unittest.main()
