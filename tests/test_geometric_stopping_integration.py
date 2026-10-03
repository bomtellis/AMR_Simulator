"""Drawn stop restrictions apply to actual delayed simulator departures."""
import copy
import unittest

from simulator import Simulation, LocalManoeuvreError
from tests.test_geometric_traffic import traffic_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class StoppingIntegrationTests(unittest.TestCase):
    def blocked_route(self,config):
        config['amrs'][0]['quantity']=2
        sim=Simulation(config)
        a,b=sim.locations['A'],sim.locations['B']
        route=sim._same_floor_segments(sim.amrs[0],a,b,start_time_value=0,payload=sim.payloads['Box'])
        sim._reserve_corridor_segments(sim.amrs[0],route[0],0)
        return sim,lambda:sim._same_floor_segments(sim.amrs[1],a,b,start_time_value=0,payload=sim.payloads['Box'])

    def test_drawn_area_is_optional_but_blocked_wait_cannot_obstruct_it(self):
        for protected in (False,True):
            config=traffic_config()
            if protected:
                config['geometry']['floors'][0]['no_queuing_areas']=[{'id':'Keep clear','bounds':[-1,-1,1,1]}]
            sim,second=self.blocked_route(config)
            original=copy.deepcopy(sim.geometric_route_reservations)
            if protected:
                with self.assertRaisesRegex(LocalManoeuvreError,'invalid_waiting_position.*Keep clear'):
                    second()
            else:
                self.assertEqual('wait_for_geometry',second()[0][0]['type'])
            self.assertEqual(original,sim.geometric_route_reservations)

    def test_door_is_protected_without_user_drawn_areas(self):
        config=traffic_config()
        config['locations'][0].update(has_door=True,door_clear_width_m=4)
        _,second=self.blocked_route(config)
        with self.assertRaisesRegex(LocalManoeuvreError,'protected_door: A'):
            second()

    def test_junction_is_protected_without_user_drawn_areas(self):
        config=traffic_config()
        config['corridors']['nodes']=[dict(name='N',floor=0,x=0,y=3),dict(name='S',floor=0,x=0,y=-3)]
        config['corridors']['edges'] += [dict(**{'from':'A','to':name,'width_m':4}) for name in ('N','S')]
        _,second=self.blocked_route(config)
        with self.assertRaisesRegex(LocalManoeuvreError,'protected_junction: A'):
            second()

    def test_invalid_drawn_areas_block_run_import_and_project_checks(self):
        config=traffic_config()
        config['geometry']['floors'][0]['passing_places']=[{'id':'P','bounds':[0,0,-1,1]}]
        for constructor in (Simulation,JsonStore):
            with self.assertRaises(ValueError): constructor(config)
        self.assertTrue(any(f.code=='GEOMETRY_INPUT' for f in check_project(config).findings))


if __name__=='__main__': unittest.main()
