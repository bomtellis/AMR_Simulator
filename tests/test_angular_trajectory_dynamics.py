"""Independent centre-path yaw limits and curvature-boundary references."""
import math
import unittest

from amr_motion_profiles import (MotionProfile, MotionProfileError, MotionSettings,
                                 profile_for_movement)
from amr_trajectories import Motion, Pose, Trajectory, trajectory_from_dict
from amr_trajectory_dynamics import retime_trajectory


def settings(**changes):
    values = dict(forward_speed_m_per_sec=10, reverse_speed_m_per_sec=10,
                  acceleration_m_per_sec2=10, braking_m_per_sec2=10,
                  maximum_turn_speed_m_per_sec=10, lateral_acceleration_m_per_sec2=10,
                  pivot_allowed=False, lateral_allowed=False,
                  rotation_speed_deg_per_sec=45, angular_acceleration_deg_per_sec2=45,
                  angular_braking_deg_per_sec2=45)
    values.update(changes)
    return MotionSettings(**values)


def arc(start, radius, sweep, movement='forward'):
    tangent = start.heading - (math.pi if movement == 'reverse' else 0)
    sign = math.copysign(1, sweep)
    centre = (start.x - sign * radius * math.sin(tangent),
              start.y + sign * radius * math.cos(tangent))
    x, y = start.x - centre[0], start.y - centre[1]
    end = Pose(centre[0] + x * math.cos(sweep) - y * math.sin(sweep),
               centre[1] + x * math.sin(sweep) + y * math.cos(sweep), start.heading + sweep)
    return Motion('arc', start, end, radius * abs(sweep), 1,
                  sweep_rad=sweep, radius_m=radius, centre=centre, movement=movement)


def path(*motions):
    return Trajectory(tuple(motions), 1, False)


class AngularTrajectoryDynamicsTests(unittest.TestCase):
    def test_quarter_circle_independent_angular_trapezoid(self):
        # 90deg: accelerate1s/22.5deg, cruise1s/45deg, brake1s/22.5deg.
        source = path(arc(Pose(0, 0, 0), 2, math.pi / 2))
        result = retime_trajectory(source, settings())
        p = MotionProfile(**result.motions[0].profile)
        self.assertAlmostEqual(3, result.duration_sec)
        self.assertAlmostEqual(math.pi / 2, p.max_speed)
        self.assertAlmostEqual(math.pi / 2, p.acceleration)
        self.assertAlmostEqual(math.pi / 2, p.braking)
        self.assertAlmostEqual(math.pi / 32, result.pose_at_time(.5).heading)
        self.assertAlmostEqual(math.pi / 4, result.pose_at_time(1.5).heading)
        self.assertEqual(source.motions[0].end, result.motions[0].end)
        direct = profile_for_movement(settings(), movement='forward', distance=math.pi, turn_radius_m=2)
        self.assertEqual(direct.to_dict(), p.to_dict())

    def test_asymmetric_angular_acceleration_and_braking_reference(self):
        # Sweep2rad, omega1: acceleration2s/1rad, cruise.5s/.5rad,
        # braking1s/.5rad. r2 converts angularlimits into v2,a1,b2.
        robot = settings(rotation_speed_deg_per_sec=math.degrees(1),
                         angular_acceleration_deg_per_sec2=math.degrees(.5),
                         angular_braking_deg_per_sec2=math.degrees(1))
        result = retime_trajectory(path(arc(Pose(0, 0, 0), 2, 2)), robot)
        p = MotionProfile(**result.motions[0].profile)
        self.assertAlmostEqual(3.5, result.duration_sec)
        self.assertAlmostEqual(2, p.max_speed)
        self.assertAlmostEqual(1, p.acceleration)
        self.assertAlmostEqual(2, p.braking)
        self.assertAlmostEqual(.25, result.pose_at_time(1).heading)
        self.assertAlmostEqual(1.875, result.pose_at_time(3).heading)

    def test_short_arc_angular_triangular_reference(self):
        # Sweep .25rad, alpha=beta1 => peak .5rad/s, total1s.
        robot = settings(rotation_speed_deg_per_sec=180,
                         angular_acceleration_deg_per_sec2=math.degrees(1),
                         angular_braking_deg_per_sec2=math.degrees(1))
        result = retime_trajectory(path(arc(Pose(0, 0, 0), 2, .25)), robot)
        self.assertAlmostEqual(1, result.duration_sec)
        self.assertAlmostEqual(.125, result.pose_at_time(.5).heading)
        self.assertAlmostEqual(1, MotionProfile(**result.motions[0].profile).peak_speed)

    def test_linear_limits_remain_binding_when_angular_limits_are_higher(self):
        robot = settings(forward_speed_m_per_sec=1, acceleration_m_per_sec2=.2,
                         braking_m_per_sec2=.3)
        p = profile_for_movement(robot, movement='forward', distance=10, turn_radius_m=2)
        self.assertEqual((1, .2, .3), (p.max_speed, p.acceleration, p.braking))
        self.assertAlmostEqual(10 + 2.5 + 5 / 3, p.duration_sec)

    def test_missing_angular_parameters_fail_only_when_low_level_arc_requested(self):
        for missing in ('rotation_speed_deg_per_sec', 'angular_acceleration_deg_per_sec2',
                        'angular_braking_deg_per_sec2'):
            robot = settings(**{missing: None})
            profile_for_movement(robot, movement='forward', distance=1)
            with self.subTest(missing=missing):
                for operation in (lambda: profile_for_movement(robot, movement='reverse', distance=1,
                                                                 turn_radius_m=2),
                                  lambda: retime_trajectory(path(arc(Pose(0, 0, 0), 2, 1)), robot)):
                    with self.assertRaises(MotionProfileError) as raised:
                        operation()
                    self.assertEqual('invalid_input', raised.exception.reason)
                    self.assertIn(missing, str(raised.exception))

    def test_signed_left_and_right_forward_and_reverse_have_equal_elapsed_yaw_limits(self):
        for movement in ('forward', 'reverse'):
            for sign in (-1, 1):
                with self.subTest(movement=movement, sign=sign):
                    result = retime_trajectory(path(arc(Pose(0, 0, 0), 2, sign * math.pi / 2,
                                                       movement)), settings())
                    self.assertAlmostEqual(3, result.duration_sec)
                    self.assertAlmostEqual(sign * math.pi / 4, result.pose_at_time(1.5).heading)
                    restored = trajectory_from_dict(result.to_dict())
                    self.assertEqual(result.pose_at_time(.75), restored.pose_at_time(.75))

    def test_curvature_discontinuities_stop_on_both_sides_of_join(self):
        for movement in ('forward', 'reverse'):
            for first_sign in (-1, 1):
                first = arc(Pose(0, 0, 0), 2, first_sign * .5, movement)
                for second_radius, second_sweep in ((2, -first_sign * .5), (3, first_sign * .5)):
                    with self.subTest(movement=movement, sign=first_sign, radius=second_radius,
                                      sweep=second_sweep):
                        second = arc(first.end, second_radius, second_sweep, movement)
                        result = retime_trajectory(path(first, second), settings())
                        self.assertEqual(0, result.motions[0].profile['end_speed'])
                        self.assertEqual(0, result.motions[1].profile['start_speed'])
                        for m in result.motions:
                            p = MotionProfile(**m.profile)
                            self.assertEqual(0, p.speed_at_time(0) * math.copysign(1, m.sweep_rad) / m.radius_m)
                            self.assertEqual(0, p.speed_at_time(p.duration_sec) / m.radius_m)

    def test_line_arc_line_yaw_velocity_has_no_boundary_jump(self):
        straight = Motion('line', Pose(0, 0, 0), Pose(4, 0, 0), 4, 1)
        bend = arc(straight.end, 2, math.pi / 2)
        after = Motion('line', bend.end, Pose(bend.end.x, bend.end.y + 4, math.pi / 2), 4, 1)
        result = retime_trajectory(path(straight, bend, after), settings())
        for first, second in zip(result.motions, result.motions[1:]):
            self.assertEqual(0, first.profile['end_speed'])
            self.assertEqual(0, second.profile['start_speed'])
        self.assertEqual([m.start for m in (straight, bend, after)], [m.start for m in result.motions])

    def test_constant_signed_curvature_subdivision_preserves_timing_and_pose(self):
        for movement in ('forward', 'reverse'):
            for sign in (-1, 1):
                start = Pose(0, 0, 0)
                whole = retime_trajectory(path(arc(start, 2, sign * math.pi / 2, movement)), settings())
                parts = []
                for fraction in (.1, .2, .7):
                    parts.append(arc(start, 2, sign * math.pi / 2 * fraction, movement))
                    start = parts[-1].end
                split = retime_trajectory(path(*parts), settings())
                with self.subTest(movement=movement, sign=sign):
                    self.assertAlmostEqual(3, split.duration_sec)
                    for first, second in zip(split.motions, split.motions[1:]):
                        self.assertGreater(first.profile['end_speed'], 0)
                        self.assertEqual(first.profile['end_speed'], second.profile['start_speed'])
                    for t in (0, .1, .5, 1, 1.5, 2, 2.9, 3):
                        expected, actual = whole.pose_at_time(t), split.pose_at_time(t)
                        self.assertAlmostEqual(expected.x, actual.x)
                        self.assertAlmostEqual(expected.y, actual.y)
                        self.assertAlmostEqual(expected.heading, actual.heading)

    def test_direction_change_stops_even_with_equal_signed_arc_curvature(self):
        first = arc(Pose(0, 0, 0), 2, .5)
        second = arc(first.end, 2, .5, 'reverse')
        result = retime_trajectory(path(first, second), settings())
        self.assertEqual(0, result.motions[0].profile['end_speed'])
        self.assertEqual(0, result.motions[1].profile['start_speed'])


if __name__ == '__main__':
    unittest.main()
