import contextlib
import copy
import io
import json
import math
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'visualiser'))
from simulator import Simulation
from amr_sim_models import Task
from amr_trajectories import trajectory_from_dict, TrajectoryError
from amr_route_reservations import RouteReservationTransaction
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from amr_sim_visualiser_pyside6 import SimulationLog, LayoutModel
from tests.test_engineering_reference import reference_config
from amr_geometric_routing import simulation_project_from_study, first_route_slot
from visualiser.geometry_workbench import EXAMPLE
from amr_project import Project
from amr_project_runs import PreparedRun, execute
from visualiser.project_playback_panel import load_playback


def geometric_config():
    config = reference_config()
    config['simulation']['motion_model'] = 'geometric_v1'
    config['simulation']['fast_assignment_estimates'] = True
    config['locations'][1].update(x=6,y=6)
    config['corridors']['nodes'][0].update(x=6,y=0,has_door=False)
    config['amrs'][0]['manoeuvring'] = dict(minimum_radius_m=2,pivot_allowed=True,
        pivot_speed_deg_per_sec=45,clearance_m=.05,initial_heading_deg=0)
    config['geometry'] = {'schema_version':1,'floors':[{'floor':0,'bounds':[-3,-3,9,9],
        'obstacles':[[2,-3,2.3,-.55],[2,.55,2.3,3]]}]}
    config['tasks'] = [dict(id='T',pickup='A',dropoff='B',payload='Box')]
    return config


class GeometricSimulationTests(unittest.TestCase):
    def run_case(self, config=None, path=None):
        sim = Simulation(config or geometric_config(),verbose=True,verbose_csv_path=path)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            if path:
                sim.write_verbose_csv()
        return sim

    def test_actual_completion_energy_and_saved_geometry_use_arc_distance(self):
        config = geometric_config()
        for imported in (False,True):
            sim = self.run_case(JsonStore(config).data if imported else config)
            self.assertEqual(1,len(sim.completed_task_records))
            self.assertFalse(sim.failed_tasks)
            expected = (8+math.pi)/2
            self.assertAlmostEqual(4+expected,sim.current_time)
            row = next(r for r in sim.verbose_rows if r['event_type']=='segment_corridor')
            trajectory = trajectory_from_dict(json.loads(row['trajectory_json']))
            self.assertAlmostEqual(8+math.pi,trajectory.length_m)
            self.assertAlmostEqual(expected,trajectory.duration_sec)
            # 750W * (1 + .35 * 10/100) applied over physical moving duration.
            consumption = sim._initial_battery_energy['R-1'] - sim.amrs[0].battery_energy_kwh()
            self.assertAlmostEqual(750*1.035*expected/3600000,consumption)
            self.assertTrue(row['event_id'])
            self.assertEqual(90,sim.amrs[0].rotation_deg)
            pickup = next(r for r in sim.verbose_rows if r['event_type']=='segment_pickup')
            dropoff = next(r for r in sim.verbose_rows if r['event_type']=='segment_dropoff')
            self.assertEqual(0,pickup['amr_rotation_deg'])
            self.assertEqual(90,dropoff['amr_rotation_deg'])

    def test_legacy_comparison_remains_ten_seconds(self):
        config = geometric_config()
        config['simulation']['motion_model']='legacy'
        sim = self.run_case(config)
        self.assertEqual(10,sim.current_time)
        self.assertFalse(any(r['trajectory_json'] for r in sim.verbose_rows))

    def test_initial_heading_adds_a_real_pivot_and_permission_is_enforced(self):
        config = geometric_config()
        config['amrs'][0]['manoeuvring']['initial_heading_deg'] = 90
        sim = self.run_case(config)
        self.assertAlmostEqual(4+(8+math.pi)/2+2,sim.current_time)
        row = next(r for r in sim.verbose_rows if r['event_type']=='segment_corridor')
        self.assertEqual('pivot',json.loads(row['trajectory_json'])['motions'][0]['kind'])
        config['amrs'][0]['manoeuvring']['pivot_allowed']=False
        sim = self.run_case(config)
        self.assertFalse(sim.completed_task_records)
        reasons = [r.get('details','') for r in sim.verbose_rows]
        self.assertTrue(any('infeasible_route' in str(r) for r in reasons))

    def test_loaded_collision_and_floor_boundary_never_complete(self):
        for change in ('load','boundary'):
            config = geometric_config()
            if change=='load':
                config['payloads'][0]['width_m']=1.01
            else:
                config['geometry']['floors'][0]['bounds']=[-3,-3,6.1,9]
            sim = self.run_case(config)
            self.assertFalse(sim.completed_task_records)
            self.assertFalse(sim.payload_instance_store.records_at('B'))
            self.assertFalse(any(r.get('trajectory_json') for r in sim.verbose_rows))

    def test_profile_denial_cannot_be_bypassed_by_geometry(self):
        config = geometric_config()
        config['route_profiles']={'clean':{'allowed_edges':[['A','Door']]}}
        config['tasks'][0]['route_profile']='clean'
        sim = self.run_case(config)
        self.assertFalse(sim.completed_task_records)

    def test_curve_and_heading_replay_follow_recorded_motion_in_both_seek_directions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'steps.csv')
            sim = self.run_case(path=path)
            log,layout = SimulationLog(),LayoutModel()
            layout.load_data(geometric_config())
            log.load(path,parallel=False)
            # Load 2s, straight 4m/2m/s=2s, then half the quarter turn.
            sec = 4+math.pi/4
            for when in (sec,sec+.2,sec):
                state = log.state_at(log.start_time+timedelta(seconds=when),layout)[0]['R-1']
                angle = (when-4)  # angular speed v/r = 1 rad/s
                self.assertAlmostEqual(4+2*math.sin(angle),state['x'],delta=.001)
                self.assertAlmostEqual(2-2*math.cos(angle),state['y'],delta=.001)
                self.assertAlmostEqual(angle,state['geometry_heading'],delta=.001)
                self.assertNotIn('geometry_error',state)
            evidence=json.loads(Path(path+'.run.json').read_text())
            self.assertIn('geometric_trajectories_v1',evidence['event_capabilities'])

    def test_corrupt_new_geometry_does_not_replay_as_straight_line(self):
        sim=self.run_case()
        row=next(r for r in sim.verbose_rows if r['event_type']=='segment_corridor')
        log=SimulationLog()
        start=sim.clock.start_datetime+timedelta(seconds=2)
        state={'raw':{**row,'trajectory_json':'{}'},'start_time':start,'end_time':start+timedelta(seconds=6)}
        log._refresh_state_position(state,start+timedelta(seconds=3))
        self.assertIsNone(state['x'])
        self.assertIsNone(state['y'])
        self.assertIn('geometry_error',state)

    def test_transaction_rollback_removes_geometric_claim(self):
        sim=Simulation(geometric_config())
        task=Task('T','A','B','Box')
        robot=sim.amrs[0]
        before=copy.deepcopy(vars(robot))
        with RouteReservationTransaction(sim,robot,[task]):
            segments,_,_=sim._same_floor_segments(robot,sim.locations['A'],sim.locations['B'],start_time_value=0,payload=sim.payloads['Box'])
            sim._reserve_corridor_segments(robot,segments,0)
            self.assertTrue(sim.geometric_route_reservations[0])
            robot.rotation_deg=123
        self.assertFalse(sim.geometric_route_reservations)
        self.assertEqual(before,vars(robot))

    def test_intersecting_moving_envelopes_wait_without_mutating_estimates(self):
        config=geometric_config()
        config['amrs'][0]['quantity']=2
        sim=Simulation(config)
        first,second=sim.amrs
        segments,duration,_=sim._same_floor_segments(first,sim.locations['A'],sim.locations['B'],start_time_value=0)
        sim._reserve_corridor_segments(first,segments,0)
        following,total,_=sim._same_floor_segments(second,sim.locations['A'],sim.locations['B'],start_time_value=0)
        self.assertEqual('wait_for_geometry',following[0]['type'])
        self.assertAlmostEqual(duration+sim.node_clearance_time_sec,following[0]['duration'])
        self.assertAlmostEqual(2*duration+sim.node_clearance_time_sec,total)
        self.assertEqual(1,len(sim.geometric_route_reservations[0]))  # read-only estimation

    def test_disjoint_envelopes_remain_concurrent_and_claims_are_owner_aware(self):
        rows=[{'owner':'R-1','start':0,'end':10,'envelope':(0,0,5,5)}]
        self.assertEqual(0,first_route_slot(rows,(10,10,15,15),0,5,'R-2',1))
        self.assertEqual(0,first_route_slot(rows,(0,0,5,5),0,5,'R-1',1))
        self.assertEqual(11,first_route_slot(rows,(0,0,5,5),0,5,'R-2',1))

    def test_return_keeps_final_heading_and_models_its_reorientation(self):
        config=geometric_config()
        config['tasks'][0].update(return_enabled=True,return_payload='Box',return_delay_minutes=0)
        sim=self.run_case(config)
        self.assertEqual(2,len(sim.completed_task_records))
        rows=[r for r in sim.verbose_rows if r['event_type']=='segment_corridor']
        self.assertEqual(2,len(rows))
        outward,back=[trajectory_from_dict(json.loads(row['trajectory_json'])) for row in rows]
        self.assertEqual('pivot',back.motions[0].kind)
        self.assertAlmostEqual(4,back.motions[0].duration_sec)  # north-facing to south-facing
        self.assertAlmostEqual(2*outward.duration_sec+12,sim.current_time)

    def test_zero_length_service_still_checks_loaded_footprint(self):
        config=geometric_config()
        config['tasks'][0]['dropoff']='A'
        config['geometry']['floors'][0]['obstacles'].append([.6,-.2,.8,.2])
        config['payloads'][0]['length_m']=1.8  # unloaded length 1 fits; loaded body overlaps
        sim=self.run_case(config)
        self.assertFalse(sim.completed_task_records)

    def test_exported_study_is_runnable_and_archive_roundtrips_geometry(self):
        before=copy.deepcopy(EXAMPLE)
        config=simulation_project_from_study(EXAMPLE)
        self.assertEqual(before,EXAMPLE)
        sim=self.run_case(config)
        self.assertEqual(1,len(sim.completed_task_records))
        self.assertAlmostEqual(12+math.pi,sim.current_time)  # speed 1 plus 4s handling
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'geometry.amrproj'
            project=Project()
            project.save(path,config,base_dir=directory)
            reopened=Project.open(path)
            self.assertEqual(config['geometry'],reopened.configuration()['geometry'])
            self.assertEqual(config['amrs'][0]['manoeuvring'],reopened.configuration()['amrs'][0]['manoeuvring'])

    def test_corrupt_arc_geometry_and_discontinuous_recordings_are_rejected(self):
        sim=self.run_case()
        row=next(r for r in sim.verbose_rows if r['event_type']=='segment_corridor')
        saved=json.loads(row['trajectory_json'])
        for field,value in [('radius_m',.1),('centre',[99,99]),('length_m',100)]:
            bad=copy.deepcopy(saved)
            bad['motions'][1][field]=value
            with self.assertRaisesRegex(TrajectoryError,'invalid_evidence'):
                trajectory_from_dict(bad)
        bad=copy.deepcopy(saved)
        bad['motions'][0]['start']['x']=1
        with self.assertRaisesRegex(TrajectoryError,'invalid_evidence'):
            trajectory_from_dict(bad)

    def test_managed_run_freezes_geometry_and_replays_the_recorded_arc(self):
        config = geometric_config()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = Project()
            project.save(root/'reference.amrproj', config)
            revision = project.revisions[-1]['id']
            draft = PreparedRun(project, root/'results')
            checks = check_project(draft.config, base_path=draft.directory)
            checks.acknowledge_warnings()
            directory = draft.commit(checks)
            with contextlib.redirect_stdout(io.StringIO()):
                execute(directory)
            frozen = (directory/'config.json').read_bytes()
            config['geometry']['floors'][0]['obstacles'] = []
            project.save(project.path, config)
            _, manifest, layout, log = load_playback(directory)
            self.assertEqual('complete', manifest['status'])
            self.assertEqual(1, manifest['completed_tasks'])
            self.assertEqual(revision, manifest['project_binding']['revision_id'])
            self.assertEqual(frozen, (directory/'config.json').read_bytes())
            state = log.state_at(log.start_time+timedelta(seconds=4+math.pi/4),layout)[0]['R-1']
            self.assertAlmostEqual(4+math.sqrt(2),state['x'],delta=.001)
            self.assertAlmostEqual(2-math.sqrt(2),state['y'],delta=.001)
            self.assertAlmostEqual(math.pi/4,state['geometry_heading'],delta=.001)
            self.assertTrue(state['raw']['event_id'])

    def test_charging_trip_uses_curve_pivot_energy_and_transactional_heading(self):
        config = geometric_config()
        config['tasks'] = []
        config['amrs'][0]['manoeuvring']['initial_heading_deg'] = 180
        sim = Simulation(config)
        sim.charge_location_names = ['B']
        sim.charge_location_name = 'B'
        robot = sim.amrs[0]
        before = copy.deepcopy(vars(robot))
        expected_time = 4+(8+math.pi)/2
        expected_energy = robot.motor_power_w*.75*expected_time/3600000
        estimate = sim._plan_return_to_charge(robot,sim.locations['A'],0)
        self.assertAlmostEqual(expected_time,estimate['finish_time'])
        self.assertAlmostEqual(expected_energy,estimate['amr_energy_kwh'])
        self.assertEqual(before,vars(robot))
        self.assertFalse(sim.geometric_route_reservations)
        with patch.object(sim,'_record_committed_segment_impacts',side_effect=RuntimeError('late failure')):
            with self.assertRaisesRegex(RuntimeError,'late failure'):
                sim._plan_return_to_charge(robot,sim.locations['A'],0,reserve=True)
        self.assertEqual(before,vars(robot))
        self.assertFalse(sim.geometric_route_reservations)
        plan = sim._plan_return_to_charge(robot,sim.locations['A'],0,reserve=True)
        self.assertAlmostEqual(expected_energy,robot.total_energy_used_kwh)
        self.assertEqual(90,robot.rotation_deg)
        motion = next(s for s in plan['segments'] if s['type']=='corridor')
        self.assertEqual('pivot',motion['trajectory']['motions'][0]['kind'])
        self.assertEqual(1,len(sim.geometric_route_reservations[0]))

    def test_input_model_is_explicit_and_unsupported_combinations_are_blocked(self):
        for change,path in [('parameter','/amrs/0/manoeuvring/pivot_allowed'),('floor','/geometry/floors'),
                            ('bay','/locations/0/inventory_spaces'),('distance','/corridors/edges/0/distance_m')]:
            config=geometric_config()
            if change=='parameter': config['amrs'][0]['manoeuvring'].pop('pivot_allowed')
            elif change=='floor': config['geometry']['floors']=[]
            elif change=='bay': config['locations'][0]['inventory_spaces']=[{'name':'Bay'}]
            else: config['corridors']['edges'][0]['distance_m']=99
            before=copy.deepcopy(config)
            for constructor in (Simulation,JsonStore):
                with self.assertRaises(ValueError): constructor(config)
            self.assertTrue(any(f.path==path and f.severity=='error' for f in check_project(config).findings))
            self.assertEqual(before,config)

    def test_scope_warning_requires_acknowledgement_and_geometry_edits_stale_it(self):
        config=geometric_config()
        report=check_project(config)
        self.assertFalse(any(f.severity=='error' for f in report.findings))
        finding=next(f for f in report.findings if f.code=='GEOMETRY_SCOPE')
        self.assertFalse(report.can_run(config))
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(config))
        config['geometry']['floors'][0]['obstacles']=[]
        self.assertIn('geometry',report.changed_inputs(finding,config))


if __name__=='__main__': unittest.main()
