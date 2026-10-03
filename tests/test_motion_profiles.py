"""Independent kinematic references, not simulation-derived expectations."""
import copy
import math
import unittest

from amr_motion_profiles import (MotionProfile, MotionProfileError, MotionSettings,
                                 stopping_distance, turn_speed_limit,
                                 select_motion_settings, profile_for_movement)
from amr_trajectories import Motion, Pose


def settings(**changes):
    values = dict(forward_speed_m_per_sec=2, reverse_speed_m_per_sec=1,
                  acceleration_m_per_sec2=1, braking_m_per_sec2=2,
                  maximum_turn_speed_m_per_sec=1.5, lateral_acceleration_m_per_sec2=.5,
                  pivot_allowed=True, lateral_allowed=True, lateral_speed_m_per_sec=.5,
                  rotation_speed_deg_per_sec=90, angular_acceleration_deg_per_sec2=90,
                  angular_braking_deg_per_sec2=90, minimum_radius_m=2)
    values.update(changes)
    return values


class MotionProfileTests(unittest.TestCase):
    def test_rest_to_rest_trapezoid_asymmetric_braking(self):
        # Accelerate 2 s over 2 m, cruise 7 m in 3.5 s, brake 1 s over 1 m.
        p = MotionProfile(10, 2, 1, 2)
        self.assertEqual(6.5, p.duration_sec)
        self.assertEqual((2, 3.5, 1), (p.acceleration_time, p.cruise_time, p.braking_time))
        self.assertEqual((2, 7, 1), (p.acceleration_distance, p.cruise_distance, p.braking_distance))
        for t, x, v in ((0, 0, 0), (1, .5, 1), (2, 2, 2), (3, 4, 2),
                        (5.5, 9, 2), (6, 9.75, 1), (6.5, 10, 0)):
            with self.subTest(t=t):
                self.assertAlmostEqual(x, p.distance_at_time(t))
                self.assertAlmostEqual(v, p.speed_at_time(t))
                self.assertAlmostEqual(t, p.time_at_distance(x))

    def test_short_route_triangular_profile(self):
        # 1 metre, a=b=1: accelerate .5m in 1s, brake .5m in 1s.
        p = MotionProfile(1, 100, 1, 1)
        self.assertEqual(1, p.peak_speed)
        self.assertEqual(2, p.duration_sec)
        self.assertEqual(0, p.cruise_time)
        self.assertEqual(.125, p.distance_at_time(.5))
        self.assertEqual(.875, p.distance_at_time(1.5))
        self.assertEqual(.5, p.speed_at_time(1.5))

    def test_triangular_profile_different_acceleration_and_braking(self):
        # a=2,b=1,d=3: peak2; accelerate1s/1m, brake2s/2m.
        p = MotionProfile(3, 10, 2, 1)
        self.assertEqual(2, p.peak_speed)
        self.assertEqual(3, p.duration_sec)
        self.assertAlmostEqual(2.5, p.distance_at_time(2))
        self.assertAlmostEqual(2, p.time_at_distance(2.5))

    def test_exact_transition_between_triangular_and_trapezoidal(self):
        p = MotionProfile(3, 2, 1, 2)
        self.assertEqual(3, p.duration_sec)
        self.assertEqual(0, p.cruise_time)
        self.assertEqual(2, p.distance_at_time(2))
        self.assertEqual(2, p.time_at_distance(2))

    def test_nonzero_boundary_speeds_trapezoidal(self):
        # Start1/end2, peak3,a1,b2: accelerate4m/2s, brake1.25m/.5s.
        # Remaining4.75m at3m/s => total49/12s.
        p = MotionProfile(10, 3, 1, 2, start_speed=1, end_speed=2)
        self.assertAlmostEqual(49 / 12, p.duration_sec)
        self.assertEqual(4, p.acceleration_distance)
        self.assertEqual(1.25, p.braking_distance)
        self.assertEqual(1.5, p.distance_at_time(1))
        self.assertEqual(1, p.time_at_distance(1.5))
        self.assertEqual(2, p.speed_at_time(p.duration_sec))

    def test_nonzero_boundary_speeds_triangular(self):
        # Start1,end2,a=b1,d=1.5 is exactly acceleration only (1s).
        p = MotionProfile(1.5, 20, 1, 1, start_speed=1, end_speed=2)
        self.assertEqual(2, p.peak_speed)
        self.assertEqual(1, p.duration_sec)
        self.assertEqual(0, p.braking_time)
        self.assertEqual(.625, p.distance_at_time(.5))
        self.assertEqual(.5, p.time_at_distance(.625))

    def test_braking_only_and_cruise_only(self):
        p = MotionProfile(1.5, 20, 1, 1, start_speed=2, end_speed=1)
        self.assertEqual(0, p.acceleration_time)
        self.assertEqual(1, p.duration_sec)
        self.assertEqual(.875, p.distance_at_time(.5))
        self.assertEqual(.5, p.time_at_distance(.875))
        p = MotionProfile(10, 2, 1, 1, start_speed=2, end_speed=2)
        self.assertEqual(5, p.duration_sec)
        self.assertEqual(2, p.distance_at_time(1))
        self.assertEqual(1, p.time_at_distance(2))

    def test_boundary_speed_constraints_report_infeasible(self):
        for args in ((1, 1, 1, 1, 2, 0), (1, 2, 1, 1, 0, 2),
                     (1, 2, 1, 1, 2, 0), (0, 2, 1, 1, 1, 1)):
            with self.subTest(args=args), self.assertRaises(MotionProfileError) as raised:
                MotionProfile(*args)
            self.assertEqual('infeasible_motion', raised.exception.reason)

    def test_invalid_parameters_report_invalid_input(self):
        for index in range(6):
            for value in (True, None, 'nonsense', math.nan, math.inf, -math.inf, -1):
                args = [1, 2, 1, 1, 0, 0]
                args[index] = value
                with self.subTest(index=index, value=value), self.assertRaises(MotionProfileError) as raised:
                    MotionProfile(*args)
                self.assertEqual('invalid_input', raised.exception.reason)
        for index in (1, 2, 3):
            args = [1, 2, 1, 1]
            args[index] = 0
            with self.assertRaises(MotionProfileError):
                MotionProfile(*args)

    def test_stationary_profile_and_clamped_endpoint(self):
        stationary = MotionProfile(0, 2, 1, 1)
        self.assertEqual(0, stationary.duration_sec)
        self.assertEqual(0, stationary.distance_at_time(100))
        self.assertEqual(1, stationary.fraction_at_time(0))
        p = MotionProfile(10, 2, 1, 1)
        self.assertEqual(10, p.distance_at_time(100))
        self.assertEqual(0, p.speed_at_time(100))
        self.assertEqual(p.duration_sec, p.time_at_distance(100))
        self.assertEqual(1, p.fraction_at_time(100))

    def test_lookup_invalid_values_are_not_clamped(self):
        p = MotionProfile(10, 2, 1, 1)
        for method in (p.distance_at_time, p.time_at_distance, p.speed_at_time, p.fraction_at_time):
            for value in (-1, math.inf, math.nan, True):
                with self.subTest(method=method, value=value), self.assertRaises(MotionProfileError):
                    method(value)

    def test_progress_and_inverse_across_profile_phases(self):
        # Inverse and monotonic checks supplement the independent numeric cases.
        for p in (MotionProfile(10, 2, 1, 2), MotionProfile(3, 10, 2, 1),
                  MotionProfile(10, 3, 1, 2, 1, 2)):
            previous = -1
            for i in range(201):
                t = p.duration_sec * i / 200
                x = p.distance_at_time(t)
                self.assertGreaterEqual(x, previous)
                self.assertAlmostEqual(t, p.time_at_distance(x), places=10)
                self.assertLessEqual(p.speed_at_time(t), p.max_speed)
                previous = x

    def test_path_pose_uses_distance_progress_not_time_fraction(self):
        p = MotionProfile(10, 2, 1, 2)
        motion = Motion('line', Pose(0, 0, 0), Pose(10, 0, 0), 10, p.duration_sec)
        self.assertEqual(.5, motion.pose_at(p.fraction_at_time(1)).x)
        self.assertEqual(9.75, motion.pose_at(p.fraction_at_time(6)).x)

    def test_stopping_distance_has_independent_kinematic_reference(self):
        self.assertEqual(4, stopping_distance(4, 2))
        self.assertEqual(.5, stopping_distance(1, 1))
        self.assertEqual(0, stopping_distance(0, 1))
        for args in ((1, 0), (-1, 1), (1, True), (math.inf, 1)):
            with self.assertRaises(MotionProfileError):
                stopping_distance(*args)

    def test_turning_speed_respects_both_limits(self):
        self.assertAlmostEqual(1, turn_speed_limit(3, .5, 2))
        self.assertEqual(.5, turn_speed_limit(.5, .5, 2))
        self.assertAlmostEqual(2, turn_speed_limit(3, .5, 8))
        for args in ((0, 1, 1), (1, 0, 1), (1, 1, 0), (1, 1, -1), (True, 1, 1)):
            with self.assertRaises(MotionProfileError):
                turn_speed_limit(*args)


class MotionSettingsTests(unittest.TestCase):
    def test_loaded_and_empty_settings_are_explicit_independent_and_immutable(self):
        inputs = {'empty': settings(), 'loaded': settings(forward_speed_m_per_sec=1, minimum_radius_m=3)}
        original = copy.deepcopy(inputs)
        self.assertEqual(2, select_motion_settings(inputs, loaded=False).forward_speed_m_per_sec)
        self.assertEqual(1, select_motion_settings(inputs, loaded=True).forward_speed_m_per_sec)
        self.assertEqual(3, select_motion_settings(inputs, loaded=True).minimum_radius_m)
        self.assertEqual(original, inputs)
        del inputs['loaded']['braking_m_per_sec2']
        for loaded in (False, True):
            with self.assertRaisesRegex(MotionProfileError, 'movement.loaded'):
                select_motion_settings(inputs, loaded=loaded)

    def test_no_invented_defaults_or_implicit_capabilities(self):
        for inputs in ({}, {'empty': settings()}, {'empty': settings(), 'loaded': None}):
            with self.assertRaises(MotionProfileError):
                select_motion_settings(inputs, loaded=True)
        with self.assertRaises(MotionProfileError):
            select_motion_settings({'empty': settings(), 'loaded': settings()}, loaded=1)
        for change in ({'pivot_allowed': 'false'}, {'lateral_allowed': 1},
                       {'rotation_speed_deg_per_sec': None}, {'lateral_speed_m_per_sec': 0},
                       {'minimum_radius_m': -1}):
            with self.assertRaises(MotionProfileError):
                MotionSettings(**settings(**change))

    def test_disabled_capability_fields_may_be_omitted_but_not_invalid(self):
        values = settings(pivot_allowed=False, lateral_allowed=False)
        for key in ('rotation_speed_deg_per_sec', 'angular_acceleration_deg_per_sec2',
                    'angular_braking_deg_per_sec2', 'lateral_speed_m_per_sec'):
            del values[key]
        robot = MotionSettings(**values)
        for movement in ('pivot', 'lateral', 'flight'):
            with self.assertRaises(MotionProfileError):
                profile_for_movement(robot, movement=movement, distance=1)
        with self.assertRaises(MotionProfileError):
            MotionSettings(**{**values, 'lateral_speed_m_per_sec': math.nan})

    def test_forward_reverse_and_lateral_use_separate_speed_caps(self):
        robot = MotionSettings(**settings())
        # D/v + v/(2a) + v/(2b), for D=10,a1,b2.
        for movement, speed, duration in (('forward', 2, 6.5), ('reverse', 1, 10.75),
                                           ('lateral', .5, 20.375)):
            p = profile_for_movement(robot, movement=movement, distance=10)
            self.assertEqual(speed, p.max_speed)
            self.assertEqual(duration, p.duration_sec)

    def test_pivot_converts_degrees_and_respects_angular_acceleration(self):
        robot = MotionSettings(**settings())
        # 180deg: accelerate1s/45deg, cruise1s/90deg, brake1s/45deg.
        p = profile_for_movement(robot, movement='pivot', distance=math.pi)
        self.assertAlmostEqual(3, p.duration_sec)
        self.assertAlmostEqual(math.pi / 4, p.distance_at_time(1))
        motion = Motion('pivot', Pose(0, 0, 0), Pose(0, 0, math.pi), 0, p.duration_sec,
                        sweep_rad=math.pi)
        self.assertAlmostEqual(math.pi / 4, motion.pose_at(p.fraction_at_time(1)).heading)

    def test_arc_limit_combines_robot_direction_and_turn_constraints(self):
        robot = MotionSettings(**settings())
        p = profile_for_movement(robot, movement='forward', distance=10, turn_radius_m=2)
        self.assertAlmostEqual(1, p.max_speed)
        p = profile_for_movement(robot, movement='reverse', distance=10, turn_radius_m=100)
        self.assertEqual(1, p.max_speed)
        with self.assertRaises(MotionProfileError):
            profile_for_movement(robot, movement='pivot', distance=1, turn_radius_m=2)


if __name__ == '__main__':
    unittest.main()
