"""Independent timing and executed-prefix checks for offset reference geometry."""
from dataclasses import replace
import math
import unittest

from amr_motion_profiles import MotionProfile, MotionProfileError
from amr_partial_run import derive_partial_run
from amr_trajectories import Motion, Pose, Trajectory, trajectory_from_dict
from amr_trajectory_dynamics import retime_trajectory
from tests.test_partial_run import FROZEN, movement_row
from tests.test_trajectory_dynamics import robot


def reference(longitudinal=1000., lateral=500., axis='reference_point'):
    return {'longitudinal_mm': longitudinal, 'lateral_mm': lateral,
            'timing_reference': 'turning_reference_point', 'pivot_axis': axis}


def reference_pivot():
    # Fixed R=(0,0), C=R-Rotation(heading)*(1,.5).
    return Motion('pivot', Pose(-1, -.5, 0), Pose(.5, -1, math.pi / 2),
                  0, 1, sweep_rad=math.pi / 2, centre=(0, 0), reference=reference())


def offset_arc():
    # Reference quarter-circle r2, tangent headings pi/2 -> pi.
    # C orbits radius sqrt(3^2+1^2), independent of the reference r2.
    return Motion('arc', Pose(3, -1, math.pi / 2), Pose(1, 3, math.pi),
                  math.pi, 1, sweep_rad=math.pi / 2, radius_m=2, centre=(0, 0),
                  reference=reference(lateral=1000))


class ReferenceOffsetDynamicsTests(unittest.TestCase):
    def test_reference_arc_with_stationary_body_requires_pivot_capability(self):
        # R traces a radius2 quarter circle around C=(0,0). Despite kind=arc,
        # this motion rotates the physical robot in place.
        motion = Motion('arc', Pose(0, 0, 0), Pose(0, 0, math.pi / 2), math.pi, 1,
                        sweep_rad=math.pi / 2, radius_m=2, centre=(0, 0),
                        reference=reference(longitudinal=0, lateral=-2000))
        self.assertEqual(0, motion.centre_orbit_radius_m)
        with self.assertRaises(MotionProfileError) as raised:
            retime_trajectory(Trajectory((motion,), 2, False), robot(pivot_allowed=False))
        self.assertEqual('infeasible_motion', raised.exception.reason)
        allowed = retime_trajectory(Trajectory((motion,), 2, True), robot())
        pose = allowed.pose_at_time(allowed.duration_sec / 2)
        self.assertEqual((0, 0), (pose.x, pose.y))
        self.assertAlmostEqual(math.pi / 4, pose.heading)
        self.assertEqual(0, allowed.motions[0].body_length_m)

    def test_arc_yaw_limits_use_reference_radius_and_preserve_body_endpoints(self):
        source = Trajectory((offset_arc(),), 2, True)
        settings = robot(forward_speed_m_per_sec=10, maximum_turn_speed_m_per_sec=10,
                         lateral_acceleration_m_per_sec2=10,
                         acceleration_m_per_sec2=10, braking_m_per_sec2=10,
                         rotation_speed_deg_per_sec=math.degrees(.5),
                         angular_acceleration_deg_per_sec2=math.degrees(.25),
                         angular_braking_deg_per_sec2=math.degrees(.25))
        timed = retime_trajectory(source, settings)
        arc = timed.motions[0]
        profile = MotionProfile(**arc.profile)
        self.assertAlmostEqual(1, profile.max_speed)  # omega*r
        self.assertAlmostEqual(.5, profile.acceleration)  # alpha*r
        self.assertAlmostEqual(.5, profile.braking)
        self.assertAlmostEqual(math.pi + 2, timed.duration_sec)
        self.assertAlmostEqual(math.pi, timed.length_m)
        self.assertAlmostEqual(math.sqrt(10) * math.pi / 2, arc.body_length_m)
        self.assertEqual(source.motions[0].start, arc.start)
        self.assertEqual(source.motions[0].end, arc.end)
        middle = timed.pose_at_time(timed.duration_sec / 2)
        self.assertAlmostEqual(2 * math.sqrt(2), middle.x)
        self.assertAlmostEqual(math.sqrt(2), middle.y)
        self.assertAlmostEqual(3 * math.pi / 4, middle.heading)
        for t in (.1, 1, 2, 3, timed.duration_sec - .1):
            self.assertLessEqual(profile.speed_at_time(t) / 2, .5 + 1e-12)
        decoded = trajectory_from_dict(timed.to_dict())
        self.assertEqual(timed.to_dict(), decoded.to_dict())

    def test_reference_axis_pivot_has_angular_profile_and_translating_body(self):
        source = Trajectory((reference_pivot(),), 2, True)
        timed = retime_trajectory(source, robot())
        motion = timed.motions[0]
        self.assertAlmostEqual(2, timed.duration_sec)
        self.assertEqual(0, timed.length_m)
        self.assertAlmostEqual(math.sqrt(1.25) * math.pi / 2, motion.body_length_m)
        self.assertAlmostEqual(math.pi / 2, motion.profile['distance'])
        angle = math.pi / 16  # .5*alpha*.5^2
        pose = timed.pose_at_time(.5)
        self.assertAlmostEqual(-math.cos(angle) + .5 * math.sin(angle), pose.x)
        self.assertAlmostEqual(-math.sin(angle) - .5 * math.cos(angle), pose.y)
        self.assertAlmostEqual(angle, pose.heading)
        fixed = motion.reference_pose_at(motion.fraction_at_time(.5))
        self.assertAlmostEqual(0, fixed.x)
        self.assertAlmostEqual(0, fixed.y)
        decoded = trajectory_from_dict(timed.to_dict())
        self.assertEqual(timed.to_dict(), decoded.to_dict())

    def test_partial_reference_pivot_reports_body_motion_without_inventing_reference_translation(self):
        timed = retime_trajectory(Trajectory((reference_pivot(),), 2, True), robot())
        activity = derive_partial_run([movement_row(timed)], FROZEN, stop_time=.5)['activities'][0]
        self.assertEqual('partial', activity['state'])
        self.assertEqual('turning_reference_point', activity['distance_reference'])
        self.assertEqual('translational_primitives_only', activity['distance_measure'])
        self.assertEqual(0, activity['elapsed_distance_m'])
        self.assertAlmostEqual(math.sqrt(1.25) * math.pi / 16, activity['elapsed_body_distance_m'])
        self.assertAlmostEqual(math.sqrt(1.25) * math.pi / 2, activity['planned_body_distance_m'])
        self.assertAlmostEqual(math.pi / 16, activity['elapsed_rotation_rad'])
        self.assertAlmostEqual(-math.cos(math.pi / 16) + .5 * math.sin(math.pi / 16),
                               activity['pose_at_cutoff']['x'])
        self.assertAlmostEqual(500 / 3600000, activity['elapsed_model_energy_kwh'])

    def test_partial_arc_reports_distinct_reference_and_body_distances(self):
        timed = retime_trajectory(Trajectory((offset_arc(),), 2, True), robot())
        activity = derive_partial_run([movement_row(timed)], FROZEN,
                                      stop_time=timed.duration_sec / 2)['activities'][0]
        self.assertAlmostEqual(math.pi / 2, activity['elapsed_distance_m'])
        self.assertAlmostEqual(math.sqrt(10) * math.pi / 4, activity['elapsed_body_distance_m'])

    def test_body_axis_offset_pivot_remains_stationary_and_zero_offset_legacy_is_unchanged(self):
        for metadata in (None, reference(axis='body_centre')):
            with self.subTest(metadata=metadata):
                raw = Motion('pivot', Pose(1, 2, 0), Pose(1, 2, math.pi / 2), 0, 1,
                             sweep_rad=math.pi / 2, reference=metadata)
                timed = retime_trajectory(Trajectory((raw,), 2, True), robot())
                self.assertAlmostEqual(2, timed.duration_sec)
                self.assertEqual(0, timed.motions[0].body_length_m)
                self.assertEqual((1, 2), (timed.pose_at_time(.5).x, timed.pose_at_time(.5).y))
                activity = derive_partial_run([movement_row(timed)], FROZEN, stop_time=.5)['activities'][0]
                self.assertEqual(0, activity['elapsed_body_distance_m'])
                self.assertEqual('body_centre' if metadata is None else 'turning_reference_point',
                                 activity['distance_reference'])

    def test_malformed_reference_pivots_are_rejected_before_timing(self):
        good = reference_pivot()
        invalid = (replace(good, end=Pose(.5, -2, math.pi / 2)),
                   replace(good, centre=()), replace(good, centre=(math.nan, 0)),
                   replace(good, reference=reference(axis='body_centre')),
                   replace(good, radius_m=1), replace(good, length_m=1),
                   replace(good, end=replace(good.end, heading=math.pi)),
                   replace(good, reference={}),
                   replace(good, reference=reference(longitudinal=True)),
                   replace(good, reference=reference(lateral=math.inf)),
                   replace(good, reference=reference(axis='guess')),
                   replace(good, reference=dict(reference(), timing_reference='guess')))
        for motion in invalid:
            with self.subTest(motion=motion), self.assertRaises(MotionProfileError):
                retime_trajectory(Trajectory((motion,), 2, True), robot())
        with self.assertRaises(MotionProfileError):
            retime_trajectory(Trajectory((good,), 2, True), robot(pivot_allowed=False))


if __name__ == '__main__':
    unittest.main()
