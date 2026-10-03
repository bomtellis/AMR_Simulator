"""Physical time profiles must drive simulation, saved playback and traffic."""
import contextlib
import copy
import csv
import io
import json
import math
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from amr_trajectories import trajectory_from_dict, TrajectoryError
from amr_geometric_traffic import swept_cells
from simulator import Simulation
from tests.test_geometric_traffic import traffic_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from amr_sim_visualiser_pyside6 import LayoutModel,SimulationLog


def dynamics_config():
    config=traffic_config()
    config['corridors']['edges'][0]['traffic_mode']='single_file'
    empty=dict(forward_speed_m_per_sec=4,reverse_speed_m_per_sec=1,
        acceleration_m_per_sec2=2,braking_m_per_sec2=2,maximum_turn_speed_m_per_sec=2,
        lateral_acceleration_m_per_sec2=1,pivot_allowed=True,lateral_allowed=False,
        rotation_speed_deg_per_sec=90,angular_acceleration_deg_per_sec2=90,
        angular_braking_deg_per_sec2=90,minimum_radius_m=2)
    loaded=dict(empty,forward_speed_m_per_sec=2,reverse_speed_m_per_sec=.5,
        acceleration_m_per_sec2=1,braking_m_per_sec2=1,rotation_speed_deg_per_sec=45,
        angular_acceleration_deg_per_sec2=45,angular_braking_deg_per_sec2=45,minimum_radius_m=3)
    config['amrs'][0]['movement']={'empty':empty,'loaded':loaded}
    return config


class DynamicsSimulationTests(unittest.TestCase):
    def test_loaded_acceleration_changes_completion_energy_and_saved_positions(self):
        config=dynamics_config()
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'steps.csv')
            sim=Simulation(config,verbose=True,verbose_csv_path=path)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
                sim.write_verbose_csv()
            # Accelerate 2s/2m, cruise 8s/16m, brake 2s/2m; plus 4s handling.
            self.assertAlmostEqual(16,sim.current_time)
            self.assertEqual(1,len(sim.completed_task_records))
            self.assertAlmostEqual(750*1.035*12/3600000,sim.amrs[0].total_energy_used_kwh)
            with open(path,newline='',encoding='utf-8-sig') as stream:
                row=next(r for r in csv.DictReader(stream) if r['event_type']=='segment_corridor')
            recorded=trajectory_from_dict(json.loads(row['trajectory_json']))
            self.assertAlmostEqual(.5,recorded.pose_at_time(1).x)
            layout,log=LayoutModel(),SimulationLog()
            layout.load_data(config)
            log.load(path,parallel=False)
            for elapsed,x in ((3,.5),(13,19.5),(3,.5)):
                state=log.state_at(log.start_time+timedelta(seconds=elapsed),layout)[0]['R-1']
                self.assertAlmostEqual(x,state['x'],delta=.001)
            cells=swept_cells(recorded,length_m=1,width_m=.7,clearance_m=0)
            first=cells[0]
            # First .25s reaches .03125m, not constant-speed .5m.
            self.assertAlmostEqual(.03125+.5,first['envelope'][2])

    def test_empty_charge_trip_uses_empty_dynamics_without_mutating_estimate(self):
        sim=Simulation(dynamics_config())
        sim.charge_location_names=['B']
        sim.charge_location_name='B'
        before=copy.deepcopy(vars(sim.amrs[0]))
        plan=sim._plan_return_to_charge(sim.amrs[0],sim.locations['A'],0)
        # Accelerate 2s/4m, cruise 3s/12m, brake 2s/4m.
        self.assertAlmostEqual(7,plan['finish_time'])
        self.assertEqual(before,vars(sim.amrs[0]))

    def test_loaded_pivot_dynamics_and_permission_override_empty_settings(self):
        config=dynamics_config()
        config['amrs'][0]['manoeuvring']['initial_heading_deg']=90
        sim=Simulation(config)
        with contextlib.redirect_stdout(io.StringIO()): sim.run()
        self.assertAlmostEqual(19,sim.current_time)  # 90deg pivot: 1s accel + 1s cruise + 1s brake
        config['amrs'][0]['movement']['loaded']['pivot_allowed']=False
        sim=Simulation(config,verbose=True)
        with contextlib.redirect_stdout(io.StringIO()): sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertTrue(any(r['status']=='infeasible_route' for r in sim.verbose_rows))

    def test_loaded_radius_is_used_for_geometry_not_just_timing(self):
        config=dynamics_config()
        config['geometry']['traffic_model']='whole_route_v1'
        config['locations'][1].update(x=6,y=6)
        config['geometry']['floors'][0]['bounds']=[-5,-5,25,25]
        config['corridors']['nodes']=[dict(name='J',floor=0,x=6,y=0)]
        config['corridors']['edges']=[{'from':a,'to':b,'width_m':4} for a,b in [('A','J'),('J','B')]]
        sim=Simulation(config)
        a,b=sim.locations['A'],sim.locations['B']
        empty=sim._same_floor_segments(sim.amrs[0],a,b,payload=None)[0][0]['trajectory']
        loaded=sim._same_floor_segments(sim.amrs[0],a,b,payload=sim.payloads['Box'])[0][0]['trajectory']
        self.assertEqual(2,empty['minimum_radius_m'])
        self.assertEqual(3,loaded['minimum_radius_m'])
        self.assertAlmostEqual(6+3*math.pi/2,loaded['length_m'])

    def test_bad_profiles_rejected_in_inputs_and_recorded_evidence(self):
        config=dynamics_config()
        config['amrs'][0]['movement']['empty']['braking_m_per_sec2']=0
        for constructor in (Simulation,JsonStore):
            with self.assertRaises(ValueError): constructor(config)
        self.assertTrue(any(f.code=='GEOMETRY_INPUT' for f in check_project(config).findings))
        sim=Simulation(dynamics_config())
        data=sim._same_floor_segments(sim.amrs[0],sim.locations['A'],sim.locations['B'],payload=sim.payloads['Box'])[0][0]['trajectory']
        data['motions'][0]['profile']['acceleration']=100
        with self.assertRaisesRegex(TrajectoryError,'invalid_evidence'):
            trajectory_from_dict(data)


if __name__=='__main__': unittest.main()
