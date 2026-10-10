"""Independent lane lengths, opposing/crossing movements and bounded claims."""
import contextlib
import csv
import copy
import io
import json
import math
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from amr_geometric_traffic import lane_trajectory, swept_cells, first_traffic_slot
from amr_trajectories import plan_trajectory, trajectory_from_dict, TrajectoryError, footprint
from amr_route_reservations import RouteReservationTransaction
from simulator import Simulation
from tests.test_geometric_simulation import geometric_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from amr_sim_visualiser_pyside6 import SimulationLog, LayoutModel


def traffic_config(width=4):
    config = geometric_config()
    config['locations'][1].update(x=20,y=0)
    config['corridors'] = {'auto_connect':False,'nodes':[],
        'edges':[{'from':'A','to':'B','width_m':width,'bidirectional':True}]}
    config['geometry'] = {'schema_version':1,'traffic_model':'keep_right_v1',
        'floors':[{'floor':0,'bounds':[-5,-5,25,5],'obstacles':[]}]}
    config['building']['node_clearance_time_sec'] = 0
    config['amrs'][0]['manoeuvring']['clearance_m'] = 0
    return config


def reserve_rows(cells,owner,start=0):
    return [{**cell,'start':start+cell['start'],'end':start+cell['end'],'owner':owner} for cell in cells]


class GeometricTrafficTests(unittest.TestCase):
    def route(self,sim,robot=0,start='A',end='B',time=0):
        return sim._same_floor_segments(sim.amrs[robot],sim.locations[start],sim.locations[end],
            start_time_value=time,payload=sim.payloads['Box'])

    def test_tangent_lane_changes_have_independent_length_and_right_side(self):
        sim = Simulation(traffic_config())
        segments,duration,distance = self.route(sim)
        trajectory = trajectory_from_dict(segments[0]['trajectory'])
        angle = math.acos(.75)  # offset 1 m = 2R(1-cos(theta)), R=2 m
        expected = 20-8*math.sin(angle)+8*angle
        self.assertAlmostEqual(expected,distance)
        self.assertAlmostEqual(expected/2,duration)
        self.assertAlmostEqual(-1,trajectory.pose_at_time(duration/2).y)
        self.assertAlmostEqual(10,trajectory.pose_at_time(duration/2).x)
        self.assertAlmostEqual(0,trajectory.motions[-1].end.y)
        self.assertTrue(all(m.radius_m >= 2 for m in trajectory.motions if m.kind=='arc'))
        self.assertEqual('keep_right',segments[0]['lane_sections'][0]['mode'])

    def test_opposing_wide_corridor_moving_claims_fit_on_right_lanes(self):
        config = traffic_config()
        sim = Simulation(config)
        first,duration,_ = self.route(sim)
        sim.amrs[0].rotation_deg = 180
        second,other_duration,_ = self.route(sim,0,'B','A')
        # This is the moving-claim component: parked endpoints are separately
        # enforced by the full-plan integration acceptance tests.
        ready,_ = first_traffic_slot(reserve_rows(first[0]['traffic_cells'],'opposing'),
                                     second[0]['traffic_cells'],0,sim.amrs[0].id,0)
        self.assertEqual(0,ready)
        self.assertAlmostEqual(duration,other_duration)
        self.assertFalse(any(s['type'].startswith('wait') for s in second))
        a,b = [trajectory_from_dict(s[0]['trajectory']) for s in (first,second)]
        self.assertAlmostEqual(-1,a.pose_at_time(duration/2).y)
        self.assertAlmostEqual(1,b.pose_at_time(duration/2).y)
        # Independent sufficient bound: centre distance exceeds summed body radii.
        for i in range(401):
            pa,pb = a.pose_at_time(duration*i/400),b.pose_at_time(duration*i/400)
            self.assertGreater(math.hypot(pa.x-pb.x,pa.y-pb.y),math.hypot(1,.7))

    def test_narrow_opposing_moving_claims_are_serialised(self):
        config = traffic_config(width=1)
        sim = Simulation(config)
        first,duration,_ = self.route(sim)
        sim.amrs[0].rotation_deg = 180
        second,total,_ = self.route(sim,0,'B','A')
        ready,blockers = first_traffic_slot(reserve_rows(first[0]['traffic_cells'],'opposing'),
                                           second[0]['traffic_cells'],0,sim.amrs[0].id,0)
        self.assertEqual('single_file',first[0]['lane_sections'][0]['mode'])
        self.assertGreaterEqual(ready,duration)
        self.assertEqual(['opposing'],blockers)
        self.assertAlmostEqual(10,total)

    def test_crossing_paths_reserve_junction_only_while_occupied(self):
        paths = [plan_trajectory(points,minimum_radius_m=2,speed_m_per_sec=2,
            pivot_allowed=False,pivot_speed_deg_per_sec=45) for points in
            ([(-10,0),(10,0)],[(0,-10),(0,10)])]
        cells = [swept_cells(t,length_m=1,width_m=.6,clearance_m=0) for t in paths]
        rows = reserve_rows(cells[0],'horizontal')
        start,blockers = first_traffic_slot(rows,cells[1],0,'vertical',0)
        # Four 0.25s occupied crossing cells form a one-second exclusion window.
        self.assertAlmostEqual(1,start)
        self.assertEqual(['horizontal'],blockers)
        self.assertLess(start,paths[0].duration_sec)
        for i in range(1001):
            t = start+(10-start)*i/1000
            h,v = paths[0].pose_at_time(t),paths[1].pose_at_time(t-start)
            self.assertTrue(abs(h.x-v.x)>=.8-1e-8 or abs(h.y-v.y)>=.8-1e-8)
        self.assertEqual((11,[]),first_traffic_slot(rows,cells[1],11,'vertical',0))

    def test_same_direction_following_waits_for_footprint_not_whole_route(self):
        trajectory = plan_trajectory([(0,0),(20,0)],minimum_radius_m=2,speed_m_per_sec=2,
                                    pivot_allowed=False,pivot_speed_deg_per_sec=45)
        cells = swept_cells(trajectory,length_m=1,width_m=.6,clearance_m=0)
        rows = reserve_rows(cells,'lead')
        start,_ = first_traffic_slot(rows,cells,0,'following',0)
        self.assertAlmostEqual(.75,start)  # 0.5s body clearance plus one conservative 0.25s cell
        self.assertEqual((0,[]),first_traffic_slot(rows,cells,0,'lead',0))

    def test_cells_enclose_arc_and_pivot_and_limits_are_explicit(self):
        sim = Simulation(traffic_config())
        sim.amrs[0].rotation_deg = 180
        segments,_,_ = self.route(sim)
        trajectory = trajectory_from_dict(segments[0]['trajectory'])
        with self.assertRaisesRegex(TrajectoryError,'search_limit'):
            swept_cells(trajectory,length_m=1,width_m=.7,clearance_m=0,max_cells=1)
        cells = segments[0]['traffic_cells']
        for cell in cells:
            polygon = cell['polygon']
            for fraction in (0,.2,.5,.8,1):
                pose = trajectory.pose_at_time(cell['start']+fraction*(cell['end']-cell['start']))
                for x,y in footprint(pose,1,.7,0):
                    for p,q in zip(polygon,polygon[1:]+polygon[:1]):
                        self.assertGreaterEqual((q[0]-p[0])*(y-p[1])-(q[1]-p[1])*(x-p[0]),-1e-8)
        before = copy.deepcopy(cells)
        with self.assertRaisesRegex(TrajectoryError,'search_limit'):
            first_traffic_slot(reserve_rows(cells,'other'),cells,0,'me',0,max_pair_checks=1)
        self.assertEqual(before,cells)

    def test_two_lane_fit_uses_loaded_width_and_clearance_at_boundary(self):
        for load_width,expected_mode in ((.7,'keep_right'),(.70001,'single_file')):
            config = traffic_config(width=1.6)
            config['amrs'][0]['manoeuvring']['clearance_m'] = .05
            config['payloads'][0]['width_m'] = load_width
            sim = Simulation(config)
            segments,_,_ = self.route(sim)
            self.assertEqual(expected_mode,segments[0]['lane_sections'][0]['mode'])

    def test_corner_keeps_junction_radius_and_continuous_lane_approaches(self):
        config = traffic_config()
        config['locations'][1].update(x=20,y=20)
        config['geometry']['floors'][0]['bounds'] = [-5,-5,25,25]
        config['corridors']['nodes'] = [dict(name='J',floor=0,x=20,y=0)]
        config['corridors']['edges'] = [dict(a,**{'width_m':4}) for a in
            ({'from':'A','to':'J'},{'from':'J','to':'B'})]
        sim = Simulation(config)
        segments,_,_ = self.route(sim)
        trajectory = trajectory_from_dict(segments[0]['trajectory'])
        corner = next(m for m in trajectory.motions if m.kind=='arc' and abs(m.sweep_rad-math.pi/2)<1e-9)
        self.assertAlmostEqual(2,corner.radius_m)
        self.assertAlmostEqual(18,corner.start.x)
        self.assertAlmostEqual(0,corner.start.y)
        self.assertAlmostEqual(20,corner.end.x)
        self.assertAlmostEqual(2,corner.end.y)
        north_lane = next(m for m in trajectory.motions if m.kind=='line' and abs(m.start.heading-math.pi/2)<1e-9)
        self.assertAlmostEqual(21,north_lane.start.x)  # right of north is east
        self.assertEqual(2,len(segments[0]['lane_sections']))

    def test_time_claims_expire_and_rollback_restores_previous_owner_claims(self):
        sim = Simulation(traffic_config())
        segments,duration,_ = self.route(sim)
        sim._reserve_corridor_segments(sim.amrs[0],segments,0)
        original = copy.deepcopy(sim.geometric_route_reservations)
        with RouteReservationTransaction(sim,sim.amrs[0],[]):
            sim._reserve_corridor_segments(sim.amrs[0],segments,100)
        self.assertEqual(original,sim.geometric_route_reservations)
        sim.current_time = duration+10000
        sim._prune_historical_reservations(sim.current_time)
        self.assertFalse(sim.geometric_route_reservations)

    def test_complete_run_records_lane_path_time_energy_and_curved_playback(self):
        config = traffic_config()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'steps.csv')
            sim = Simulation(config,verbose=True,verbose_csv_path=path)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
                sim.write_verbose_csv()
            angle = math.acos(.75)
            expected_travel = (20-8*math.sin(angle)+8*angle)/2
            self.assertEqual(1,len(sim.completed_task_records))
            self.assertAlmostEqual(4+expected_travel,sim.current_time)
            self.assertAlmostEqual(750*1.035*expected_travel/3600000,sim.amrs[0].total_energy_used_kwh)
            with open(path,newline='',encoding='utf-8-sig') as stream:
                row = next(r for r in csv.DictReader(stream) if r['event_type']=='segment_corridor')
            evidence = json.loads(row['traffic_json'])
            self.assertEqual('swept_time_v1',evidence['reservation_policy'])
            self.assertEqual('keep_right',evidence['lane_sections'][0]['mode'])
            layout,log = LayoutModel(),SimulationLog()
            layout.load_data(config)
            log.load(path,parallel=False)
            state = log.state_at(log.start_time+timedelta(seconds=2+expected_travel/2),layout)[0]['R-1']
            self.assertAlmostEqual(-1,state['y'],delta=.001)
            self.assertAlmostEqual(10,state['x'],delta=.001)

    def test_short_lane_fails_unless_user_models_single_file_section(self):
        config = traffic_config()
        config['locations'][1]['x'] = 2
        sim = Simulation(config,verbose=True)
        with contextlib.redirect_stdout(io.StringIO()): sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertTrue(any('keep-right transitions' in row['details'] for row in sim.verbose_rows))
        config['corridors']['edges'][0]['traffic_mode'] = 'single_file'
        sim = Simulation(config)
        with contextlib.redirect_stdout(io.StringIO()): sim.run()
        self.assertEqual(1,len(sim.completed_task_records))
        self.assertAlmostEqual(5,sim.current_time)  # 2m/2m/s plus four seconds handling

    def test_lane_shift_is_checked_against_real_obstacles(self):
        config = traffic_config()
        config['geometry']['floors'][0]['obstacles'] = [[9,-1.5,11,-.7]]
        sim = Simulation(config,verbose=True)
        with contextlib.redirect_stdout(io.StringIO()): sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertTrue(any(row['status']=='collision' for row in sim.verbose_rows))

    def test_transaction_does_not_publish_partial_geometric_legs(self):
        sim = Simulation(traffic_config())
        with RouteReservationTransaction(sim,sim.amrs[0],[]):
            segments,_,_ = self.route(sim)
            sim._reserve_corridor_segments(sim.amrs[0],segments,0)
            self.assertFalse(sim.geometric_route_reservations)
        self.assertFalse(sim.geometric_route_reservations)

    def test_invalid_traffic_policy_rejected_by_run_editor_and_checks(self):
        for field in ('model','edge'):
            config = traffic_config()
            if field=='model': config['geometry']['traffic_model']='guess'
            else: config['corridors']['edges'][0]['traffic_mode']='left'
            for constructor in (Simulation,JsonStore):
                with self.assertRaises(ValueError): constructor(config)
            self.assertTrue(any(f.code=='GEOMETRY_INPUT' for f in check_project(config).findings))


if __name__ == '__main__': unittest.main()
