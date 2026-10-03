"""Analytic reverse/lateral movement and shared clearance/playback references."""
import copy
import math
import unittest
from dataclasses import replace

from amr_motion_profiles import MotionSettings, MotionProfileError
from amr_trajectories import (Pose, Trajectory, TrajectoryError, plan_trajectory,
                              plan_reverse_trajectory, plan_lateral_trajectory,
                              trajectory_from_dict, check_clearance, footprint)
from amr_trajectory_dynamics import retime_trajectory
from amr_geometric_traffic import swept_cells, polygons_overlap


def reverse(points, **changes):
    values = dict(minimum_radius_m=2, speed_m_per_sec=1, pivot_allowed=False,
                  pivot_speed_deg_per_sec=90, start_heading_deg=0)
    values.update(changes)
    return plan_reverse_trajectory(points, **values)


def settings(**changes):
    values = dict(forward_speed_m_per_sec=3, reverse_speed_m_per_sec=1,
                  acceleration_m_per_sec2=1, braking_m_per_sec2=1,
                  maximum_turn_speed_m_per_sec=2, lateral_acceleration_m_per_sec2=10,
                  pivot_allowed=True, lateral_allowed=True, lateral_speed_m_per_sec=.5,
                  rotation_speed_deg_per_sec=90, angular_acceleration_deg_per_sec2=90,
                  angular_braking_deg_per_sec2=90)
    values.update(changes)
    return MotionSettings(**values)


def angle_equal(test, first, second):
    test.assertAlmostEqual(0, math.remainder(first - second, 2 * math.pi))


class DirectionalTrajectoryTests(unittest.TestCase):
    def test_straight_reverse_preserves_body_heading_without_pivot(self):
        path = reverse([(0, 0), (-4, 0)])
        self.assertEqual(1, len(path.motions))
        motion = path.motions[0]
        self.assertEqual(('line', 'reverse', 4, 4),
                         (motion.kind, motion.movement, motion.length_m, motion.duration_sec))
        for f in (0, .25, .5, 1):
            pose = motion.pose_at(f)
            self.assertEqual(-4 * f, pose.x)
            angle_equal(self, pose.heading, 0)

    def test_reverse_quarter_turn_has_correct_body_orientation_and_analytic_timing(self):
        path = retime_trajectory(reverse([(0, 0), (-6, 0), (-6, -6)]), settings())
        self.assertEqual(['line', 'arc', 'line'], [m.kind for m in path.motions])
        self.assertTrue(all(m.movement == 'reverse' for m in path.motions))
        self.assertAlmostEqual(8 + math.pi, path.length_m)
        self.assertAlmostEqual(9 + math.pi, path.duration_sec)
        self.assertAlmostEqual(4.5, path.motions[0].duration_sec)
        pose = path.pose_at_time(4.5 + math.pi / 2)
        self.assertAlmostEqual(-4 - math.sqrt(2), pose.x)
        self.assertAlmostEqual(-2 + math.sqrt(2), pose.y)
        angle_equal(self, pose.heading, math.pi / 4)
        angle_equal(self, path.motions[-1].end.heading, math.pi / 2)

    def test_reverse_curve_turn_cap_overrides_reverse_maximum(self):
        path = retime_trajectory(reverse([(0, 0), (-6, 0), (-6, -6)]),
                                 settings(lateral_acceleration_m_per_sec2=.125))
        self.assertAlmostEqual(.5, path.motions[1].profile['max_speed'])
        self.assertAlmostEqual(2 * math.pi, path.motions[1].duration_sec)

    def test_actual_initial_heading_mismatch_needs_explicit_pivot_permission(self):
        with self.assertRaisesRegex(TrajectoryError, 'infeasible_route'):
            reverse([(0, 0), (-4, 0)], start_heading_deg=90)
        path = reverse([(0, 0), (-4, 0)], start_heading_deg=90, pivot_allowed=True)
        self.assertEqual('pivot', path.motions[0].kind)
        self.assertAlmostEqual(math.pi / 2, abs(path.motions[0].sweep_rad))
        angle_equal(self, path.motions[0].start.heading, math.pi / 2)
        angle_equal(self, path.motions[0].end.heading, 0)
        angle_equal(self, path.motions[1].start.heading, 0)
        trajectory_from_dict(path.to_dict())

    def test_lateral_translation_preserves_heading_and_uses_lateral_speed(self):
        path = plan_lateral_trajectory(Pose(0, 0, 0), (0, 2), speed_m_per_sec=.5, lateral_allowed=True)
        path = retime_trajectory(path, settings())
        # Accel .5sec/.125m, cruise3.5sec/1.75m, brake.5sec/.125m.
        self.assertAlmostEqual(4.5, path.duration_sec)
        pose = path.pose_at_time(.5)
        self.assertEqual(0, pose.x)
        self.assertAlmostEqual(.125, pose.y)
        self.assertEqual(0, pose.heading)
        self.assertEqual('lateral', path.motions[0].movement)
        right = plan_lateral_trajectory(Pose(0, 0, math.pi / 2), (2, 0),
                                        speed_m_per_sec=.5, lateral_allowed=True)
        self.assertEqual(1, right.pose_at_time(2).x)
        self.assertEqual(math.pi / 2, right.pose_at_time(2).heading)

    def test_lateral_permission_and_perpendicular_constraint_are_explicit(self):
        for destination, permission in (((0, 1), False), ((1, 1), True), ((1, 0), True)):
            with self.assertRaises(TrajectoryError) as raised:
                plan_lateral_trajectory(Pose(0, 0, 0), destination,
                                        speed_m_per_sec=1, lateral_allowed=permission)
            self.assertEqual('infeasible_route', raised.exception.reason)
        path = plan_lateral_trajectory(Pose(0, 0, 0), (0, 1), speed_m_per_sec=1, lateral_allowed=True)
        with self.assertRaises(MotionProfileError) as raised:
            retime_trajectory(path, settings(lateral_allowed=False))
        self.assertEqual('infeasible_motion', raised.exception.reason)

    def test_forward_reverse_direction_change_stops_without_rotating_body(self):
        forward = plan_trajectory([(0, 0), (2, 0)], minimum_radius_m=2, speed_m_per_sec=3,
                                  pivot_allowed=False, pivot_speed_deg_per_sec=90)
        backward = reverse([(2, 0), (0, 0)])
        joined = retime_trajectory(Trajectory(forward.motions + backward.motions, 2, False), settings())
        self.assertEqual(0, joined.motions[0].profile['end_speed'])
        self.assertEqual(0, joined.motions[1].profile['start_speed'])
        self.assertAlmostEqual(2 * math.sqrt(2) + 3, joined.duration_sec)
        angle_equal(self, joined.motions[0].end.heading, joined.motions[1].start.heading)

    def test_lateral_left_to_right_reversal_stops(self):
        outward = plan_lateral_trajectory(Pose(0, 0, 0), (0, 1), speed_m_per_sec=.5, lateral_allowed=True)
        inward = plan_lateral_trajectory(Pose(0, 1, 0), (0, 0), speed_m_per_sec=.5, lateral_allowed=True)
        joined = retime_trajectory(Trajectory(outward.motions + inward.motions, 0, False), settings())
        self.assertAlmostEqual(5, joined.duration_sec)
        self.assertEqual(0, joined.motions[0].profile['end_speed'])
        self.assertEqual(0, joined.motions[1].profile['start_speed'])

    def test_versioned_directional_evidence_replays_exact_motion(self):
        for path in (reverse([(0, 0), (-6, 0), (-6, -6)]),
                     plan_lateral_trajectory(Pose(0, 0, 0), (0, 2), speed_m_per_sec=1, lateral_allowed=True)):
            path = retime_trajectory(path, settings())
            data = path.to_dict()
            self.assertEqual((2, 'directional_fillet_v1'), (data['schema_version'], data['model']))
            restored = trajectory_from_dict(data)
            self.assertEqual(path, restored)
            for f in (0, .1, .5, .9, 1):
                self.assertEqual(path.pose_at_time(path.duration_sec * f), restored.pose_at_time(path.duration_sec * f))

    def test_legacy_forward_evidence_stays_compatible_and_rejects_reverse_disguise(self):
        forward = plan_trajectory([(0, 0), (2, 0)], minimum_radius_m=2, speed_m_per_sec=1,
                                  pivot_allowed=False, pivot_speed_deg_per_sec=90)
        data = forward.to_dict()
        self.assertEqual(1, data['schema_version'])
        self.assertNotIn('movement', data['motions'][0])
        self.assertEqual(forward, trajectory_from_dict(data))
        data['motions'][0]['movement'] = 'reverse'
        with self.assertRaisesRegex(TrajectoryError, 'invalid_evidence'):
            trajectory_from_dict(data)

    def test_corrupt_directional_orientation_and_arc_metadata_are_rejected(self):
        source = reverse([(0, 0), (-6, 0), (-6, -6)]).to_dict()
        for index, field, value in ((0, 'movement', 'forward'), (1, 'movement', 'lateral'),
                                    (0, 'movement', 'diagonal')):
            data = copy.deepcopy(source)
            data['motions'][index][field] = value
            with self.assertRaisesRegex(TrajectoryError, 'invalid_evidence'):
                trajectory_from_dict(data)
        data = plan_lateral_trajectory(Pose(0, 0, 0), (0, 1), speed_m_per_sec=1, lateral_allowed=True).to_dict()
        data['motions'][0]['start']['heading'] = math.pi / 2
        data['motions'][0]['end']['heading'] = math.pi / 2
        with self.assertRaisesRegex(TrajectoryError, 'invalid_evidence'):
            trajectory_from_dict(data)

    def test_continuous_static_clearance_follows_actual_lateral_sweep(self):
        path = plan_lateral_trajectory(Pose(0, 0, 0), (0, 2), speed_m_per_sec=1, lateral_allowed=True)
        self.assertEqual('collision', check_clearance(path, length_m=2, width_m=.4,
            obstacles=[(.8, .9, 1.1, 1.1)])['status'])
        self.assertEqual('clear', check_clearance(path, length_m=2, width_m=.4,
            obstacles=[(1.1, .9, 1.2, 1.1)])['status'])

    def test_reverse_curve_swept_footprint_includes_mid_arc(self):
        path = reverse([(0, 0), (-6, 0), (-6, -6)])
        x, y = -4 - math.sqrt(2), -2 + math.sqrt(2)
        self.assertEqual('collision', check_clearance(path, length_m=1, width_m=.6,
            obstacles=[(x - .05, y - .05, x + .05, y + .05)])['status'])

    def test_lateral_swept_cell_contains_endpoint_footprints(self):
        path = plan_lateral_trajectory(Pose(0, 0, 0), (0, 2), speed_m_per_sec=1, lateral_allowed=True)
        cells = swept_cells(path, length_m=2, width_m=.4, clearance_m=0)
        # First cell travels y0→.25; complete y envelope is [-.2,.45].
        self.assertEqual((-1., -.2, 1., .45), cells[0]['envelope'])
        obstacle = [(.8, .42), (.9, .42), (.9, .44), (.8, .44)]
        self.assertTrue(polygons_overlap(cells[0]['polygon'], obstacle))

    def test_invalid_directional_inputs_do_not_create_motion(self):
        for value in (True, math.nan, math.inf, 'invalid'):
            with self.assertRaises(TrajectoryError):
                reverse([(0, 0), (-1, 0)], start_heading_deg=value)
        for destination in ((0, 0), (0, math.nan), (False, 1), (0, 1e10)):
            with self.assertRaises(TrajectoryError):
                plan_lateral_trajectory(Pose(0, 0, 0), destination, speed_m_per_sec=1, lateral_allowed=True)
        with self.assertRaises(TrajectoryError):
            plan_lateral_trajectory(Pose(0, 0, 0), (0, 1), speed_m_per_sec=1, lateral_allowed=1)


if __name__ == '__main__':
    unittest.main()
