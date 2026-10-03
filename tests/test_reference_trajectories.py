"""Independent rigid-reference geometry, endpoint and saved-evidence checks."""
import copy
import math
import unittest

from amr_reference_trajectories import (plan_reference_trajectory, plan_reference_lateral_trajectory,
                                       reference_metadata, reference_motion_to_body)
from amr_trajectories import (Motion, Pose, Trajectory, TrajectoryError, plan_trajectory,
                              plan_reverse_trajectory, plan_lateral_trajectory,
                              trajectory_from_dict, check_clearance)


def plan(points, **changes):
    values = dict(reference_longitudinal_mm=1000, reference_lateral_mm=500,
                  pivot_axis='body_centre', minimum_radius_m=2, speed_m_per_sec=1,
                  pivot_allowed=False, pivot_speed_deg_per_sec=90)
    values.update(changes)
    return plan_reference_trajectory(points, **values)


class ReferenceTrajectoryTests(unittest.TestCase):
    def test_forward_fillet_keeps_graph_endpoints_and_changes_actual_centre_orbit(self):
        result = plan([(0, 0), (6, 0), (6, 6)])
        first, arc, last = result.motions
        self.assertEqual(Pose(0, 0, 0), first.start)
        self.assertEqual(Pose(6, 6, math.pi/2), last.end)
        # Shifted reference supports y=.5, x=5.5 intersect(5.5,.5).
        # Radius2 trim -> entry(3.5,.5), exit(5.5,2.5), centre(3.5,2.5).
        self.assertAlmostEqual(2.5, first.length_m)
        self.assertAlmostEqual(4.5, last.length_m)
        self.assertEqual((3.5, 2.5), arc.centre)
        self.assertAlmostEqual(math.sqrt(7.25), arc.centre_orbit_radius_m)
        self.assertAlmostEqual(math.pi, arc.length_m)
        self.assertAlmostEqual(math.sqrt(7.25)*math.pi/2, arc.body_length_m)
        r = arc.reference_pose_at(.5)
        self.assertAlmostEqual(3.5 + math.sqrt(2), r.x)
        self.assertAlmostEqual(2.5 - math.sqrt(2), r.y)
        c = arc.pose_at(.5)
        self.assertAlmostEqual(r.x - .5/math.sqrt(2), c.x)
        self.assertAlmostEqual(r.y - 1.5/math.sqrt(2), c.y)

    def test_reverse_curve_uses_body_relative_offset_with_preserved_endpoints(self):
        result = plan([(0, 0), (-6, 0), (-6, -6)], movement='reverse', start_heading_deg=0)
        first, arc, last = result.motions
        self.assertAlmostEqual(0, math.remainder(first.start.heading, 2*math.pi))
        self.assertEqual((0, 0), (first.start.x, first.start.y))
        self.assertEqual((-6, -6), (last.end.x, last.end.y))
        self.assertTrue(all(m.movement == 'reverse' for m in result.motions))
        # Reverse leftward path turn has opposite body-relative radial sign.
        self.assertAlmostEqual(math.sqrt(1 + 1.5**2), arc.centre_orbit_radius_m)
        self.assertEqual(result, trajectory_from_dict(result.to_dict()))

    def test_reference_transform_quarter_circle_has_analytic_body_and_reference_positions(self):
        ref = reference_metadata(1000, 500, 'reference_point')
        source = Motion('arc', Pose(0, 0, 0), Pose(2, 2, math.pi/2), math.pi, math.pi,
                        math.pi/2, 2, (0, 2))
        body = reference_motion_to_body(source, ref)
        self.assertEqual(Pose(-1, -.5, 0), body.start)
        self.assertAlmostEqual(2.5, body.end.x)
        self.assertAlmostEqual(1, body.end.y)
        self.assertAlmostEqual(math.sqrt(7.25), body.centre_orbit_radius_m)
        self.assertAlmostEqual(math.sqrt(2), body.reference_pose_at(.5).x)
        self.assertAlmostEqual(2-math.sqrt(2), body.reference_pose_at(.5).y)

    def test_reference_axis_pivot_moves_centre_about_fixed_reference(self):
        ref = reference_metadata(1000, 0, 'reference_point')
        source = Motion('pivot', Pose(0, 0, 0), Pose(0, 0, math.pi/2), 0, 1, math.pi/2)
        body = reference_motion_to_body(source, ref)
        self.assertEqual(Pose(-1, 0, 0), body.start)
        self.assertAlmostEqual(0, body.end.x)
        self.assertAlmostEqual(-1, body.end.y)
        self.assertAlmostEqual(-math.sqrt(.5), body.pose_at(.5).x)
        self.assertAlmostEqual(-math.sqrt(.5), body.pose_at(.5).y)
        self.assertEqual(0, body.length_m)
        self.assertAlmostEqual(math.pi/2, body.body_length_m)
        for f in (0, .1, .5, .9, 1):
            self.assertAlmostEqual(0, body.reference_pose_at(f).x)
            self.assertAlmostEqual(0, body.reference_pose_at(f).y)
        path = Trajectory((body,), 2, True)
        self.assertEqual(path, trajectory_from_dict(path.to_dict()))

    def test_body_axis_pivot_is_stationary_and_has_rotating_reference(self):
        result = plan([(0, 0), (1, 0), (1, 1)], pivot_allowed=True,
                      reference_longitudinal_mm=200, reference_lateral_mm=100)
        pivot = next(m for m in result.motions if m.kind == 'pivot')
        self.assertEqual((1, 0), (pivot.start.x, pivot.start.y))
        self.assertEqual((1, 0), (pivot.end.x, pivot.end.y))
        self.assertEqual(0, pivot.body_length_m)
        self.assertAlmostEqual(1.2, pivot.reference_pose_at(0).x)
        self.assertAlmostEqual(.9, pivot.reference_pose_at(1).x)
        self.assertAlmostEqual(.2, pivot.reference_pose_at(1).y)

    def test_reference_axis_internal_fallback_is_real_movement(self):
        result = plan([(0, 0), (1, 0), (1, 1)], pivot_allowed=True,
                      reference_longitudinal_mm=200, reference_lateral_mm=100,
                      pivot_axis='reference_point')
        pivot = next(m for m in result.motions if m.kind == 'pivot')
        self.assertAlmostEqual(.7, pivot.start.x)
        self.assertAlmostEqual(0, pivot.start.y)
        self.assertAlmostEqual(1, pivot.end.x)
        self.assertAlmostEqual(-.1, pivot.end.y)
        self.assertAlmostEqual(math.hypot(.2, .1), pivot.centre_orbit_radius_m)
        self.assertEqual((0, 0), (result.motions[0].start.x, result.motions[0].start.y))
        self.assertEqual((1, 1), (result.motions[-1].end.x, result.motions[-1].end.y))

    def test_initial_centre_pivot_keeps_initial_graph_anchor(self):
        result = plan([(0, 0), (4, 0)], pivot_allowed=True, start_heading_deg=90)
        pivot = result.motions[0]
        self.assertEqual('pivot', pivot.kind)
        self.assertEqual((0, 0), (pivot.start.x, pivot.start.y))
        self.assertEqual((0, 0), (pivot.end.x, pivot.end.y))
        self.assertEqual((4, 0), (result.motions[-1].end.x, result.motions[-1].end.y))

    def test_initial_reference_pivot_does_not_fabricate_a_connector(self):
        with self.assertRaisesRegex(TrajectoryError, 'connector manoeuvre'):
            plan([(0, 0), (4, 0)], pivot_allowed=True, start_heading_deg=90,
                 pivot_axis='reference_point')

    def test_offset_arc_cannot_bypass_physical_in_place_pivot_permission(self):
        # Forward left rref2 with reference2m to body's right: centre is the
        # fixed circle centre, while the reference follows a real radius2 arc.
        with self.assertRaisesRegex(TrajectoryError, 'requires pivot permission'):
            plan([(0, 0), (6, 0), (6, 6)], reference_longitudinal_mm=0,
                 reference_lateral_mm=-2000, pivot_allowed=False)
        result = plan([(0, 0), (6, 0), (6, 6)], reference_longitudinal_mm=0,
                      reference_lateral_mm=-2000, pivot_allowed=True)
        arc = result.motions[1]
        self.assertEqual('arc', arc.kind)
        self.assertAlmostEqual(0, arc.centre_orbit_radius_m)
        self.assertAlmostEqual(0, arc.body_length_m)
        self.assertAlmostEqual(math.pi, arc.length_m)
        self.assertAlmostEqual(6, arc.pose_at(.5).x)
        self.assertAlmostEqual(0, arc.pose_at(.5).y)
        self.assertAlmostEqual(math.pi/4, arc.pose_at(.5).heading)
        data = result.to_dict()
        data['pivot_allowed'] = False
        with self.assertRaisesRegex(TrajectoryError, 'requires pivot permission'):
            trajectory_from_dict(data)

    def test_parallel_displaced_reversal_rejects_missing_connector(self):
        with self.assertRaisesRegex(TrajectoryError, 'connector'):
            plan([(0, 0), (4, 0), (0, 0)], pivot_allowed=True, pivot_axis='reference_point')
        result = plan([(0, 0), (4, 0), (0, 0)], pivot_allowed=True, pivot_axis='body_centre')
        self.assertEqual('pivot', result.motions[1].kind)

    def test_lateral_translation_keeps_heading_and_reference_offset(self):
        result = plan_reference_lateral_trajectory(Pose(0, 0, 0), (0, 2),
                    reference_longitudinal_mm=1000, reference_lateral_mm=500,
                    pivot_axis='body_centre', speed_m_per_sec=1, lateral_allowed=True)
        motion = result.motions[0]
        self.assertEqual(Pose(0, 1, 0), motion.pose_at(.5))
        self.assertEqual(Pose(1, 1.5, 0), motion.reference_pose_at(.5))
        self.assertEqual(2, motion.body_length_m)
        self.assertEqual(result, trajectory_from_dict(result.to_dict()))

    def test_zero_offsets_preserve_exact_legacy_evidence_and_timing(self):
        points = [(0, 0), (6, 0), (6, 6)]
        kwargs = dict(minimum_radius_m=2, speed_m_per_sec=1, pivot_allowed=True, pivot_speed_deg_per_sec=90)
        for movement, planner in (('forward', plan_trajectory), ('reverse', plan_reverse_trajectory)):
            expected = planner(points, **kwargs)
            result = plan(points, reference_longitudinal_mm=0, reference_lateral_mm=0,
                          movement=movement, **kwargs)
            self.assertEqual(expected.to_dict(), result.to_dict())
            self.assertNotIn('reference', result.to_dict()['motions'][0])
        expected = plan_lateral_trajectory(Pose(0, 0, 0), (0, 2), speed_m_per_sec=1, lateral_allowed=True)
        actual = plan_reference_lateral_trajectory(Pose(0, 0, 0), (0, 2), speed_m_per_sec=1,
                    lateral_allowed=True, reference_longitudinal_mm=0, reference_lateral_mm=0,
                    pivot_axis='body_centre')
        self.assertEqual(expected.to_dict(), actual.to_dict())

    def test_bad_metadata_and_corrupt_evidence_are_rejected(self):
        for change in ({'reference_longitudinal_mm': math.nan}, {'reference_lateral_mm': True},
                       {'pivot_axis': None}, {'movement': 'diagonal'}):
            with self.assertRaises(TrajectoryError):
                plan([(0, 0), (4, 0)], **change)
        data = plan([(0, 0), (6, 0), (6, 6)]).to_dict()
        self.assertEqual((3, 'reference_offset_v1'), (data['schema_version'], data['model']))
        for change in ('offset', 'radius', 'centre', 'endpoint', 'missing', 'timing'):
            bad = copy.deepcopy(data)
            row = bad['motions'][1]
            if change == 'offset': row['reference']['longitudinal_mm'] += 1
            elif change == 'radius': row['radius_m'] += .5
            elif change == 'centre': row['centre'] = (99, 99)
            elif change == 'endpoint': row['end']['x'] += .5
            elif change == 'missing': del row['reference']
            else: row['reference']['timing_reference'] = 'body_centre'
            with self.subTest(change=change), self.assertRaisesRegex(TrajectoryError, 'invalid_evidence'):
                trajectory_from_dict(bad)

    def test_reference_semantics_cannot_be_disguised_as_legacy_evidence(self):
        data = plan([(0, 0), (4, 0)]).to_dict()
        data['schema_version'], data['model'] = 1, 'forward_fillet_v1'
        with self.assertRaisesRegex(TrajectoryError, 'Reference metadata requires'):
            trajectory_from_dict(data)

    def test_body_pivot_rejects_ignored_malformed_or_inconsistent_centre(self):
        data = plan([(0, 0), (1, 0), (1, 1)], pivot_allowed=True,
                    reference_longitudinal_mm=200, reference_lateral_mm=100).to_dict()
        index = next(i for i, row in enumerate(data['motions']) if row['kind'] == 'pivot')
        for centre in ([math.nan, 0], [math.inf, 0], [True, 0], [1], [1, 0, 0],
                       [99, 0], ['1', 0], {}, None):
            bad = copy.deepcopy(data)
            bad['motions'][index]['centre'] = centre
            with self.subTest(centre=centre), self.assertRaisesRegex(TrajectoryError, 'invalid_evidence'):
                trajectory_from_dict(bad)
        # Explicitly recording the actual fixed centre is unambiguous and valid.
        data['motions'][index]['centre'] = [1, 0]
        pivot = trajectory_from_dict(data).motions[index]
        self.assertEqual((1, 0), (pivot.pose_at(.5).x, pivot.pose_at(.5).y))

    def test_reference_evidence_rejects_boolean_dimensions_and_stray_line_orbit(self):
        data = plan([(0, 0), (4, 0)]).to_dict()
        for key, value in (('centre', [0, 0]), ('radius_m', .1), ('radius_m', False),
                           ('radius_m', '0'), ('sweep_rad', False), ('length_m', True),
                           ('duration_sec', True)):
            bad = copy.deepcopy(data)
            bad['motions'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(TrajectoryError, 'invalid_evidence'):
                trajectory_from_dict(bad)
        for key in ('length_m', 'duration_sec', 'minimum_radius_m'):
            bad = copy.deepcopy(data)
            bad[key] = True
            with self.subTest(key=key), self.assertRaisesRegex(TrajectoryError, 'invalid_evidence'):
                trajectory_from_dict(bad)

    def test_multiple_left_right_corners_preserve_endpoints_and_reference_radius(self):
        # Long segments isolate the geometry from fit fallback. Both body axes
        # and signs of offsets are exercised, for forward and reverse travel.
        points = [(0, 0), (10, 0), (10, 10), (20, 10), (20, 0)]
        count = 0
        for longitudinal in (-1000, 0, 1000):
            for lateral in (-500, 0, 500):
                for movement in ('forward', 'reverse'):
                    if longitudinal == lateral == 0:
                        continue
                    count += 1
                    result = plan(points, reference_longitudinal_mm=longitudinal,
                                  reference_lateral_mm=lateral, movement=movement)
                    self.assertEqual((0, 0), (result.motions[0].start.x, result.motions[0].start.y))
                    self.assertEqual((20, 0), (result.motions[-1].end.x, result.motions[-1].end.y))
                    self.assertEqual(3, sum(m.kind == 'arc' for m in result.motions))
                    for motion in result.motions:
                        if motion.kind == 'arc':
                            self.assertEqual(2, motion.radius_m)
                            for f in (0, .3, 1):
                                r = motion.reference_pose_at(f)
                                self.assertAlmostEqual(2, math.hypot(r.x-motion.centre[0], r.y-motion.centre[1]))
                    self.assertEqual(result, trajectory_from_dict(result.to_dict()))
        self.assertEqual(16, count)

    def test_actual_offset_sweep_is_used_for_static_clearance(self):
        ref = reference_metadata(1000, 500, 'reference_point')
        body = reference_motion_to_body(Motion('arc', Pose(0, 0, 0), Pose(2, 2, math.pi/2),
                        math.pi, math.pi, math.pi/2, 2, (0, 2)), ref)
        middle = body.pose_at(.5)
        obstacle = (middle.x-.01, middle.y-.01, middle.x+.01, middle.y+.01)
        result = check_clearance(Trajectory((body,), 2, False), length_m=.1, width_m=.1,
                                  obstacles=[obstacle])
        self.assertEqual('collision', result['status'])


if __name__ == '__main__':
    unittest.main()
