"""Wall margins and total inter-robot gaps are independent physical distances."""
import copy
import unittest

from amr_clearances import resolved_clearances
from amr_geometric_traffic import first_traffic_slot,polygon_bounds
from amr_trajectories import footprint,Pose
from simulator import Simulation
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from tests.test_geometric_traffic import traffic_config


class GeometricClearanceTests(unittest.TestCase):
    def modern_config(self,width=4):
        config=traffic_config(width)
        config['geometry']['clearances']={'wall_m':.1,'robot_m':.1}
        config['amrs'][0]['manoeuvring'].pop('clearance_m')
        return config

    def test_project_values_robot_overrides_and_legacy_adapter(self):
        config=self.modern_config()
        settings=config['amrs'][0]['manoeuvring']
        self.assertEqual({'wall_m':.1,'robot_m':.1,'explicit':True},resolved_clearances(config,settings))
        settings.update(wall_clearance_m=.2,robot_clearance_m=.3)
        self.assertEqual({'wall_m':.2,'robot_m':.3,'explicit':True},resolved_clearances(config,settings))
        legacy=traffic_config()
        legacy['amrs'][0]['manoeuvring']['clearance_m']=.05
        self.assertEqual({'wall_m':.05,'robot_m':.1,'explicit':False},
                         resolved_clearances(legacy,legacy['amrs'][0]['manoeuvring']))

    def test_two_lane_width_is_two_bodies_two_wall_gaps_and_one_robot_gap(self):
        for width,mode in ((1.7,'keep_right'),(1.6999,'single_file')):
            sim=Simulation(self.modern_config(width))
            segments,_,_=sim._same_floor_segments(sim.amrs[0],sim.locations['A'],sim.locations['B'],payload=sim.payloads['Box'])
            section=segments[0]['lane_sections'][0]
            self.assertEqual(mode,section['mode'])
            if mode=='keep_right':
                self.assertAlmostEqual(.4,section['offset_m'])
                self.assertAlmostEqual(.1,2*section['offset_m']-.7)
                self.assertAlmostEqual(.1,width/2-section['offset_m']-.7/2)

    def test_pair_separation_is_larger_requirement_not_sum(self):
        for y,ready in ((1.2,0),(1.1999,5)):
            for a_gap,b_gap in ((.1,.2),(.2,.1)):
                a=footprint(Pose(0,0,0),1,1)
                b=footprint(Pose(0,y,0),1,1)
                reserved=[dict(start=0,end=5,owner='A',polygon=a,envelope=polygon_bounds(a),robot_clearance_m=a_gap)]
                cells=[dict(start=0,end=5,polygon=b,envelope=polygon_bounds(b),robot_clearance_m=b_gap)]
                self.assertEqual(ready,first_traffic_slot(reserved,cells,0,'B',0)[0])

    def test_wall_requirement_does_not_become_inter_robot_gap(self):
        config=self.modern_config()
        config['geometry']['clearances']={'wall_m':.4,'robot_m':.1}
        sim=Simulation(config)
        segments,_,_=sim._same_floor_segments(sim.amrs[0],sim.locations['A'],sim.locations['B'],payload=sim.payloads['Box'])
        segment=segments[0]
        self.assertEqual(.4,segment['wall_clearance_m'])
        self.assertEqual(.1,segment['robot_clearance_m'])
        straight_cell=next(c for c in segment['traffic_cells'] if abs(c['envelope'][3]-c['envelope'][1]-.7)<1e-9)
        self.assertEqual(.1,straight_cell['robot_clearance_m'])

    def test_modern_clearance_inputs_roundtrip_and_stale_checks(self):
        config=self.modern_config()
        store=JsonStore(config)
        self.assertEqual(config['geometry']['clearances'],store.data['geometry']['clearances'])
        report=check_project(config)
        self.assertFalse(any(f.severity=='error' for f in report.findings))
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(config))
        config['geometry']['clearances']['wall_m']=.2
        self.assertFalse(report.can_run(config))

    def test_invalid_and_missing_clearances_reject_without_mutation(self):
        for value in (None,True,-.1,float('nan'),float('inf'),'0.1'):
            config=self.modern_config()
            config['geometry']['clearances']['robot_m']=value
            for constructor in (Simulation,JsonStore):
                with self.assertRaises(ValueError): constructor(config)
        config=self.modern_config()
        config['geometry'].pop('clearances')
        before=copy.deepcopy(config)
        with self.assertRaises(ValueError): Simulation(config)
        self.assertEqual(before,config)


if __name__=='__main__': unittest.main()
