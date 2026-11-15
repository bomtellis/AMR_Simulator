"""Actual stop sequences, transfer restrictions and booking/energy contracts."""
import contextlib
from copy import deepcopy
import io
import unittest

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.project_checks import check_project


def floor_config(transfer=False, waypoint=True):
    cfg = reference_config()
    cfg['building'].update(floor_count=6, floor_height_m=4, edge_slowdown_per_amr=0)
    if waypoint:
        cfg['building']['mandatory_floor_waypoints'] = [dict(from_floor=0, to_floors=[1,2,3,4,5], via_floor=2)]
    cfg['locations'] = [dict(name='A', floor=0, x=0, y=0)] + [
        dict(name=f'B{floor}', floor=floor, x=4, y=0) for floor in range(1, 6)]
    cfg['corridors'] = dict(auto_connect=False, nodes=[], edges=[])
    cfg['lifts'] = []
    lifts = [('Low', [0,2], 2), ('High', [1,2,3,4,5], 6)] if transfer else [('L', list(range(6)), 2)]
    for name, floors, x in lifts:
        cfg['lifts'].append(dict(id=name, served_floors=floors, start_floor=floors[0], speed_floors_per_sec=1,
            door_time_sec=2, boarding_time_sec=1, capacity_length_m=5, capacity_width_m=5,
            capacity_height_m=5, health_loss_per_journey_percent=0,
            mean_time_between_failures_hours=0,
            floor_locations={str(f): dict(x=x,y=0) for f in floors}))
        for f in floors:
            endpoint = 'A' if f==0 else f'B{f}'
            cfg['corridors']['edges'].append(dict(**{'from':endpoint, 'to':f'{name}-F{f}'},
                                                     width_m=3, distance_m=2))
    if transfer:
        cfg['corridors']['edges'].append(dict(**{'from':'Low-F2','to':'High-F2'}, width_m=3, distance_m=4))
    return cfg


def rides(plan):
    return [(s['from_floor'],s['to_floor']) for s in plan['segments'] if s['type']=='lift_transfer']


class FloorWaypointTests(unittest.TestCase):
    def plan(self, cfg, floor=1, reserve=False):
        sim = Simulation(cfg)
        plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T','A',f'B{floor}','Box'), reserve=reserve)
        return sim, plan

    def test_all_five_destinations_and_floor_one_backtrack(self):
        for f in range(1,6):
            with self.subTest(floor=f):
                sim, plan = self.plan(floor_config(), f, reserve=True)
                self.assertIsNotNone(plan)
                self.assertEqual([(0,2)] if f==2 else [(0,2),(2,f)], rides(plan))
                self.assertEqual(f'B{f}', plan['end_location'])
                self.assertEqual(len(rides(plan)), len(sim.lift_reservations['L']))
                bookings = sorted(sim.lift_reservations['L'])
                self.assertTrue(all(a[1] <= b[0] for a,b in zip(bookings,bookings[1:])))

    def test_same_lift_second_ride_has_no_phantom_reposition_and_time_reconciles(self):
        _, plan = self.plan(floor_config(), reserve=True)
        self.assertEqual([(0,2),(2,1)], rides(plan))
        self.assertFalse([s for s in plan['segments'] if s['type']=='lift_reposition'])
        self.assertAlmostEqual(21, plan['duration'])
        self.assertAlmostEqual(plan['duration'], sum(s['duration'] for s in plan['segments']))
        self.assertAlmostEqual(plan['energy_kwh'], sum(s.get('energy_kwh',0) for s in plan['segments']))

    def test_transfer_between_lifts_works_without_waypoint_when_graph_forces_it(self):
        cfg = floor_config(transfer=True, waypoint=False)
        sim, plan = self.plan(cfg, 5, reserve=True)
        self.assertEqual([(0,2),(2,5)], rides(plan))
        self.assertEqual(['Low','High'], [s['lift_id'] for s in plan['segments'] if s['type']=='lift_transfer'])
        self.assertTrue(sim._route_possible_between_locations(sim.amrs[0], sim.locations['A'],
                                                             sim.locations['B5'], sim.payloads['Box']))
        self.assertEqual(1,len(sim.lift_reservations['Low']))
        self.assertEqual(1,len(sim.lift_reservations['High']))

    def test_profile_can_block_transfer_corridor_and_does_not_fall_back(self):
        cfg = floor_config(transfer=True)
        cfg['route_profiles'] = {'low_only': dict(allowed_lifts=['Low'])}
        sim = Simulation(cfg)
        task = Task('T','A','B5','Box',route_profile='low_only')
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0],task,reserve=True))
        self.assertFalse(any(sim.lift_reservations.values()))
        rules = sim._resolve_task_route_rules(task)
        self.assertFalse(sim._route_possible_between_locations(sim.amrs[0],sim.locations['A'],
                                                              sim.locations['B5'],sim.payloads['Box'],rules))

    def test_unreachable_waypoint_blocks_even_when_direct_lift_exists(self):
        cfg = floor_config()
        cfg['lifts'][0]['served_floors'] = [0,1]
        cfg['lifts'][0]['floor_locations'] = {k:v for k,v in cfg['lifts'][0]['floor_locations'].items() if k in ('0','1')}
        cfg['corridors']['edges'] = cfg['corridors']['edges'][:1] + cfg['corridors']['edges'][1:2]
        sim, plan = self.plan(cfg)
        self.assertIsNone(plan)
        self.assertFalse(sim._route_possible_between_locations(sim.amrs[0],sim.locations['A'],sim.locations['B1'],sim.payloads['Box']))

    def test_estimates_do_not_book_lifts(self):
        sim = Simulation(floor_config())
        before = deepcopy(dict(sim.lift_reservations))
        plan = sim._estimate_task_for_amr(sim.amrs[0],Task('T','A','B1','Box'),reserve=False)
        self.assertIsNotNone(plan)
        self.assertEqual(before,dict(sim.lift_reservations))

    def test_second_ride_respects_wear_and_scheduled_repair(self):
        cfg = floor_config()
        cfg['lifts'][0].update(mean_time_between_failures_hours=1/3600,
                               mean_time_to_repair_hours=10/3600)
        sim, plan = self.plan(cfg, reserve=True)
        self.assertIsNotNone(plan)
        # First lift service lasts 8 s, then its deterministic repair lasts 10 s.
        self.assertAlmostEqual(31, plan['duration'])
        self.assertEqual(2, sim.lifts[0].failures_count)
        waits = [s for s in plan['segments'] if s['type']=='wait_for_lift']
        self.assertEqual([10], [s['duration'] for s in waits])

    def test_simultaneous_robots_cannot_overlap_either_lift_ride(self):
        cfg = floor_config()
        cfg['amrs'][0]['quantity']=2
        sim=Simulation(cfg)
        for i,amr in enumerate(sim.amrs):
            self.assertIsNotNone(sim._estimate_task_for_amr(amr,Task(f'T{i}','A','B1','Box'),reserve=True))
        bookings=sorted(sim.lift_reservations['L'])
        self.assertEqual(4,len(bookings))
        self.assertTrue(all(a[1]<=b[0] for a,b in zip(bookings,bookings[1:])))

    def test_other_origins_and_reverse_journeys_keep_direct_routes(self):
        sim = Simulation(floor_config())
        for a,b,expected in [('B1','B5',[(1,5)]),('B5','A',[(5,0)])]:
            plan = sim._nearest_compatible_lift_plan(0,sim.amrs[0],sim.locations[a],sim.locations[b],sim.payloads['Box'])
            from amr_floor_routing import lift_plan_journeys
            self.assertEqual(expected,[(leg['origin_lift'].floor,leg['destination_lift'].floor) for leg in lift_plan_journeys(plan)])

    def test_preflight_matches_connecting_and_blocked_routes(self):
        cfg = floor_config(transfer=True)
        cfg['tasks'] = [dict(id='T',pickup='A',dropoff='B5',payload='Box')]
        report = check_project(cfg)
        self.assertTrue(report.route_checks)
        self.assertEqual('Reachable',report.route_checks[0]['status'])
        cfg['route_profiles'] = {'low_only':dict(allowed_lifts=['Low'])}
        cfg['tasks'][0]['route_profile'] = 'low_only'
        self.assertEqual('Blocked',check_project(cfg).route_checks[0]['status'])

    def test_execution_completes_original_task_at_final_destination(self):
        cfg = floor_config(transfer=True)
        cfg['tasks'] = [dict(id='T',pickup='A',dropoff='B1',payload='Box')]
        sim = Simulation(cfg,verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_tasks)
        self.assertEqual(['T'],[r['task_id'] for r in sim.completed_task_records])
        self.assertEqual('B1',sim.amrs[0].location_name)

    def test_batch_routing_and_charger_travel_also_stop_at_waypoint(self):
        cfg = floor_config()
        slot = dict(payload_capacity_kg=100,payload_length_capacity_m=2,payload_width_capacity_m=2,payload_height_capacity_m=2)
        cfg['amrs'][0].update(multi_stop_enabled=True,payload_slots=[dict(slot,name='One'),dict(slot,name='Two')])
        sim = Simulation(cfg)
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[0],[Task('T1','A','B1','Box'),Task('T2','A','B1','Box')],reserve=True)
        self.assertEqual([(0,2),(2,1)],rides(plan))
        cfg['building']['charge_location'] = 'B1'
        sim = Simulation(cfg)
        sim.amrs[0].location_name='A'
        plan = sim._plan_return_to_charge_impl(sim.amrs[0],sim.locations['A'],0,reserve=False)
        self.assertEqual([(0,2),(2,1)],rides(plan))


if __name__=='__main__':
    unittest.main()
