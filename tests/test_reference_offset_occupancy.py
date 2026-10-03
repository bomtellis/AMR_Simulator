"""Independent body-centre occupancy references for offset turning points."""
import math
import unittest

from amr_geometric_occupancy import stationary_claim
from amr_geometric_traffic import first_traffic_slot, swept_cells
from amr_occupancy_plan import occupancy_plan
from amr_trajectories import Motion, Pose, Trajectory, TrajectoryError, trajectory_from_dict


def reference(longitudinal=1000, lateral=500, pivot_axis='reference_point'):
    return dict(longitudinal_mm=longitudinal, lateral_mm=lateral,
                timing_reference='turning_reference_point', pivot_axis=pivot_axis)


def offset_arc(*, reverse=False, duration=.25):
    # Reference curve R(theta)=(2sin(theta), 2-2cos(theta)), 0<=theta<=pi/2.
    # Body C=R-Rot(body_heading)*(1,.5), with body_heading=theta(+pi reverse).
    if reverse:
        start, end = Pose(1, .5, math.pi), Pose(1.5, 3, 3*math.pi/2)
    else:
        start, end = Pose(-1, -.5, 0), Pose(2.5, 1, math.pi/2)
    motion = Motion('arc', start, end, math.pi, duration, math.pi/2, 2, (0, 2),
                    movement='reverse' if reverse else 'forward', reference=reference())
    return Trajectory((motion,), 2, True)


def independently_rotated_rectangle(x, y, heading, half_length, half_width):
    c, s = math.cos(heading), math.sin(heading)
    return [(x+dx*c-dy*s, y+dx*s+dy*c)
            for dx, dy in ((-half_length, -half_width), (half_length, -half_width),
                           (half_length, half_width), (-half_length, half_width))]


class ReferenceOffsetOccupancyTests(unittest.TestCase):
    def assert_polygon(self, expected, actual):
        self.assertEqual(len(expected), len(actual))
        for a, b in zip(expected, actual):
            self.assertAlmostEqual(a[0], b[0])
            self.assertAlmostEqual(a[1], b[1])

    def test_left_arc_enclosure_uses_body_orbit_not_smaller_reference_radius(self):
        path = offset_arc()
        cell, = swept_cells(path, length_m=1, width_m=.5, clearance_m=0)
        body_orbit = math.sqrt(7.25)  # body start(-1,-.5) relative to centre(0,2)
        self.assertAlmostEqual(body_orbit, path.motions[0].centre_orbit_radius_m)
        theta = math.pi/4
        x = 2*math.sin(theta)-math.cos(theta)+.5*math.sin(theta)
        y = 2-2*math.cos(theta)-math.sin(theta)-.5*math.cos(theta)
        inflation = 2*(body_orbit+math.hypot(.5,.25))*math.sin(math.pi/8)
        expected = independently_rotated_rectangle(x, y, theta, .5+inflation, .25+inflation)
        self.assert_polygon(expected, cell['polygon'])
        self.assertAlmostEqual(math.pi, path.length_m)  # explicitly reference travel metric
        self.assertAlmostEqual(body_orbit*math.pi/2, path.motions[0].body_length_m)

    def test_reverse_arc_enclosure_uses_its_different_body_orbit(self):
        path = trajectory_from_dict(offset_arc(reverse=True).to_dict())
        motion = path.motions[0]
        self.assertAlmostEqual(math.sqrt(3.25), motion.centre_orbit_radius_m)
        cell, = swept_cells(path, length_m=1, width_m=.5, clearance_m=0)
        theta, heading = math.pi/4, 5*math.pi/4
        x = 2*math.sin(theta)-math.cos(heading)+.5*math.sin(heading)
        y = 2-2*math.cos(theta)-math.sin(heading)-.5*math.cos(heading)
        inflation = 2*(math.sqrt(3.25)+math.hypot(.5,.25))*math.sin(math.pi/8)
        self.assert_polygon(independently_rotated_rectangle(x, y, heading, .5+inflation, .25+inflation), cell['polygon'])

    def test_large_offset_continuous_bound_encloses_all_independent_footprint_corners(self):
        # A long offset deliberately makes the old radius2-based bound too small.
        # The analytic chord bound proves coverage; sampled independent corners
        # additionally catch a wrong pose frame or sign in the implementation.
        path = Trajectory((Motion('arc', Pose(-20,0,0), Pose(2,-18,math.pi/2),
            math.pi,.25,math.pi/2,2,(0,2),reference=reference(20000,0)),),2,True)
        cell, = swept_cells(path,length_m=1,width_m=.5,clearance_m=0)
        orbit = math.sqrt(404)
        inflation = 2*(orbit+math.hypot(.5,.25))*math.sin(math.pi/8)
        mid = math.pi/4
        centre_x,centre_y = 2*math.sin(mid)-20*math.cos(mid), 2-2*math.cos(mid)-20*math.sin(mid)
        self.assert_polygon(independently_rotated_rectangle(centre_x,centre_y,mid,.5+inflation,.25+inflation),cell['polygon'])
        for index in range(65):
            theta = math.pi/2*index/64
            x,y = 2*math.sin(theta)-20*math.cos(theta),2-2*math.cos(theta)-20*math.sin(theta)
            for px,py in independently_rotated_rectangle(x,y,theta,.5,.25):
                along = (px-centre_x)*math.cos(mid)+(py-centre_y)*math.sin(mid)
                across = -(px-centre_x)*math.sin(mid)+(py-centre_y)*math.cos(mid)
                self.assertLessEqual(abs(along),.5+inflation+1e-10)
                self.assertLessEqual(abs(across),.25+inflation+1e-10)

    def test_reference_axis_pivot_reserves_translating_body_and_keeps_reference_fixed(self):
        motion = Motion('pivot',Pose(-1,0,0),Pose(0,-1,math.pi/2),0,.25,math.pi/2,
                        0,(0,0),reference=reference(1000,0))
        path = trajectory_from_dict(Trajectory((motion,),2,True).to_dict())
        decoded = path.motions[0]
        self.assertEqual(0,decoded.length_m)
        self.assertAlmostEqual(1,decoded.centre_orbit_radius_m)
        self.assertAlmostEqual(math.pi/2,decoded.body_length_m)
        for fraction in (0,.25,.5,.75,1):
            pose = decoded.reference_pose_at(fraction)
            self.assertAlmostEqual(0,pose.x)
            self.assertAlmostEqual(0,pose.y)
        cell, = swept_cells(path,length_m=1,width_m=.5,clearance_m=0)
        inflation = 2*(1+math.hypot(.5,.25))*math.sin(math.pi/8)
        expected = independently_rotated_rectangle(-math.sqrt(.5),-math.sqrt(.5),math.pi/4,
                                                    .5+inflation,.25+inflation)
        self.assert_polygon(expected,cell['polygon'])
        # At t=.24 the body lies around (−.063,−.998), so a tiny probe at
        # (0,-1) must not be admitted through the reference pivot's body sweep.
        probe = stationary_claim(Pose(0,-1,0),start=0,end=.001,owner='probe',length_m=.01,width_m=.01)
        slot,owners = first_traffic_slot([{**cell,'owner':'turning'}],[probe],.24,'probe',0)
        self.assertGreater(slot,.24)
        self.assertEqual(['turning'],owners)

    def test_zero_offset_matches_existing_arc_cells_exactly(self):
        plain = Motion('arc',Pose(0,0,0),Pose(2,2,math.pi/2),math.pi,.25,math.pi/2,2,(0,2))
        explicit = Motion('arc',plain.start,plain.end,plain.length_m,plain.duration_sec,
                          plain.sweep_rad,plain.radius_m,plain.centre,reference=reference(0,0))
        kwargs = dict(length_m=1,width_m=.7,clearance_m=.1)
        self.assertEqual(swept_cells(Trajectory((plain,),2,True),**kwargs),
                         swept_cells(Trajectory((explicit,),2,True),**kwargs))

    def test_decoded_loaded_occupancy_and_terminal_are_centred_on_body_not_reference(self):
        path = offset_arc()
        motion = path.motions[0]
        segment = dict(type='corridor',duration=.25,distance_m=math.pi,
                       motion_model='geometric_v1',trajectory=path.to_dict())
        claims = occupancy_plan(initial_pose=motion.start,floor=0,start=5,owner='R',
            robot_length_m=1,robot_width_m=.6,loaded_length_m=2,loaded_width_m=.8,
            robot_clearance_m=.1,segments=[segment,dict(type='dropoff',duration=0)],initial_loaded=True)
        moving,instant,tail = claims
        self.assertEqual((5,5.25),(moving['start'],moving['end']))
        self.assertEqual('instantaneous',instant['occupancy_kind'])
        self.assertEqual((5.25,5.25),(instant['start'],instant['end']))
        for observed,expected in zip(instant['envelope'],(2.1,0,2.9,2)):
            self.assertAlmostEqual(expected,observed)
        for observed,expected in zip(tail['envelope'],(2.2,.5,2.8,1.5)):
            self.assertAlmostEqual(expected,observed)
        self.assertEqual(motion.end,tail['pose'])
        self.assertEqual(math.inf,tail['end'])
        self.assertFalse(tail['loaded'])
        with self.assertRaises(TrajectoryError):
            occupancy_plan(initial_pose=Pose(0,0,0),floor=0,start=5,owner='R',
                robot_length_m=1,robot_width_m=.6,loaded_length_m=2,loaded_width_m=.8,
                robot_clearance_m=.1,segments=[segment],initial_loaded=True)


if __name__=='__main__': unittest.main()
