import math
import unittest
from dataclasses import replace

from amr_motion_profiles import MotionProfile, MotionProfileError, MotionSettings
from amr_trajectories import Motion, Pose, Trajectory, plan_trajectory
from amr_trajectory_dynamics import retime_trajectory


def robot(**changes):
    values = dict(forward_speed_m_per_sec=2, reverse_speed_m_per_sec=1,
                  acceleration_m_per_sec2=1, braking_m_per_sec2=1,
                  maximum_turn_speed_m_per_sec=1.5, lateral_acceleration_m_per_sec2=.5,
                  pivot_allowed=True, lateral_allowed=False,
                  rotation_speed_deg_per_sec=90, angular_acceleration_deg_per_sec2=90,
                  angular_braking_deg_per_sec2=90)
    values.update(changes)
    return MotionSettings(**values)


def path(points, **changes):
    values = dict(minimum_radius_m=2, speed_m_per_sec=2, pivot_allowed=True,
                  pivot_speed_deg_per_sec=90)
    values.update(changes)
    return plan_trajectory(points, **values)


class TrajectoryDynamicsTests(unittest.TestCase):
    def test_single_straight_independent_acceleration_reference(self):
        source = path([(0, 0), (10, 0)])
        result = retime_trajectory(source, robot(braking_m_per_sec2=2))
        self.assertEqual(6.5, result.duration_sec)
        self.assertEqual(10, result.length_m)
        self.assertEqual(5, source.duration_sec)
        self.assertEqual(.5, result.pose_at_time(1).x)
        self.assertEqual(9.75, result.pose_at_time(6).x)
        self.assertEqual(source.motions[0].start, result.motions[0].start)
        self.assertEqual(source.motions[0].end, result.motions[0].end)

    def test_collinear_subdivision_does_not_add_artificial_stops(self):
        whole = retime_trajectory(path([(0, 0), (10, 0)]), robot(braking_m_per_sec2=2))
        split = retime_trajectory(path([(0, 0), (2, 0), (5, 0), (10, 0)]), robot(braking_m_per_sec2=2))
        self.assertAlmostEqual(6.5, split.duration_sec)
        self.assertEqual(3, len(split.motions))
        for first, second in zip(split.motions, split.motions[1:]):
            self.assertEqual(first.profile['end_speed'], second.profile['start_speed'])
            self.assertGreater(first.profile['end_speed'], 0)
        for t in (0, .25, 1, 2, 3, 4, 5, 6, 6.5):
            self.assertAlmostEqual(whole.pose_at_time(t).x, split.pose_at_time(t).x)

    def test_short_subdivisions_propagate_acceleration_and_braking_limits(self):
        # Total1m triangular a=b1 peak1, duration2, regardless of subdivisions.
        result = retime_trajectory(path([(0, 0), (.1, 0), (.9, 0), (1, 0)]), robot())
        self.assertAlmostEqual(2, result.duration_sec)
        self.assertAlmostEqual(math.sqrt(.2), result.motions[0].profile['end_speed'])
        self.assertAlmostEqual(math.sqrt(.2), result.motions[2].profile['start_speed'])
        self.assertAlmostEqual(.5, result.pose_at_time(1).x)

    def test_decimal_subdivision_grid_preserves_feasibility_timing_and_progress(self):
        # Regression: upward-rounded sqrt boundary speeds caused 787 of these
        # 5,832 physically valid cases to fail the minimum-distance check.
        count = 0
        splits = ((.1, .9), (.01, .1, .9, .99), (.1, .2, .3, .4, .5, .6, .7, .8, .9))
        for distance in (.0001, .001, .01, .1, .3, 1, 3, 10, 100):
            for speed in (.01, .1, .3, 1, 3, 10):
                for acceleration in (.01, .1, .3, 1, 3, 10):
                    for braking in (.01, .1, .3, 1, 3, 10):
                        settings = robot(forward_speed_m_per_sec=speed,
                                         acceleration_m_per_sec2=acceleration, braking_m_per_sec2=braking)
                        whole = Trajectory((Motion('line', Pose(0, 0, 0), Pose(distance, 0, 0),
                                                   distance, distance / speed),), 1, False)
                        expected = retime_trajectory(whole, settings)
                        for fractions in splits:
                            count += 1
                            points = [0] + [distance * f for f in fractions] + [distance]
                            motions = tuple(Motion('line', Pose(x, 0, 0), Pose(y, 0, 0),
                                                   y - x, (y - x) / speed)
                                            for x, y in zip(points, points[1:]))
                            with self.subTest(distance=distance, speed=speed, acceleration=acceleration,
                                              braking=braking, fractions=fractions):
                                result = retime_trajectory(Trajectory(motions, 1, False), settings)
                                self.assertTrue(math.isclose(expected.duration_sec, result.duration_sec,
                                                             rel_tol=1e-11, abs_tol=1e-12))
                                for f in (0, .01, .1, .25, .5, .75, .9, .99, 1):
                                    t = expected.duration_sec * f
                                    self.assertTrue(math.isclose(expected.pose_at_time(t).x,
                                                                 result.pose_at_time(t).x,
                                                                 rel_tol=1e-10, abs_tol=1e-12))
        self.assertEqual(5832, count)

    def test_tangent_arc_cap_and_boundary_continuity(self):
        # r2, lateral accel .5 => turncap1. First4m line: accelerate2s/2m,
        # cruise.25s/.5m, brake1s/1.5m =>3.25s. Arc pi m at1; final symmetric.
        result = retime_trajectory(path([(0, 0), (6, 0), (6, 6)]), robot())
        self.assertAlmostEqual(6.5 + math.pi, result.duration_sec)
        first, arc, last = result.motions
        self.assertAlmostEqual(3.25, first.duration_sec)
        self.assertAlmostEqual(1, first.profile['end_speed'])
        self.assertAlmostEqual(1, arc.profile['start_speed'])
        self.assertAlmostEqual(1, arc.profile['end_speed'])
        self.assertAlmostEqual(1, last.profile['start_speed'])
        self.assertEqual(0, first.profile['start_speed'])
        self.assertEqual(0, last.profile['end_speed'])
        pose = result.pose_at_time(first.duration_sec + math.pi / 2)
        self.assertAlmostEqual(4 + math.sqrt(2), pose.x)
        self.assertAlmostEqual(2 - math.sqrt(2), pose.y)
        self.assertAlmostEqual(math.pi / 4, pose.heading)

    def test_configured_turn_speed_can_be_tighter_than_lateral_limit(self):
        result = retime_trajectory(path([(0, 0), (6, 0), (6, 6)]), robot(maximum_turn_speed_m_per_sec=.5))
        self.assertEqual(.5, result.motions[1].profile['max_speed'])
        self.assertAlmostEqual(2 * math.pi, result.motions[1].duration_sec)

    def test_pivot_stops_translation_and_has_angular_dynamics(self):
        result = retime_trajectory(path([(0, 0), (1, 0), (1, 1)]), robot())
        self.assertEqual(['line', 'pivot', 'line'], [m.kind for m in result.motions])
        self.assertAlmostEqual(6, result.duration_sec)
        for m in result.motions:
            self.assertEqual(0, m.profile['start_speed'])
            self.assertEqual(0, m.profile['end_speed'])
            self.assertAlmostEqual(2, m.duration_sec)
        pose = result.pose_at_time(2.5)
        self.assertEqual((1, 0), (pose.x, pose.y))
        self.assertAlmostEqual(math.pi / 16, pose.heading)

    def test_profile_parameters_reconstruct_each_duration(self):
        result = retime_trajectory(path([(0, 0), (6, 0), (6, 6)]), robot())
        for m in result.motions:
            profile = MotionProfile(**m.profile)
            self.assertEqual(m.duration_sec, profile.duration_sec)
            self.assertEqual(m.length_m, profile.distance)
        self.assertEqual(result, retime_trajectory(result, robot()))

    def test_forbidden_pivot_is_infeasible_not_silently_replaced(self):
        with self.assertRaises(MotionProfileError) as raised:
            retime_trajectory(path([(0, 0), (1, 0), (1, 1)]), robot(pivot_allowed=False))
        self.assertEqual('infeasible_motion', raised.exception.reason)

    def test_discontinuous_and_invalid_motion_inputs_are_rejected(self):
        p = path([(0, 0), (10, 0)])
        m = p.motions[0]
        for bad in (None, Trajectory((), 2, True), replace(p, motions=(replace(m, length_m=-1),)),
                    replace(p, motions=(replace(m, kind='unknown'),)),
                    replace(p, motions=(replace(m, length_m=math.inf),)),
                    replace(p, motions=(m, m))):
            with self.subTest(bad=bad), self.assertRaises(MotionProfileError):
                retime_trajectory(bad, robot())
        with self.assertRaises(MotionProfileError):
            retime_trajectory(p, {})


if __name__ == '__main__':
    unittest.main()
