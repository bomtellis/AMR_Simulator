import math
import unittest

from amr_trajectories import plan_trajectory, check_clearance, TrajectoryError


def plan(points, **changes):
    options = dict(minimum_radius_m=2, speed_m_per_sec=2, pivot_allowed=False, pivot_speed_deg_per_sec=45)
    options.update(changes)
    return plan_trajectory(points, **options)


class TrajectoryTests(unittest.TestCase):
    def test_straight_three_four_five(self):
        path = plan([(0,0), (3,4)])
        self.assertEqual(5, path.length_m)
        self.assertEqual(2.5, path.duration_sec)
        self.assertEqual((3,4), (path.motions[-1].end.x, path.motions[-1].end.y))

    def test_quarter_circle_has_exact_length_tangents_and_radius(self):
        path = plan([(0,0), (6,0), (6,6)])
        self.assertEqual(['line', 'arc', 'line'], [m.kind for m in path.motions])
        self.assertAlmostEqual(8 + math.pi, path.length_m)
        self.assertAlmostEqual(4 + math.pi/2, path.duration_sec)
        arc = path.motions[1]
        self.assertAlmostEqual(4, arc.start.x)
        self.assertAlmostEqual(0, arc.start.y)
        self.assertAlmostEqual(6, arc.end.x)
        self.assertAlmostEqual(2, arc.end.y)
        for f in (0, .1, .5, .9, 1):
            pose = arc.pose_at(f)
            self.assertAlmostEqual(2, math.hypot(pose.x-4, pose.y-2))
            self.assertAlmostEqual(math.pi/2*f, pose.heading)

    def test_right_turn_mirrors_left_turn(self):
        left, right = plan([(0,0), (6,0), (6,6)]), plan([(0,0), (6,0), (6,-6)])
        self.assertAlmostEqual(left.length_m, right.length_m)
        for a,b in zip(left.poses(), right.poses()):
            self.assertAlmostEqual(a.x, b.x)
            self.assertAlmostEqual(a.y, -b.y)
            self.assertAlmostEqual(a.heading, -b.heading)

    def test_short_segments_do_not_shrink_radius_or_fabricate_path(self):
        with self.assertRaisesRegex(TrajectoryError, 'infeasible_route'):
            plan([(0,0), (1,0), (1,1)])
        with self.assertRaisesRegex(TrajectoryError, 'infeasible_route'):
            plan([(0,0), (6,0), (6,3), (12,3)])  # two 2m trims need 4m

    def test_explicit_pivot_has_rotation_time_and_zero_distance(self):
        path = plan([(0,0), (1,0), (1,1)], pivot_allowed=True)
        self.assertEqual(['line','pivot','line'], [m.kind for m in path.motions])
        self.assertAlmostEqual(2, path.length_m)
        self.assertAlmostEqual(3, path.duration_sec)  # 2m/2m/s + 90deg/45deg/s
        pivot = path.motions[1]
        self.assertEqual(0, pivot.length_m)
        self.assertAlmostEqual(math.pi/4, pivot.pose_at(.5).heading)

    def test_uturn_requires_explicit_pivot_permission(self):
        with self.assertRaisesRegex(TrajectoryError, 'infeasible_route'):
            plan([(0,0), (2,0), (0,0)])
        path = plan([(0,0), (2,0), (0,0)], pivot_allowed=True)
        self.assertAlmostEqual(6, path.duration_sec)  # travel 2s, pivot 4s

    def test_straight_loaded_opening_exact_fit_and_just_fail(self):
        path = plan([(0,0), (6,0)])
        walls = [(2,-3,2.2,-.5), (2,.5,2.2,3)]
        for width, expected in [(1, 'clear'), (1.00001, 'collision')]:
            self.assertEqual(expected, check_clearance(path, length_m=2, width_m=width, obstacles=walls)['status'])
        self.assertEqual('clear', check_clearance(path, length_m=2, width_m=.8, clearance_m=.1, obstacles=walls)['status'])
        self.assertEqual('collision', check_clearance(path, length_m=2, width_m=.8, clearance_m=.10001, obstacles=walls)['status'])

    def test_line_swept_hull_catches_thin_wall_between_endpoints(self):
        path = plan([(0,0), (100,0)])
        self.assertEqual('collision', check_clearance(path, length_m=1, width_m=1, obstacles=[(49.999,-1,50.001,1)])['status'])

    def test_pivot_checks_rotating_corners_not_only_endpoints(self):
        path = plan([(0,0), (1,0), (1,1)], pivot_allowed=True)
        # A long thin robot is clear at 0/90 degrees but clips at 45 degrees.
        result = check_clearance(path, length_m=2, width_m=.2, obstacles=[(1.6,.6,1.7,.7)])
        self.assertEqual('collision', result['status'])
        self.assertEqual(1, result['motion'])

    def test_curved_sweep_can_be_certified_clear(self):
        path = plan([(0,0), (6,0), (6,6)])
        result = check_clearance(path, length_m=1.2, width_m=.8, obstacles=[(2,2,3,3), (7,0,8,6)])
        self.assertEqual('clear', result['status'])

    def test_limits_and_uncertain_clearance_are_not_clear(self):
        path = plan([(0,0), (1,0), (1,1)], pivot_allowed=True)
        result = check_clearance(path, length_m=2, width_m=.2, obstacles=[(1.9,.4,2,.5)], max_checks=1)
        self.assertEqual('search_limit', result['status'])
        result = check_clearance(path, length_m=2, width_m=.2, obstacles=[(2,.11,2.1,.12)], resolution_m=10)
        self.assertEqual('clearance_unresolved', result['status'])

    def test_invalid_input_rejects_instead_of_fallback(self):
        for points in ([(0,0)], [(0,0),(0,0)], [(0,0),(float('nan'),1)]):
            with self.assertRaisesRegex(TrajectoryError, 'invalid_input'):
                plan(points)
        for changes in ({'minimum_radius_m': 0}, {'speed_m_per_sec': -1}, {'pivot_allowed':'false'}, {'pivot_speed_deg_per_sec': 0}):
            with self.assertRaisesRegex(TrajectoryError, 'invalid_input'):
                plan([(0,0),(1,0)], **changes)

    def test_export_retains_exact_motion_geometry(self):
        path = plan([(0,0), (6,0), (6,6)])
        exported = path.to_dict()
        self.assertEqual('forward_fillet_v1', exported['model'])
        self.assertAlmostEqual(math.pi, exported['motions'][1]['length_m'])
        self.assertAlmostEqual(path.duration_sec, sum(m['duration_sec'] for m in exported['motions']))


if __name__ == '__main__':
    unittest.main()
