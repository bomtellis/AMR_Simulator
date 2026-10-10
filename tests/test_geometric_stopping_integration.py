"""Drawn stop restrictions apply to actual delayed simulator departures."""
import copy
import unittest

from simulator import Simulation, LocalManoeuvreError
from amr_route_reservations import RouteReservationTransaction
from tests.test_geometric_traffic import traffic_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class StoppingIntegrationTests(unittest.TestCase):
    def blocked_route(self,config):
        config['amrs'][0]['quantity']=2
        # A committed northbound crossing reaches the horizontal route while
        # R-2 approaches from A. Robots start at distinct, valid physical poses.
        config['locations'] += [dict(name='C',floor=0,x=10,y=-4),
                                dict(name='D',floor=0,x=10,y=4),
                                dict(name='E',floor=0,x=-3,y=0)]
        config['corridors']['edges'] += [{'from':'C','to':'D','width_m':4},
            {'from':'E','to':'A','width_m':1,'traffic_mode':'single_file'}]
        config['geometry']['initial_placements'] = [
            {'amr_id':'R-1','location':'C','heading_deg':90},
            {'amr_id':'R-2','location':'E','heading_deg':0}]
        sim=Simulation(config)
        a,b=sim.locations['A'],sim.locations['B']
        first=sim.amrs[0]
        route=sim._same_floor_segments(first,sim.locations['C'],sim.locations['D'],start_time_value=5.5)
        with RouteReservationTransaction(sim,first,[]) as transaction:
            sim._check_geometric_occupancy(first,route[0],5.5,sim.locations['C'],90,reserve=True)
            transaction.committed=True
        # Inspect the intermediate leg after the 3 m E→A approach at 2 m/s.
        # A may be traversed, but an inserted wait there must obey stop protection.
        # This is an uncommitted leg estimate; the actual initial parked pose is E.
        return sim,lambda:sim._same_floor_segments(sim.amrs[1],a,b,start_time_value=1.5,payload=sim.payloads['Box'])

    def test_drawn_area_is_optional_but_blocked_wait_cannot_obstruct_it(self):
        for protected in (False,True):
            config=traffic_config()
            if protected:
                config['geometry']['floors'][0]['no_queuing_areas']=[{'id':'Keep clear','bounds':[-1,-1,1,1]}]
            sim,second=self.blocked_route(config)
            original=copy.deepcopy(sim.geometric_route_reservations)
            original_occupancy=sim.geometric_occupancy
            if protected:
                with self.assertRaisesRegex(LocalManoeuvreError,'invalid_waiting_position.*Keep clear'):
                    second()
            else:
                self.assertEqual('wait_for_geometry',second()[0][0]['type'])
            self.assertEqual(original,sim.geometric_route_reservations)
            self.assertIs(original_occupancy,sim.geometric_occupancy)

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
